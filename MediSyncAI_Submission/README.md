# MediSync AI — College Demonstration Build

A runnable Flask prototype for a digital medical-record wallet with role-based dashboards, demo OTP registration, secure password hashing, document uploads, patient timeline, doctor notes, admin activity view, and a clearly labeled demonstration-only health indicator.

## Requirements
- Python 3.10+
- VS Code recommended
- No MySQL installation required for this submission build: SQLite creates `medisync.db` automatically.

## Run on Windows
1. Extract the ZIP.
2. Open the extracted `MediSyncAI_Submission` folder in VS Code.
3. Open Terminal → New Terminal.
4. Run:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
5. Open http://127.0.0.1:5000

## Demo accounts
- Patient: `patient@medisync.demo` / `Patient@123`
- Doctor: `doctor@medisync.demo` / `Doctor@123`
- Admin: `admin@medisync.demo` / `Admin@123`

## OTP registration demo
Register a new account. The app prints the 6-digit OTP in the VS Code terminal where `python app.py` is running. Enter that code on the verification screen. OTP expires in 5 minutes and is limited to 5 attempts. This is a development-only delivery method; it does not send a real SMS/email.

## Important project limitations
- The AI Health page uses a simple rule-based demonstration indicator, not a trained or clinically validated medical model. It must not be used for diagnosis or treatment decisions.
- Uploaded files are stored locally in `uploads/`. This prototype is not production-ready for real patient data.
- Doctor access is broad in this classroom demo. A real deployment must enforce explicit patient consent, doctor assignment, stronger audit controls, secure storage, CSRF protection, rate limiting, HTTPS, secrets management, backups and applicable privacy/legal requirements.
- Change `MEDISYNC_SECRET` to a random secret before any deployment. Never deploy with Flask debug mode enabled.
- Demo accounts are inserted automatically for presentation purposes.

## Frontend/backend linkage
Flask serves HTML from `templates/`, CSS/JavaScript from `static/`, and handles form submissions through routes in `app.py`. Forms use `method="POST"` and named fields that Flask reads using `request.form`. `url_for()` generates route/static URLs.
