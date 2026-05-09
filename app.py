from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import re
import pickle
import json
import numpy as np
from googletrans import Translator
from gtts import gTTS
import io
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import base64

app = Flask(__name__)

# Load AI Model for Letters (مدرب على hand landmarks)
with open("AI  model/model.p", "rb") as f:
    model_dict = pickle.load(f)
    model = model_dict['model']

# Labels mapping for letters
labels_dict = {
    0: 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H', 8: 'I', 9: 'J',
    10: 'K', 11: 'L', 12: 'M', 13: 'N', 14: 'O', 15: 'P', 16: 'Q', 17: 'R', 18: 'S',
    19: 'T', 20: 'U', 21: 'V', 22: 'W', 23: 'X', 24: 'Y', 25: 'Z', 26: 'del',
    27: 'nothing', 28: 'space'
}



# ----------------------- Load Word-to-Videos Mapping -----------------------
# Use DigitalOcean Spaces CDN for videos when configured.
VIDEO_BASE_URL = os.environ.get('VIDEO_BASE_URL', 'https://grad.fra1.cdn.digitaloceanspaces.com/videos').strip()
if VIDEO_BASE_URL:
    VIDEO_BASE_URL = VIDEO_BASE_URL.rstrip('/')
VIDEOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AI  model', 'videos')
word_videos_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AI  model', 'word_videos_map.json')
with open(word_videos_map_path, 'r') as f:
    WORD_VIDEOS_MAP = json.load(f)
print(f"Word-to-videos mapping loaded: {len(WORD_VIDEOS_MAP)} words with videos")

@app.context_processor
def inject_video_base_url():
    return {'video_base_url': VIDEO_BASE_URL}

# ----------------------- Validation Functions -----------------------
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@(gmail|yahoo|outlook)\.com$'
    return re.match(pattern, email)

def is_valid_password(password):
    pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&$#])[A-Za-z\d@$!%*?&$#]{8,}$'
    return re.match(pattern, password)

app.secret_key = os.environ.get('SECRET_KEY', 'anyrandomstring')

# OTP storage: {email: {'otp': '123456', 'expires': datetime}}
otp_storage = {}

SUPPORTED_LANGUAGE_CODES = {'ar', 'en', 'fr', 'de', 'es'}
LANGUAGE_ALIASES = {
    'arabic': 'ar',
    'ar': 'ar',
    'ar-sa': 'ar',
    'العربية': 'ar',
    'english': 'en',
    'en': 'en',
    'en-us': 'en',
    'francais': 'fr',
    'french': 'fr',
    'fr': 'fr',
    'fr-fr': 'fr',
    'allemand': 'de',
    'german': 'de',
    'de': 'de',
    'de-de': 'de',
    'spanish': 'es',
    'espanol': 'es',
    'español': 'es',
    'es': 'es',
    'es-es': 'es',
}

COMMON_TO_EN_FALLBACK = {
    'bonjour': 'hello',
    'salut': 'hello',
    'merci': 'thanks',
    'au revoir': 'goodbye',
    'hola': 'hello',
    'gracias': 'thanks',
    'hallo': 'hello',
    'danke': 'thanks',
    'مرحبا': 'hello',
    'اهلا': 'hello',
    'أهلا': 'hello',
}

SEARCH_WORD_ALIASES = {
    'hi': 'hello',
    'hey': 'hello',
    'greetings': 'hello',
    'thanks': 'thankyou',
    'thank': 'thankyou',
    'goodbye': 'bye',
}


def normalize_language_code(lang_value, default='en', allow_auto=False):
    """Normalize language input from UI labels or locale codes to a 2-letter code."""
    if lang_value is None:
        return 'auto' if allow_auto and default == 'auto' else default

    raw = str(lang_value).strip().lower()
    if not raw:
        return 'auto' if allow_auto and default == 'auto' else default

    if allow_auto and raw == 'auto':
        return 'auto'

    if raw in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[raw]

    if raw in SUPPORTED_LANGUAGE_CODES:
        return raw

    if '-' in raw or '_' in raw:
        base = raw.replace('_', '-').split('-')[0]
        if base in SUPPORTED_LANGUAGE_CODES:
            return base

    return default


def resolve_search_word(word):
    """Map equivalent words to canonical keys that exist in WORD_VIDEOS_MAP."""
    if not word:
        return word

    mapped = SEARCH_WORD_ALIASES.get(word, word)
    if mapped in WORD_VIDEOS_MAP:
        return mapped
    if word in WORD_VIDEOS_MAP:
        return word
    return mapped

