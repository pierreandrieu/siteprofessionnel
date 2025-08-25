# Depuis le dossier du projet
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

# 1) Rebuild (image web)
$COMPOSE build web

# 2) (ré)appliquer les droits host (idempotent)
$COMPOSE run --rm init-fs

# 3) Publier/maj tes PDFs
python3 scripts/dev_publish_symlinks.py \
  --src "/home/pierre/workspace/enseignement-lycee" \
  --dst "/var/www/pierreandrieu/media/documents" \
  --mode copy --prune

# 4) Redéployer
$COMPOSE up -d

# 5) Sanity check
$COMPOSE ps
$COMPOSE logs --tail=50 web

