#!/usr/bin/env bash
# FL-32 · Respaldo de la BD (pg_dump formato custom) y de los fotogramas (STORAGE_LOCAL_PATH).
#
#   DATABASE_URL=… STORAGE_LOCAL_PATH=/data/evidence scripts/backup.sh [destino]
#
# Deja <destino>/wwm-AAAAMMDDTHHMMSSZ/{db.dump, evidence.tar.gz, MANIFEST, SHA256SUMS} y borra
# los respaldos de más de BACKUP_KEEP_DAYS días (14). Sirve igual para Aiven u otro PostgreSQL.
# Probar cada respaldo con scripts/restore_test.sh (un respaldo sin probar no es un respaldo).
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_pgenv.sh

url="$(from_env DATABASE_URL)"
storage="$(from_env STORAGE_LOCAL_PATH)"
[[ -n "$url" ]] || { echo "Falta DATABASE_URL" >&2; exit 2; }
[[ -n "$storage" ]] || { echo "Falta STORAGE_LOCAL_PATH" >&2; exit 2; }
pgenv "$url"

root="${1:-${BACKUP_DIR:-backups}}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$root/wwm-$stamp"
mkdir -p "$out"
umask 077  # el dump tiene datos personales: solo el dueño lo lee

pg_dump --format=custom --no-owner --no-privileges --file "$out/db.dump"
if [[ -d "$storage" ]]; then
  tar -czf "$out/evidence.tar.gz" -C "$storage" .
  files="$(find "$storage" -type f | wc -l | tr -d ' ')"
else
  tar -czf "$out/evidence.tar.gz" --files-from /dev/null
  files=0
fi
{
  echo "created_at=$stamp"
  echo "alembic_version=$(psql -X -At -c 'SELECT version_num FROM alembic_version')"
  echo "evidence_files=$files"
  table_counts | sed 's/^/rows./; s/ /=/'
} > "$out/MANIFEST"
(cd "$out" && sha256sum db.dump evidence.tar.gz MANIFEST > SHA256SUMS)

find "$root" -maxdepth 1 -type d -name 'wwm-*' -mtime +"${BACKUP_KEEP_DAYS:-14}" -exec rm -rf {} +
echo "Respaldo listo: $out ($(du -sh "$out" | cut -f1), $files fotogramas)"
