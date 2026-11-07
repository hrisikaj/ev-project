## Local database setup

Each city runs its own single-node CockroachDB. The database files (`proj-city*/`) are not committed to git. Rebuild them from the files in this repo.

Requirments: Python venv with `requirements.txt` installed, and the `cockroach` binary available.

How to rebuild:
1. Start a node. (Run in its own terminal; it stays in the foreground):
   ```
   cockroach start-single-node --insecure --store=proj-city1 --listen-addr=localhost:26258 --http-addr=localhost:8081
   ```
   Use a different store name and ports for each additional city (for example, `proj-city2` on 26259/8082 and `proj-city3` on 26260/8083).

2. Create the db & schema
   ```
   cockroach sql --insecure --host=localhost:26258 -f db/schema.sql
   ```

3. ACN API KEY (register at https://ev.caltech.edu/register). See the .env file.

   `.env` is git-ignored. Never commit your key.

4. Load data: TBD