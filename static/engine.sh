#!/bin/bash
# SPD Stealth Engine - BIMODAL MODE (Direct Ingestion)

USER_ID=$1
TARGET_URL=$2
REPO_NAME=$(basename "$GITHUB_REPOSITORY")

if [ -z "$TARGET_URL" ]; then
    # ==========================================
    # 📁 REPO MODE (SAST + Local DAST)
    # ==========================================
    echo "🛡️ SPD Engine: Source Code Emulation for $REPO_NAME"
    
    # 1. Static Analysis (SAST)
    python3 -m pip install flask bandit --quiet
    if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt --quiet; fi
    bandit -r . -f txt -o bandit_report.txt || true
    
    # 2. Exfiltrate Bandit Directly to Backend
    echo "📤 Transmitting SAST artifact to Orchestrator..."
    curl -X POST -F "report=@bandit_report.txt" -F "filename=${REPO_NAME}_bandit.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

    # 3. Dynamic Analysis (Local DAST)
    chmod -R 777 .
    python3 app.py > app_log.txt 2>&1 & 
    echo "⏳ Waiting 30s for Application to stabilize..."
    sleep 30
    docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r zap_report.html || true

    sudo chown -R $USER:$USER .
    
    # 4. Exfiltrate ZAP Directly to Backend
    UNIQUE_REPORT_NAME="${REPO_NAME}_${USER_ID}_zap.html"
    mv zap_report.html $UNIQUE_REPORT_NAME
    
    echo "📤 Transmitting secure DAST artifact to Orchestrator..."
    curl -X POST -F "report=@${UNIQUE_REPORT_NAME}" -F "filename=${UNIQUE_REPORT_NAME}" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

    echo "✅ Repo Audit Complete."

else
    # ==========================================
    # 🌐 URL MODE (Remote DAST Only)
    # ==========================================
    echo "🌐 SPD Engine: Live SaaS Perimeter Scan on $TARGET_URL"

    # 1. Dynamic Analysis (Remote DAST)
    docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t $TARGET_URL -r zap_report.html || true

    sudo chown -R $USER:$USER .

    # 2. Exfiltrate ZAP Directly to Backend
    UNIQUE_REPORT_NAME="URL_SCAN_${USER_ID}_zap.html"
    mv zap_report.html $UNIQUE_REPORT_NAME

    echo "📤 Transmitting secure DAST artifact to Orchestrator..."
    curl -X POST -F "report=@${UNIQUE_REPORT_NAME}" -F "filename=${UNIQUE_REPORT_NAME}" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

    echo "✅ URL Audit Complete."
fi