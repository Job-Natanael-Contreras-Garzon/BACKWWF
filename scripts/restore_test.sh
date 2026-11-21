#!/usr/bin/env bash
# FL-32 · Prueba de restauración: restaura un respaldo en una BD DESCARTABLE y verifica que
# coincide con su MANIFEST (versión de Alembic, filas por tabla y cantidad de fotogramas).
#
#   RESTORE_DATABASE_URL=postgresql://…/wwf_restore_test scripts/restore_test.sh backups/wwm-…
#
# Nunca toca la BD de DATABASE_URL: si ambas apuntan a la misma base (o a faunadb), se niega.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_pgenv.sh

dir="${1:?Uso: restore_test.sh <carpeta del respaldo>}"
target="${RESTORE_DATABASE_URL:?Falta RESTORE_DATABASE_URL (una BD descartable)}"
(cd "$dir" && sha256sum --quiet -c SHA256SUMS) || { echo "Checksums no coinciden" >&2; exit 1; }

pgenv "$target"
target_id="$PGHOST:$PGPORT/$PGDATABASE"
if [[ "$PGDATABASE" == "faunadb" ]]; then echo "Me niego a restaurar sobre faunadb" >&2; exit 2; fi
prod="$(from_env DATABASE_URL)"
if [[ -n "$prod" ]]; then
  (pgenv "$prod"; [[ "$PGHOST:$PGPORT/$PGDATABASE" != "$target_id" ]]) ||
    { echo "RESTORE_DATABASE_URL apunta a la BD de DATABASE_URL" >&2; exit 2; }
fi

pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error \
  --dbname "$PGDATABASE" "$dir/db.dump"

fail=0
expected_version="$(grep '^alembic_version=' "$dir/MANIFEST" | cut -d= -f2)"
actual_version="$(psql -X -At -c 'SELECT version_num FROM alembic_version')"
[[ "$expected_version" == "$actual_version" ]] ||
  { echo "alembic: esperaba $expected_version, hay $actual_version" >&2; fail=1; }
diff <(grep '^rows\.' "$dir/MANIFEST" | sed 's/^rows\.//; s/=/ /') <(table_counts) >&2 ||
  { echo "Las filas por tabla no coinciden" >&2; fail=1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$dir/evidence.tar.gz" -C "$tmp"
files="$(find "$tmp" -type f | wc -l | tr -d ' ')"
expected_files="$(grep '^evidence_files=' "$dir/MANIFEST" | cut -d= -f2)"
[[ "$files" == "$expected_files" ]] ||
  { echo "fotogramas: esperaba $expected_files, hay $files" >&2; fail=1; }

if [[ $fail -ne 0 ]]; then echo "RESTAURACIÓN FALLIDA" >&2; exit 1; fi
echo "Restauración OK en $target_id: alembic $actual_version, $files fotogramas, filas iguales."
