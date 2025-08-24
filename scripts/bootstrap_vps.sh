#!/usr/bin/env bash
set -euo pipefail

### ====== PARAMÈTRES À ADAPTER (ou via variables d'env) ======
DOMAIN="${DOMAIN:-pierreandrieu.fr}"
WWW_DOMAIN="${WWW_DOMAIN:-www.pierreandrieu.fr}"
CANONICAL_HOST="${CANONICAL_HOST:-$DOMAIN}"

DEPLOY_USER="${DEPLOY_USER:-$USER}"

# Arbo perso
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/workspace}"
PROJECT_NAME="${PROJECT_NAME:-siteprofessionnel}"
PROJECT_DIR="${PROJECT_DIR:-$WORKSPACE_DIR/$PROJECT_NAME}"

# Dépôt des cours (sources PDF)
ENS_DIR="${ENS_DIR:-$WORKSPACE_DIR/enseignement-lycee}"

# Racine statique/médias servies par Nginx
WWW_ROOT="${WWW_ROOT:-/var/www/pierreandrieu}"
STATIC_DIR="$WWW_ROOT/static"
MEDIA_DIR="$WWW_ROOT/media"
DOCS_DIR="$MEDIA_DIR/documents"

# Fichiers de conf
NGINX_SITE="/etc/nginx/sites-available/$DOMAIN"
NGINX_SITE_LINK="/etc/nginx/sites-enabled/$DOMAIN"
NGINX_PC_SNIPPET="/etc/nginx/snippets/pc_ratelimit.conf"
NGINX_CONF="/etc/nginx/nginx.conf"

# Compose (prod)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"

### ====== UTILITAIRES ======
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }
ensure_dir() { sudo install -d -m "$2" -o "$3" -g "$4" "$1"; }
append_once() { local file="$1" line="$2"; grep -qxF "$line" "$file" || echo "$line" | sudo tee -a "$file" >/dev/null; }

### ====== 1) PAQUETS DE BASE ======
echo "==> Installation paquets de base"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl git ufw nginx certbot python3-certbot-nginx

# Docker (méthode convenience script ; rerunnable)
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installation Docker"
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$DEPLOY_USER" || true
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "==> Installation docker compose plugin"
  sudo apt-get install -y docker-compose-plugin
fi

### ====== 2) FIREWALL ======
echo "==> UFW (22, 80, 443)"
sudo ufw allow OpenSSH >/dev/null || true
sudo ufw allow 80/tcp >/dev/null || true
sudo ufw allow 443/tcp >/dev/null || true
sudo ufw --force enable

### ====== 3) ARBO WEB & DROITS ======
echo "==> Arborescence $WWW_ROOT"
ensure_dir "$WWW_ROOT"  "2775" "$DEPLOY_USER" "www-data"
ensure_dir "$STATIC_DIR" "2775" "$DEPLOY_USER" "www-data"
ensure_dir "$MEDIA_DIR"  "2775" "$DEPLOY_USER" "www-data"
ensure_dir "$DOCS_DIR"   "2775" "$DEPLOY_USER" "www-data"

# Setgid sur les dossiers pour conserver www-data
sudo find "$WWW_ROOT" -type d -exec chmod 2775 {} \;
sudo find "$WWW_ROOT" -type f -exec chmod 0664 {} \;

### ====== 4) CLONES (si absents) ======
echo "==> Clonage des dépôts si manquants"
ensure_dir "$WORKSPACE_DIR" "0755" "$DEPLOY_USER" "$DEPLOY_USER"

if [ ! -d "$PROJECT_DIR/.git" ]; then
  git clone "https://github.com/pierreandrieu/siteprofessionnel.git" "$PROJECT_DIR"
fi
if [ ! -d "$ENS_DIR/.git" ]; then
  git clone "https://github.com/pierreandrieu/enseignement-lycee.git" "$ENS_DIR"
fi

### ====== 5) ENV PROD (.env.prod) ======
echo "==> Fichier d'environnement ($ENV_FILE)"
cd "$PROJECT_DIR"
# 1) Exiger le fichier .env.prod
if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ Fichier $ENV_FILE manquant. Crée-le d'abord (à partir de .env.prod.sample) puis relance." >&2
  exit 1
fi

### ====== 6) NGINX : snippet rate-limit + include ======
echo "==> Snippet rate-limit (pc_ratelimit.conf)"
if [ ! -f "$NGINX_PC_SNIPPET" ]; then
  sudo tee "$NGINX_PC_SNIPPET" >/dev/null <<'NGX'
# /etc/nginx/snippets/pc_ratelimit.conf
map $cookie_sessionid $pc_key {
    "~.+"   $cookie_sessionid;
    default $binary_remote_addr;
}
limit_req_zone  $pc_key  zone=pc_rate:10m  rate=30r/m;  # 30 req/min par clé
limit_conn_zone $pc_key  zone=pc_conn:10m;
NGX
fi

if ! grep -q 'snippets/pc_ratelimit.conf' "$NGINX_CONF"; then
  echo "==> Ajout include du snippet dans nginx.conf"
  sudo sed -i 's@^\s*include /etc/nginx/mime.types;@include /etc/nginx/mime.types;\n    include /etc/nginx/snippets/pc_ratelimit.conf;@' "$NGINX_CONF"
fi

### ====== 7) NGINX : vhost minimal HTTP (certbot passera ensuite en HTTPS) ======
echo "==> VHost Nginx ($NGINX_SITE)"
if [ ! -f "$NGINX_SITE" ]; then
  sudo tee "$NGINX_SITE" >/dev/null <<NGX
# $DOMAIN — HTTP bootstrap (Certbot ajoutera TLS)
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN $WWW_DOMAIN;

    # Static
    location /static/ {
        alias $STATIC_DIR/;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
        access_log off;
    }

    # Media
    location /media/ {
        alias $MEDIA_DIR/;
        types { application/pdf pdf; }
        default_type application/octet-stream;
        add_header X-Content-Type-Options "nosniff" always;
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
    }

    # Rate-limit ciblé (ex: /plandeclasse/)
    location /plandeclasse/ {
        limit_req   zone=pc_rate  burst=10;
        limit_conn  pc_conn  2;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        \$connection_upgrade;
    }
}
NGX
  sudo ln -sf "$NGINX_SITE" "$NGINX_SITE_LINK"
  sudo nginx -t
  sudo systemctl reload nginx
fi

### ====== 8) DOCKER : build & up ======
echo "==> Docker Compose (prod)"
docker compose -f "$COMPOSE_FILE" up -d --build
docker compose -f "$COMPOSE_FILE" ps

### ====== 9) CERTIFICATS LET'S ENCRYPT (auto, via plugin nginx) ======
echo "==> Certbot (Let's Encrypt)"
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  sudo certbot --nginx -d "$DOMAIN" -d "$WWW_DOMAIN" --agree-tos -m "admin@$DOMAIN" -n
  sudo systemctl reload nginx
fi

### ====== 10) PUBLICATION DES PDF (copy → /var/www/.../media/documents) ======
echo "==> Publication des PDF (copy)"
python3 "$PROJECT_DIR/scripts/dev_publish_symlinks.py" \
  --src "$ENS_DIR" \
  --dst "$DOCS_DIR" \
  --mode copy \
  --prune

echo "==> FIN ✓ — ton site devrait répondre sur https://$DOMAIN/"
