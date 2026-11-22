## Local database setup (instructions generated via CLAUDE)

Each city runs its own single-node CockroachDB. The database files (`proj-city*/`) are not committed to git. Rebuild them from the files in this repo.

Requirements: Python venv with `requirements.txt` installed, and the `cockroach` binary available.

How to rebuild:
1. WSL Ubuntu, Python 3.10: python -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt. Put your ACN API key in .env as ACN_API_KEY (never commit this file)

2. Fetch data: python data_cleansing/get_data.py

3. Start the nodes, create the dbs & schema (run from the project root, safe to re-run):
   ```
   chmod +x scripts/start_cockroach.sh
   ./scripts/start_cockroach.sh
   ```
   This starts three single-node CockroachDBs in the background: city1 (SQL 26258, console 8081), city2 (26259, 8082), city3 (26260, 8083). It also creates each city's database and applies db/schema.sql.

4. Seed ports: python scripts/seed_data.py (run from the project root, safe to re-run)
   city1 gets 310 ports (55 real Caltech ACN stations + 255 synthetic), city2 gets 200 and city3 gets 112 (all synthetic). Synthetic lots and ports have ids starting with `syn-`.