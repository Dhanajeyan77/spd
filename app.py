import os
import base64
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Route for the Home Page
@app.route('/')
def index():
    return render_template('index.html')

# Route for the Onboarding Page
@app.route('/onboard_page')
def onboard_page():
    return render_template('onboard.html')

# API Route to "Inject" the YAML into the student's repo
@app.route('/inject', methods=['POST'])
def inject_yaml():
    owner = request.form.get('owner')
    repo = request.form.get('repo')
    token = request.form.get('token')
    
    # The URL to create a file in the student's repo via GitHub API
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/workflows/kamaraj-audit.yml"
    
    # Your Master Security YAML Logic
    yaml_content = """
name: Kamaraj Security Audit
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
          target: 'https://google.com' # Change this to student's live URL
    """
    
    encoded_content = base64.b64encode(yaml_content.encode()).decode()
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    data = {
        "message": "🛡️ Onboarding to SPD Security Portal",
        "content": encoded_content
    }
    
    response = requests.put(url, json=data, headers=headers)
    
    if response.status_code == 201:
        return "<h1>Success!</h1><p>Security YAML Injected. Your repo is now protected.</p>"
    else:
        return f"<h1>Error</h1><p>{response.json().get('message')}</p>", 400

if __name__ == '__main__':
    app.run(debug=True)