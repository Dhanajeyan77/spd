#!/bin/bash
# SPD Stealth Engine - REPO MODE

USER_ID=$1
REPO_NAME=$(basename "$GITHUB_REPOSITORY")

echo "🛡️ SPD Engine: Source Code Emulation for $REPO_NAME"

# 1. SAST
python3 -m pip install flask bandit --quiet
if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt --quiet; fi
bandit -r . -f txt -o bandit_report.txt || true

# 2. Local DAST
chmod -R 777 .
python3 app.py > app_log.txt 2>&1 & 
echo "⏳ Waiting 30s for Application to stabilize..."
sleep 30
docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r zap_report.html || true

sudo chown -R $USER:$USER .

# 3. Exfiltrate Bandit (Text file to DB)
curl -X POST -F "report=@bandit_report.txt" -F "filename=${REPO_NAME}_bandit.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

# 4. Host ZAP on GitHub Pages & Send URL to DB
UNIQUE_REPORT_NAME="${REPO_NAME}_${USER_ID}_zap.html"
cp zap_report.html $UNIQUE_REPORT_NAME

git config --global user.name "SPD Orchestrator"
git config --global user.email "bot@spd.com"
git fetch origin gh-pages || true
git checkout gh-pages 2>/dev/null || git checkout --orphan gh-pages
git add $UNIQUE_REPORT_NAME
git commit -m "Auto-deploy ZAP report"
git push origin gh-pages

OWNER=$(echo $GITHUB_REPOSITORY | cut -d'/' -f1)
PAGES_URL="https://${OWNER}.github.io/${REPO_NAME}/${UNIQUE_REPORT_NAME}"

curl -X POST -F "report_url=${PAGES_URL}" -F "filename=${UNIQUE_REPORT_NAME}" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report
echo "✅ Repo Audit Complete."