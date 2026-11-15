#!/bin/sh
# Initializes additional PostgreSQL databases required by HydraJob:
# - Separate test database (POSTGRES_TEST_DB, default: hydrajob_test)
# - Separate n8n persistence database (N8N_DB_NAME, default: n8n)
# Mounted read-only at /docker-entrypoint-initdb.d/01-init-databases.sh

set -eu

TEST_DB="${POSTGRES_TEST_DB:-hydrajob_test}"
N8N_DB="${N8N_DB_NAME:-n8n}"
APP_USER="${POSTGRES_USER:-hydrajob}"

create_db_if_missing() {
    db_name="$1"
    # Validate identifier to avoid SQL injection from misconfigured env vars.
    case "$db_name" in
        ''|*[!a-zA-Z0-9_]*)
            echo "ERROR: Invalid database identifier '$db_name'" >&2
            exit 1
            ;;
    esac

    exists="$(psql -v ON_ERROR_STOP=1 --username "$APP_USER" --dbname "$POSTGRES_DB" -tAc "SELECT 1 FROM pg_database WHERE datname = '$db_name'")"
    if [ "$exists" != "1" ]; then
        echo "Creating database '$db_name' owned by '$APP_USER'..."
        psql -v ON_ERROR_STOP=1 --username "$APP_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE \"$db_name\" OWNER \"$APP_USER\";"
    else
        echo "Database '$db_name' already exists."
    fi
}

create_db_if_missing "$TEST_DB"
create_db_if_missing "$N8N_DB"
