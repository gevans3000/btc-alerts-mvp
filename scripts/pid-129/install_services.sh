#!/bash
# install_services.sh - Dynamically generate and install systemd services
# Works for Linux and Mac (with Homebrew systemd or standard systemd)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_NAME=$(whoami)
GROUP_NAME=$(id -gn)
PYTHON_PATH="${ROOT_DIR}/.venv/bin/python3"

echo ">>> Generating services for ${USER_NAME} in ${ROOT_DIR} <<<"

# 1. Main Service
cat > "${ROOT_DIR}/pid-129-btc-alerts.service" <<EOF
[Unit]
Description=BTC Alerts MVP Service (PID-129)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${ROOT_DIR}
Environment="PATH=${ROOT_DIR}/.venv/bin:${ROOT_DIR}:/usr/local/bin:/usr/bin:/bin"
ExecStart=${PYTHON_PATH} ${ROOT_DIR}/app.py --loop
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=10s
StandardOutput=append:${ROOT_DIR}/logs/service.log
StandardError=append:${ROOT_DIR}/logs/service.log
SyslogIdentifier=btc-alerts-mvp
Nice=-5

[Install]
WantedBy=default.target
EOF

# 2. Watchdog Service
cat > "${ROOT_DIR}/pid-129-watchdog.service" <<EOF
[Unit]
Description=BTC Alerts MVP Watchdog (PID-129)

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${ROOT_DIR}
ExecStartPre=/bin/sleep 5
ExecStart=${ROOT_DIR}/scripts/pid-129/healthcheck.sh
ExecStop=/bin/kill -TERM \$MAINPID
Restart=on-failure
RestartSec=30s
StandardOutput=append:${ROOT_DIR}/logs/pid-129-watchdog.log
StandardError=append:${ROOT_DIR}/logs/pid-129-watchdog.log

[Install]
WantedBy=default.target
EOF

echo ">>> Services generated. To install locally (Linux/Mac with systemd): <<<"
echo "mkdir -p ~/.config/systemd/user/"
echo "cp *.service ~/.config/systemd/user/"
echo "systemctl --user daemon-reload"
echo "systemctl --user enable pid-129-btc-alerts.service"
echo "systemctl --user start pid-129-btc-alerts.service"
