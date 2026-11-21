# shellcheck shell=bash
# PG_BIN (opcional): carpeta de pg_dump/pg_restore/psql de la MISMA versión mayor que el servidor
# (p. ej. /usr/lib/postgresql/16/bin). Un cliente más nuevo escribe SETs que un servidor viejo
# no entiende (transaction_timeout en 17+), y la restauración falla.
if [[ -n "${PG_BIN:-}" ]]; then PATH="$PG_BIN:$PATH"; fi
# Convierte una URL de SQLAlchemy (postgresql+asyncpg://…) en variables PG* para pg_dump/psql,
# así la contraseña no queda en la línea de comandos (ps) ni en los logs. Uso: pgenv "$URL".
pgenv() {
  eval "$(python3 - "$1" <<'PY'
import shlex, sys
from urllib.parse import parse_qs, unquote, urlsplit
u = urlsplit(sys.argv[1].replace("+asyncpg", "", 1))
q = {k: v[-1] for k, v in parse_qs(u.query).items()}
ssl = q.get("sslmode") or {"require": "require", "true": "require"}.get(q.get("ssl", ""), "")
env = {
    "PGHOST": u.hostname or "", "PGPORT": str(u.port or 5432),
    "PGUSER": unquote(u.username or ""), "PGPASSWORD": unquote(u.password or ""),
    "PGDATABASE": u.path.lstrip("/"), "PGSSLMODE": ssl or "prefer",
}
print(" ".join(f"export {k}={shlex.quote(v)}" for k, v in env.items()))
PY
)"
}

# Lee VAR desde el entorno o, si falta, desde la línea VAR= de .env (sin ejecutar el archivo).
from_env() {
  local name="$1" value="${!1:-}"
  if [[ -z "$value" && -f .env ]]; then
    value="$(grep -E "^${name}=" .env | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')"
  fi
  printf '%s' "$value"
}

table_counts() {  # "tabla filas" por línea, orden estable
  psql -X -At -c "SELECT table_name FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1" |
    while read -r t; do printf '%s %s\n' "$t" "$(psql -X -At -c "SELECT count(*) FROM \"$t\"")"; done
}

# Corta con un mensaje claro si pg_dump/pg_restore no son de la versión mayor del servidor.
require_same_major() {
  local server client
  server="$(psql -X -At -c 'SHOW server_version_num')"
  server=$((server / 10000))
  client="$(pg_dump --version | grep -oE '[0-9]+' | head -n1)"
  if [[ "$server" != "$client" ]]; then
    echo "pg_dump/pg_restore son v$client y el servidor es v$server: usa el cliente v$server" \
      "(define PG_BIN, p. ej. /usr/lib/postgresql/$server/bin)" >&2
    exit 3
  fi
}
