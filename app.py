from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import re
import pickle
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



# ----------------------- Validation Functions -----------------------
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@(gmail|yahoo|outlook)\.com$'
    return re.match(pattern, email)

def is_valid_password(password):
    pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    return re.match(pattern, password)

app.secret_key = os.environ.get('SECRET_KEY', 'anyrandomstring')

# OTP storage: {email: {'otp': '123456', 'expires': datetime}}
otp_storage = {}

# Email configuration
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_EMAIL = os.environ.get('SMTP_EMAIL', 'kero22197@gmail.com')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'npsbotisrbnawcsb')

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(to_email, otp_code):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = 'SLR - Password Reset OTP'

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: #f9f9f9; border-radius: 10px; padding: 30px;">
                <h2 style="color: #333; text-align: center;">Password Reset</h2>
                <p style="color: #555;">You requested to reset your password. Use the OTP code below:</p>
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

        if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"\d", password) or not re.search(r"[@$!%*?&]", password):
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
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        # Validation
        if not is_valid_email(email):
            flash("Invalid email address.", "error")
            return render_template("register.html")
        if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"\d", password) or not re.search(r"[@$!%*?&]", password):
            flash("Password must be at least 8 chars, include uppercase, number and special char.", "error")
            return render_template("register.html")

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            flash("You are already registered with this email.", "error")
            return render_template("register.html")
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, hashed_password)
        )
        conn.commit()
        conn.close()
        flash("Registration successful! You can now login.", "success")
        return redirect(url_for("register"))

    return render_template("register.html")

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
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("Email or password incorrect.", "error")
            return render_template("login.html")
    
    return render_template("login.html")

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

@app.route("/words-camera")
def words_camera():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("words_camera.html")

@app.route("/text-to-sign")
def text_to_sign():
    if not session.get("user_id"):
        flash("You need to login first.", "error")
        return redirect(url_for("login"))
    return render_template("text_to_sign.html")

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
    if not data or 'text' not in data or 'lang' not in data:
        return jsonify({'error': 'Missing text or language'}), 400
    
    try:
        text = data['text'].strip()
        lang = data['lang']
        
        if not text:
            return jsonify({'error': 'Empty text'}), 400
        
        lang_map = {
            'Arabic': 'ar',
            'English': 'en',
            'French': 'fr',
            'German': 'de',
            'Spanish': 'es'
        }
        
        target_lang = lang_map.get(lang, 'ar')
        
        translator = Translator()
        result = translator.translate(text, dest=target_lang)
        
        return jsonify({
            'translation': result.text,
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
        
        lang_map = {
            'Arabic': 'ar',
            'English': 'en',
            'French': 'fr',
            'German': 'de',
            'Spanish': 'es'
        }
        
        tts_lang = lang_map.get(lang, 'en')
        
        tts = gTTS(text=text, lang=tts_lang)
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        
        return send_file(audio_buffer, mimetype='audio/mpeg')
        
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
