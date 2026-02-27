from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import requests
import os as os
import os
from werkzeug.utils import secure_filename

OLLAMA_URL = os.environ.get(
"OLLAMA_URL",
"http://localhost:11434/api/generate"
    )
#OLLAMA_URL = "http://100.75.119.97:30068/api/generate"
OLLAMA_MODEL = "translategemma:12b"

def translate_kn_to_en(text):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": (
            "Translate the following text from Kannada to English.\n"
            "Return ONLY the English translation.\n"
            "Do NOT include explanations.\n\n"
            f"{text}"
        ),
        "stream": False
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=60)
    return r.json()["response"].strip()


def translate_en_to_kn(text):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": (
            "Translate the following text from English to Kannada.\n"
            "IMPORTANT RULES:\n"
            "- Output MUST be in Kannada language\n"
            "- Output MUST be in Kannada script\n"
            "- DO NOT use Hindi or Devanagari script\n"
            "- DO NOT explain anything\n"
            "- ONLY return the translated sentence\n\n"
            f"{text}"
        ),
        "stream": False
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=60)
    return r.json()["response"].strip()



app = Flask(__name__)
app.secret_key = "secret123"


BASE_DIR = "/app"
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "db.sqlite3")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/upload", methods=["GET", "POST"])
def upload_document():
    if "user_id" not in session or session["role"] != "patient":
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("document")

        if file and file.filename:
            filename = secure_filename(file.filename)

            patient_folder = os.path.join(
                UPLOAD_FOLDER, f"patient_{session['user_id']}"
            )
            os.makedirs(patient_folder, exist_ok=True)

            filepath = os.path.join(patient_folder, filename)
            print("SAVING TO:", filepath)
            file.save(filepath)

            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO documents (patient_id, filename, filepath)
                VALUES (?, ?, ?)
            """, (session["user_id"], filename, filepath))
            conn.commit()
            conn.close()

        return redirect("/dashboard")

    return render_template("upload.html")

@app.route("/documents/<int:patient_id>")
def view_documents(patient_id):
    if "user_id" not in session or session["role"] != "doctor":
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT filename, filepath, uploaded_at
        FROM documents
        WHERE patient_id = ?
        ORDER BY uploaded_at DESC
    """, (patient_id,))
    docs = cur.fetchall()
    conn.close()

    return render_template("documents.html", docs=docs)


from flask import send_file

@app.route("/download")
def download_file():
    path = request.args.get("path")
    if not path.startswith(UPLOAD_FOLDER):
        return "Invalid path", 403
    return send_file(path, as_attachment=True)



