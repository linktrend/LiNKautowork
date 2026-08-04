#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="$1"
PROJECT_NAME="$2"
RESTORE_TMP="$(mktemp -d)"
cleanup_restore() { rm -rf "$RESTORE_TMP"; }
trap cleanup_restore EXIT

DUMP_FILE="$RESTORE_TMP/control.sql"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres pg_dump -U postgres -d automation_contracts --schema=platform --schema=lautowork --no-owner --no-privileges > "$DUMP_FILE"
test -s "$DUMP_FILE"
DUMP_DIGEST="$(shasum -a 256 "$DUMP_FILE" | awk '{print $1}')"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres dropdb -U postgres --if-exists automation_restore
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres createdb -U postgres automation_restore
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_restore < "$DUMP_FILE" >/dev/null
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres psql -v ON_ERROR_STOP=1 -U postgres -d automation_restore <<'SQL'
do $$ begin
  if (select count(*) from lautowork.automation_instances) < 2 then raise exception 'control instances were not restored'; end if;
  if (select count(*) from lautowork.automation_releases) < 3 then raise exception 'catalogue release identities were not restored'; end if;
  if (select count(*) from lautowork.automation_eval_runs) < 1 then raise exception 'WP-06 evaluation receipt references were not restored'; end if;
  if (select count(*) from lautowork.automation_health_snapshots) < 1 then raise exception 'monitor health state was not restored'; end if;
  if (select count(*) from lautowork.automation_incidents) < 1 then raise exception 'incident state was not restored'; end if;
  if (select count(*) from lautowork.automation_pause_controls) < 1 then raise exception 'pause state was not restored'; end if;
end $$;
SQL
echo "Disposable control-data restore passed (sha256:${DUMP_DIGEST}); catalogue/eval references and WP-08 operational rows reconstructed."
