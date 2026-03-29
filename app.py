import os
import base64
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- SYSTEM CONFIGURATION ---
# Pulls your Master Token from Render Environment Variables
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/onboard_page')
def onboard_page():
    return render_template('onboard.html')

# --- 1. THE DYNAMIC INJECTION (Uses Student's Token) ---
@app.route('/inject', methods=['POST'])
def inject_yaml():
    # 1. Capture Form Data
    owner = request.form.get('owner')
    repo = request.form.get('repo')
    student_token = request.form.get('token')
    stack = request.form.get('stack')
    port = request.form.get('port')
    
    # 2. Define Dynamic Logic based on Tech Stack
    if stack == "python":
        run_cmd = "python app.py & sleep 10"
        sast_cmd = "pip install bandit && bandit -r ."
    elif stack == "node":
        run_cmd = "npm start & sleep 15"
        sast_cmd = "npm audit"
    elif stack == "java":
        run_cmd = "mvn spring-boot:run & sleep 25"
        sast_cmd = "echo 'Running Java Static Analysis'"
    else:
        run_cmd = "sleep 5" # Default fallback
        sast_cmd = "echo 'Generic SAST'"

    # 3. Construct the Custom YAML (Injecting Port and Commands)
    yaml_content = f"""
name: SPD Security Audit
on: [push, repository_dispatch]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: SAST Scan ({stack})
        run: {sast_cmd}
        
      - name: Start Application (DAST Staging)
        run: {run_cmd}
        
      - name: OWASP ZAP DAST Scan
        uses: zaproxy/action-baseline@v0.12.0
        with:
          target: 'http://localhost:{port}'
    """
    
    encoded_content = base64.b64encode(yaml_content.encode()).decode()
    
    # 4. GitHub API URL for the specific student repo
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/spd-audit.yml"
    
    # 5. Execute Injection using Student's Token
    headers = {
        "Authorization": f"token {student_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    payload = {
        "message": "🛡️ SPD System: Automated DevSecOps Onboarding",
        "content": encoded_content
    }
    
    response = requests.put(url, json=payload, headers=headers)
    
    if response.status_code == 201:
        return "<h1>Success!</h1><p>SPD Security Policy has been injected and customized for your stack.</p>"
    else:
        error_msg = response.json().get('message', 'Unknown Error')
        return f"<h1>Error</h1><p>{error_msg}</p>", 400

# --- 2. THE SYSTEM ORCHESTRATOR (Uses YOUR Master Token) ---
@app.route('/webhook', methods=['POST'])
def github_webhook():
    event_data = request.json
    
    if 'repository' in event_data and GITHUB_TOKEN:
        owner = event_data['repository']['owner']['login']
        repo = event_data['repository']['name']
        
        # Command the student's repo to run the SPD workflow
        dispatch_url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
        dispatch_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        dispatch_data = {"event_type": "spd_audit_trigger"}
        
        requests.post(dispatch_url, json=dispatch_data, headers=dispatch_headers)
        
    return "OK", 200

if __name__ == '__main__':
    # False for production; set True for testing on Latitude 5411
    app.run(port=5000, debug=False)