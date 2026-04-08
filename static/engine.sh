#!/bin/bash
# SPD Universal Engine v3.0 (Hybrid Repo & URL Support)

USER_ID=$1
# We capture the second argument. If it's empty, we default to localhost.
TARGET_URL=${2:-"http://localhost:5000"}

# Logic to determine if this is a Repo scan or a URL scan
if [ "$TARGET_URL" == "http://localhost:5000" ]; then
    SCAN_TYPE="REPO"
    REPO_NAME=$(basename "$GITHUB_REPOSITORY")
    DISPLAY_NAME=$REPO_NAME
else
    SCAN_TYPE="URL"
    DISPLAY_NAME=$(echo $TARGET_URL | sed 's|https\?://||' | cut -d'/' -f1)
fi

echo "🛡️ SPD Engine: Starting Audit for $DISPLAY_NAME [$SCAN_TYPE Mode]..."

# 1. Setup Environment
python3 -m pip install flask bandit --quiet

# 2. SAST & APP START (Only for Repositories)
if [ "$SCAN_TYPE" == "REPO" ]; then
    echo "🔍 Running SAST (Bandit)..."
    if [ -f requirements.txt ]; then python3 -m pip install -r requirements.txt --quiet; fi
    bandit -r . -f txt -o bandit_report.txt || true

    echo "🌐 Launching Application Environment..."
    chmod -R 777 .
    python3 app.py > app_log.txt 2>&1 & 
    echo "⏳ Waiting 30s for stability..."
    sleep 30
else
    echo "⏩ Skipping SAST/App Startup for Live URL scan..."
    echo "SAST skipped for remote URL target." > bandit_report.txt
fi

# 3. DAST (ZAP) - This now targets the dynamic URL
echo "🚀 Launching ZAP Baseline Scan against $TARGET_URL..."
docker run --rm -v $(pwd):/zap/wrk/:rw --network=host \
    ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
    -t "$TARGET_URL" -r zap_report.html || true

# 4. Fix Permissions & Exfiltrate
sudo chown -R $USER:$USER .

# NEW: Clean the display name for safe filenames (removes dots and slashes)
SAFE_FILENAME=$(echo $DISPLAY_NAME | sed 's/[^a-zA-Z0-9]/_/g')

echo "📤 Sending telemetry to SPD Orchestrator..."
# Send Bandit/Log
curl -X POST -F "report=@bandit_report.txt" -F "filename=${SAFE_FILENAME}_sast.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

# Send ZAP
if [ -f zap_report.html ]; then
    curl -X POST -F "report=@zap_report.html" -F "filename=${SAFE_FILENAME}_dast.html" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report
else
    echo "❌ Error: zap_report.html generation failed!"
fi

# Send ZAP
if [ -f zap_report.html ]; then
    curl -X POST -F "report=@zap_report.html" -F "filename=${DISPLAY_NAME}_dast.html" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report
else
    echo "❌ Error: zap_report.html generation failed!"
fi

echo "✅ Audit Complete for $DISPLAY_NAME."