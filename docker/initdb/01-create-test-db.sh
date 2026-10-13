#!/bin/bash
# Runs once, when the db container initializes an empty data directory.
# Creates a second database used only by the `tests` compose service, kept
# separate from the main app database so running tests never touches
# development data.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE "${POSTGRES_TEST_DB:-skinai_test}";
EOSQL