@app.route("/my-documents")
def my_documents():
    if "user_id" not in session or session["role"] != "patient":
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT filename, filepath, uploaded_at
        FROM documents
        WHERE patient_id = ?
        ORDER BY uploaded_at DESC
    """, (session["user_id"],))
    docs = cur.fetchall()
    conn.close()

    return render_template("documents.html", docs=docs)



# =====================================================
# 🗄️ DATABASE
# =====================================================
def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    db = get_db()
    cur = db.cursor()
    
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            filename TEXT,
            filepath TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            password TEXT,
            role TEXT
        )
    """)

    # Appointments
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            doctor_id INTEGER,
            date TEXT,
            reason TEXT,
            status TEXT
        )
    """)

    # Messages (bilingual)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message_en TEXT,
            message_kn TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.commit()
    db.close()

# =====================================================
# 🏠 ROUTES
# =====================================================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- KANNADA AI CHAT ----------------
@app.route("/kannada-ai", methods=["GET", "POST"])
def kannada_ai():

    # Always initialize chat
    if "ai_chat" not in session:
        session["ai_chat"] = []

    if request.method == "POST":
        user_input = request.form.get("message", "").strip()

        if user_input:
            # Store user message
            session["ai_chat"].append({
                "role": "user",
                "text": user_input
            })

            try:
                payload = {
                    "model": "llama3.1:8b",
                    "prompt": (
                                    "You are a general health guidance assistant.\n"
                                    "You are NOT a doctor.\n"
                                    "Do NOT diagnose diseases.\n"
                                    "Do NOT prescribe medicines.\n"
                                    "Provide only general wellness and lifestyle advice.\n"
                                    "IMPORTANT:\n"
                                    "- Respond ONLY in Kannada language\n"
                                    "- Use Kannada script only\n"
                                    "- Do NOT use English or Hindi\n\n"
                                    f"User question: {user_input}"
                                ),
                                                "stream": False
                }

                r = requests.post(
                    OLLAMA_URL,
                    json=payload,
                    timeout=60
                )

                ai_reply = r.json().get("response", "").strip()

                # SAFETY: handle empty response
                if not ai_reply:
                    ai_reply = "ಕ್ಷಮಿಸಿ, ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಶ್ನೆಯನ್ನು ಪ್ರಯತ್ನಿಸಿ."

            except Exception:
                ai_reply = (
                    "ಕ್ಷಮಿಸಿ, AI ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. "
                    "ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ."
                )

            # Store AI response
            session["ai_chat"].append({
                "role": "ai",
                "text": ai_reply
            })

            session.modified = True

    return render_template(
        "kannada_ai.html",
        chat=session["ai_chat"]
    )



# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
            (
                request.form["name"],
                request.form["email"],
                request.form["password"],
                request.form["role"]
            )
        )
        db.commit()
        db.close()
        return redirect(url_for("login"))
    return render_template("register.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT id,name,role FROM users WHERE email=? AND password=?",
            (request.form["email"], request.form["password"])
        )
        user = cur.fetchone()
        db.close()

        if user:
            session["user_id"] = user[0]
            session["name"] = user[1]
            session["role"] = user[2]
            return redirect(url_for("dashboard"))
        return "Invalid credentials"

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ---------------- PATIENT DASHBOARD ----------------
    if session["role"] == "patient":
        cur.execute("""
                        SELECT id, name
                        FROM users
                        WHERE role = 'doctor'
                    """)
        doctors = cur.fetchall()

        conn.close()
        return render_template(
            "patient_dashboard.html",
            doctors=doctors
        )

    # ---------------- DOCTOR DASHBOARD ----------------
    if session["role"] == "doctor":
        cur.execute("""
                        SELECT id, name
                        FROM users
                        WHERE role = 'patient'
                    """)
        patients = cur.fetchall()

        conn.close()
        return render_template(
            "doctor_dashboard.html",
            patients=patients
        )

    conn.close()
    return redirect("/login")

@app.route("/ai-report", methods=["GET", "POST"])
def ai_report():
    if "user_id" not in session:
        return redirect("/login")

    result = None

    if request.method == "POST":
        file = request.files.get("image")

        if file and file.filename:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)

            import base64, requests

            with open(filepath, "rb") as img:
                image_base64 = base64.b64encode(img.read()).decode("utf-8")

            # 1️⃣ IMAGE ANALYSIS (ENGLISH)
            payload = {
                "model": "ALIENTELLIGENCE/medicalimaginganalysis",
                "prompt": (
                    "You are a medical assistant. "
                    "Explain what you see in this medical image in simple terms. "
                    "This is not a diagnosis."
                    "its default about fracture just explain"
                ),
                "images": [image_base64],
                "stream": False
            }

            try:
                r = requests.post(
                    OLLAMA_URL,
                    json=payload,
                    timeout=180
                )

                if r.status_code == 200:
                    english_result = r.json().get("response", "")

                    # 2️⃣ TRANSLATE TO KANNADA (ONLY FOR PATIENT)
                    if session.get("role") == "patient" and english_result:
                        translate_payload = {
                            "model": "translategemma:12b",
                            "prompt": f"Translate the following medical explanation to Kannada:\n\n{english_result}",
                            "stream": False
                        }

                        tr = requests.post(
                            OLLAMA_URL,
                            json=translate_payload,
                            timeout=120
                        )

                        if tr.status_code == 200:
                            result = tr.json().get("response", english_result)
                        else:
                            result = english_result
                    else:
                        result = english_result

            except Exception as e:
                print("AI ERROR:", e)
                result = "ಎಐ ಸೇವೆ ಲಭ್ಯವಿಲ್ಲ." if session.get("role") == "patient" else "AI service unavailable."

    return render_template("ai_report.html", result=result)








# ---------------- BOOK APPOINTMENT ----------------
@app.route("/book", methods=["GET", "POST"])
def book():
    if "user_id" not in session or session["role"] != "patient":
        return redirect(url_for("dashboard"))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,name FROM users WHERE role='doctor'")
    doctors = cur.fetchall()

    if request.method == "POST":
        cur.execute("""
            INSERT INTO appointments (patient_id,doctor_id,date,reason,status)
            VALUES (?,?,?,?,?)
        """, (
            session["user_id"],
            request.form["doctor"],
            request.form["date"],
            request.form["reason"],
            "Pending"
        ))
        db.commit()
        db.close()
        return redirect(url_for("dashboard"))

    db.close()
    return render_template("book_appointment.html", doctors=doctors)

# ---------------- VIEW APPOINTMENTS ----------------
@app.route("/appointments")
def appointments():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor()

    if session["role"] == "doctor":
        cur.execute("""
            SELECT a.id,u.name,a.date,a.reason,a.status
            FROM appointments a
            JOIN users u ON a.patient_id=u.id
            WHERE a.doctor_id=?
        """, (session["user_id"],))
    else:
        cur.execute("""
            SELECT a.id,u.name,a.date,a.reason,a.status
            FROM appointments a
            JOIN users u ON a.doctor_id=u.id
            WHERE a.patient_id=?
        """, (session["user_id"],))

    data = cur.fetchall()
    db.close()
    return render_template("view_appointments.html", data=data)

# ---------------- CHAT ----------------
@app.route("/chat/<int:other_id>", methods=["GET", "POST"])
def chat(other_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        raw = request.form["message"]

        

        if session["role"] == "patient":
            # Patient input = Kannada
            message_kn = raw
            message_en = translate_kn_to_en(raw)
        else:
            # Doctor input = English
            message_en = raw
            message_kn = translate_en_to_kn(raw)


        cur.execute("""
            INSERT INTO messages (sender_id,receiver_id,message_en,message_kn)
            VALUES (?,?,?,?)
        """, (session["user_id"], other_id, message_en, message_kn))
        db.commit()

    # STRICT language enforcement
    if session["role"] == "patient":
        cur.execute("""
            SELECT sender_id,message_kn
            FROM messages
            WHERE (sender_id=? AND receiver_id=?)
               OR (sender_id=? AND receiver_id=?)
            ORDER BY timestamp
        """, (session["user_id"], other_id, other_id, session["user_id"]))
    else:
        cur.execute("""
            SELECT sender_id,message_en
            FROM messages
            WHERE (sender_id=? AND receiver_id=?)
               OR (sender_id=? AND receiver_id=?)
            ORDER BY timestamp
        """, (session["user_id"], other_id, other_id, session["user_id"]))

    chats = cur.fetchall()
    cur.execute("SELECT name FROM users WHERE id=?", (other_id,))
    other_name = cur.fetchone()[0]
    db.close()

    return render_template(
        "chat.html",
        chats=chats,
        other_name=other_name
    )



if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )