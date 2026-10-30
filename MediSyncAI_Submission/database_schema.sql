-- SQLite schema reference. app.py creates these tables automatically on startup.
CREATE TABLE users (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 mobile TEXT NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')),
 verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE documents (
 id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, uploaded_by INTEGER NOT NULL,
 title TEXT NOT NULL, doc_type TEXT NOT NULL, original_name TEXT NOT NULL,
 stored_name TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE medical_records (
 id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, doctor_id INTEGER NOT NULL,
 title TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE predictions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
 input_summary TEXT NOT NULL, result TEXT NOT NULL, probability REAL NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE otp_verifications (
 id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, otp_hash TEXT NOT NULL,
 expires_at INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 purpose TEXT NOT NULL, payload TEXT, created_at INTEGER NOT NULL
);
CREATE TABLE audit_logs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT NOT NULL,
 details TEXT DEFAULT '', created_at TEXT NOT NULL
);
