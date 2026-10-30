import os, sqlite3, secrets, hashlib, hmac, time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "medisync.db"
UPLOAD_DIR = BASE_DIR / "uploads"
MODEL_PATH = BASE_DIR / "models" / "diabetes_model.joblib"

saved_model = None
model = None
label_encoder = None
feature_columns = None

if MODEL_PATH.exists():
    saved_model = joblib.load(MODEL_PATH)
    model = saved_model["pipeline"]
    label_encoder = saved_model["label_encoder"]
    feature_columns = saved_model["feature_columns"]
else:
    app_model_message = (
        "Trained model not found. Run train_model.py first."
    )
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("MEDISYNC_SECRET", "dev-only-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')),
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS otp_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            purpose TEXT NOT NULL,
            payload TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            uploaded_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS medical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            notes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES users(id),
            FOREIGN KEY(doctor_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            input_summary TEXT NOT NULL,
            result TEXT NOT NULL,
            probability REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        # Demo accounts for presentation. Change passwords before any real deployment.
        demo = [
            ("Demo Patient", "patient@medisync.demo", "9000000001", "Patient@123", "patient"),
            ("Dr. Demo Sharma", "doctor@medisync.demo", "9000000002", "Doctor@123", "doctor"),
            ("System Admin", "admin@medisync.demo", "9000000003", "Admin@123", "admin"),
        ]
        for name, email, mobile, password, role in demo:
            db.execute("""INSERT OR IGNORE INTO users
                (name,email,mobile,password_hash,role,verified,created_at)
                VALUES (?,?,?,?,?,1,?)""",
                (name,email,mobile,generate_password_hash(password),role,datetime.now().isoformat(timespec="seconds")))
        db.commit()

def audit(user_id, action, details=""):
    with connect_db() as db:
        db.execute("INSERT INTO audit_logs(user_id,action,details,created_at) VALUES (?,?,?,?)",
                   (user_id, action, details[:300], datetime.now().isoformat(timespec="seconds")))
        db.commit()

def current_user():
    if "user_id" not in session:
        return None
    with connect_db() as db:
        return db.execute("SELECT id,name,email,mobile,role,verified FROM users WHERE id=?",
                          (session["user_id"],)).fetchone()

@app.before_request
def load_user():
    g.user = current_user()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for("login"))
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def otp_digest(code, salt):
    return hashlib.sha256((salt + code).encode()).hexdigest()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "patient")
        if not name or not email or not mobile or len(password) < 8 or role not in ("patient", "doctor"):
            flash("Enter all details. Password must be at least 8 characters.", "danger")
            return render_template("register.html")
        with connect_db() as db:
            if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                flash("An account with this email already exists. Please sign in.", "warning")
                return redirect(url_for("login"))
            db.execute("DELETE FROM otp_verifications WHERE email=?", (email,))
            code = f"{secrets.randbelow(1000000):06d}"
            salt = secrets.token_hex(16)
            payload = "|".join([name.replace("|"," "), mobile.replace("|"," "), generate_password_hash(password), role, salt])
            db.execute("""INSERT INTO otp_verifications(email,otp_hash,expires_at,attempts,purpose,payload,created_at)
                          VALUES (?,?,?,?,?,?,?)""",
                       (email, otp_digest(code,salt), int(time.time())+300, 0, "register", payload, int(time.time())))
            db.commit()
        # Demo delivery: print OTP in terminal. Replace with an SMS/email provider for production.
        print(f"\n[MEDISYNC DEMO OTP] {email}: {code} (expires in 5 minutes)\n")
        session["pending_email"] = email
        flash("Demo OTP generated. Check the VS Code terminal where Flask is running.", "info")
        return redirect(url_for("verify_otp"))
    return render_template("register.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("register"))
    if request.method == "POST":
        code = request.form.get("otp", "").strip()
        with connect_db() as db:
            row = db.execute("SELECT * FROM otp_verifications WHERE email=? AND purpose='register' ORDER BY id DESC LIMIT 1",
                             (email,)).fetchone()
            if not row:
                flash("OTP request not found. Please register again.", "danger")
                return redirect(url_for("register"))
            if row["expires_at"] < int(time.time()):
                flash("OTP expired. Please register again.", "danger")
                return redirect(url_for("register"))
            if row["attempts"] >= 5:
                flash("Too many attempts. Please register again.", "danger")
                return redirect(url_for("register"))
            payload = row["payload"].split("|", 4)
            salt = payload[4]
            if not hmac.compare_digest(row["otp_hash"], otp_digest(code, salt)):
                db.execute("UPDATE otp_verifications SET attempts=attempts+1 WHERE id=?", (row["id"],))
                db.commit()
                flash("Incorrect OTP. Please try again.", "danger")
                return render_template("otp.html", email=email)
            name, mobile, password_hash, role, _ = payload
            db.execute("""INSERT INTO users(name,email,mobile,password_hash,role,verified,created_at)
                          VALUES (?,?,?,?,?,1,?)""",
                       (name,email,mobile,password_hash,role,datetime.now().isoformat(timespec="seconds")))
            user_id = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
            db.execute("DELETE FROM otp_verifications WHERE email=?", (email,))
            db.commit()
        session.clear()
        session["user_id"] = user_id
        audit(user_id, "register", "Account verified by demo OTP")
        flash("Your account is verified and ready.", "success")
        return redirect(url_for("dashboard"))
    return render_template("otp.html", email=email)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password) and user["verified"]:
            session.clear()
            session["user_id"] = user["id"]
            audit(user["id"], "login", "Successful login")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    if g.user:
        audit(g.user["id"], "logout", "User logged out")
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = g.user
    with connect_db() as db:
        if user["role"] == "patient":
            docs = db.execute("SELECT * FROM documents WHERE patient_id=? ORDER BY id DESC LIMIT 5", (user["id"],)).fetchall()
            preds = db.execute("SELECT * FROM predictions WHERE patient_id=? ORDER BY id DESC LIMIT 3", (user["id"],)).fetchall()
            doc_count = db.execute("SELECT COUNT(*) n FROM documents WHERE patient_id=?", (user["id"],)).fetchone()["n"]
            record_count = db.execute("SELECT COUNT(*) n FROM medical_records WHERE patient_id=?", (user["id"],)).fetchone()["n"]
            return render_template("patient_dashboard.html", docs=docs, preds=preds, doc_count=doc_count, record_count=record_count)
        if user["role"] == "doctor":
            patients = db.execute("""SELECT id,name,email FROM users WHERE role='patient' ORDER BY name""").fetchall()
            docs = db.execute("""SELECT d.*,u.name patient_name FROM documents d JOIN users u ON u.id=d.patient_id ORDER BY d.id DESC LIMIT 8""").fetchall()
            return render_template("doctor_dashboard.html", patients=patients, docs=docs)
        users = db.execute("SELECT id,name,email,role,created_at FROM users ORDER BY id DESC").fetchall()
        logs = db.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 12").fetchall()
        counts = {
            "users": db.execute("SELECT COUNT(*) n FROM users").fetchone()["n"],
            "patients": db.execute("SELECT COUNT(*) n FROM users WHERE role='patient'").fetchone()["n"],
            "doctors": db.execute("SELECT COUNT(*) n FROM users WHERE role='doctor'").fetchone()["n"],
            "documents": db.execute("SELECT COUNT(*) n FROM documents").fetchone()["n"],
        }
    return render_template("admin_dashboard.html", users=users, logs=logs, counts=counts)