# Email configuration
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_EMAIL = os.environ.get('SMTP_EMAIL', 'slr.sign.language@gmail.com')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'gtcygfndecwupgxm')

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(to_email, otp_code, purpose='reset'):
    try:
        msg = MIMEMultipart()
        msg['From'] = f'SLR <{SMTP_EMAIL}>'
        msg['To'] = to_email

        if purpose == 'register':
            msg['Subject'] = 'SLR - Email Verification'
            title = 'Email Verification'
            desc = 'Please verify your email address to complete registration. Use the OTP code below:'
        else:
            msg['Subject'] = 'SLR - Password Reset OTP'
            title = 'Password Reset'
            desc = 'You requested to reset your password. Use the OTP code below:'

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: #f9f9f9; border-radius: 10px; padding: 30px;">
                <h2 style="color: #333; text-align: center;">{title}</h2>
                <p style="color: #555;">{desc}</p>
                <div style="text-align: center; margin: 25px 0;">
                    <span style="font-size: 32px; font-weight: bold; color: #4f46e5; letter-spacing: 8px; background: #e8e5ff; padding: 15px 30px; border-radius: 10px;">{otp_code}</span>
                </div>
                <p style="color: #888; font-size: 13px; text-align: center;">This code expires in 5 minutes.</p>
                <p style="color: #888; font-size: 13px; text-align: center;">If you didn't request this, please ignore this email.</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False

# ----------------------- Database -----------------------
def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db_schema():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            correct_answers INTEGER NOT NULL,
            wrong_answers INTEGER NOT NULL,
            score_percent INTEGER NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            is_favorite INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Backward-compatible migration for existing databases.
    cursor.execute("PRAGMA table_info(learning_history)")
    learning_cols = [row[1] for row in cursor.fetchall()]
    if 'is_favorite' not in learning_cols:
        cursor.execute('ALTER TABLE learning_history ADD COLUMN is_favorite INTEGER DEFAULT 0')

    conn.commit()
    conn.close()


ensure_db_schema()

# ----------------------- AI Prediction Function -----------------------
def model_predict(landmarks):
    # تحويل landmarks لمصفوفة 1D قبل التنبؤ
    landmarks_array = np.array(landmarks).reshape(1, -1)
    prediction = model.predict(landmarks_array)
    return prediction[0]

# ----------------------- Routes -----------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about_page():
    return render_template("about.html")

@app.route("/forget-password", methods=["GET", "POST"])
def forget_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your email.", "error")
            return render_template("forgetpass.html")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            flash("No account found with this email.", "error")
            return render_template("forgetpass.html")

        otp_code = generate_otp()
        otp_storage[email] = {
            'otp': otp_code,
            'expires': datetime.now() + timedelta(minutes=5)
        }

        if send_otp_email(email, otp_code):
            flash("OTP sent to your email!", "success")
            session['reset_email'] = email
            return redirect(url_for('verify_otp'))
        else:
            flash("Failed to send OTP. Please try again.", "error")
            return render_template("forgetpass.html")

    return render_template("forgetpass.html")

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get('reset_email')
    if not email:
        flash("Please request OTP first.", "error")
        return redirect(url_for('forget_password'))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if email not in otp_storage:
            flash("OTP expired. Please request a new one.", "error")
            return redirect(url_for('forget_password'))

        stored = otp_storage[email]
        if datetime.now() > stored['expires']:
            del otp_storage[email]
            flash("OTP expired. Please request a new one.", "error")
            return redirect(url_for('forget_password'))

        if entered_otp == stored['otp']:
            session['otp_verified'] = True
            del otp_storage[email]
            return redirect(url_for('reset_password'))
        else:
            flash("Invalid OTP. Please try again.", "error")
            return render_template("verify_otp.html", email=email)

    return render_template("verify_otp.html", email=email)

