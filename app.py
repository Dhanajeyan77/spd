import os, base64, requests, json, smtplib, psycopg2
from psycopg2.extras import RealDictCursor
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory
from celery import Celery # NEW IMPORT

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret"

# --- CELERY & REDIS CONFIGURATION ---
# We look for a REDIS_URL environment variable. If not found, it defaults to localhost for your testing.
app.config['CELERY_BROKER_URL'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)
# --- CONFIGURATION ---
DATABASE_URL = os.environ.get('DATABASE_URL', '')
MAIL_ID = "padmamunishdhanajeyan@gmail.com"
MAIL_PW = "vnhp wnww vbwr hqjf" 
REPORT_DIR = os.path.join(os.getcwd(), 'reports')

# Ensure the base directory exists on startup
if not os.path.exists(REPORT_DIR):
    os.makedirs(REPORT_DIR, exist_ok=True)

# --- DB HELPER ---
def get_db():
    # Sanitizing DSN for Neon PostgreSQL compatibility
    clean_url = DATABASE_URL.strip().replace('"', '').replace("'", "").replace('\n', '').replace('\r', '')
    return psycopg2.connect(clean_url, cursor_factory=RealDictCursor)
# --- SECURITY GRADING ENGINE ---
def calculate_security_grade(file_path, report_type):
    """Parses raw telemetry files and applies the A/B/C Risk Matrix."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()

        high_count = 0
        medium_count = 0

        if report_type == 'Bandit':
            # Bandit uses explicit severity tags
            high_count = content.count('severity: high')
            medium_count = content.count('severity: medium')
            
        elif report_type == 'ZAP':
            # ZAP HTML reports use specific CSS classes for risk levels
            high_count = content.count('risk-3') # High
            medium_count = content.count('risk-2') # Medium

        # The Grading Matrix Algorithm
        if high_count >= 1 or medium_count >= 3:
            return 'C' # Critical Exposure
        elif medium_count > 0:
            return 'B' # Functional Security (Minor Leaks)
        else:
            return 'A' # Secure Perimeter

    except Exception as e:
        print(f"⚠️ Grading Parsing Error: {e}")
        return 'N/A'
# --- EMAIL ENGINE ---
def send_audit_email(email, filename, username):
    msg = EmailMessage()
    msg['Subject'] = f"🛡️ SPD Security Alert: Audit Complete for {filename}"
    msg['From'] = MAIL_ID
    msg['To'] = email
    
    # Professional Email Body with Dashboard Link
    msg.set_content(f"""Hello {username},

The automated security audit for your project has been completed successfully.
Please find the detailed analysis report attached to this email.

You can also manage your assets and view history at:
https://spd-1j53.onrender.com/dashboard

Best regards,
SPD Orchestrator Engine""")

    try:
        # Resolve path and attach file
        file_path = os.path.join(REPORT_DIR, username, filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                file_data = f.read()
                # Determine MIME type
                subtype = 'html' if filename.endswith('.html') else 'plain'
                msg.add_attachment(
                    file_data,
                    maintype='text',
                    subtype=subtype,
                    filename=filename
                )

        # SMTP with 15-second timeout to prevent Gunicorn Worker Timeout
        with smtplib.SMTP_SSL('smtp.gmail.com', 587, timeout=15) as smtp:
            smtp.login(MAIL_ID, MAIL_PW)
            smtp.send_message(msg)
        print(f"📧 Email successfully delivered to {email}")
    except Exception as e:
        print(f"⚠️ SMTP Alert skipped: {str(e)}")

# --- AUTH ROUTES ---
@app.route('/')
def index(): return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        un, em, pw = request.form.get('username'), request.form.get('email'), request.form.get('password')
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (un, em, pw))
        conn.commit(); cur.close(); conn.close()
        return redirect('/')
    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    un, pw = request.form.get('username'), request.form.get('password')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username FROM users WHERE username=%s AND password=%s", (un, pw))
    user = cur.fetchone()
    cur.close(); conn.close()
    if user:
        session['user_id'], session['username'] = user['id'], user['username']
        return redirect('/dashboard')
    return "Invalid Credentials", 401

@app.route('/logout')
def logout(): session.clear(); return redirect('/')
# --- BACKGROUND WORKERS (CELERY) ---
@celery.task(bind=True)
def async_trigger_github_scan(self, repo_owner, repo_name, github_token, username):
    """This function runs entirely in the background via Redis."""
    print(f"⚙️ Worker picked up task: Scanning {repo_owner}/{repo_name} for {username}")
    
    yaml_content = f"""name: SPD Audit
on: [push]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl -s https://spd-1j53.onrender.com/static/engine.sh | bash -s -- {username}"""
    
    encoded = base64.b64encode(yaml_content.encode()).decode()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/.github/workflows/spd-audit.yml"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
    
    # 1. Check if file exists to get the SHA
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    
    # 2. Push the workflow (Triggers the scan)
    payload = {"message": "🛡️ SPD Injection", "content": encoded}
    if sha: payload["sha"] = sha
    
    response = requests.put(url, json=payload, headers=headers)
    
    if response.status_code in [200, 201]:
        return f"Success: Triggered {repo_name}"
    else:
        return f"Failed: API returned {response.status_code}"


