import os
import sqlite3
import hashlib
import secrets
import hmac
from math import radians, sin, cos, sqrt, atan2


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, "drainproof.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
HASH_ALGORITHM = "sha256"
HASH_ITERATIONS = 600000
VALID_ROLES = ["Citizen", "Admin", "Worker", "Staff"]
VALID_GPS_SOURCES = {"EXIF", "SCREENSHOT_OCR"}
MAX_RESOLUTION_DISTANCE = 100.0


def get_connection():
    """Open a SQLite connection that returns dictionary-like rows."""
    os.makedirs(BASE_DIR, exist_ok=True)
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_table():
    """Create tables and safely add columns to an existing project database."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Citizen',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter TEXT,
                location TEXT,
                issue_type TEXT,
                description TEXT,
                photo TEXT,
                severity TEXT,
                ai_analysis TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reported_by INTEGER,
                report_latitude REAL,
                report_longitude REAL,
                report_gps_source TEXT DEFAULT 'EXIF',
                resolution_photo TEXT,
                resolution_latitude REAL,
                resolution_longitude REAL,
                resolution_gps_source TEXT DEFAULT 'EXIF',
                resolved_by INTEGER,
                resolved_at TIMESTAMP,
                resolution_distance_m REAL,
                location_verified INTEGER DEFAULT 0
            )
        """)

        cursor.execute("PRAGMA table_info(issues)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        migrations = {
            "reporter": "ALTER TABLE issues ADD COLUMN reporter TEXT",
            "location": "ALTER TABLE issues ADD COLUMN location TEXT",
            "issue_type": "ALTER TABLE issues ADD COLUMN issue_type TEXT",
            "description": "ALTER TABLE issues ADD COLUMN description TEXT",
            "photo": "ALTER TABLE issues ADD COLUMN photo TEXT",
            "severity": "ALTER TABLE issues ADD COLUMN severity TEXT",
            "ai_analysis": "ALTER TABLE issues ADD COLUMN ai_analysis TEXT",
            "status": "ALTER TABLE issues ADD COLUMN status TEXT DEFAULT 'Pending'",
            "created_at": "ALTER TABLE issues ADD COLUMN created_at TIMESTAMP",
            "reported_by": "ALTER TABLE issues ADD COLUMN reported_by INTEGER",
            "report_latitude": "ALTER TABLE issues ADD COLUMN report_latitude REAL",
            "report_longitude": "ALTER TABLE issues ADD COLUMN report_longitude REAL",
            "report_gps_source": "ALTER TABLE issues ADD COLUMN report_gps_source TEXT DEFAULT 'EXIF'",
            "resolution_photo": "ALTER TABLE issues ADD COLUMN resolution_photo TEXT",
            "resolution_latitude": "ALTER TABLE issues ADD COLUMN resolution_latitude REAL",
            "resolution_longitude": "ALTER TABLE issues ADD COLUMN resolution_longitude REAL",
            "resolution_gps_source": "ALTER TABLE issues ADD COLUMN resolution_gps_source TEXT DEFAULT 'EXIF'",
            "resolved_by": "ALTER TABLE issues ADD COLUMN resolved_by INTEGER",
            "resolved_at": "ALTER TABLE issues ADD COLUMN resolved_at TIMESTAMP",
            "resolution_distance_m": "ALTER TABLE issues ADD COLUMN resolution_distance_m REAL",
            "location_verified": "ALTER TABLE issues ADD COLUMN location_verified INTEGER DEFAULT 0",
        }

        for column_name, sql in migrations.items():
            if column_name not in existing_columns:
                cursor.execute(sql)

        # Earlier app versions only accepted EXIF GPS, so legacy GPS rows are
        # labelled EXIF. New OCR-based submissions explicitly store their source.
        cursor.execute("""
            UPDATE issues
            SET report_gps_source = 'EXIF'
            WHERE report_gps_source IS NULL OR TRIM(report_gps_source) = ''
        """)
        cursor.execute("""
            UPDATE issues
            SET resolution_gps_source = 'EXIF'
            WHERE resolution_gps_source IS NULL OR TRIM(resolution_gps_source) = ''
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_reported_by ON issues(reported_by)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status)")
        connection.commit()
    finally:
        connection.close()


def hash_password(password):
    if not password:
        raise ValueError("Password cannot be empty.")

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS
    ).hex()

    return f"sha256${HASH_ITERATIONS}${salt}${digest}"



def verify_password(password, stored_hash):
    try:
        parts = stored_hash.split("$")

        # Old format: salt$digest
        if len(parts) == 2:
            salt, original_hash = parts
            algorithm = "sha256"
            iterations = 100000

        # New format: algorithm$iterations$salt$digest
        elif len(parts) == 4:
            algorithm, iterations, salt, original_hash = parts
            iterations = int(iterations)

        else:
            return False

        if algorithm != "sha256":
            return False

        digest = hashlib.pbkdf2_hmac(
            algorithm,
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        ).hex()

        return hmac.compare_digest(digest, original_hash)

    except (ValueError, TypeError, AttributeError):
        return False





# =========================================================
# USER ACCOUNT MANAGEMENT
# =========================================================

def create_user(full_name, email, password, role="Citizen"):
    """Create a new user account."""

    full_name = str(full_name or "").strip()
    email = str(email or "").strip().lower()
    role = str(role or "Citizen").strip().capitalize()

    if not full_name:
        raise ValueError("Full name is required.")

    if not email:
        raise ValueError("Email address is required.")

    if not password:
        raise ValueError("Password is required.")

    if role not in VALID_ROLES:
        raise ValueError("Invalid user role.")

    password_hash = hash_password(password)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users (
                full_name,
                email,
                password_hash,
                role
            )
            VALUES (?, ?, ?, ?)
            """,
            (full_name, email, password_hash, role)
        )

        connection.commit()

        return cursor.lastrowid

    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists.")

    finally:
        connection.close()


