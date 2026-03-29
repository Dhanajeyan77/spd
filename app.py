import os
import base64
import requests
import json
import smtplib
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret"

# --- CONFIGURATION ---
MAIL_ID = "padmamunishdhanajeyan@gmail.com"
MAIL_PW = "iibl iezd nvac yxqr" 
REPORT_DIR = 'reports'
USER_DB = 'users.json'

# Ensure directories exist
if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)

# --- DATABASE HELPERS ---
def load_db():
    if not os.path.exists(USER_DB):
        with open(USER_DB, 'w') as f: json.dump({}, f)
        return {}
    try:
        with open(USER_DB, 'r') as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except: return {}

def save_db(data):
    with open(USER_DB, 'w') as f: json.dump(data, f, indent=4)

# --- EMAIL ENGINE ---
def send_audit_email(recipient_email, repo_name):
    msg = EmailMessage()
    msg['Subject'] = f"🛡️ SPD Alert: Security Audit Complete for {repo_name}"
    msg['From'] = MAIL_ID
    msg['To'] = recipient_email
    msg.set_content(f"Hello,\n\nThe security audit for {repo_name} is complete.\n\nYou can view the detailed SAST/DAST findings here: https://spd-1j53.onrender.com/dashboard")
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(MAIL_ID, MAIL_PW)
            smtp.send_message(msg)
    except Exception as e: print(f"Mail Error: {e}")

# --- ROUTES ---
@app.route('/')
def index(): return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = load_db()
        un = request.form.get('username')
        db[un] = {"email": request.form.get('email'), "password": request.form.get('password')}
        save_db(db)
        if not os.path.exists(os.path.join(REPORT_DIR, un)): os.makedirs(os.path.join(REPORT_DIR, un))
        return redirect('/')
    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    db = load_db()
    un = request.form.get('username')
    pw = request.form.get('password')
    if un in db and db[un]['password'] == pw:
        session['username'] = un
        return redirect('/dashboard')
    return "Invalid Credentials", 401

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect('/')
    un = session['username']
    user_path = os.path.join(REPORT_DIR, un)
    reports = os.listdir(user_path) if os.path.exists(user_path) else []
    return render_template('dashboard.html', username=un, reports=reports)

@app.route('/inject', methods=['POST'])
def inject_yaml():
    if 'username' not in session: return redirect('/')
    owner, repo, token = request.form.get('owner'), request.form.get('repo'), request.form.get('token')
    username = session['username']

    yaml_content = f"""
name: SPD Security Audit
on: [push]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SPD Stealth Engine
        run: curl -s https://spd-1j53.onrender.com/static/engine.sh | bash -s -- {username}
    """
    encoded = base64.b64encode(yaml_content.encode()).decode()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/spd-audit.yml"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    # Force SHA Reconciliation
    sha = None
    existing = requests.get(url, headers=headers)
    if existing.status_code == 200: sha = existing.json().get('sha')

    payload = {"message": "🛡️ SPD Fresh Onboarding", "content": encoded}
    if sha: payload["sha"] = sha
    
    requests.put(url, json=payload, headers=headers)
    return redirect('/dashboard')

@app.route('/upload-report', methods=['POST'])
def upload_report():
    username = request.form.get('username')
    file = request.files.get('report')
    filename = request.form.get('filename')
    if username and file:
        user_path = os.path.join(REPORT_DIR, username)
        if not os.path.exists(user_path): os.makedirs(user_path)
        file.save(os.path.join(user_path, filename))
        # Automatic email on upload
        db = load_db()
        if username in db: send_audit_email(db[username]['email'], filename)
        return "OK", 200
    return "Fail", 400

@app.route('/view/<username>/<filename>')
def view_report(username, filename):
    return send_from_directory(os.path.join(REPORT_DIR, username), filename)

@app.route('/report/<username>/<filename>')
def show_report(username, filename):
    if 'username' not in session: return redirect('/')
    return render_template('report_viewer.html', username=username, filename=filename)

@app.route('/send-manual-mail', methods=['POST'])
def send_manual_mail():
    if 'username' not in session: return redirect('/')
    un = session['username']
    filename = request.form.get('filename')
    db = load_db()
    if un in db:
        send_audit_email(db[un]['email'], filename)
        return f"<h1>Success!</h1><p>Report for {filename} has been sent to {db[un]['email']}.</p><a href='/dashboard'>Back</a>"
    return "Error", 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)