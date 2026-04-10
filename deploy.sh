#!/bin/bash
set -euo pipefail

# Webcam Streams — Deployment Script
# Usage: ./deploy.sh [theme]
# Example: ./deploy.sh beach

THEME="${1:-beach}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Validate theme exists
if [ ! -f "themes/${THEME}.json" ]; then
    echo "ERROR: Theme '${THEME}' not found in themes/ directory."
    echo "Available themes:"
    ls themes/*.json 2>/dev/null | xargs -I{} basename {} .json
    exit 1
fi

# Get port from theme config
PORT=$(python3 -c "import json; t=json.load(open('themes/${THEME}.json')); print(t.get('port', 8080))")
SERVICE_NAME="webcam-${THEME}-stream"

echo ""
echo "=============================================="
echo "  Webcam Streams — Deploying: ${THEME}"
echo "  Port: ${PORT}"
echo "=============================================="
echo ""

# ── System packages ──────────────────────────────

echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-venv python3-pip \
    ffmpeg fonts-dejavu-core \
    > /dev/null 2>&1

# Install yt-dlp (latest from GitHub releases for best YouTube compat)
if ! command -v yt-dlp &>/dev/null; then
    echo "  Installing yt-dlp..."
    sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
        -o /usr/local/bin/yt-dlp
    sudo chmod a+rx /usr/local/bin/yt-dlp
else
    echo "  yt-dlp already installed, updating..."
    sudo yt-dlp -U 2>/dev/null || true
fi
echo "  Done."

# ── Python virtual environment ───────────────────

echo "[2/6] Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Done."

# ── Directory structure ──────────────────────────

echo "[3/6] Creating directories..."
mkdir -p output library/videos library/music library/thumbnails \
         overlays/images webcams templates static themes
echo "  Done."

# ── Environment file ────────────────────────────

echo "[4/6] Checking configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    # Set the theme in .env
    sed -i "s/^STREAM_THEME=.*/STREAM_THEME=${THEME}/" .env
    sed -i "s/^FLASK_PORT=.*/FLASK_PORT=${PORT}/" .env
    echo ""
    echo "  =========================================="
    echo "  IMPORTANT: Edit .env with your stream key!"
    echo "  =========================================="
    echo ""
    echo "  nano $SCRIPT_DIR/.env"
    echo ""
else
    echo "  .env already exists, skipping."
fi

# ── Systemd service ─────────────────────────────

echo "[5/6] Installing systemd service..."

ACTUAL_USER="$(whoami)"

cat > /tmp/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Webcam Stream - ${THEME}
After=network.target

[Service]
Type=simple
User=${ACTUAL_USER}
WorkingDirectory=${SCRIPT_DIR}
Environment=STREAM_THEME=${THEME}
EnvironmentFile=${SCRIPT_DIR}/.env
ExecStart=${SCRIPT_DIR}/venv/bin/gunicorn \\
    --bind 0.0.0.0:${PORT} \\
    --workers 1 \\
    --threads 4 \\
    --timeout 300 \\
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/${SERVICE_NAME}.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
echo "  Done."

# ── Start service ────────────────────────────────

echo "[6/6] Starting service..."
sudo systemctl restart ${SERVICE_NAME}

sleep 2
if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "  Service is running!"
else
    echo "  WARNING: Service may not have started. Check:"
    echo "  sudo journalctl -u ${SERVICE_NAME} -n 20"
fi

# ── Done ─────────────────────────────────────────

IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================================="
echo "  Deployment Complete!"
echo "=============================================="
echo ""
echo "  Theme:   ${THEME}"
echo "  Web UI:  http://${IP}:${PORT}"
echo ""
echo "  Next steps:"
echo "  1. Open the URL above in your browser"
echo "  2. Go to Settings and enter your YouTube stream key"
echo "  3. Go to Sources and add webcam URLs"
echo "  4. Go to Music and upload or generate tracks"
echo "  5. Start streaming!"
echo ""
echo "  Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
