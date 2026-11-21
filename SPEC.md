
# DrainProof AI – Software Requirements and Technical Specification

## 1. Introduction

### 1.1 Purpose

DrainProof AI is a web-based civic issue reporting and monitoring system designed to manage drainage-related complaints using artificial intelligence, image processing, GPS extraction, and location-based resolution evidence.

The system aims to make drainage issue reporting more organized, transparent, and easier to monitor.

### 1.2 Scope

The application supports:

- Citizen registration and authentication.
- Drainage issue reporting.
- Image upload and AI-based analysis.
- GPS coordinate extraction from photographs.
- OCR-based coordinate extraction from screenshots.
- Staff handling of issue resolution.
- Location-based resolution evidence matching.
- Administrative user and issue management.

### 1.3 Intended Users

1. Citizens
2. Staff members
3. Administrators

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Application framework | Streamlit |
| Programming language | Python |
| Database | SQLite |
| AI model | Google Gemini 2.5 Flash |
| Image processing | Pillow |
| OCR engine | Tesseract OCR |
| OCR integration | Pytesseract |
| GPS extraction | EXIF metadata |
| HTTP communication | Requests |
| Configuration | python-dotenv |

## 3. System Architecture

The application follows a modular architecture.

```text
              USER
                |
                v
       STREAMLIT APPLICATION
              app.py
                |
       +--------+---------+
       |        |         |
       v        v         v
   DATABASE    AI       IMAGE AND
    MODULE   ANALYSIS   GPS / OCR
   db.py    ai_analysis.py
       |        |         |
       v        v         v
    SQLite   Gemini    EXIF / Tesseract
   Database   API       OCR
```

### 3.1 Application Layer

`app.py` manages:

- User authentication.
- Role-based navigation.
- Issue reporting.
- Dashboard rendering.
- Photograph uploads.
- GPS extraction and verification.
- Resolution evidence submission.

### 3.2 AI Analysis Layer

`ai_analysis.py` communicates with the Gemini API to analyze uploaded photographs and return structured drainage issue analysis.

### 3.3 Database Layer

`database/db.py` manages:

- Database initialization.
- User accounts.
- Password hashing and verification.
- Issue records.
- Resolution evidence.
- Issue status updates.
- Database schema migrations.

## 4. Functional Requirements

### FR-01: User Registration

The system shall allow citizens to create accounts by providing their name, email address, and password.

### FR-02: User Authentication

The system shall authenticate users and provide access according to their assigned roles.

### FR-03: Role-Based Access

The system shall support three roles:

- Citizen
- Staff
- Admin

Each role shall have its corresponding application interface and permissions.

### FR-04: Issue Reporting

The system shall allow citizens to submit drainage-related complaints with:

- Issue description.
- Issue category.
- Location information.
- Supporting photograph.

### FR-05: Image Upload

The system shall accept JPG, JPEG, PNG, and WEBP image formats.

Uploaded photographs shall be stored in the application's uploads directory.

### FR-06: AI Image Analysis

The system shall send supported images to Gemini 2.5 Flash for drainage-related analysis.

The AI response shall include:

- Detected issue.
- Severity classification.
- Recommendation.
- Analysis details.

Severity values shall include Low, Medium, High, and Unknown.

### FR-07: GPS Extraction

The system shall attempt to extract geographic coordinates from image EXIF metadata.

### FR-08: OCR Coordinate Extraction

If EXIF GPS metadata is unavailable, the system shall attempt to read visible coordinates from a screenshot using Tesseract OCR.

### FR-09: Issue Management

Authorized users shall be able to access issue management features according to their roles.

### FR-10: Resolution Evidence Submission

Staff shall be able to submit a resolution photograph with extracted coordinates as evidence of completed work.

### FR-11: Location-Based Resolution Matching

The system shall calculate the geographical distance between the original report coordinates and resolution evidence coordinates.

The maximum permitted resolution distance shall be 100 metres.

Evidence beyond this limit shall not satisfy the location-matching condition.

### FR-12: Resolution Status

When acceptable resolution evidence is saved within the permitted distance, the issue status shall be updated to Resolved.

### FR-13: Administrative Management

Administrators shall have access to user management and administrative dashboard functionality.

## 5. Non-Functional Requirements

### 5.1 Security

- Passwords shall not be stored as plain text.
- Password hashing shall use a random salt and repeated SHA-256 hashing.
- API keys shall be stored outside public source code.
- Role-based access shall restrict application functionality.