def register_citizen(full_name, email, password):
    """Register a new Citizen account."""

    return create_user(
        full_name=full_name,
        email=email,
        password=password,
        role="Citizen"
    )


def get_user_by_email(email):
    """Retrieve a user using their email address."""

    email = str(email or "").strip().lower()

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,)
        )

        return cursor.fetchone()

    finally:
        connection.close()


def authenticate_user(email, password):
    """Authenticate a user without changing their existing password hash."""

    if not email or not password:
        return None

    user = get_user_by_email(email)

    if user is None:
        return None

    if verify_password(password, user["password_hash"]):
        return user

    return None


def get_all_users():
    """Retrieve all registered users without exposing password hashes."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                full_name,
                email,
                role,
                created_at
            FROM users
            ORDER BY id ASC
            """
        )

        return cursor.fetchall()

    finally:
        connection.close()

def _validate_gps_source(source, field_name):
    source = str(source or "EXIF").strip().upper()
    if source not in VALID_GPS_SOURCES:
        raise ValueError(f"Invalid {field_name}. Use EXIF or SCREENSHOT_OCR.")
    return source


def _validate_coordinates(latitude, longitude):
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        raise ValueError("Valid latitude and longitude coordinates are required.")

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    return latitude, longitude


def calculate_distance_metres(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance between two coordinates in metres."""
    lat1, lon1 = _validate_coordinates(lat1, lon1)
    lat2, lon2 = _validate_coordinates(lat2, lon2)

    earth_radius = 6371000.0
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    a = min(1.0, max(0.0, a))
    return earth_radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def save_issue(
    reporter,
    location,
    issue_type,
    description,
    photo=None,
    user_id=None,
    report_latitude=None,
    report_longitude=None,
    report_gps_source="EXIF"
):
    report_latitude, report_longitude = _validate_coordinates(
        report_latitude, report_longitude
    )
    report_gps_source = _validate_gps_source(
        report_gps_source, "report GPS source"
    )

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO issues (
                reporter, location, issue_type, description, photo, status,
                reported_by, report_latitude, report_longitude, report_gps_source
            )
            VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?, ?, ?)
        """, (
            reporter, location, issue_type, description, photo, user_id,
            report_latitude, report_longitude, report_gps_source
        ))
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_all_issues():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM issues ORDER BY id DESC")
        return cursor.fetchall()
    finally:
        connection.close()


def get_issue_by_id(issue_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
        return cursor.fetchone()
    finally:
        connection.close()


def get_active_issues():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM issues WHERE LOWER(status) != 'resolved' ORDER BY id DESC"
        )
        return cursor.fetchall()
    finally:
        connection.close()


def get_resolved_issues():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM issues WHERE LOWER(status) = 'resolved' ORDER BY id DESC"
        )
        return cursor.fetchall()
    finally:
        connection.close()



