import os
import base64
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- SYSTEM CONFIGURATION ---
# This pulls your token from Render's "Environment Variables" safely
# On your local laptop, you can set this in your terminal: export GITHUB_TOKEN=your_token
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/onboard_page')
def onboard_page():
    return render_template('onboard.html')

# --- 1. THE INJECTION (Uses Student's Token from Form) ---
@app.route('/inject', methods=['POST'])
def inject_yaml():
    owner = request.form.get('owner')
    repo = request.form.get('repo')
    student_token = request.form.get('token') 
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/spd-audit.yml"
    
    # The Master SPD Logic
    yaml_content = """
name: SPD Security Audit
on: [push, repository_dispatch]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Bandit SAST
        run: pip install bandit && bandit -r .
      - name: ZAP DAST
        uses: zaproxy/action-baseline@v0.12.0
        with:
          target: 'https://google.com'
    """
    
    encoded_content = base64.b64encode(yaml_content.encode()).decode()
    
    # Using STUDENT'S token for the one-time injection
    headers = {
        "Authorization": f"token {student_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "message": "🛡️ SPD System: Automated Security Onboarding",
        "content": encoded_content
    }
    
    response = requests.put(url, json=data, headers=headers)
    
    if response.status_code == 201:
        return "<h1>Success!</h1><p>SPD Security YAML Injected. Check your GitHub Actions tab!</p>"
    else:
        return f"<h1>Error</h1><p>{response.json().get('message')}</p>", 400

# --- 2. THE TRIGGER (Uses YOUR Master Token from Render) ---
@app.route('/webhook', methods=['POST'])
def github_webhook():
    event_data = request.json
    
    # We only care about 'push' events to start the audit
    if 'repository' in event_data and GITHUB_TOKEN:
        owner = event_data['repository']['owner']['login']
        repo = event_data['repository']['name']
        
        dispatch_url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
        
        # Using YOUR Master Token to command the cloud
        dispatch_headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        dispatch_data = {"event_type": "spd_audit_trigger"}
        
        requests.post(dispatch_url, json=dispatch_data, headers=dispatch_headers)
        
    return "OK", 200

if __name__ == '__main__':
    # For local testing on Latitude 5411
    app.run(port=5000, debug=False)