@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    email = session.get('reset_email')
    if not email:
        flash("Please request OTP first.", "error")
        return redirect(url_for('forget_password'))

    otp_code = generate_otp()
    otp_storage[email] = {
        'otp': otp_code,
        'expires': datetime.now() + timedelta(minutes=5)
    }

    if send_otp_email(email, otp_code, purpose='reset'):
        flash("A new OTP has been sent to your email.", "success")
    else:
        flash("Failed to resend OTP. Please try again.", "error")

    return redirect(url_for('verify_otp'))

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = session.get('reset_email')
    verified = session.get('otp_verified')
    if not email or not verified:
        flash("Please verify OTP first.", "error")
        return redirect(url_for('forget_password'))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            flash("Passwords don't match.", "error")
            return render_template("reset_password.html")

        if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"\d", password) or not re.search(r"[@$!%*?&#]", password):
            flash("Password must be at least 8 chars, include uppercase, number and special char.", "error")
            return render_template("reset_password.html")

        hashed = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE email = ?", (hashed, email))
        conn.commit()
        conn.close()

        session.pop('reset_email', None)
        session.pop('otp_verified', None)
        flash("Password reset successfully! Please login.", "success")
        return redirect(url_for('login'))

    return render_template("reset_password.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        # Clear stale pending registration data before starting a new validation flow.
        session.pop('reg_username', None)
        session.pop('reg_email', None)
        session.pop('reg_password', None)

        # Validation
        if not username:
            flash("Username is required.", "error")
            return render_template("register.html", username=username, email=email)
        if not is_valid_email(email):
            flash("Invalid email address.", "error")
            return render_template("register.html", username=username, email=email)

        if not is_valid_password(password):
            flash("Password must be at least 8 chars, include uppercase, number and special char.", "error")
            return render_template("register.html", username=username, email=email)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("You are already registered with this email.", "error")
            return render_template("register.html", username=username, email=email)
        conn.close()

        # Invalidate any previous OTP for this email; only keep the latest valid registration code.
        otp_storage.pop(email, None)

        # Send OTP for email verification
        otp_code = generate_otp()
        otp_storage[email] = {
            'otp': otp_code,
            'expires': datetime.now() + timedelta(minutes=5)
        }

        if send_otp_email(email, otp_code, purpose='register'):
            # Store registration data in session temporarily
            session['reg_username'] = username
            session['reg_email'] = email
            session['reg_password'] = generate_password_hash(password)
            flash("Verification code sent to your email!", "success")
            return redirect(url_for('verify_register'))
        else:
            flash("Failed to send verification email. Please try again.", "error")
            return render_template("register.html", username=username, email=email)

    return render_template("register.html", username="", email="")

@app.route("/verify-register", methods=["GET", "POST"])
def verify_register():
    email = session.get('reg_email')
    if not email:
        flash("Please register first.", "error")
        return redirect(url_for('register'))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if email not in otp_storage:
            flash("OTP expired. Please register again.", "error")
            return redirect(url_for('register'))

        stored = otp_storage[email]
        if datetime.now() > stored['expires']:
            del otp_storage[email]
            flash("OTP expired. Please register again.", "error")
            return redirect(url_for('register'))

        if entered_otp == stored['otp']:
            del otp_storage[email]
            # Now save the user to the database
            username = session.get('reg_username')
            hashed_password = session.get('reg_password')
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
            conn.close()
            # Clean up session
            session.pop('reg_username', None)
            session.pop('reg_email', None)
            session.pop('reg_password', None)
            flash("Email verified! Registration successful. You can now login.", "success")
            return redirect(url_for('login'))
        else:
            flash("Invalid OTP. Please try again.", "error")
            return render_template("verify_register.html", email=email)

    return render_template("verify_register.html", email=email)

@app.route("/resend-register-otp", methods=["POST"])
def resend_register_otp():
    email = session.get('reg_email')
    if not email:
        flash("Please register first.", "error")
        return redirect(url_for('register'))

    otp_code = generate_otp()
    otp_storage[email] = {
        'otp': otp_code,
        'expires': datetime.now() + timedelta(minutes=5)
    }

    if send_otp_email(email, otp_code, purpose='register'):
        flash("A new verification code has been sent to your email.", "success")
    else:
        flash("Failed to resend verification code. Please try again.", "error")

    return redirect(url_for('verify_register'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["email"] = user["email"]
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("Email or password incorrect.", "error")
            return render_template("login.html", email=email)
    
    return render_template("login.html", email="")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/camera")
def open_camera():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("camera.html")

@app.route("/text-to-sign")
def text_to_sign():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("text_to_sign.html")

@app.route("/learn-sign")
def learn_sign():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("learn_sign.html", words=sorted(WORD_VIDEOS_MAP.keys()))

@app.route('/search_videos', methods=['POST'])
def search_videos():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400

    text = data['text'].strip().lower()
    if not text:
        return jsonify({'error': 'Empty text'}), 400

    words = text.split()
    results = []
    for word in words:
        word_clean = re.sub(r'[^a-z]', '', word)
        if not word_clean:
            continue
        search_word = resolve_search_word(word_clean)
        videos = WORD_VIDEOS_MAP.get(search_word, [])
        results.append({
            'word': search_word,
            'found': len(videos) > 0,
            'video_count': len(videos),
            'video_id': videos[0] if videos else None
        })

    return jsonify({'results': results, 'status': 'success'})

@app.route('/sign_video/<video_id>')
def serve_sign_video(video_id):
    if not session.get("user_id"):
        return jsonify({'error': 'Not authenticated'}), 401

    safe_id = re.sub(r'[^0-9]', '', video_id)
    if not safe_id:
        return jsonify({'error': 'Invalid video ID'}), 400

    # Prefer CDN URL when configured; fallback to local file.
    if VIDEO_BASE_URL:
        base_url = VIDEO_BASE_URL.rstrip('/')
        return redirect(f"{base_url}/{safe_id}.mp4")

    video_path = os.path.join(VIDEOS_DIR, f'{safe_id}.mp4')
    if not os.path.isfile(video_path):
        return jsonify({'error': 'Video not found'}), 404

    return send_file(video_path, mimetype='video/mp4')

@app.route('/word_videos/<word>')
def get_word_videos(word):
    word_clean = re.sub(r'[^a-z]', '', word.lower())
    search_word = resolve_search_word(word_clean)
    videos = WORD_VIDEOS_MAP.get(search_word, [])
    return jsonify({'word': search_word, 'videos': videos, 'count': len(videos)})

# ----------------------- Voice to Sign Route -----------------------
@app.route("/voice-to-sign")
def voice_to_sign():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("voice_to_sign.html", words=sorted(WORD_VIDEOS_MAP.keys()))

# ----------------------- Sign Quiz Routes -----------------------
@app.route("/sign-quiz")
def sign_quiz():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    # Start a fresh tracked attempt each time quiz page is opened.
    session.pop('active_quiz_result_id', None)
    return render_template("sign_quiz.html")

@app.route('/quiz_question', methods=['GET'])
def quiz_question():
    if not session.get("user_id"):
        return jsonify({'error': 'Not authenticated'}), 401

    # Pick a random word that has videos
    words_with_videos = [w for w, vids in WORD_VIDEOS_MAP.items() if len(vids) > 0]
    if len(words_with_videos) < 4:
        return jsonify({'error': 'Not enough words'}), 500

    correct_word = random.choice(words_with_videos)
    video_id = random.choice(WORD_VIDEOS_MAP[correct_word])

    # Generate 3 wrong options
    wrong_words = random.sample([w for w in words_with_videos if w != correct_word], 3)
    options = wrong_words + [correct_word]
    random.shuffle(options)

    return jsonify({
        'video_id': video_id,
        'correct': correct_word,
        'options': options,
        'status': 'success'
    })

@app.route('/quiz_pick_sign', methods=['GET'])
def quiz_pick_sign():
    if not session.get("user_id"):
        return jsonify({'error': 'Not authenticated'}), 401

    words_with_videos = [w for w, vids in WORD_VIDEOS_MAP.items() if len(vids) > 0]
    if len(words_with_videos) < 4:
        return jsonify({'error': 'Not enough words'}), 500

    correct_word = random.choice(words_with_videos)
    correct_video = random.choice(WORD_VIDEOS_MAP[correct_word])

    wrong_words = random.sample([w for w in words_with_videos if w != correct_word], 3)
    wrong_videos = [random.choice(WORD_VIDEOS_MAP[w]) for w in wrong_words]

    options = [{'video_id': correct_video, 'word': correct_word}]
    for w, v in zip(wrong_words, wrong_videos):
        options.append({'video_id': v, 'word': w})
    random.shuffle(options)

    return jsonify({
        'word': correct_word,
        'correct_video': correct_video,
        'options': options,
        'status': 'success'
    })

# ----------------------- Quiz Results Routes -----------------------
@app.route('/save_quiz_progress', methods=['POST'])
def save_quiz_progress():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    total = int(data.get('total', 0))
    correct = int(data.get('correct', 0))
    wrong = int(data.get('wrong', 0))

    if total < 0 or correct < 0 or wrong < 0:
        return jsonify({'error': 'Invalid counters'}), 400

    score_pct = round((correct / total) * 100) if total > 0 else 0
    user_id = session['user_id']
    active_id = session.get('active_quiz_result_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    if active_id:
        cursor.execute('SELECT id FROM quiz_results WHERE id = ? AND user_id = ?', (active_id, user_id))
        exists = cursor.fetchone()
        if exists:
            cursor.execute(
                'UPDATE quiz_results SET total_questions = ?, correct_answers = ?, wrong_answers = ?, score_percent = ?, played_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?',
                (total, correct, wrong, score_pct, active_id, user_id)
            )
        else:
            active_id = None

    if not active_id:
        cursor.execute(
            'INSERT INTO quiz_results (user_id, total_questions, correct_answers, wrong_answers, score_percent) VALUES (?, ?, ?, ?, ?)',
            (user_id, total, correct, wrong, score_pct)
        )
        active_id = cursor.lastrowid

    conn.commit()
    conn.close()

    session['active_quiz_result_id'] = active_id
    return jsonify({'status': 'saved', 'id': active_id})

@app.route('/save_quiz_result', methods=['POST'])
def save_quiz_result():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    total = int(data.get('total', 0))
    correct = int(data.get('correct', 0))
    wrong = int(data.get('wrong', 0))
    score_pct = round((correct / total) * 100) if total > 0 else 0
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO quiz_results (user_id, total_questions, correct_answers, wrong_answers, score_percent) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], total, correct, wrong, score_pct)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'saved'})