### 5.2 Reliability

- Database tables shall be created automatically when the application starts.
- Database initialization shall support adding missing columns to older database versions.
- Invalid image formats shall be rejected.

### 5.3 Usability

- The application shall provide a browser-based interface.
- Users shall interact through role-specific dashboards.
- The application shall provide feedback for operations and errors.

### 5.4 Maintainability

- Application logic, AI analysis, and database operations shall be separated into modules.
- Database migrations shall support schema updates.

## 6. Database Design

### 6.1 Users Table

| Field | Description |
|---|---|
| id | Unique user identifier |
| full_name | User's full name |
| email | Unique email address |
| password_hash | Hashed password |
| role | Citizen, Staff, or Admin |
| created_at | Account creation timestamp |

### 6.2 Issues Table

| Field | Description |
|---|---|
| id | Unique issue identifier |
| reporter | Reporter information |
| location | Reported location |
| issue_type | Type of drainage issue |
| description | Issue description |
| photo | Original report photograph |
| severity | AI severity classification |
| ai_analysis | AI analysis details |
| status | Issue status |
| created_at | Report creation timestamp |
| reported_by | Reporting user ID |
| report_latitude | Original report latitude |
| report_longitude | Original report longitude |
| report_gps_source | EXIF or SCREENSHOT_OCR |
| resolution_photo | Resolution photograph |
| resolution_latitude | Resolution latitude |
| resolution_longitude | Resolution longitude |
| resolution_gps_source | Resolution GPS source |
| resolved_by | Staff user identifier |
| resolved_at | Resolution timestamp |
| resolution_distance_m | Distance between report and resolution |
| location_verified | EXIF-based verification indicator |

## 7. GPS and Resolution Verification

### 7.1 GPS Sources

The system supports two coordinate extraction sources:

**EXIF**

Coordinates embedded in the original image metadata.

**SCREENSHOT_OCR**

Coordinates read from visible text in a screenshot using OCR.

### 7.2 Distance Calculation

The application calculates the distance between two geographic coordinates using the Haversine formula.

### 7.3 Verification Conditions

The maximum resolution distance is configured as 100 metres.

The application records whether the report and resolution evidence use trusted EXIF GPS sources.

- EXIF-to-EXIF evidence can be marked as location verified when the location checks pass.
- OCR-based evidence can be accepted for location matching but is not marked as independently EXIF-verified.
- Resolution evidence outside the permitted distance is rejected.

### 7.4 Important Limitation

Location matching does not prove that the drainage problem itself has been repaired. The current system uses coordinate proximity and submitted evidence; additional image validation and human inspection may be required.

## 8. Application Workflow

### 8.1 Issue Reporting Workflow

1. Citizen logs into the application.
2. Citizen enters drainage issue details.
3. Citizen uploads a photograph.
4. System attempts EXIF GPS extraction.
5. If EXIF GPS is unavailable, OCR coordinate extraction is attempted.
6. Image is analyzed using Gemini.
7. Issue details and analysis are stored in SQLite.

### 8.2 Resolution Workflow

1. Staff accesses the issue.
2. Staff submits a resolution photograph.
3. System extracts coordinates using EXIF or OCR.
4. System calculates the distance from the original report.
5. Evidence within the configured distance can be accepted.
6. Issue status is updated to Resolved.
7. Resolution details are stored in the database.

## 9. Constraints and Limitations

- Gemini analysis requires a valid API key and network access.
- OCR accuracy depends on screenshot clarity and coordinate formatting.
- Images without usable GPS information may not provide sufficient location evidence.
- The current database and uploaded photographs are stored locally.
- Local storage is not sufficient for reliable persistent cloud deployment.
- AI-generated analysis may require human review.
- Coordinate proximity alone cannot prove physical repair.

## 10. Future Enhancements

- Persistent cloud database.
- Cloud photograph storage.
- Interactive geographic issue maps.
- Notifications and status tracking.
- Improved image validation.
- Analytics and report generation.
- Automated testing and deployment monitoring.

## 11. Conclusion

DrainProof AI integrates AI-powered image analysis, GPS extraction, OCR, and role-based issue management into a civic drainage reporting system.

The system provides a foundation for organized reporting and location-based resolution evidence matching, with opportunities for further improvements in persistence, validation, and deployment.

---

**Document:** DrainProof AI Technical Specification  
**Version:** 1.0  
**Status:** Development
