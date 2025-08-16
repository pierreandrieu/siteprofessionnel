# Déploiement du site Django avec Docker et Nginx

Ce document décrit les étapes nécessaires pour déployer l’application sur un VPS à partir d’un serveur vide.

---

## Pré-requis

Installer les mises à jour, Git, UFW, Docker et Docker Compose :

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ufw
curl -fsSL https://get.docker.com | sh
sudo groupadd docker || true
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

---

## Clonage du projet

Créer un dossier de travail puis cloner le dépôt :

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/pierreandrieu/siteprofessionnel.git
cd siteprofessionnel
```

---

## Configuration des variables d’environnement

Copier le fichier `.env.prod` vers `.env` et restreindre ses droits :

```bash
cp .env.prod .env
chmod 600 .env
```

Adapter le fichier `.env` selon les besoins. Exemple :

```env
DJANGO_ALLOWED_HOSTS=pierreandrieu.fr,www.pierreandrieu.fr,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://pierreandrieu.fr,https://www.pierreandrieu.fr
```

---

## Construction et lancement de l’application

Construire et démarrer les conteneurs :

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Vérifier l’état des services :

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -n 50 web
```

---

## Vérification interne

Vérifier que l’application répond via Gunicorn :

```bash
curl -i -H "Host: pierreandrieu.fr"      -H "X-Forwarded-Proto: https"      http://127.0.0.1:8000/healthz
```

Un retour `200 OK` indique que l’application est accessible.

---

## Configuration Nginx

Créer le fichier `/etc/nginx/sites-available/pierreandrieu` :

```nginx
server {
    listen 80;
    server_name pierreandrieu.fr www.pierreandrieu.fr;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activer le site et redémarrer Nginx :

```bash
sudo ln -sf /etc/nginx/sites-available/pierreandrieu /etc/nginx/sites-enabled/pierreandrieu
sudo nginx -t
sudo systemctl restart nginx
```

---

## Certificat SSL avec Certbot

Installer et configurer Let’s Encrypt :

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pierreandrieu.fr -d www.pierreandrieu.fr
```

---

## Mise à jour de l’application

Mettre à jour le code puis redémarrer :

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
