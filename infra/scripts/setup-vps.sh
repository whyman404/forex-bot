#!/usr/bin/env bash
# ============================================================================
# infra/scripts/setup-vps.sh — Ubuntu 22.04 LTS production hardening
# ============================================================================
# Owner: Hestia Kaoru
#
# Usage (run as root, freshly-provisioned VPS):
#   curl -fsSL https://raw.githubusercontent.com/whyman404/forex-bot/main/infra/scripts/setup-vps.sh | sudo bash
# Or upload & run:
#   scp infra/scripts/setup-vps.sh root@<vps>:/root/
#   ssh root@<vps> bash /root/setup-vps.sh
#
# Steps:
#   1) apt update + install (docker, compose, git, ufw, fail2ban, unattended-upgrades, node-exporter, gnupg, awscli)
#   2) Create non-root user 'forex' (uid 1000)
#   3) SSH hardening: key auth only, no root, no password
#   4) UFW: 22, 80, 443 in; everything else deny
#   5) fail2ban for sshd
#   6) sysctl tuning (somaxconn, file-max, vm.swappiness, network)
#   7) 2 GB swapfile
#   8) Time sync (timesyncd)
#   9) Install node_exporter as systemd service
#  10) Create /srv/forex-bot data dirs with correct ownership
#
# Idempotent: re-running this script should be safe.
# ============================================================================

set -euo pipefail
IFS=$'\n\t'

readonly LOG_FILE="/var/log/forex-bot-setup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date -u +'%H:%M:%SZ')] [$1] ${*:2}"; }

[[ "$(id -u)" -eq 0 ]] || { log ERROR "must run as root"; exit 1; }

readonly DEPLOY_USER="${DEPLOY_USER:-forex}"
readonly DEPLOY_HOME="/home/$DEPLOY_USER"
readonly SSH_PUB_KEY="${SSH_PUB_KEY:-}"
readonly DATA_DIR="/srv/forex-bot"

# --- 1. Apt ------------------------------------------------------------------
log INFO "[1/10] apt update + install"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release \
    git rsync tmux htop iotop ncdu jq vim \
    ufw fail2ban unattended-upgrades \
    awscli postgresql-client gnupg-agent \
    chrony \
    apt-transport-https \
    software-properties-common

# Docker official repo
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# --- 2. Deploy user ---------------------------------------------------------
log INFO "[2/10] creating deploy user '$DEPLOY_USER'"
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"

mkdir -p "$DEPLOY_HOME/.ssh"
chmod 700 "$DEPLOY_HOME/.ssh"

if [[ -n "$SSH_PUB_KEY" ]]; then
    echo "$SSH_PUB_KEY" > "$DEPLOY_HOME/.ssh/authorized_keys"
    chmod 600 "$DEPLOY_HOME/.ssh/authorized_keys"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
else
    log WARN "no SSH_PUB_KEY env; copy root's authorized_keys to $DEPLOY_USER"
    if [[ -f /root/.ssh/authorized_keys ]]; then
        cp /root/.ssh/authorized_keys "$DEPLOY_HOME/.ssh/authorized_keys"
        chmod 600 "$DEPLOY_HOME/.ssh/authorized_keys"
        chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
    fi
fi

# sudo without password for restart commands (narrow scope)
cat > /etc/sudoers.d/forex-deploy <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /bin/systemctl restart docker, /bin/systemctl reload caddy
EOF
chmod 440 /etc/sudoers.d/forex-deploy

# --- 3. SSH hardening -------------------------------------------------------
log INFO "[3/10] SSH hardening"
SSHD_CONF=/etc/ssh/sshd_config

backup_and_set() {
    local key="$1" val="$2"
    if grep -qE "^[#[:space:]]*$key\b" "$SSHD_CONF"; then
        sed -i -E "s|^[#[:space:]]*$key\b.*|$key $val|" "$SSHD_CONF"
    else
        echo "$key $val" >> "$SSHD_CONF"
    fi
}

cp "$SSHD_CONF" "$SSHD_CONF.bak.$(date +%s)"
backup_and_set PermitRootLogin no
backup_and_set PasswordAuthentication no
backup_and_set ChallengeResponseAuthentication no
backup_and_set KbdInteractiveAuthentication no
backup_and_set UsePAM yes
backup_and_set X11Forwarding no
backup_and_set AllowAgentForwarding no
backup_and_set MaxAuthTries 3
backup_and_set LoginGraceTime 30
backup_and_set ClientAliveInterval 300
backup_and_set ClientAliveCountMax 2
backup_and_set Protocol 2

# Restrict ssh to deploy user
if ! grep -q "^AllowUsers" "$SSHD_CONF"; then
    echo "AllowUsers $DEPLOY_USER" >> "$SSHD_CONF"
fi

sshd -t || { log ERROR "sshd config invalid; not restarting"; exit 1; }
systemctl reload ssh

# --- 4. UFW -----------------------------------------------------------------
log INFO "[4/10] UFW firewall"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'ssh'
ufw allow 80/tcp comment 'http'
ufw allow 443/tcp comment 'https'
ufw allow 443/udp comment 'http3'
# Optional: Prometheus from CF Tunnel — handled inside docker network, not host
ufw --force enable
ufw status verbose

