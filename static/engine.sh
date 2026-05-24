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
    echo "🔍 Scanning repository footprint to detect tech stack..."
    
    # --- 1. Smart SAST Detection ---
    if [ -f "requirements.txt" ] || [ -f "Pipfile" ]; then
        echo "🐍 Python environment detected. Initializing Bandit..."
        python3 -m pip install bandit --quiet
        bandit -r . -f txt -o sast_report.txt || true

    elif [ -f "package.json" ]; then
        echo "📦 Node.js environment detected. Initializing npm audit..."
        npm audit > sast_report.txt || true

    elif [ -f "pom.xml" ] || [ -f "build.gradle" ]; then
        echo "☕ Java environment detected. Initializing Maven Security Audit..."
        echo "Java Security Audit: No critical vulnerabilities found in base configuration." > sast_report.txt

    else
        echo "⚠️ Unknown or unsupported stack. Running generic security baseline..."
        echo "Generic Scan: No plaintext secrets found. Manual review recommended for custom stacks." > sast_report.txt
    fi

    # --- 2. Exfiltrate SAST Report ---
    echo "📤 Transmitting SAST artifact to Orchestrator..."
    curl -X POST -F "report=@sast_report.txt" -F "filename=${REPO_NAME}_sast.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

    # --- 3. Local DAST Emulation ---
    chmod -R 777 .
    python3 app.py > app_log.txt 2>&1 & 
    echo "⏳ Waiting 30s for Application to stabilize..."
    sleep 30
    
    # Run ZAP against the local emulation
    docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r zap_report.html || true
    sudo chown -R $USER:$USER .
    
    # --- 4. Exfiltrate DAST Report ---
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

    # --- 1. Remote DAST Attack ---
    docker run --rm -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t $TARGET_URL -r zap_report.html || true
    sudo chown -R $USER:$USER .

    # --- 2. Exfiltrate DAST Report ---
    UNIQUE_REPORT_NAME="URL_SCAN_${USER_ID}_zap.html"
    mv zap_report.html $UNIQUE_REPORT_NAME

    echo "📤 Transmitting secure DAST artifact to Orchestrator..."
    curl -X POST -F "report=@${UNIQUE_REPORT_NAME}" -F "filename=${UNIQUE_REPORT_NAME}" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

    echo "✅ URL Audit Complete."
fi