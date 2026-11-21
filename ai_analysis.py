
import os
import json
import re
import mimetypes
from pathlib import Path

import requests
from dotenv import load_dotenv


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-2.5-flash"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL_NAME}:generateContent"
)


# --------------------------------------------------
# IMAGE ANALYSIS
# --------------------------------------------------

def analyze_image(image_path):
    """
    Analyze a drainage issue photograph using Gemini AI.

    Returns:
        Dictionary containing:
        severity, detected_issue, recommendation, analysis
    """

    if not GEMINI_API_KEY:
        return {
            "severity": "Unknown",
            "detected_issue": "Gemini API key is missing.",
            "recommendation": "Configure GEMINI_API_KEY in the .env file.",
            "analysis": "AI analysis could not start."
        }

    if not image_path:
        return {
            "severity": "Unknown",
            "detected_issue": "No image was provided.",
            "recommendation": "Upload an issue photograph.",
            "analysis": "Image path is missing."
        }

    image_path = Path(image_path)

    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path

    if not image_path.exists():
        return {
            "severity": "Unknown",
            "detected_issue": "Image file was not found.",
            "recommendation": "Check the uploaded image file.",
            "analysis": "Image file does not exist."
        }

    try:
        # Read image
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()

        mime_type, _ = mimetypes.guess_type(str(image_path))

        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        # Gemini prompt
        prompt = """
You are an expert urban drainage and infrastructure inspection AI.

Analyze the uploaded photograph carefully.

Identify visible problems such as:
- Blocked drainage
- Overflowing drains
- Waterlogging
- Damaged drainage infrastructure
- Garbage accumulation
- Sewage leakage
- Stagnant water
- Drainage blockage
- Flooding risks

Classify the issue using exactly one severity:

LOW:
Minor issue with limited immediate impact.

MEDIUM:
Noticeable drainage problem requiring maintenance.

HIGH:
Serious blockage, overflow, flooding, sewage exposure,
or a significant public safety risk.

Do not invent problems that cannot be seen in the photograph.
If the image does not clearly show a drainage problem,
state that the issue cannot be reliably identified.

Return ONLY valid JSON in this format:

{
    "severity": "Low, Medium, High, or Unknown",
    "detected_issue": "Description of the visible issue",
    "recommendation": "Recommended corrective action",
    "analysis": "Detailed explanation of your assessment"
}
"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": __import__("base64").b64encode(
                                    image_data
                                ).decode("utf-8")
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        response = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=90
        )

        if response.status_code != 200:
            try:
                error_message = response.json().get(
                    "error", {}
                ).get("message", response.text)
            except ValueError:
                error_message = response.text

            return {
                "severity": "Unknown",
                "detected_issue": "Gemini API request failed.",
                "recommendation": "Check your Gemini API configuration.",
                "analysis": f"Gemini API error: {error_message}"
            }

        result = response.json()

        candidates = result.get("candidates", [])

        if not candidates:
            return {
                "severity": "Unknown",
                "detected_issue": "Gemini returned no analysis.",
                "recommendation": "Try uploading the image again.",
                "analysis": "No response candidate was returned."
            }

        parts = candidates[0].get("content", {}).get("parts", [])

        response_text = "".join(
            part.get("text", "") for part in parts
        ).strip()

        # Extract JSON
        match = re.search(
            r"\{.*\}",
            response_text,
            re.DOTALL
        )

        if not match:
            raise ValueError("Gemini did not return valid JSON.")

        analysis_result = json.loads(match.group())

        severity = str(
            analysis_result.get("severity", "Unknown")
        ).strip().capitalize()

        if severity not in ["Low", "Medium", "High", "Unknown"]:
            severity = "Unknown"

        return {
            "severity": severity,
            "detected_issue": str(
                analysis_result.get("detected_issue", "Not available")
            ),
            "recommendation": str(
                analysis_result.get("recommendation", "Not available")
            ),
            "analysis": str(
                analysis_result.get("analysis", "Not available")
            )
        }

    except requests.exceptions.Timeout:
        return {
            "severity": "Unknown",
            "detected_issue": "Gemini request timed out.",
            "recommendation": "Try again later.",
            "analysis": "The request exceeded the allowed time."
        }

    except requests.exceptions.RequestException as error:
        return {
            "severity": "Unknown",
            "detected_issue": "Network connection failed.",
            "recommendation": "Check your internet connection.",
            "analysis": str(error)
        }

    except (ValueError, KeyError, TypeError) as error:
        return {
            "severity": "Unknown",
            "detected_issue": "Could not interpret Gemini's response.",
            "recommendation": "Try analysing the image again.",
            "analysis": str(error)
        }

    except Exception as error:
        return {
            "severity": "Unknown",
            "detected_issue": "Unexpected AI analysis error.",
            "recommendation": "Check the application terminal.",
            "analysis": str(error)
        }
