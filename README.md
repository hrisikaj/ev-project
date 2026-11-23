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

 ## Running the reservation servers

Each city has its own FastAPI server (app/main.py) that talks only to its own database. The CITY env var picks which one. Start the three databases and seed the ports first (steps above).

5. Start one server per city, each in its own terminal (run from the project root):
   ```
   LENDING=off CITY=city1 uvicorn app.main:app --port 8001
   LENDING=off CITY=city2 uvicorn app.main:app --port 8002
   LENDING=off CITY=city3 uvicorn app.main:app --port 8003
   ```
   LENDING picks the method: `off` is static escrow (each city only books its own ports, a full city redirects once), `on` is dynamic escrow (a full city first borrows idle ports from a neighbor, then redirects if that fails). Use the same value on all three servers. Restart the servers after changing it.

6. Check a server: curl localhost:8001/health (should return the city, db "up" and its port count)

7. Make a reservation:
   ```
   curl -X POST localhost:8001/reserve -H "Content-Type: application/json" -d '{"u_id": 1}'
   ```
   Optional fields: arrive_in_min (0-10, default 0) and duration_min (default 60). Every attempt is logged in that city's `requests` table (home_city, handled_by, redirect_count, retries, status, reject_reason).

Settings (env vars, all optional): LENDING (off/on, default off), LEND_BATCH (ports per loan, default 5), MAX_REDIRECTS (default 1). Redirect order is set in NEIGHBORS in app/main.py: city1 -> city2, city2 -> city1, city3 -> city1.

## Tests

Both tests delete all reservations and requests first, so only run them on test data.

- Double-booking test (no servers needed, only city3's database): `python -m scripts.test_concur`. It fires 400 simultaneous requests at city3's 112 ports for the same hour. Pass = 112 accepted, 0 double bookings.
- Lending test (all three servers running with LENDING=on): `python -m scripts.test_lending`. It fills city1, sends 200 simultaneous requests, and checks all three databases for double bookings. Pass = 0 double bookings.

After a test, clear leftover data before trying the API by hand:
```
cockroach sql --insecure --host=localhost:26258 -d city1 -e "DELETE FROM reservations; DELETE FROM requests; DELETE FROM ports WHERE home_city <> 'city1'; DELETE FROM lots WHERE city <> 'city1'"
```
(repeat on 26259/city2 and 26260/city3, and for those two use `UPDATE ports SET booking_city = home_city` in place of the two DELETEs on ports and lots)  