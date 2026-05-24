import os, base64, requests, json, smtplib, psycopg2
from psycopg2.extras import RealDictCursor
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory, Response 
from celery import Celery 
from celery.schedules import crontab # NEW: Required for Approach A (Scheduled Scans)

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret"

# --- CELERY & REDIS CONFIGURATION ---
HARDCODED_REDIS = "rediss://default:gQAAAAAAAg5ZAAIgcDI1MjRlNjIwNjFkYzg0OTFiYjkwYTRkOGRkNTMyMzU2ZQ@huge-skunk-134745.upstash.io:6379?ssl_cert_reqs=CERT_NONE"

app.config['CELERY_BROKER_URL'] = HARDCODED_REDIS
app.config['CELERY_RESULT_BACKEND'] = HARDCODED_REDIS

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# NEW: Approach A - Celery Beat Scheduler
# Wakes up every Sunday at Midnight to run a continuous perimeter scan on all registered URLs
celery.conf.beat_schedule = {
    'weekly-url-perimeter-scan': {
        'task': 'app.async_trigger_all_urls',
        'schedule': crontab(hour=0, minute=0, day_of_week='sun'),
    },
}

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
    clean_url = DATABASE_URL.strip().replace('"', '').replace("'", "").replace('\n', '').replace('\r', '')
    return psycopg2.connect(clean_url, cursor_factory=RealDictCursor)

# --- SECURITY GRADING ENGINE ---
def calculate_security_grade(content, report_type):
    """Parses raw telemetry text (not files!) and applies the A/B/C Risk Matrix."""
    try:
        content_lower = content.lower()
        high_count = 0
        medium_count = 0

        if report_type == 'Bandit':
            high_count = content_lower.count('severity: high')
            medium_count = content_lower.count('severity: medium')
            
        elif report_type == 'ZAP':
            high_count = content_lower.count('risk-3') 
            medium_count = content_lower.count('risk-2') 

        if high_count >= 1 or medium_count >= 3:
            return 'C' 
        elif medium_count > 0:
            return 'B' 
        else:
            return 'A' 

    except Exception as e:
        print(f"⚠️ Grading Parsing Error: {e}")
        return 'N/A'

