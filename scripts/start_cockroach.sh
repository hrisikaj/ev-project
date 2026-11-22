#!/usr/bin/env bash

# Start three nodes- one per city


set -euo pipefail

cd "$(dirname "$0")/.." #running from root

for n in 1 2 3; do
    SQL_PORT=$((26257 + n))
    RPC_PORT=$((26356 + n))
    HTTP_PORT=$((8080 + n))

    if cockroach sql --insecure --host=localhost:$SQL_PORT -e "SELECT 1" >/dev/null 2>&1; 
        then echo "city$n already running on $SQL_PORT"
        continue
    fi

    echo "starting city$n on $SQL_PORT"
    cockroach start-single-node --insecure --store=proj-city$n --listen-addr=localhost:$RPC_PORT --sql-addr=localhost:$SQL_PORT --http-addr=localhost:$HTTP_PORT --background
done


for n in 1 2 3; do
    SQL_PORT=$((26257 + n))
    cockroach sql --insecure --host=localhost:$SQL_PORT -e "CREATE DATABASE IF NOT EXISTS city$n"
    cockroach sql --insecure --host=localhost:$SQL_PORT -d city$n -f db/schema.sql
done

echo "all three cities ready"