# --- 5. fail2ban ------------------------------------------------------------
log INFO "[5/10] fail2ban"
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled  = true
port     = ssh
filter   = sshd
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
ignoreip = 127.0.0.1/8 ::1
EOF

systemctl enable --now fail2ban
systemctl reload fail2ban

# --- 6. Sysctl --------------------------------------------------------------
log INFO "[6/10] sysctl tuning"
cat > /etc/sysctl.d/99-forex-bot.conf <<'EOF'
# Networking
net.core.somaxconn = 4096
net.core.netdev_max_backlog = 4096
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.ip_local_port_range = 10240 65535
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3

# Connection tracking (for high-connection Caddy/Cloudflare)
net.netfilter.nf_conntrack_max = 524288

# File descriptors
fs.file-max = 1048576

# VM
vm.swappiness = 10
vm.overcommit_memory = 1
vm.max_map_count = 262144  # ES / Loki

# Security defense-in-depth
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.tcp_syncookies = 1
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
EOF

sysctl --system

# Increase open files limit
cat > /etc/security/limits.d/99-forex-bot.conf <<EOF
*       soft    nofile  65536
*       hard    nofile  65536
$DEPLOY_USER soft    nofile  65536
$DEPLOY_USER hard    nofile  65536
EOF

# --- 7. Swap ----------------------------------------------------------------
log INFO "[7/10] swapfile"
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon --show

# --- 8. Time sync -----------------------------------------------------------
log INFO "[8/10] time sync (chrony)"
systemctl enable --now chrony
timedatectl set-timezone UTC

# --- 9. node_exporter -------------------------------------------------------
log INFO "[9/10] node_exporter"
NE_VERSION="1.8.2"
NE_USER="node_exporter"
NE_BIN="/usr/local/bin/node_exporter"
NE_TEXTFILE="/var/lib/node_exporter/textfile_collector"

if ! id "$NE_USER" >/dev/null 2>&1; then
    useradd --no-create-home --shell /usr/sbin/nologin "$NE_USER"
fi

if [[ ! -x "$NE_BIN" ]] || ! "$NE_BIN" --version 2>&1 | grep -q "$NE_VERSION"; then
    cd /tmp
    curl -fsSL "https://github.com/prometheus/node_exporter/releases/download/v${NE_VERSION}/node_exporter-${NE_VERSION}.linux-amd64.tar.gz" -o ne.tgz
    tar xzf ne.tgz
    install -m 755 "node_exporter-${NE_VERSION}.linux-amd64/node_exporter" "$NE_BIN"
    rm -rf "node_exporter-${NE_VERSION}.linux-amd64" ne.tgz
fi

mkdir -p "$NE_TEXTFILE"
chown -R "$NE_USER:$NE_USER" "$NE_TEXTFILE"

cat > /etc/systemd/system/node_exporter.service <<EOF
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
User=$NE_USER
Group=$NE_USER
Type=simple
ExecStart=$NE_BIN \\
    --collector.textfile.directory=$NE_TEXTFILE \\
    --collector.systemd \\
    --collector.processes \\
    --web.listen-address=127.0.0.1:9100
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter
systemctl status node_exporter --no-pager

# Note: bind to 127.0.0.1; docker prometheus reaches it via host network if
# needed, or run node-exporter as a container in compose for full container
# visibility. This systemd one collects host-level OS metrics safely.

# --- 10. Data dirs ----------------------------------------------------------
log INFO "[10/10] data dirs at $DATA_DIR"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" \
    "$DATA_DIR/data/postgres" \
    "$DATA_DIR/data/postgres-wal" \
    "$DATA_DIR/data/redis" \
    "$DATA_DIR/data/prometheus" \
    "$DATA_DIR/data/grafana" \
    "$DATA_DIR/data/loki" \
    "$DATA_DIR/data/alertmanager" \
    "$DATA_DIR/data/caddy/data" \
    "$DATA_DIR/data/caddy/config" \
    "$DATA_DIR/data/caddy/logs" \
    "$DATA_DIR/data/engine"

install -d -o root -g root -m 0750 /etc/forex-bot
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0755 /var/log/forex-bot

# --- Unattended upgrades ---------------------------------------------------
log INFO "configuring unattended-upgrades"
cat > /etc/apt/apt.conf.d/51forex-bot-unattended <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades

# --- Done ------------------------------------------------------------------
cat <<EOF

=============================================================================
  VPS SETUP COMPLETE
=============================================================================
  Deploy user      : $DEPLOY_USER
  Data dir         : $DATA_DIR
  Open ports       : 22 (ssh), 80, 443
  Docker installed : $(docker --version)
  Compose plugin   : $(docker compose version --short)
  Swap             : $(swapon --show | tail -1 | awk '{print $3}')
  Log              : $LOG_FILE

  NEXT STEPS:
    1) Copy your .env.prod to /etc/forex-bot/.env (chmod 600 root:root)
    2) On your laptop: rsync project to $DATA_DIR (or use scripts/deploy.sh)
    3) ssh $DEPLOY_USER@<this-host>
    4) cd $DATA_DIR && make deploy-prod

  Reboot recommended for sysctl + limits to fully apply:
    shutdown -r now
EOF