# --- DASHBOARD & FLEET MANAGEMENT ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect('/')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM repositories WHERE user_id=%s", (session['user_id'],))
    repos = cur.fetchall()
    cur.execute("SELECT * FROM url_targets WHERE user_id=%s", (session['user_id'],))
    urls = cur.fetchall()
    
    user_path = os.path.join(REPORT_DIR, session['username'])
    reports = os.listdir(user_path) if os.path.exists(user_path) else []
    
    cur.close(); conn.close()
    return render_template('dashboard.html', repos=repos, urls=urls, reports=reports)

@app.route('/add-repo', methods=['POST'])
def add_repo():
    owner, repo, token = request.form.get('owner'), request.form.get('repo'), request.form.get('token')
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO repositories (user_id, repo_owner, repo_name, github_token) VALUES (%s,%s,%s,%s)", 
                (session['user_id'], owner, repo, token))
    conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')

@app.route('/delete-repo/<int:id>')
def delete_repo(id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM repositories WHERE id=%s AND user_id=%s", (id, session['user_id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')

@app.route('/delete-url/<int:id>')
def delete_url(id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM url_targets WHERE id=%s AND user_id=%s", (id, session['user_id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')

@app.route('/add-url', methods=['POST'])
def add_url():
    name, url = request.form.get('name'), request.form.get('url')
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO url_targets (user_id, target_name, target_url) VALUES (%s,%s,%s)", 
                (session['user_id'], name, url))
    conn.commit(); cur.close(); conn.close()
    return redirect('/dashboard')

# --- ORCHESTRATION ---
@app.route('/inject/<int:repo_id>')
def inject_workflow(repo_id):
    if 'user_id' not in session: return redirect('/')
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM repositories WHERE id=%s AND user_id=%s", (repo_id, session['user_id']))
    repo = cur.fetchone()
    cur.close(); conn.close()
    
    if repo:
        # This is the magic! .delay() pushes the heavy API work to Upstash Redis instantly!
        async_trigger_github_scan.delay(
            repo['repo_owner'], 
            repo['repo_name'], 
            repo['github_token'], 
            session['username']
        )
        print("✅ Scan safely queued in Upstash Redis!")
        
    return redirect('/dashboard')
# --- TELEMETRY INGESTION ---
# --- TELEMETRY INGESTION ---
@app.route('/upload-report', methods=['POST'])
def upload_report():
    try:
        un = request.form.get('username')
        file = request.files.get('report')
        filename = request.form.get('filename')
        
        # 1. Physical Persistence
        user_path = os.path.join(REPORT_DIR, un)
        os.makedirs(user_path, exist_ok=True)
        file_path = os.path.join(user_path, filename)
        file.save(file_path)

        # 2. Heuristic Security Grading (NEW)
        report_type = 'ZAP' if 'zap' in filename.lower() or 'dast' in filename.lower() else 'Bandit'
        security_grade = calculate_security_grade(file_path, report_type)
        print(f"📊 Telemetry Graded: {filename} received Grade {security_grade}")

        # 3. Relational Synchronization
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT email FROM users WHERE username=%s", (un,))
        user_data = cur.fetchone()
        
        # Updated to include the 'grade' column
        cur.execute("""
            INSERT INTO scan_reports (user_id, report_name, report_type, status, grade)
            VALUES ((SELECT id FROM users WHERE username=%s), %s, %s, 'Completed', %s)
        """, (un, filename, report_type, security_grade))
        
        conn.commit(); cur.close(); conn.close()
        
        # 4. Asynchronous SMTP Alert
        if user_data:
            # You could even pass the grade into the email if you update the email function!
            send_audit_email(user_data['email'], filename, un)
            
        return "OK", 200
    except Exception as e:
        print(f"Ingestion Error: {e}")
        return str(e), 500

# Artifact Retrieval Route
@app.route('/report/<username>/<filename>')
def view_file(username, filename):
    user_path = os.path.join(REPORT_DIR, username)
    if not os.path.exists(os.path.join(user_path, filename)):
        return "Report file not found", 404
    return send_from_directory(user_path, filename)
# Add this near your other orchestration routes
@app.route('/scan-url/<int:url_id>')
def scan_live_url(url_id):
    if 'user_id' not in session: return redirect('/')
    
    # 1. Fetch the target URL from Neon
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM url_targets WHERE id=%s AND user_id=%s", (url_id, session['user_id']))
    target = cur.fetchone()
    
    if not target:
        cur.close(); conn.close()
        return "URL Target not found", 404

    # 2. Configuration (Use Render Environment Variables for the Token!)
    # GITHUB_TOKEN should be your PAT with 'workflow' scope
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') 
    OWNER = "Dhanajeyan77"
    REPO = "SPD-Engine-Runner"
    
    dispatch_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/main.yml/dispatches"
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 3. The Payload - Matches the 'inputs' in your main.yml
    payload = {
        "ref": "main",
        "inputs": {
            "username": session['username'],
            "target_url": target['target_url']
        }
    }
    
    # 4. Trigger the GitHub Runner
    response = requests.post(dispatch_url, json=payload, headers=headers)
    
    cur.close(); conn.close()
    
    if response.status_code == 204:
        print(f"🚀 SaaS Scan Triggered for {target['target_url']}")
        return redirect('/dashboard')
    else:
        print(f"❌ Trigger Failed: {response.text}")
        return f"GitHub API Error: {response.status_code}", 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)