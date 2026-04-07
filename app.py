import os, base64, requests, json, smtplib, psycopg2
from psycopg2.extras import RealDictCursor
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, send_from_directory

app = Flask(__name__)
app.secret_key = "kamaraj_spd_secret"

# --- CONFIGURATION ---

MAIL_ID = "padmamunishdhanajeyan@gmail.com"
MAIL_PW = "jvok ejcw xdpo szwq"
REPORT_DIR = 'reports'

if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)

# --- DB HELPER ---
def get_db():
    # 1. Get the raw string from environment
    raw_url = os.environ.get('DATABASE_URL', '')
    
    # 2. Aggressive cleaning: strip spaces, remove " and ' quotes
    clean_url = raw_url.strip().replace('"', '').replace("'", "").replace('\n', '').replace('\r', '')
    
    # 3. Connect using the sanitized string
    return psycopg2.connect(clean_url, cursor_factory=RealDictCursor)
# --- EMAIL ENGINE ---
def send_audit_email(email, repo_name):
    msg = EmailMessage()
    msg['Subject'] = f"🛡️ SPD Alert: Security Audit Complete for {repo_name}"
    msg['From'] = MAIL_ID
    msg['To'] = email
    msg.set_content(f"The security audit for {repo_name} is complete.\nView reports: https://spd-1j53.onrender.com/dashboard")
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(MAIL_ID, MAIL_PW)
            smtp.send_message(msg)
    except Exception as e: print(f"Mail Error: {e}")

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
    
    # Get physical files from folder
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
    
    yaml_content = f"name: SPD Audit\non: [push]\njobs:\n  audit:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: curl -s https://spd-1j53.onrender.com/static/engine.sh | bash -s -- {session['username']}"
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

@app.route('/upload-report', methods=['POST'])
def upload_report():
    un = request.form.get('username')
    file = request.files.get('report')
    filename = request.form.get('filename')
    
    user_path = os.path.join(REPORT_DIR, un)
    if not os.path.exists(user_path): os.makedirs(user_path)
    file.save(os.path.join(user_path, filename))
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT email FROM users WHERE username=%s", (un,))
    user = cur.fetchone()
    if user: send_audit_email(user['email'], filename)
    cur.close(); conn.close()
    return "OK", 200

# Report viewers remain the same
@app.route('/view/<username>/<filename>')
def view_file(username, filename):
    return send_from_directory(os.path.join(REPORT_DIR, username), filename)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)