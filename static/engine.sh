#!/bin/bash
# SPD Stealth Engine v2.0
# Usage: bash engine.sh <username>

USER_ID=$1
REPO_NAME=$(basename "$GITHUB_REPOSITORY")

echo "🛡️ SPD Engine: Auditing $REPO_NAME for User $USER_ID..."

# 1. Environment Setup
python3 -m pip install flask bandit --quiet

# 2. Static Analysis (SAST)
bandit -r . -f txt -o bandit_report.txt || true

# 3. Dynamic Analysis (DAST)
# Run ZAP Docker (host network to see localhost:5000)
docker run -v $(pwd):/zap/wrk/:rw --network=host ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r zap_report.html || true

# 4. Telemetry Exfiltration (Sending data back to your portal)
sudo chown -R $USER:$USER .
echo "📤 Exfiltrating telemetry to SPD Portal..."

curl -X POST -F "report=@bandit_report.txt" -F "filename=${REPO_NAME}_bandit.txt" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report
curl -X POST -F "report=@zap_report.html" -F "filename=${REPO_NAME}_zap.html" -F "username=${USER_ID}" https://spd-1j53.onrender.com/upload-report

echo "✅ Audit Complete. Check your dashboard."