
import os
from dotenv import load_dotenv
from google import genai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

api_key = os.getenv("GEMINI_API_KEY")

try:
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say: DrainProof AI Gemini connection successful!"
    )

    print("Gemini connected successfully!")
    print(response.text)

except Exception as e:
    print("Connection error:", e)