@app.route('/quiz_history')
def quiz_history():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT total_questions, correct_answers, wrong_answers, score_percent, played_at FROM quiz_results WHERE user_id = ? ORDER BY played_at DESC LIMIT 10',
        (session['user_id'],)
    )
    rows = cursor.fetchall()
    conn.close()
    history = []
    for r in rows:
        history.append({
            'total': r['total_questions'],
            'correct': r['correct_answers'],
            'wrong': r['wrong_answers'],
            'score': r['score_percent'],
            'date': r['played_at']
        })
    return jsonify({'history': history})


@app.route('/save_learning', methods=['POST'])
def save_learning():
    if not session.get('user_id'):
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    source = (data.get('source') or 'text-to-sign').strip().lower()
    is_favorite = 1 if data.get('favorite') else 0

    if not content:
        return jsonify({'error': 'No content provided'}), 400

    if len(content) > 300:
        return jsonify({'error': 'Content is too long'}), 400

    allowed_sources = {'text-to-sign', 'learn-sign', 'voice-to-sign', 'camera'}
    if source not in allowed_sources:
        source = 'text-to-sign'

    conn = get_db_connection()
    cursor = conn.cursor()

    # Prevent duplicated rows for the same item; auto-save refreshes timestamp.
    cursor.execute(
        'SELECT id, is_favorite FROM learning_history WHERE user_id = ? AND source = ? AND content = ?',
        (session['user_id'], source, content)
    )
    existing = cursor.fetchone()

    if existing:
        final_favorite = 1 if (existing['is_favorite'] or is_favorite) else 0
        cursor.execute(
            'UPDATE learning_history SET is_favorite = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?',
            (final_favorite, existing['id'])
        )
    else:
        cursor.execute(
            'INSERT INTO learning_history (user_id, source, content, is_favorite) VALUES (?, ?, ?, ?)',
            (session['user_id'], source, content, is_favorite)
        )

    conn.commit()
    conn.close()

    return jsonify({'status': 'saved', 'favorite': bool(is_favorite)})