@app.route("/documents", methods=["GET", "POST"])
@login_required
def documents():
    if request.method == "POST":
        if g.user["role"] == "admin":
            flash("Admin accounts cannot upload patient documents.", "warning")
            return redirect(url_for("documents"))
        file = request.files.get("file")
        title = request.form.get("title", "").strip()
        doc_type = request.form.get("doc_type", "Other")
        notes = request.form.get("notes", "").strip()
        patient_id = g.user["id"]
        if g.user["role"] == "doctor":
            patient_id = request.form.get("patient_id", type=int)
            with connect_db() as db:
                p = db.execute("SELECT id FROM users WHERE id=? AND role='patient'", (patient_id,)).fetchone() if patient_id else None
            if not p:
                flash("Choose a valid patient.", "danger")
                return redirect(url_for("documents"))
        if not file or not file.filename or not allowed_file(file.filename) or not title:
            flash("Add a title and a PDF, PNG, JPG or JPEG file (max 8 MB).", "danger")
            return redirect(url_for("documents"))
        original = secure_filename(file.filename)
        stored = secrets.token_hex(16) + "." + original.rsplit(".",1)[1].lower()
        file.save(UPLOAD_DIR / stored)
        with connect_db() as db:
            db.execute("""INSERT INTO documents(patient_id,uploaded_by,title,doc_type,original_name,stored_name,notes,created_at)
                          VALUES (?,?,?,?,?,?,?,?)""",
                       (patient_id,g.user["id"],title,doc_type,original,stored,notes,datetime.now().isoformat(timespec="seconds")))
            db.commit()
        audit(g.user["id"], "document_upload", f"{title} for patient {patient_id}")
        flash("Document uploaded successfully.", "success")
        return redirect(url_for("documents"))
    with connect_db() as db:
        if g.user["role"] == "patient":
            docs = db.execute("SELECT d.*,u.name uploader FROM documents d JOIN users u ON u.id=d.uploaded_by WHERE d.patient_id=? ORDER BY d.id DESC", (g.user["id"],)).fetchall()
            patients = []
        elif g.user["role"] == "doctor":
            docs = db.execute("SELECT d.*,u.name uploader,p.name patient_name FROM documents d JOIN users u ON u.id=d.uploaded_by JOIN users p ON p.id=d.patient_id ORDER BY d.id DESC", ()).fetchall()
            patients = db.execute("SELECT id,name FROM users WHERE role='patient' ORDER BY name").fetchall()
        else:
            docs = db.execute("SELECT d.*,u.name uploader,p.name patient_name FROM documents d JOIN users u ON u.id=d.uploaded_by JOIN users p ON p.id=d.patient_id ORDER BY d.id DESC", ()).fetchall()
            patients = []
    return render_template("documents.html", docs=docs, patients=patients)

