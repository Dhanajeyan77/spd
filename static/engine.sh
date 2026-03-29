#!/bin/bash
# SPD Stealth Engine v2.5 (Fixed DAST Reporting)

USER_ID=$1
REPO_NAME=$(basename "$GITHUB_REPOSITORY")

echo "🛡️ SPD Engine: Starting Audit for $REPO_NAME..."

# 1. Setup Environment
python3 -m pip install flask bandit --quiet
if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt --quiet; fi

# 2. SAST (Bandit)
bandit -r . -f txt -o bandit_report.txt || true

# 3. Start Application (CRITICAL: Must match YAML success)
chmod -R 777 .
python3 app.py > app_log.txt 2>&1 & 
echo "⏳ Waiting 30s for Application to stabilize on Port 5000..."
sleep 30

# 4. DAST (ZAP) - Using the Web-Swing Baseline
# We use the official Docker image but force it to look at the host port
echo "🚀 Launching ZAP Baseline Scan..."
docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r zap_report.html || true

# 5. Fix Permissions & Exfiltrate
sudo chown -R $USER:$USER .

echo "📤 Sending reports to Kamaraj Portal..."
# Send Bandit
curl -X POST -F "report=@bandit_report.txt" -F "filename=${REPO_NAME}_bandit.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

# Send ZAP (Only if it exists)
if [ -f zap_report.html ]; then
    curl -X POST -F "report=@zap_report.html" -F "filename=${REPO_NAME}_zap.html" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report
else
    echo "❌ Error: zap_report.html was not generated!"
fi

echo "✅ Audit Complete."