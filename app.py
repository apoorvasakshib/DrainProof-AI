
import os
import re
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from PIL import Image, ImageOps, ImageEnhance

try:
    import pytesseract
except ImportError:
    pytesseract = None

from ai_analysis import analyze_image

from database.db import (
    create_table,
    authenticate_user,
    register_citizen,
    create_user,
    get_all_users,
    get_user_by_email,
    get_all_issues,
    save_issue,
    save_resolution_evidence,
    update_issue_status,
    update_issue_analysis,
    update_issue_details,
    delete_issue,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"

load_dotenv(BASE_DIR / ".env")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="DrainProof AI",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

create_table()
# =========================================================
# INITIAL ADMIN ACCOUNT SETUP
# =========================================================

try:
    admin_name = st.secrets["ADMIN_NAME"]
    admin_email = st.secrets["ADMIN_EMAIL"]
    admin_password = st.secrets["ADMIN_PASSWORD"]

    existing_admin = get_user_by_email(admin_email)

    if existing_admin is None:
        create_user(
            full_name=admin_name,
            email=admin_email,
            password=admin_password,
            role="Admin"
        )

    elif existing_admin["role"] != "Admin":
        st.error(
            "The configured admin email belongs to a non-admin account."
        )

except (KeyError, FileNotFoundError):
    pass
MAX_VERIFICATION_DISTANCE = 100


# =========================================================
# GENERAL HELPERS
# =========================================================

def get_value(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def get_photo_path(photo):
    if not photo:
        return None

    path = Path(str(photo))

    if not path.is_absolute():
        path = BASE_DIR / path

    return path


def save_uploaded_photo(uploaded_file):
    if uploaded_file is None:
        return None

    extension = Path(uploaded_file.name).suffix.lower()

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    if extension not in allowed_extensions:
        raise ValueError("Please upload a JPG, PNG or WEBP image.")

    filename = f"{uuid.uuid4().hex}{extension}"
    destination = UPLOAD_DIR / filename

    with open(destination, "wb") as file:
        file.write(uploaded_file.getbuffer())

    return str(destination.relative_to(BASE_DIR))


def delete_photo_file(photo):
    path = get_photo_path(photo)

    if path is None:
        return

    try:
        resolved_path = path.resolve()
        upload_path = UPLOAD_DIR.resolve()

        if (
            os.path.commonpath(
                [str(upload_path), str(resolved_path)]
            ) == str(upload_path)
            and resolved_path.is_file()
        ):
            resolved_path.unlink()

    except (ValueError, OSError):
        pass


def severity_label(severity):
    severity = str(severity or "Unknown").upper()

    if severity == "HIGH":
        return "🔴 HIGH"
    if severity == "MEDIUM":
        return "🟠 MEDIUM"
    if severity == "LOW":
        return "🟢 LOW"

    return "⚪ UNKNOWN"


def status_label(status):
    status = str(status or "Pending")

    if status.lower() == "resolved":
        return "✅ Resolved"
    if status.lower() == "in progress":
        return "🔵 In Progress"

    return "🟡 Pending"


def load_issues():
    return get_all_issues()


def issue_is_resolved(issue):
    return str(
        get_value(issue, "status", "Pending")
    ).lower() == "resolved"


def get_active_issues():
    return [
        issue for issue in load_issues()
        if not issue_is_resolved(issue)
    ]


def get_resolved_issues():
    return [
        issue for issue in load_issues()
        if issue_is_resolved(issue)
    ]


# =========================================================
# EXIF GPS EXTRACTION
# =========================================================

def rational_to_float(value):
    """Convert an EXIF rational value into a float."""

    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if value.denominator == 0:
            raise ValueError("Invalid GPS rational value.")

        return float(value.numerator) / float(value.denominator)

    if isinstance(value, tuple) and len(value) == 2:
        if value[1] == 0:
            raise ValueError("Invalid GPS rational value.")

        return float(value[0]) / float(value[1])

    return float(value)


def dms_to_decimal(values, direction):
    """Convert GPS degrees, minutes and seconds to decimal coordinates."""

    if not values or len(values) != 3:
        raise ValueError("GPS coordinate is incomplete.")

    degrees = rational_to_float(values[0])
    minutes = rational_to_float(values[1])
    seconds = rational_to_float(values[2])

    decimal_value = (
        degrees
        + minutes / 60
        + seconds / 3600
    )

    direction = str(direction).upper()

    if direction in ("S", "W"):
        decimal_value *= -1
    elif direction not in ("N", "E"):
        raise ValueError("GPS direction is invalid.")

    return decimal_value


def extract_gps_from_photo(photo_path):
    """
    Extract latitude and longitude from the original photo's EXIF GPS data.

    Returns:
        (latitude, longitude, None) when GPS is available.
        (None, None, error_message) when GPS is missing or invalid.
    """

    path = get_photo_path(photo_path)

    if path is None or not path.exists():
        return None, None, "The uploaded photograph could not be found."

    try:
        with Image.open(path) as image:
            exif = image.getexif()

            if not exif:
                return None, None, (
                    "This photograph does not contain EXIF GPS metadata. "
                    "Please upload the original geotagged photograph."
                )

            gps_info = exif.get_ifd(0x8825)

            if not gps_info:
                return None, None, (
                    "GPS metadata was not found in this photograph. "
                    "Please upload an original photo with location tagging enabled."
                )

            latitude_values = gps_info.get(2)
            latitude_ref = gps_info.get(1)

            longitude_values = gps_info.get(4)
            longitude_ref = gps_info.get(3)

            if not all([
                latitude_values,
                latitude_ref,
                longitude_values,
                longitude_ref
            ]):
                return None, None, (
                    "The photograph contains incomplete GPS metadata."
                )

            latitude = dms_to_decimal(
                latitude_values,
                latitude_ref
            )

            longitude = dms_to_decimal(
                longitude_values,
                longitude_ref
            )

            if not (-90 <= latitude <= 90):
                return None, None, "The latitude value is invalid."

            if not (-180 <= longitude <= 180):
                return None, None, "The longitude value is invalid."

            return latitude, longitude, None

    except Exception as error:
        return None, None, (
            f"Could not read GPS metadata from this photograph: {error}"
        )


def _parse_labeled_coordinate(ocr_text, label_pattern, axis):
    """Read one labelled decimal coordinate from OCR text."""
    pattern = (
        rf"\b(?:{label_pattern})\b\s*[:=]?\s*"
        rf"([NSEW])?\s*([+-]?\d{{1,3}}(?:[.,]\d+)?)\s*°?\s*([NSEW])?"
    )
    match = re.search(pattern, ocr_text, flags=re.IGNORECASE)

    if not match:
        return None

    direction_before, number_text, direction_after = match.groups()
    direction = (direction_after or direction_before or "").upper()
    value = float(number_text.replace(",", "."))

    if direction:
        allowed = ("N", "S") if axis == "latitude" else ("E", "W")
        if direction not in allowed:
            return None
        value = abs(value)
        if direction in ("S", "W"):
            value *= -1

    limit = 90 if axis == "latitude" else 180
    if not -limit <= value <= limit:
        return None

    return value


def extract_gps_from_screenshot(photo_path):
    """
    Read clearly labelled decimal latitude/longitude text from a screenshot.

    OCR coordinates are convenient for accepting screenshots, but they are
    not cryptographic or independent proof of where a photograph was taken.
    """
    if pytesseract is None:
        return None, None, (
            "Screenshot GPS reading requires pytesseract. Install it with "
            "'.\\venv\\Scripts\\python.exe -m pip install pytesseract'. "
            "You must also install the Windows Tesseract OCR application."
        )

    path = get_photo_path(photo_path)
    if path is None or not path.exists():
        return None, None, "The uploaded screenshot could not be found."

    
    
    try:
        # Configure Tesseract executable on Windows.
        if os.name == "nt":
            windows_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

            if os.path.exists(windows_tesseract):
                pytesseract.pytesseract.tesseract_cmd = windows_tesseract

            project_tessdata = Path(__file__).resolve().parent / "tessdata"

            if (project_tessdata / "eng.traineddata").exists():
                os.environ["TESSDATA_PREFIX"] = str(project_tessdata)

        # Process the uploaded screenshot on both Windows and Linux.
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")

            if image.width < 1800:
                scale = min(3, max(2, 1800 // max(image.width, 1)))
                image = image.resize(
                    (image.width * scale, image.height * scale)
                )

            image = ImageOps.grayscale(image)
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Contrast(image).enhance(1.6)

            ocr_text = pytesseract.image_to_string(
                image,
                config="--oem 3 --psm 11"
            )



        # Correct common OCR substitutions only when they occur between digits.
        ocr_text = re.sub(r"(?<=\d)[Oo](?=[\d.,])", "0", ocr_text)
        ocr_text = re.sub(r"(?<=\d)[Il](?=[\d.,])", "1", ocr_text)

        latitude = _parse_labeled_coordinate(
            ocr_text, r"LATITUDE|LAT|LATITUTE", "latitude"
        )
        longitude = _parse_labeled_coordinate(
            ocr_text, r"LONGITUDE|LONG|LON|LNG", "longitude"
        )

        if latitude is None or longitude is None:
            return None, None, (
                "The screenshot was read, but clearly labelled decimal "
                "Latitude and Longitude values were not found. Please use "
                "a screenshot that visibly shows both labels and coordinates, "
                "for example: Latitude: 12.9716 N, Longitude: 77.5946 E."
            )

        return latitude, longitude, None

    except Exception as error:
        message = str(error)
        if "tesseract is not installed" in message.lower() or "not in your path" in message.lower():
            return None, None, (
                "The Tesseract OCR application is not installed or is not "
                "available in PATH. Install the Windows Tesseract OCR app, "
                "then restart VS Code and Streamlit."
            )
        return None, None, f"Could not read coordinates from screenshot: {error}"


def extract_coordinates(photo_path):
    """Try trusted EXIF GPS first, then labelled screenshot OCR."""
    latitude, longitude, exif_error = extract_gps_from_photo(photo_path)
    if exif_error is None:
        return latitude, longitude, "EXIF", None

    latitude, longitude, ocr_error = extract_gps_from_screenshot(photo_path)
    if ocr_error is None:
        return latitude, longitude, "SCREENSHOT_OCR", None

    return None, None, None, (
        f"{exif_error} Screenshot OCR fallback: {ocr_error}"
    )


def calculate_distance_metres(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS coordinates using Haversine."""

    from math import radians, sin, cos, sqrt, atan2

    earth_radius = 6371000

    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))
    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius * c


# =========================================================
# GEMINI AI ANALYSIS
# =========================================================

def analyse_issue_with_gemini(
    photo_path,
    description="",
    location="",
    issue_type=""
):
    if not photo_path:
        return None, "No photograph is available for AI analysis."

    try:
        image_path = get_photo_path(photo_path)

        if image_path is None or not image_path.exists():
            return None, "The uploaded image could not be found."

        result = analyze_image(str(image_path))

        if not isinstance(result, dict):
            return None, "Gemini returned an invalid response."

        severity = str(
            result.get("severity", "Unknown")
        ).strip().capitalize()

        if severity not in ["Low", "Medium", "High", "Unknown"]:
            severity = "Unknown"

        detected_issue = result.get(
            "detected_issue",
            "Not available"
        )

        recommendation = result.get(
            "recommendation",
            "Not available"
        )

        analysis = result.get(
            "analysis",
            "Not available"
        )

        complete_analysis = (
            f"DETECTED ISSUE:\n{detected_issue}\n\n"
            f"SEVERITY: {severity}\n\n"
            f"RECOMMENDED ACTION:\n{recommendation}\n\n"
            f"AI ANALYSIS:\n{analysis}"
        )

        return {
            "analysis": complete_analysis,
            "severity": severity,
            "detected_issue": detected_issue,
            "recommendation": recommendation
        }, None

    except Exception as error:
        return None, f"AI analysis failed: {error}"


# =========================================================
# AUTHENTICATION
# =========================================================

def logout():
    st.session_state.pop("authenticated_user", None)
    st.rerun()


def login_screen():
    st.title("🌊 DrainProof AI")
    st.subheader("Smart Urban Drainage Monitoring System")

    st.write(
        "Report drainage issues, monitor civic infrastructure "
        "and support faster municipal action."
    )

    login_tab, register_tab = st.tabs(
        ["Login", "Citizen Registration"]
    )

    with login_tab:
        st.subheader("Login")

        with st.form("login_form"):
            email = st.text_input("Email address")
            password = st.text_input(
                "Password",
                type="password"
            )

            submitted = st.form_submit_button(
                "Login",
                use_container_width=True
            )

        if submitted:
            if not email.strip() or not password:
                st.error("Please enter your email and password.")
            else:
                user = authenticate_user(email, password)

                if user:
                    st.session_state["authenticated_user"] = dict(user)
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid email or password.")

    with register_tab:
        st.subheader("Create Citizen Account")

        with st.form("registration_form"):
            full_name = st.text_input("Full name")
            new_email = st.text_input("Email address")
            new_password = st.text_input(
                "Create password",
                type="password"
            )
            confirm_password = st.text_input(
                "Confirm password",
                type="password"
            )

            register_button = st.form_submit_button(
                "Register",
                use_container_width=True
            )

        if register_button:
            if not all([
                full_name.strip(),
                new_email.strip(),
                new_password,
                confirm_password
            ]):
                st.error("Please complete all fields.")

            elif new_password != confirm_password:
                st.error("Passwords do not match.")

            elif len(new_password) < 8:
                st.error("Password must contain at least 8 characters.")

            else:
                try:
                    register_citizen(
                        full_name,
                        new_email,
                        new_password
                    )

                    st.success(
                        "Registration successful! You can now log in."
                    )

                except Exception as error:
                    if "UNIQUE" in str(error).upper():
                        st.error("This email is already registered.")
                    else:
                        st.error(f"Registration failed: {error}")


# =========================================================
# SIDEBAR
# =========================================================

def show_sidebar(user):
    st.sidebar.title("🌊 DrainProof AI")
    st.sidebar.write(f"**{user['full_name']}**")
    st.sidebar.caption(user["role"])
    st.sidebar.divider()

    if st.sidebar.button("Logout", use_container_width=True):
        logout()


# =========================================================
# FILTER AND SEARCH
# =========================================================

def filter_issues(issues, key_prefix):
    if not issues:
        st.info("No issues available.")
        return []

    col1, col2 = st.columns(2)

    with col1:
        search = st.text_input(
            "Search by issue ID or location",
            key=f"{key_prefix}_search"
        )

    with col2:
        issue_types = sorted({
            str(get_value(issue, "issue_type", "Unknown"))
            for issue in issues
        })

        selected_type = st.selectbox(
            "Filter by issue type",
            ["All"] + issue_types,
            key=f"{key_prefix}_type"
        )

    col3, col4 = st.columns(2)

    with col3:
        selected_severity = st.selectbox(
            "Filter by severity",
            ["All", "HIGH", "MEDIUM", "LOW", "UNKNOWN"],
            key=f"{key_prefix}_severity"
        )

    with col4:
        sort_order = st.selectbox(
            "Sort by",
            ["Newest first", "Oldest first"],
            key=f"{key_prefix}_sort"
        )

    filtered = []

    for issue in issues:
        issue_id = str(get_value(issue, "id", ""))
        location = str(get_value(issue, "location", ""))
        issue_type = str(get_value(issue, "issue_type", "Unknown"))
        severity = str(
            get_value(issue, "severity", "UNKNOWN")
        ).upper()

        search_text = f"{issue_id} {location}".lower()

        if search and search.lower() not in search_text:
            continue

        if selected_type != "All" and issue_type != selected_type:
            continue

        if selected_severity != "All" and severity != selected_severity:
            continue

        filtered.append(issue)

    filtered.sort(
        key=lambda issue: int(get_value(issue, "id", 0)),
        reverse=(sort_order == "Newest first")
    )

    return filtered


# =========================================================
# ISSUE DISPLAY
# =========================================================

def display_issue(issue, show_photo=True):
    issue_id = get_value(issue, "id")
    reporter = get_value(issue, "reporter", "Not provided")
    location = get_value(issue, "location", "Not provided")
    issue_type = get_value(issue, "issue_type", "Not specified")
    description = get_value(issue, "description", "")
    status = get_value(issue, "status", "Pending")
    severity = get_value(issue, "severity", "Unknown")
    created_at = get_value(issue, "created_at", "Unknown")
    photo = get_value(issue, "photo")

    with st.container(border=True):
        st.markdown(f"### Issue #{issue_id}")

        col1, col2 = st.columns(2)

        with col1:
            st.write(f"**Reporter:** {reporter}")
            st.write(f"**Location:** {location}")
            st.write(f"**Issue type:** {issue_type}")

        with col2:
            st.write(f"**Status:** {status_label(status)}")
            st.write(f"**Severity:** {severity_label(severity)}")
            st.write(f"**Reported:** {created_at}")

        st.write("**Description:**")
        st.write(description or "No description provided.")

        if show_photo and photo:
            photo_path = get_photo_path(photo)

            if photo_path and photo_path.exists():
                st.image(
                    str(photo_path),
                    caption=f"Original report photo — Issue #{issue_id}",
                    use_container_width=True
                )

        latitude = get_value(issue, "report_latitude")
        longitude = get_value(issue, "report_longitude")

        if latitude is not None and longitude is not None:
            report_source = get_value(issue, "report_gps_source", "EXIF") or "EXIF"
            st.caption(
                f"Report GPS: {latitude}, {longitude} | Source: {report_source}"
            )
            if report_source == "SCREENSHOT_OCR":
                st.warning(
                    "Report coordinates came from screenshot text and are "
                    "not independently verified."
                )
        else:
            st.warning("No report GPS coordinates are stored for this issue.")

        analysis = get_value(issue, "ai_analysis")

        if analysis:
            with st.expander("AI Analysis"):
                st.write(analysis)


# =========================================================
# REPORT AN ISSUE
# =========================================================

def report_issue_page(user):
    st.title("📝 Report an Issue")
    st.write(
        "Submit a drainage or civic infrastructure complaint with "
        "location coordinates."
    )

    st.info(
        "The app first checks EXIF GPS metadata. If it is missing, it can "
        "try to read clearly visible, labelled decimal Latitude and "
        "Longitude values from a screenshot. Screenshot OCR coordinates "
        "are accepted for reporting but are not independently verified."
    )

    with st.form("report_issue_form"):
        reporter = st.text_input(
            "Reporter name",
            value=user["full_name"]
        )

        location = st.text_input(
            "Issue location",
            placeholder="Enter the street, area or landmark"
        )

        issue_type = st.selectbox(
            "Issue type",
            [
                "Blocked Drainage",
                "Waterlogging",
                "Overflowing Drain",
                "Damaged Drain",
                "Garbage Blocking Drain",
                "Other"
            ]
        )

        description = st.text_area(
            "Describe the issue",
            placeholder="Explain what happened and where..."
        )

        
        uploaded_photo = st.file_uploader(
            "Upload geotagged photograph or screenshot with visible coordinates",
            type=["jpg", "jpeg", "png", "webp"]
        )

        submitted = st.form_submit_button(
            "Submit Report",
            use_container_width=True
        )

    if submitted:
        if not reporter.strip() or not location.strip():
            st.error("Please enter the reporter name and location.")

        elif not description.strip():
            st.error("Please describe the issue.")

        elif uploaded_photo is None:
            st.error("Please upload a photograph.")

        else:
            saved_photo = None
            issue_saved = False

            try:
                # ==========================================
                # SAVE UPLOADED PHOTOGRAPH
                # ==========================================

                saved_photo = save_uploaded_photo(uploaded_photo)

                # ==========================================
                # EXTRACT GPS COORDINATES
                # ==========================================

                latitude, longitude, report_source, gps_error = (
                    extract_coordinates(saved_photo)
                )

                if gps_error:
                    delete_photo_file(saved_photo)
                    saved_photo = None
                    st.error(gps_error)

                else:
                    # ==========================================
                    # SAVE ISSUE TO DATABASE
                    # ==========================================

                    issue_id = save_issue(
                        reporter=reporter.strip(),
                        location=location.strip(),
                        issue_type=issue_type,
                        description=description.strip(),
                        photo=saved_photo,
                        user_id=user["id"],
                        report_latitude=latitude,
                        report_longitude=longitude,
                        report_gps_source=report_source
                    )

                    issue_saved = True

                    # ==========================================
                    # AUTOMATIC GEMINI SEVERITY ANALYSIS
                    # ==========================================

                    try:
                        with st.spinner(
                            "Gemini AI is analysing your reported issue..."
                        ):
                            ai_result, ai_error = analyse_issue_with_gemini(
                                photo_path=saved_photo,
                                description=description.strip(),
                                location=location.strip(),
                                issue_type=issue_type
                            )

                        if ai_result:
                            analysis_saved = update_issue_analysis(
                                issue_id,
                                ai_analysis=ai_result["analysis"],
                                severity=ai_result["severity"]
                            )

                            if analysis_saved:
                                st.success(
                                    "Gemini AI analysis completed! "
                                    f"Severity: {ai_result['severity']}"
                                )

                                st.write(
                                    "**Detected issue:** "
                                    + str(ai_result["detected_issue"])
                                )

                                st.write(
                                    "**Recommended action:** "
                                    + str(ai_result["recommendation"])
                                )

                            else:
                                st.warning(
                                    "AI analysis completed, but the result "
                                    "could not be saved to the database."
                                )

                        else:
                            st.warning(
                                "Report saved, but AI analysis failed: "
                                + str(ai_error)
                            )

                    except Exception as ai_error:
                        st.warning(
                            "Report saved, but Gemini AI analysis encountered "
                            f"an error: {ai_error}"
                        )

                    # ==========================================
                    # REPORT SUCCESS MESSAGE
                    # ==========================================

                    st.success(
                        f"Report submitted successfully! Issue ID: {issue_id}"
                    )

                    st.write(
                        f"**Saved report GPS:** {latitude:.7f}, "
                        f"{longitude:.7f}"
                    )

                    if report_source == "SCREENSHOT_OCR":
                        st.warning(
                            "Coordinates were read from screenshot text. "
                            "They are not independently verified and cannot "
                            "by themselves prove the photograph location."
                        )
                    else:
                        st.success(
                            "Report coordinates extracted from EXIF GPS."
                        )

                    st.info(
                        "Your issue is now available for municipal review."
                    )

            except Exception as error:
                if saved_photo and not issue_saved:
                    delete_photo_file(saved_photo)

                st.error(f"Could not submit report: {error}")



# =========================================================
# DASHBOARD
# =========================================================

def dashboard_page():
    st.title("📊 Admin Dashboard")
    st.write("Overview of reported drainage issues.")

    active = get_active_issues()
    resolved = get_resolved_issues()
    all_issues = active + resolved

    high = sum(
        str(get_value(issue, "severity", "")).upper() == "HIGH"
        for issue in active
    )

    medium = sum(
        str(get_value(issue, "severity", "")).upper() == "MEDIUM"
        for issue in active
    )

    low = sum(
        str(get_value(issue, "severity", "")).upper() == "LOW"
        for issue in active
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Active Issues", len(active))
    col2.metric("Resolved Issues", len(resolved))
    col3.metric("High Severity", high)
    col4.metric("Total Reports", len(all_issues))

    st.divider()
    st.subheader("Active Issue Severity")

    a, b, c = st.columns(3)
    a.metric("High", high)
    b.metric("Medium", medium)
    c.metric("Low", low)

    st.divider()
    st.subheader("Recent Active Reports")

    recent = sorted(
        active,
        key=lambda issue: int(get_value(issue, "id", 0)),
        reverse=True
    )[:5]

    if not recent:
        st.info("No active issues.")
    else:
        for issue in recent:
            display_issue(issue)


# =========================================================
# RESOLUTION EVIDENCE AND VERIFICATION
# =========================================================

def resolution_evidence_form(issue, user):
    issue_id = get_value(issue, "id")

    st.markdown(f"**Submit after-repair evidence for Issue #{issue_id}**")

    st.info(
        "Upload an after-repair photograph with EXIF GPS, or a screenshot "
        "that clearly displays labelled decimal Latitude and Longitude. "
        "The coordinates must be within "
        f"{MAX_VERIFICATION_DISTANCE} metres of the original report. "
        "Screenshot OCR is accepted as evidence input but is not trusted "
        "as independent location verification."
    )

    uploaded_resolution_photo = st.file_uploader(
        "Upload resolution photograph or screenshot with visible coordinates",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"resolution_photo_{issue_id}"
    )

    if st.button(
        "Verify and Submit Resolution",
        key=f"verify_resolution_{issue_id}",
        use_container_width=True
    ):
        if uploaded_resolution_photo is None:
            st.error("Please upload the after-repair photograph.")
            return

        saved_resolution_photo = None

        try:
            saved_resolution_photo = save_uploaded_photo(
                uploaded_resolution_photo
            )

            (
                resolution_latitude,
                resolution_longitude,
                resolution_source,
                gps_error
            ) = extract_coordinates(saved_resolution_photo)

            if gps_error:
                delete_photo_file(saved_resolution_photo)
                st.error(gps_error)
                return

            if resolution_source == "SCREENSHOT_OCR":
                st.warning(
                    "Resolution coordinates were read from screenshot text. "
                    "They are not independently verified."
                )
            else:
                st.success("Resolution coordinates extracted from EXIF GPS.")

            report_latitude = get_value(issue, "report_latitude")
            report_longitude = get_value(issue, "report_longitude")

            if report_latitude is None or report_longitude is None:
                delete_photo_file(saved_resolution_photo)
                st.error(
                    "The original report does not have saved GPS "
                    "coordinates. This issue cannot be location-verified."
                )
                return

            distance = calculate_distance_metres(
                report_latitude,
                report_longitude,
                resolution_latitude,
                resolution_longitude
            )

            st.write(
                f"**Report coordinates:** "
                f"{float(report_latitude):.7f}, "
                f"{float(report_longitude):.7f}"
            )

            st.write(
                f"**Resolution coordinates:** "
                f"{resolution_latitude:.7f}, "
                f"{resolution_longitude:.7f}"
            )

            st.write(f"**Distance between photographs:** {distance:.2f} metres")

            if distance > MAX_VERIFICATION_DISTANCE:
                delete_photo_file(saved_resolution_photo)
                st.error(
                    f"Location verification failed. The photos are "
                    f"{distance:.2f} metres apart. The allowed distance "
                    f"is {MAX_VERIFICATION_DISTANCE} metres. "
                    "The issue has not been marked as resolved."
                )
                return

            result = save_resolution_evidence(
                issue_id=issue_id,
                resolution_photo=saved_resolution_photo,
                resolution_latitude=resolution_latitude,
                resolution_longitude=resolution_longitude,
                officer_id=user["id"],
                max_distance=MAX_VERIFICATION_DISTANCE,
                resolution_gps_source=resolution_source
            )

            # Check the database after saving rather than assuming
            # that the operation succeeded.
            refreshed_issue = next(
                (
                    item for item in get_all_issues()
                    if int(get_value(item, "id", -1)) == int(issue_id)
                ),
                None
            )

            if refreshed_issue and issue_is_resolved(refreshed_issue):
                st.success(
                    f"Issue #{issue_id} passed the location check "
                    "and is now marked Resolved."
                )
                saved_resolution_photo = None
                st.rerun()
            else:
                report_source = get_value(
                    issue, "report_gps_source", "EXIF"
                ) or "EXIF"

                if (
                    report_source != "EXIF"
                    or resolution_source != "EXIF"
                ):
                    st.warning(
                        "The resolution evidence and coordinates were saved, "
                        "but the issue remains active. Automatic resolution "
                        "requires EXIF GPS on both the original report photo "
                        "and the after-repair photo. Screenshot OCR coordinates "
                        "are not independently verified."
                    )
                else:
                    st.warning(
                        "The evidence was submitted, but the issue was not "
                        "marked as Resolved. Please check the issue record."
                    )
                saved_resolution_photo = None

        except Exception as error:
            if saved_resolution_photo:
                delete_photo_file(saved_resolution_photo)

            st.error(f"Could not submit resolution evidence: {error}")


# =========================================================
# MANAGE ISSUES
# =========================================================

def manage_issues_page(user):
    st.title("🛠️ Manage Issues")

    issues = get_active_issues()
    filtered = filter_issues(issues, "manage")

    if not filtered:
        st.info("No matching active issues.")
        return

    for issue in filtered:
        issue_id = get_value(issue, "id")

        display_issue(issue)

        with st.expander(f"Manage Issue #{issue_id}"):
            current_status = get_value(
                issue,
                "status",
                "Pending"
            )

            # Resolved is intentionally excluded here.
            # A separate GPS verification process is required.
            status_options = ["Pending", "In Progress"]

            if current_status not in status_options:
                current_status = "Pending"

            new_status = st.selectbox(
                "Update status",
                status_options,
                index=status_options.index(current_status),
                key=f"staff_status_{issue_id}"
            )

            if st.button(
                "Save Status",
                key=f"staff_save_{issue_id}"
            ):
                try:
                    update_issue_status(issue_id, new_status)
                    st.success("Issue status updated.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not update status: {error}")

            st.divider()
            st.markdown("**Edit issue details**")

            new_reporter = st.text_input(
                "Reporter",
                value=str(get_value(issue, "reporter", "")),
                key=f"edit_reporter_{issue_id}"
            )

            new_location = st.text_input(
                "Location",
                value=str(get_value(issue, "location", "")),
                key=f"edit_location_{issue_id}"
            )

            new_issue_type = st.text_input(
                "Issue type",
                value=str(get_value(issue, "issue_type", "")),
                key=f"edit_issue_type_{issue_id}"
            )

            new_description = st.text_area(
                "Description",
                value=str(get_value(issue, "description", "")),
                key=f"edit_description_{issue_id}"
            )

            if st.button(
                "Save Issue Details",
                key=f"edit_save_{issue_id}"
            ):
                try:
                    update_issue_details(
                        issue_id,
                        new_reporter,
                        new_location,
                        new_issue_type,
                        new_description
                    )
                    st.success("Issue details updated.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not update issue: {error}")

            st.divider()

            if st.button(
                "Delete Issue",
                key=f"delete_issue_{issue_id}"
            ):
                try:
                    delete_issue(issue_id)
                    st.success(f"Issue #{issue_id} deleted.")
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not delete issue: {error}")

            st.divider()

            resolution_evidence_form(issue, user)


# =========================================================
# RESOLVED ISSUES
# =========================================================

def resolved_issues_page():
    st.title("✅ Resolved Issues")

    issues = get_resolved_issues()

    if not issues:
        st.info("No verified resolved issues are available.")
        return

    filtered = filter_issues(issues, "resolved")

    for issue in filtered:
        issue_id = get_value(issue, "id")

        with st.container(border=True):
            st.markdown(f"### Issue #{issue_id}")
            st.write(f"**Location:** {get_value(issue, 'location', '')}")
            st.write(f"**Issue type:** {get_value(issue, 'issue_type', '')}")
            st.write(f"**Status:** {status_label(get_value(issue, 'status'))}")
            st.write(f"**Severity:** {severity_label(get_value(issue, 'severity'))}")

            report_photo = get_value(issue, "photo")
            resolution_photo = get_value(issue, "resolution_photo")

            before_col, after_col = st.columns(2)

            with before_col:
                st.markdown("**Before repair**")

                path = get_photo_path(report_photo)

                if path and path.exists():
                    st.image(
                        str(path),
                        use_container_width=True
                    )
                else:
                    st.warning("Original report photograph is unavailable.")

            with after_col:
                st.markdown("**After repair**")

                path = get_photo_path(resolution_photo)

                if path and path.exists():
                    st.image(
                        str(path),
                        use_container_width=True
                    )
                else:
                    st.warning("Resolution photograph is unavailable.")

            report_latitude = get_value(issue, "report_latitude")
            report_longitude = get_value(issue, "report_longitude")
            resolution_latitude = get_value(issue, "resolution_latitude")
            resolution_longitude = get_value(issue, "resolution_longitude")
            distance = get_value(issue, "resolution_distance_m")

            st.divider()
            st.markdown("**GPS verification details**")

            gps_col1, gps_col2 = st.columns(2)

            with gps_col1:
                st.write("**Original report GPS**")
                st.write(
                    f"{report_latitude}, {report_longitude}"
                )

            with gps_col2:
                st.write("**Resolution photo GPS**")
                st.write(
                    f"{resolution_latitude}, {resolution_longitude}"
                )

            st.caption(
                "Report GPS source: "
                f"{get_value(issue, 'report_gps_source', 'EXIF') or 'EXIF'}"
                " | Resolution GPS source: "
                f"{get_value(issue, 'resolution_gps_source', 'EXIF') or 'EXIF'}"
            )

            if distance is not None:
                st.metric(
                    "Distance between photographs",
                    f"{float(distance):.2f} metres"
                )

            verified = get_value(issue, "location_verified", 0)

            if verified:
                st.success(
                    f"Location check passed — within "
                    f"{MAX_VERIFICATION_DISTANCE} metres."
                )
            else:
                st.error("Location verification is not confirmed.")

            st.write(
                f"**Resolved by staff user ID:** "
                f"{get_value(issue, 'resolved_by', 'Not available')}"
            )
            st.write(
                f"**Resolved at:** "
                f"{get_value(issue, 'resolved_at', 'Not available')}"
            )


# =========================================================
# CITIZEN REPORTS
# =========================================================

def citizen_reports_page(user):
    st.title("📄 My Reports")

    user_id = user["id"]

    my_issues = [
        issue for issue in get_all_issues()
        if str(get_value(issue, "reported_by", "")) == str(user_id)
    ]

    if not my_issues:
        st.info("You have not submitted any reports yet.")
        return

    my_issues.sort(
        key=lambda issue: int(get_value(issue, "id", 0)),
        reverse=True
    )

    for issue in my_issues:
        display_issue(issue)


# =========================================================
# STAFF DASHBOARD
# =========================================================

def staff_dashboard_page(user):
    st.title("🧰 Worker Dashboard")
    st.write("Review active drainage complaints and submit resolution evidence.")

    active = get_active_issues()
    resolved = get_resolved_issues()

    col1, col2, col3 = st.columns(3)
    col1.metric("Active Issues", len(active))
    col2.metric("Resolved Issues", len(resolved))
    col3.metric("Total Reports", len(active) + len(resolved))

    st.divider()

    page = st.sidebar.radio(
        "Worker Navigation",
        [
            "Active Issues",
            "Resolved Issues"
        ]
    )

    if page == "Active Issues":
        manage_issues_page(user)
    else:
        resolved_issues_page()


# =========================================================
# USER MANAGEMENT
# =========================================================


def user_management_page():
    st.title("User Management")

    # -----------------------------------------
    # CREATE Worker ACCOUNT
    # -----------------------------------------

    st.subheader("Create Worker Account")

    with st.form("create_staff_form"):
        staff_name = st.text_input("Worker Full Name")
        staff_email = st.text_input("Worker Email")
        staff_password = st.text_input(
            "Worker Password",
            type="password"
        )
        confirm_password = st.text_input(
            "Confirm Password",
            type="password"
        )

        create_staff = st.form_submit_button(
            "Create Worker Account",
            use_container_width=True
        )

        if create_staff:
            if not staff_name.strip() or not staff_email.strip():
                st.error("Please enter the worker name and email.")

            elif not staff_password:
                st.error("Please enter a password.")

            elif staff_password != confirm_password:
                st.error("Passwords do not match.")

            else:
                try:
                    create_user(
                        full_name=staff_name,
                        email=staff_email,
                        password=staff_password,
                        role="Worker"
                    )

                    st.success("Worker account created successfully!")
                    st.rerun()

                except Exception as error:
                    st.error(f"Could not create worker account: {error}")

    st.divider()

    # -----------------------------------------
    # REGISTERED USERS
    # -----------------------------------------

    st.subheader("Registered Users")

    try:
        users = get_all_users()

        st.write(f"Registered users: {len(users)}")

        if not users:
            st.info("No users are registered.")
            return

        for user in users:
            with st.container(border=True):
                st.write(
                    f"**{get_value(user, 'full_name', 'Unknown')}**"
                )
                st.write(
                    f"Email: {get_value(user, 'email', 'Not available')}"
                )
                st.write(
                    f"Role: {get_value(user, 'role', 'Not available')}"
                )
                st.write(
                    f"User ID: {get_value(user, 'id', 'Not available')}"
                )

    except Exception as error:
        st.error(f"Could not load users: {error}")

    

# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

def main():
    if "authenticated_user" not in st.session_state:
        login_screen()
        return

    user = st.session_state["authenticated_user"]

    show_sidebar(user)

    role = str(user.get("role", "")).strip()

    if role == "Admin":
        page = st.sidebar.radio(
            "Navigation",
            [
                "Dashboard",
                "Report an Issue",
                "Manage Issues",
                "Resolved Issues",
                "User Management"
            ]
        )

        if page == "Dashboard":
            dashboard_page()

        elif page == "Report an Issue":
            report_issue_page(user)

        elif page == "Manage Issues":
            manage_issues_page(user)

        elif page == "Resolved Issues":
            resolved_issues_page()

        elif page == "User Management":
            user_management_page()

    elif role == "Citizen":
        page = st.sidebar.radio(
            "Navigation",
            [
                "Report an Issue",
                "My Reports"
            ]
        )

        if page == "Report an Issue":
            report_issue_page(user)

        elif page == "My Reports":
            citizen_reports_page(user)

    elif role in ["Worker", "Staff"]:
        staff_dashboard_page(user)

    else:
        st.error("Invalid account role.")
        logout()


if __name__ == "__main__":
    main()
