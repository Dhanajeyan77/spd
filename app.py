import os
import base64
import requests
import json
import smtplib
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret" # Needed for login sessions

# --- CONFIGURATION ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
MAIL_ID = "padmamunishdhanajeyan@gmail.com"
MAIL_PW = "iibl iezd nvac yxqr"  # Your App Password
REPORT_DIR = 'reports'
USER_DB = 'users.json'

# Ensure system folders and database exist
if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)
if not os.path.exists(USER_DB):
    with open(USER_DB, 'w') as f: json.dump({}, f)

# --- DATABASE HELPERS ---
def load_db():
    with open(USER_DB, 'r') as f: return json.load(f)

def save_db(data):
    with open(USER_DB, 'w') as f: json.dump(data, f, indent=4)

# --- EMAIL ENGINE ---
def send_audit_email(recipient_email, repo_name):
    msg = EmailMessage()
    msg['Subject'] = f"🛡️ SPD Alert: Security Audit Complete for {repo_name}"
    msg['From'] = MAIL_ID
    msg['To'] = recipient_email
    msg.set_content(f"""
    Hello,
    
    The SPD Orchestrator has completed a security audit for your repository: {repo_name}.
    
    The Static (Bandit) and Dynamic (ZAP) telemetry results are now available on your dashboard.
    Please review the 7 ZAP warnings to secure your deployment.
    
    View Dashboard: https://spd-1j53.onrender.com/dashboard
    
    Regards,
    Kamaraj SPD Portal
    """)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(MAIL_ID, MAIL_PW)
            smtp.send_message(msg)
    except Exception as e:
        print(f"Mail Error: {e}")

# --- ROUTES: AUTHENTICATION ---
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = load_db()
        un = request.form.get('username')
        db[un] = {
            "email": request.form.get('email'),
            "password": request.form.get('password')
        }
        save_db(db)
        # Create user report folder
        if not os.path.exists(os.path.join(REPORT_DIR, un)):
            os.makedirs(os.path.join(REPORT_DIR, un))
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

# --- ROUTES: DASHBOARD & INJECTION ---
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
    
    owner = request.form.get('owner')
    repo = request.form.get('repo')
    token = request.form.get('token')
    stack = request.form.get('stack')
    port = request.form.get('port')
    username = session['username']

    # The Stealth YAML (Universal for all stacks)
    yaml_content = f"""
name: SPD Security Audit
on: [push]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SPD Stealth Engine
        run: curl -s https://spd-1j53.onrender.com/static/engine.sh | bash -s -- {username} {stack} {port}
    """
    
    encoded = base64.b64encode(yaml_content.encode()).decode()
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/spd-audit.yml"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.put(url, json={"message": "🛡️ SPD Onboarding", "content": encoded}, headers=headers)
    return redirect('/dashboard')

# --- ROUTES: TELEMETRY & VIEWING ---
@app.route('/upload-report', methods=['POST'])
def upload_report():
    username = request.form.get('username')
    file = request.files.get('report')
    filename = request.form.get('filename')
    
    if username and file:
        user_path = os.path.join(REPORT_DIR, username)
        if not os.path.exists(user_path): os.makedirs(user_path)
        file.save(os.path.join(user_path, filename))
        
        # Trigger Email Alert
        db = load_db()
        if username in db:
            send_audit_email(db[username]['email'], filename.split('_')[0])
            
        return "Telemetry Ingested", 200
    return "Fail", 400

@app.route('/view/<username>/<filename>')
def view_report(username, filename):
    return send_from_directory(os.path.join(REPORT_DIR, username), filename)

if __name__ == '__main__':
    app.run(port=5000, debug=False)