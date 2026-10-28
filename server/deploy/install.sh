#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv
if ! id eva >/dev/null 2>&1; then
    useradd --system --home-dir /opt/eva --shell /usr/sbin/nologin eva
fi
mkdir -p /opt/eva /var/lib/eva /etc/eva
chmod 750 /etc/eva
tar -xzf /root/eva-release.tar.gz -C /opt/eva
python3 -m venv /opt/eva/.venv
/opt/eva/.venv/bin/pip install -r /opt/eva/requirements.txt
if [ ! -f /etc/eva/eva.env ]; then
    /opt/eva/.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
Path('/etc/eva/eva.env').write_text(
    'APP_MODE=draft\nDATABASE_PATH=/var/lib/eva/bot.db\n'
    'KNOWLEDGE_PATH=knowledge/server_draft.json\n'
    f'WEBHOOK_SECRET={secrets.token_urlsafe(48)}\n'
    f'WAZZUP_WEBHOOK_TOKEN={secrets.token_urlsafe(48)}\n', encoding='utf-8')
PY
fi
chown root:eva /etc/eva /etc/eva/eva.env
chmod 640 /etc/eva/eva.env
chown -R eva:eva /var/lib/eva
cp /opt/eva/deploy/eva.service /etc/systemd/system/eva.service
systemctl daemon-reload
systemctl enable --now eva.service
systemctl restart eva.service