@app.route("/document/<int:doc_id>/file")
@login_required
def document_file(doc_id):
    with connect_db() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        abort(404)
    if g.user["role"] == "patient" and doc["patient_id"] != g.user["id"]:
        abort(403)
    if g.user["role"] == "doctor":
        # Demo access to records is permitted to authenticated doctors; real deployment needs explicit consent/assignment.
        pass
    if g.user["role"] == "admin":
        pass
    audit(g.user["id"], "document_view", f"Document {doc_id}")
    return send_from_directory(UPLOAD_DIR, doc["stored_name"], as_attachment=False, download_name=doc["original_name"])

@app.route("/timeline")
@login_required
def timeline():
    if g.user["role"] != "patient":
        flash("The personal timeline is available for patient accounts.", "info")
        return redirect(url_for("dashboard"))
    with connect_db() as db:
        docs = db.execute("SELECT * FROM documents WHERE patient_id=? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
        records = db.execute("SELECT * FROM medical_records WHERE patient_id=? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
        preds = db.execute("SELECT * FROM predictions WHERE patient_id=? ORDER BY created_at DESC", (g.user["id"],)).fetchall()
    items = sorted(list(docs)+list(records)+list(preds), key=lambda x: x["created_at"], reverse=True)
    return render_template("timeline.html", items=items)


@app.route("/ai-health", methods=["GET", "POST"])
@role_required("patient")
def ai_health():
    result = None
    error = None

    if request.method == "POST":
        if model is None:
            error = "The trained model is unavailable. Please train it first."
            return render_template(
                "ai_health.html",
                result=None,
                error=error
            )

        try:
            age = int(request.form.get("age", ""))

            if not 1 <= age <= 120:
                raise ValueError("Enter an age between 1 and 120.")

            gender = request.form.get("gender", "")
            if gender not in ("Male", "Female"):
                raise ValueError("Please select a valid gender.")

            symptoms = [
                "polyuria",
                "polydipsia",
                "sudden_weight_loss",
                "weakness",
                "polyphagia",
                "genital_thrush",
                "visual_blurring",
                "itching",
                "irritability",
                "delayed_healing",
                "partial_paresis",
                "muscle_stiffness",
                "alopecia",
                "obesity"
            ]

            values = {
                "age": age,
                "gender": gender
            }

            for field in symptoms:
                value = request.form.get(field, "")

                if value not in ("Yes", "No"):
                    raise ValueError(
                        "Please answer every symptom question."
                    )

                values[field] = value

            import re

            def normalize(name):
                return re.sub(
                    r"[^a-z0-9]+",
                    "_",
                    name.strip().lower()
                ).strip("_")

            normalized_values = {
                normalize(key): value
                for key, value in values.items()
            }

            row = {}

            for column in feature_columns:
                key = normalize(column)

                if key not in normalized_values:
                    raise ValueError(
                        "The form does not match the trained model "
                        f"feature: {column}"
                    )

                row[column] = normalized_values[key]

            input_data = pd.DataFrame(
                [row],
                columns=feature_columns
            )

            prediction = model.predict(input_data)[0]

            predicted_label = str(
                label_encoder.inverse_transform(
                    [prediction]
                )[0]
            )

            confidence = None

            if hasattr(model, "predict_proba"):
                probabilities = model.predict_proba(input_data)[0]
                confidence = float(max(probabilities))

            result = {
                "level": predicted_label,
                "confidence": (
                    round(confidence * 100, 2)
                    if confidence is not None
                    else None
                )
            }

            summary = (
                f"Age={age}, Gender={gender}, "
                + ", ".join(
                    f"{field}={values[field]}"
                    for field in symptoms
                )
            )

            with connect_db() as db:
                db.execute(
                    """
                    INSERT INTO predictions
                    (patient_id, input_summary, result,
                     probability, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        g.user["id"],
                        summary,
                        predicted_label,
                        confidence if confidence is not None else 0.0,
                        datetime.now().isoformat(timespec="seconds")
                    )
                )
                db.commit()

            audit(
                g.user["id"],
                "ai_health_prediction",
                "Trained model prediction generated"
            )

        except ValueError as exc:
            error = str(exc)

        except Exception:
            app.logger.exception("Model prediction failed")
            error = "Unable to generate the prediction. Check the model configuration."

    return render_template(
        "ai_health.html",
        result=result,
        error=error
    )

@app.route("/doctor/patient/<int:patient_id>", methods=["GET", "POST"])
@role_required("doctor")
def patient_detail(patient_id):
    with connect_db() as db:
        patient = db.execute("SELECT id,name,email,mobile FROM users WHERE id=? AND role='patient'", (patient_id,)).fetchone()
        if not patient:
            abort(404)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            notes = request.form.get("notes", "").strip()
            if title and notes:
                db.execute("INSERT INTO medical_records(patient_id,doctor_id,title,notes,created_at) VALUES (?,?,?,?,?)",
                           (patient_id,g.user["id"],title,notes,datetime.now().isoformat(timespec="seconds")))
                db.commit()
                audit(g.user["id"], "doctor_note_added", f"Patient {patient_id}: {title}")
                flash("Clinical note saved.", "success")
                return redirect(url_for("patient_detail", patient_id=patient_id))
            flash("Enter a title and note.", "danger")
        records = db.execute("""SELECT m.*,u.name doctor_name FROM medical_records m JOIN users u ON u.id=m.doctor_id WHERE m.patient_id=? ORDER BY m.id DESC""", (patient_id,)).fetchall()
        docs = db.execute("SELECT * FROM documents WHERE patient_id=? ORDER BY id DESC", (patient_id,)).fetchall()
    return render_template("patient_detail.html", patient=patient, records=records, docs=docs)

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page or record could not be found."), 404

@app.errorhandler(413)
def too_large(_):
    flash("File is too large. Maximum upload size is 8 MB.", "danger")
    return redirect(url_for("documents"))

init_db()

if __name__ == "__main__":
    app.run(debug=True)
