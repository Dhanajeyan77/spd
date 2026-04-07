import os, base64, requests, json, smtplib, psycopg2
from psycopg2.extras import RealDictCursor
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret"

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
    
    yaml_content = f"""name: SPD Audit
on: [push]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl -s https://spd-1j53.onrender.com/static/engine.sh | bash -s -- {session['username']}"""
    
    encoded = base64.b64encode(yaml_content.encode()).decode()
    url = f"https://api.github.com/repos/{repo['repo_owner']}/{repo['repo_name']}/contents/.github/workflows/spd-audit.yml"
    headers = {"Authorization": f"token {repo['github_token']}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(url, headers=headers)
    sha = res.json().get('sha') if res.status_code == 200 else None
    
    payload = {"message": "🛡️ SPD Injection", "content": encoded}
    if sha: payload["sha"] = sha
    
    requests.put(url, json=payload, headers=headers)
    cur.close(); conn.close()
    return redirect('/dashboard')

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
        file.save(os.path.join(user_path, filename))

        # 2. Relational Synchronization
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT email FROM users WHERE username=%s", (un,))
        user_data = cur.fetchone()
        
        report_type = 'ZAP' if 'zap' in filename.lower() else 'Bandit'
        cur.execute("""
            INSERT INTO scan_reports (user_id, report_name, report_type, status)
            VALUES ((SELECT id FROM users WHERE username=%s), %s, %s, 'Completed')
        """, (un, filename, report_type))
        
        conn.commit(); cur.close(); conn.close()
        
        # 3. Asynchronous SMTP Alert
        if user_data:
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)