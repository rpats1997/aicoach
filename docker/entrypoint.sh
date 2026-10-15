#!/usr/bin/env bash
set -euo pipefail

PGDATA=/var/lib/postgresql/data

mkdir -p "$PGDATA"
chown -R postgres:postgres /var/lib/postgresql

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "[entrypoint] Initializing PostgreSQL data directory..."
    su postgres -c "/usr/local/bin/pg-initdb -D $PGDATA"

    su postgres -c "/usr/local/bin/pg-pg_ctl -D $PGDATA -l /tmp/pg_init.log -w start"
    su postgres -c "/usr/local/bin/pg-psql --command \"CREATE USER coachai WITH SUPERUSER PASSWORD 'coachai';\""
    su postgres -c "/usr/local/bin/pg-createdb -O coachai coachai"
    su postgres -c "/usr/local/bin/pg-pg_ctl -D $PGDATA -m fast -w stop"

    echo "[entrypoint] Database initialized."
fi

exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
