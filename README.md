## Local database setup

Each city runs its own single-node CockroachDB. The database files (`proj-city*/`) are not committed to git. Rebuild them from the files in this repo.

Requirments: Python venv with `requirements.txt` installed, and the `cockroach` binary available.

How to rebuild:
1. WSL Ubuntu, Python 3.10: python -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt. Put your ACN API key in .env as ACN_API_KEY (never commit this file)



2. Start a node. (Run in its own terminal; it stays in the foreground):
   ```
   cockroach start-single-node --insecure --store=proj-city1 --listen-addr=localhost:26258 --http-addr=localhost:8081
   ```
   Use a different store name and ports for each additional city (for example, `proj-city2` on 26259/8082 and `proj-city3` on 26260/8083).

2. Create the db & schema
   ```
   cockroach sql --insecure --host=localhost:26258 -f db/schema.sql
   ```
   
3. Fetch data: python data_cleansing/get_data.py

4. Seed ports: python scripts/seed_data.py (run from the project root)