# Future Minds Online (منصة فيوتشر مايندز التعليمية)

[![Django](https://img.shields.io/badge/Django-5.0+-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=black)](https://render.com)
[![Status](https://img.shields.io/badge/Production-Ready-brightgreen?style=for-the-badge)]()

**Future Minds Online** is a comprehensive, production-ready Learning Management System (LMS) and Academy Operations Platform built specifically for Future Minds Academy. It manages online and in-person (offline) STEM/coding courses, live class scheduling, automated attendance tracking via Google Meet integration, interactive assignments, quizzes with automated document-based question extraction, and real-time student progress monitoring.

---

## 🌟 Key Features Overview

### 🔐 1. Multi-Role Authentication & Access Control
- **Four Distinct Roles**:
  - 🛡️ **Academy Admin**: Full system control, analytics overview, attendance policy configuration, and user/course management.
  - 👨‍🏫 **Instructor**: Class session scheduling, assignment grading, quiz creation with automated question extractions, and student alert monitoring.
  - 🎓 **Student**: Interactive dashboard, live session countdowns with status locking, lesson materials, assignment submissions, single-attempt quizzes, and overall progress tracking.
  - 👨‍👩‍👧 **Parent**: Read-only oversight of their child's attendance rate, grades, and academic alerts.
- **RTL & Egyptian Arabic Localization**: Complete UI tailored with Egyptian dialect nuances and modern Bootstrap 5 dark/purple brand aesthetic.

---

### 📅 2. Live Class Sessions & Smart Attendance System
- **Automated Recurrence Scheduling**: Auto-generate full course session schedules (e.g. 8 sessions every Saturday and Tuesday starting from a base date).
- **Time-Locked Live Buttons**: The "Join Class" button automatically transforms into a locked icon 🔒 until the scheduled class time arrives.
- **Automated Attendance Logging**:
  - Tracks student attendance status: `PRESENT`, `LATE`, `ABSENT`, or `EXCUSED`.
  - Distinguishes between Online students (Google Meet click events) and Offline/In-Person students (manual instructor check-in).
  - Customizable attendance grace periods (e.g., 15-minute early window, 5-minute late cutoff).

---

### 🧠 3. Interactive Assessment & Quiz Engine
- **Multi-Format Quiz Question Extractor (`assessment/extractor.py`)**:
  - Upload question banks directly from **Word (`.docx`)**, **Excel (`.xlsx`)**, **CSV (`.csv`)**, **Text (`.txt`)**, or **JSON (`.json`)**.
  - Smart column and header identification in both Arabic (أ، ب، ج، د / السؤال / الإجابة) and English (Option A-D / Correct Answer / Explanation).
- **Single Quiz Attempt Policy**: Enforces strict single-attempt limits per student to guarantee academic integrity.
- **Visual Question Editor**: Instructors can review, edit, delete, or manually append questions after uploading.
- **Assignments & Grading**: Assignment submission portal supporting code snippets, solution text, and starter starter files with instructor feedback.

---

### 📊 4. Progress Tracking & Performance Analytics
- **Lesson Completion Logic**: Automatically marks a lesson as completed when a student attends the session (`PRESENT`/`LATE`) AND downloads the corresponding booklet/material (`DOWNLOAD_MATERIAL`).
- **Comprehensive Score Calculation**: Aggregates attendance rate, assignment scores, and quiz averages into an overall percentage.
- **Automated Risk Alerts**: Generates warning alerts for students with low attendance or failing averages.

---

## 🏗️ Project Architecture & Tech Stack

```text
Future-Minds-Online/
├── academy/           # Courses, Lessons, Materials, Class Sessions, & Attendance
├── assessment/        # Quizzes, Assignments, Submissions, Question Extractor, & Progress Service
├── core/              # Custom User Model, Authentication, Notifications, & Activity Logs
├── future_minds/      # Project WSGI/ASGI Settings & Core URL Routing
├── static/            # CSS Design System (RTL Bootstrap 5 + Brand Variables), JS, & Images
├── templates/         # HTML5 Templates (Dashboard, Classes, Quizzes, Progress, Profiles)
├── build.sh           # Production Deployment Script
├── render.yaml        # Render Cloud Infrastructure Blueprint
└── requirements.txt   # Python Dependencies
```

- **Backend**: Python 3.12+, Django 5.0+
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design Tokens), JavaScript (ES6+), Bootstrap 5.3 RTL, FontAwesome 6
- **Database**: PostgreSQL (Production) / SQLite3 (Development)
- **Static Assets**: WhiteNoise (Compressed Manifest Storage)
- **Document Processing**: `python-docx`, `openpyxl`

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- Python 3.12+ installed
- Git

### 2. Clone & Setup Virtual Environment
```bash
git clone https://github.com/mennahaleem401/Future-Minds-Online.git
cd Future-Minds-Online

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies & Run Migrations
```bash
pip install -r requirements.txt
python manage.py migrate
```

### 4. Populate Seed Data (Optional)
To instantly populate the database with demo courses, instructors, students, and sessions:
```bash
python manage.py setup_demo_data
```

### 5. Run Development Server
```bash
python manage.py runserver
```
Navigate to `http://127.0.0.1:8000` in your browser.

---

## ☁️ Production Deployment Guide

### Deploying on Render (Recommended)

1. **Option A: Web Service Deployment (100% Free)**
   - Sign up at [Render.com](https://render.com).
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repository `mennahaleem401/Future-Minds-Online`.
   - Set the following fields:
     - **Runtime**: `Python 3`
     - **Build Command**: `bash ./build.sh`
     - **Start Command**: `gunicorn future_minds.wsgi:application`
   - Add Environment Variables:
     - `DEBUG`: `False`
     - `PYTHON_VERSION`: `3.12`
     - `SECRET_KEY`: *(Generate a secure random string)*
     - `ADMIN_USERNAME`: `admin` *(Optional for auto-creating initial admin)*
     - `ADMIN_PASSWORD`: `YourStrongPassword`
   - Click **Create Web Service**.

2. **Option B: Render Blueprint Deployment (Managed PostgreSQL)**
   - Click **New +** -> **Blueprint**.
   - Connect the repository. Render will automatically read `render.yaml` and configure both the Web Service and PostgreSQL database.

---

## 🧪 Automated Testing

The project comes with a comprehensive suite of unit tests covering authentication, question extraction, quiz attempt locks, attendance tracking, and progress calculations.

To execute the test suite:
```bash
python manage.py test
```

---

## 📄 License & Attribution

Developed for **Future Minds Academy**. All rights reserved.