@app.route('/history')
def history_page():
    if not session.get('user_id'):
        flash("You need to login first.", "error")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT total_questions, correct_answers, wrong_answers, score_percent, played_at '
        'FROM quiz_results WHERE user_id = ? ORDER BY played_at DESC LIMIT 30',
        (session['user_id'],)
    )
    quiz_rows = cursor.fetchall()

    cursor.execute(
        'SELECT source, content, is_favorite, created_at FROM learning_history '
        'WHERE user_id = ? ORDER BY created_at DESC LIMIT 100',
        (session['user_id'],)
    )
    learn_rows = cursor.fetchall()
    conn.close()

    quiz_history_data = []
    for r in quiz_rows:
        quiz_history_data.append({
            'total': r['total_questions'],
            'correct': r['correct_answers'],
            'wrong': r['wrong_answers'],
            'score': r['score_percent'],
            'date': r['played_at']
        })

    learning_history_data = []
    for r in learn_rows:
        learning_history_data.append({
            'source': r['source'],
            'content': r['content'],
            'is_favorite': bool(r['is_favorite']),
            'date': r['created_at']
        })

    return render_template(
        'history.html',
        quiz_history=quiz_history_data,
        learning_history=learning_history_data
    )

# ----------------------- Predict Route -----------------------
@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()
    if not data or 'landmarks' not in data:
        return jsonify({'error': 'No landmarks provided'}), 400
    
    try:
        landmarks = data['landmarks']
        
        # التأكد من طول الـ landmarks (21 نقطة × 2 إحداثيات normalized)
        if len(landmarks) != 42:
            print(f"Warning: Expected 42 values, got {len(landmarks)}")
            if len(landmarks) > 42:
                landmarks = landmarks[:42]
            else:
                landmarks = landmarks + [0] * (42 - len(landmarks))
        
        # تحويل إلى numpy array
        landmarks_array = np.array(landmarks, dtype=np.float32).reshape(1, -1)
        
        # إجراء التنبؤ
        prediction = model.predict(landmarks_array)
        
        # تحويل النتيجة للحرف باستخدام labels_dict
        predicted_label = int(prediction[0])
        result = labels_dict.get(predicted_label, "Unknown")
        
        print(f"Prediction result: {result} (label: {predicted_label})")
        
        return jsonify({'prediction': result, 'status': 'success'})
        
    except Exception as e:
        print(f"Prediction error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ----------------------- Translate Route -----------------------
@app.route('/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'Missing text'}), 400
    
    try:
        text = data['text'].strip()
        lang = data.get('lang', 'en')
        src_lang = data.get('src', 'auto')
        
        if not text:
            return jsonify({'error': 'Empty text'}), 400
        
        target_lang = normalize_language_code(lang, default='en')
        source_lang = normalize_language_code(src_lang, default='auto', allow_auto=True)

        translator = Translator()
        translated_text = ''

        for _ in range(3):
            try:
                result = translator.translate(text, src=source_lang, dest=target_lang)
                translated_text = (result.text or '').strip()
                if translated_text:
                    break
            except Exception:
                continue

        # If explicit source fails, retry with auto-detect as fallback.
        if not translated_text and source_lang != 'auto':
            for _ in range(2):
                try:
                    result = translator.translate(text, src='auto', dest=target_lang)
                    translated_text = (result.text or '').strip()
                    if translated_text:
                        break
                except Exception:
                    continue

        # Fallback for short Arabic inputs where auto-detect can be unstable.
        if translated_text == text and re.search(r'[\u0600-\u06FF]', text) and target_lang != 'ar':
            try:
                result = translator.translate(text, src='ar', dest=target_lang)
                translated_text = (result.text or '').strip() or translated_text
            except Exception:
                pass

        if target_lang == 'en' and source_lang != 'en' and translated_text.strip().lower() == text.strip().lower():
            translated_text = COMMON_TO_EN_FALLBACK.get(text.strip().lower(), translated_text)

        if not translated_text:
            return jsonify({'error': 'Translation service unavailable. Try again.'}), 503
        
        return jsonify({
            'translation': translated_text,
            'target_lang': target_lang,
            'source_lang': source_lang,
            'status': 'success'
        })
        
    except Exception as e:
        print(f"Translation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ----------------------- TTS Route -----------------------
@app.route('/tts', methods=['POST'])
def text_to_speech():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'Missing text'}), 400
    
    try:
        text = data['text'].strip()
        lang = data.get('lang', 'en')
        
        if not text:
            return jsonify({'error': 'Empty text'}), 400
        
        tts_lang = normalize_language_code(lang, default='en')

        last_error = None
        audio_buffer = None
        for _ in range(2):
            try:
                tts = gTTS(text=text, lang=tts_lang)
                audio_buffer = io.BytesIO()
                tts.write_to_fp(audio_buffer)
                audio_buffer.seek(0)
                break
            except Exception as err:
                last_error = err
                audio_buffer = None

        if audio_buffer is None:
            raise RuntimeError(last_error or 'TTS generation failed')
        
        return send_file(audio_buffer, mimetype='audio/mpeg')
        
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.static_folder, 'images', 'logo.png'), mimetype='image/png')

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port, debug=True, use_reloader=False)
