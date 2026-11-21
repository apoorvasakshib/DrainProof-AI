
# DrainProof AI

### AI-Powered Drainage Issue Reporting and Verification System

DrainProof AI is a web-based civic issue reporting and monitoring application designed to help citizens report drainage-related problems and help authorized staff manage and verify their resolution.

The system combines image-based AI analysis, GPS location extraction, OCR-based coordinate detection, and role-based dashboards to improve the reporting and tracking of drainage issues.

## Features

### 1. User Management
- Citizen account registration and login.
- Role-based access for Citizens, Staff, and Admins.
- Secure password hashing.
- Admin user management.

### 2. Drainage Issue Reporting
- Submit drainage-related complaints.
- Add issue descriptions and location details.
- Upload photographs in JPG, JPEG, PNG, and WEBP formats.
- Extract GPS coordinates from uploaded photographs.

### 3. AI-Based Image Analysis
- Uses Google's Gemini 2.5 Flash model.
- Analyzes uploaded photographs for visible drainage-related problems.
- Provides detected issue details and recommendations.
- Classifies severity as Low, Medium, High, or Unknown.

### 4. GPS and OCR-Based Location Extraction
- Extracts GPS coordinates from image EXIF metadata.
- Uses Tesseract OCR as a fallback to read visible coordinates from screenshots.
- Supports two recorded GPS sources: EXIF and SCREENSHOT_OCR.

### 5. Resolution Evidence Verification
- Staff can submit photographs as resolution evidence.
- Compares resolution coordinates with the original report coordinates.
- Uses a 100-metre maximum resolution distance.
- Stores resolution evidence, coordinates, GPS source, and distance.
- Distinguishes EXIF-to-EXIF location verification from OCR-based location matching.

### 6. Dashboards
- Citizen reports.
- Staff dashboard.
- Admin dashboard.
- Issue status and resolution management.
- User management for administrators.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend and application | Streamlit |
| Programming language | Python |
| Database | SQLite |
| AI image analysis | Google Gemini 2.5 Flash |
| Image processing | Pillow |
| OCR | Tesseract OCR |
| Python OCR integration | Pytesseract |
| GPS extraction | Image EXIF metadata |
| Password security | Salted SHA-256 hashing with PBKDF2-style iteration |

## Project Structure

```text
DrainProof-AI/
│
├── app.py
├── ai_analysis.py
├── create_admin.py
├── test_gemini.py
├── requirements.txt
├── packages.txt
├── .gitignore
├── README.md
├── SPEC.md
│
├── database/
│   ├── __init__.py
│   └── db.py
│
├── uploads/
├── tessdata/
├── drainproof.db
├── .streamlit/
└── venv/
```

Local database files, uploaded photographs, virtual environments, and secrets should not be committed to GitHub.

## Installation and Setup

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd DrainProof-AI
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual repository URL.

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure the Gemini API key

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

Never upload your `.env` file or expose your API key publicly.

### 6. Install Tesseract OCR

Install the Tesseract OCR application on your system and ensure that it is available to Pytesseract.

The `packages.txt` file contains the Linux system package required for Streamlit Community Cloud:

```text
tesseract-ocr
```

### 7. Run the application

```bash
streamlit run app.py
```

The application will open in your browser.

## User Roles

| Role | Responsibilities |
|---|---|
| Citizen | Register, log in, and report drainage issues |
| Staff | Manage assigned work and submit resolution evidence |
| Admin | Access administrative dashboard and manage users |

## Resolution Verification Logic

The application compares the original report coordinates with the coordinates extracted from the resolution photograph.

- Maximum permitted distance: 100 metres.
- EXIF GPS coordinates are treated as the trusted source for location verification.
- OCR-extracted coordinates can be used for location matching.
- `location_verified` is set to 1 only when both the report and resolution sources are EXIF and the verification conditions are satisfied.

## Security and Deployment Notes

- Passwords are stored as salted hashes, not as plain text.
- API keys and secrets must remain outside source control.
- `.gitignore` excludes local databases, uploads, virtual environments, and secret files.
- The current application uses local SQLite storage and local photograph storage. These need persistent database and file-storage services for reliable production deployment.

## Future Enhancements

- Persistent cloud database integration.
- Cloud storage for uploaded photographs.
- Improved image authenticity and drainage issue validation.
- Interactive issue-location maps.
- Notifications for issue status changes.
- Advanced analytics and reporting.
- Deployment hardening and automated testing.

## Project Status

DrainProof AI is under development. Features and deployment configuration may evolve as the project is improved.

---

**DrainProof AI – Making Civic Drainage Issue Reporting Smarter.**