# --- EMAIL ENGINE ---
def send_audit_email(email, filename, username):
    msg = EmailMessage()
    msg['Subject'] = f"🛡️ SPD Security Alert: Audit Complete for {filename}"
    msg['From'] = MAIL_ID
    msg['To'] = email
    
    msg.set_content(f"""Hello {username},

The automated security audit for your project has been completed successfully.
Please find the detailed analysis report attached to this email.

You can also manage your assets and view history at:
https://spd-1j53.onrender.com/dashboard

Best regards,
SPD Orchestrator Engine""")

    try:
        file_path = os.path.join(REPORT_DIR, username, filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                file_data = f.read()
                subtype = 'html' if filename.endswith('.html') else 'plain'
                msg.add_attachment(file_data, maintype='text', subtype=subtype, filename=filename)

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
    
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    
    payload = {"message": "🛡️ SPD Injection", "content": encoded}
    if sha: payload["sha"] = sha
    
    response = requests.put(url, json=payload, headers=headers)
    
    if response.status_code in [200, 201]:
        return f"Success: Triggered {repo_name}"
    else:
        return f"Failed: API returned {response.status_code}"

# NEW: Approach A Worker - Queries all target URLs and fires off GitHub Action scans automatically
@celery.task(bind=True)
def async_trigger_all_urls(self):
    print("🕒 [CRON] Initiating scheduled perimeter scans...")
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT users.username, url_targets.target_url FROM url_targets JOIN users ON url_targets.user_id = users.id")
    targets = cur.fetchall()
    cur.close(); conn.close()

    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    OWNER = "Dhanajeyan77"
    REPO = "SPD-Engine-Runner"
    dispatch_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/main.yml/dispatches"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    for target in targets:
        payload = {"ref": "main", "inputs": {"username": target['username'], "target_url": target['target_url']}}
        requests.post(dispatch_url, json=payload, headers=headers)
        print(f"🚀 [CRON] Triggered DAST scan for {target['target_url']}")
    
    return f"Dispatched {len(targets)} scheduled scans."

# --- DASHBOARD & FLEET MANAGEMENT ---
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect('/')
    conn = get_db(); cur = conn.cursor()
    
    cur.execute("SELECT * FROM repositories WHERE user_id=%s", (session['user_id'],))
    repos = cur.fetchall()
    
    cur.execute("SELECT * FROM url_targets WHERE user_id=%s", (session['user_id'],))
    urls = cur.fetchall()
    
    cur.execute("""
        SELECT *, TO_CHAR(created_at, 'Mon DD, YYYY - HH12:MI AM') as scan_date 
        FROM scan_reports 
        WHERE user_id=%s ORDER BY created_at DESC
    """, (session['user_id'],))
    reports = cur.fetchall()
    
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

@app.route('/history')
def history():
    if 'user_id' not in session: return redirect('/')
    conn = get_db(); cur = conn.cursor()
    
    cur.execute("""
        SELECT *, 
        TO_CHAR(created_at, 'YYYY-MM-DD') as raw_date,
        TO_CHAR(created_at, 'Day, Mon DD, YYYY') as nice_date,
        TO_CHAR(created_at, 'HH12:MI AM') as nice_time
        FROM scan_reports 
        WHERE user_id=%s ORDER BY created_at DESC
    """, (session['user_id'],))
    all_reports = cur.fetchall()
    
    cur.close(); conn.close()
    return render_template('history.html', reports=all_reports)

# --- ORCHESTRATION ---
@app.route('/inject/<int:repo_id>')
def inject_workflow(repo_id):
    if 'user_id' not in session: return redirect('/')
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM repositories WHERE id=%s AND user_id=%s", (repo_id, session['user_id']))
    repo = cur.fetchone()
    cur.close(); conn.close()
    
    if repo:
        async_trigger_github_scan.delay(
            repo['repo_owner'], 
            repo['repo_name'], 
            repo['github_token'], 
            session['username']
        )
        print("✅ Scan safely queued in Upstash Redis!")
        
    return redirect('/dashboard')

# NEW: Approach B - External CI/CD Webhook
# Vercel, AWS, or developers ping this URL when they finish a deployment to trigger an instant scan
@app.route('/api/webhook/trigger', methods=['POST'])
def external_webhook():
    data = request.json
    if not data: return "Invalid Payload", 400

    api_key = data.get('spd_api_key')
    target_url = data.get('target_url')
    username = data.get('username')

    # Security check: Make sure unauthorized people can't spam your engine
    if api_key != "SUPER_SECRET_KEY":
        return "Unauthorized", 401

    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    OWNER = "Dhanajeyan77"
    REPO = "SPD-Engine-Runner"
    dispatch_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/main.yml/dispatches"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    payload = {"ref": "main", "inputs": {"username": username, "target_url": target_url}}
    res = requests.post(dispatch_url, json=payload, headers=headers)

    if res.status_code == 204:
        print(f"🔗 [WEBHOOK] External pipeline triggered scan for {target_url}")
        return "SaaS Perimeter Scan Queued Successfully", 202
    else:
        return f"Failed to trigger scan: {res.text}", 500

# --- TELEMETRY INGESTION ---
@app.route('/upload-report', methods=['POST'])
def upload_report():
    try:
        un = request.form.get('username')
        filename = request.form.get('filename')
        file = request.files.get('report')
        
        report_type = 'ZAP' if 'zap' in filename.lower() or 'dast' in filename.lower() else 'Bandit'
        security_grade = 'N/A'
        final_status = 'Completed'
        report_text = ""

        if file:
            report_text = file.read().decode('utf-8', errors='ignore')
            security_grade = calculate_security_grade(report_text, report_type)
            print(f"📊 Telemetry Graded In-Memory: {filename} received Grade {security_grade}")

        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO scan_reports (user_id, report_name, report_type, status, grade, report_content)
            VALUES ((SELECT id FROM users WHERE username=%s), %s, %s, %s, %s, %s)
        """, (un, filename, report_type, final_status, security_grade, report_text))
        conn.commit(); cur.close(); conn.close()
        
        return "OK", 200
    except Exception as e:
        print(f"Ingestion Error: {e}")
        return str(e), 500

# --- ARTIFACT RETRIEVAL ---
@app.route('/report/<username>/<filename>')
def view_file(username, filename):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT report_content FROM scan_reports 
        WHERE user_id=(SELECT id FROM users WHERE username=%s) AND report_name=%s
        ORDER BY id DESC LIMIT 1
    """, (username, filename))
    report = cur.fetchone()
    cur.close(); conn.close()

    if report and report['report_content']:
        if filename.endswith('.txt'):
            return Response(report['report_content'], mimetype='text/plain')
        else:
            return report['report_content']

    return "Report not found or permanently deleted.", 404
    
@app.route('/scan-url/<int:url_id>')
def scan_live_url(url_id):
    if 'user_id' not in session: return redirect('/')
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM url_targets WHERE id=%s AND user_id=%s", (url_id, session['user_id']))
    target = cur.fetchone()
    
    if not target:
        cur.close(); conn.close()
        return "URL Target not found", 404

    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') 
    OWNER = "Dhanajeyan77"
    REPO = "SPD-Engine-Runner"
    
    dispatch_url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/main.yml/dispatches"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    payload = {"ref": "main", "inputs": {"username": session['username'], "target_url": target['target_url']}}
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