# shellcheck shell=bash
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