def save_resolution_evidence(
    issue_id,
    resolution_photo,
    resolution_latitude,
    resolution_longitude,
    officer_id,
    max_distance=MAX_RESOLUTION_DISTANCE,
    resolution_gps_source="EXIF"
):
    """
    Save resolution evidence.

    Coordinates within the allowed distance can resolve an issue.
    EXIF-to-EXIF evidence is independently location-verified.
    OCR evidence can resolve an issue but is not independently verified.
    """
    resolution_latitude, resolution_longitude = _validate_coordinates(
        resolution_latitude, resolution_longitude
    )

    resolution_gps_source = _validate_gps_source(
        resolution_gps_source, "resolution GPS source"
    )

    max_distance = float(max_distance)

    if max_distance <= 0:
        raise ValueError("Maximum verification distance must be positive.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM issues WHERE id = ?",
            (issue_id,)
        )

        issue = cursor.fetchone()

        if issue is None:
            raise ValueError("Issue not found.")

        report_latitude = issue["report_latitude"]
        report_longitude = issue["report_longitude"]

        if report_latitude is None or report_longitude is None:
            raise ValueError(
                "The original report has no saved GPS coordinates."
            )

        distance = calculate_distance_metres(
            report_latitude,
            report_longitude,
            resolution_latitude,
            resolution_longitude
        )

        if distance > max_distance:
            raise ValueError(
                f"The photographs are {distance:.2f} metres apart; "
                f"the maximum allowed distance is {max_distance:.2f} metres."
            )

        report_source = _validate_gps_source(
            issue["report_gps_source"],
            "report GPS source"
        )

        # Only EXIF-to-EXIF evidence is independently verified.
        sources_are_trusted = (
            report_source == "EXIF"
            and resolution_gps_source == "EXIF"
        )

        # Both EXIF and OCR coordinates can resolve an issue
        # when the distance is within the allowed limit.
        new_status = "Resolved"
        resolved_by = officer_id
        location_verified = 1 if sources_are_trusted else 0

        cursor.execute("""
            UPDATE issues
            SET resolution_photo = ?,
                resolution_latitude = ?,
                resolution_longitude = ?,
                resolution_gps_source = ?,
                resolved_by = ?,
                resolved_at = CURRENT_TIMESTAMP,
                resolution_distance_m = ?,
                location_verified = ?,
                status = ?
            WHERE id = ?
        """, (
            resolution_photo,
            resolution_latitude,
            resolution_longitude,
            resolution_gps_source,
            resolved_by,
            distance,
            location_verified,
            new_status,
            issue_id
        ))

        connection.commit()

        return {
            "saved": cursor.rowcount > 0,
            "verified": bool(location_verified),
            "distance": distance,
            "status": new_status,
            "report_gps_source": report_source,
            "resolution_gps_source": resolution_gps_source
        }

    finally:
        connection.close()



def update_issue_status(issue_id, status):
    status = str(status or "").strip()
    allowed_statuses = {"Pending", "In Progress", "Resolved"}
    if status not in allowed_statuses:
        raise ValueError("Invalid issue status.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
        issue = cursor.fetchone()
        if issue is None:
            return False

        if status == "Resolved":
            report_source = str(issue["report_gps_source"] or "EXIF").upper()
            resolution_source = str(issue["resolution_gps_source"] or "EXIF").upper()
            if not (
                issue["location_verified"] == 1
                and issue["resolution_photo"]
                and report_source == "EXIF"
                and resolution_source == "EXIF"
                and issue["resolution_distance_m"] is not None
                and float(issue["resolution_distance_m"]) <= MAX_RESOLUTION_DISTANCE
            ):
                raise ValueError(
                    "This issue cannot be marked Resolved. A resolution photo "
                    "and verified EXIF GPS coordinates within 50 metres are required."
                )

        cursor.execute(
            "UPDATE issues SET status = ? WHERE id = ?",
            (status, issue_id)
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def update_issue_analysis(issue_id, ai_analysis=None, severity=None):
    """Update AI analysis; tolerate the older severity/analysis argument order."""
    severity_values = {"Low", "Medium", "High", "Unknown", "LOW", "MEDIUM", "HIGH", "UNKNOWN"}
    if ai_analysis in severity_values and severity not in severity_values:
        ai_analysis, severity = severity, ai_analysis

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE issues
            SET ai_analysis = ?, severity = ?
            WHERE id = ?
        """, (ai_analysis, severity, issue_id))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def update_issue_details(issue_id, reporter, location, issue_type, description):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE issues
            SET reporter = ?, location = ?, issue_type = ?, description = ?
            WHERE id = ?
        """, (reporter, location, issue_type, description, issue_id))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def _delete_upload_file(photo_path):
    if not photo_path:
        return

    candidate = str(photo_path)
    if not os.path.isabs(candidate):
        candidate = os.path.join(BASE_DIR, candidate)

    candidate = os.path.abspath(candidate)
    upload_root = os.path.abspath(UPLOAD_DIR)

    try:
        if (
            os.path.commonpath([upload_root, candidate]) == upload_root
            and os.path.isfile(candidate)
        ):
            os.remove(candidate)
    except (ValueError, OSError):
        pass


def delete_issue(issue_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT photo, resolution_photo FROM issues WHERE id = ?",
            (issue_id,)
        )
        issue = cursor.fetchone()
        if issue is None:
            return False

        report_photo = issue["photo"]
        resolution_photo = issue["resolution_photo"]

        cursor.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
        connection.commit()
        deleted = cursor.rowcount > 0

        if deleted:
            _delete_upload_file(report_photo)
            if resolution_photo != report_photo:
                _delete_upload_file(resolution_photo)

        return deleted
    finally:
        connection.close()
