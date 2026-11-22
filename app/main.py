import os
import psycopg
from fastapi import FastAPI

CITY = os.environ.get("CITY", "city1")

SQL_PORTS = {"city1": 26258, "city2": 26259, "city3": 26260}
DB_URL = f"postgresql://root@localhost:{SQL_PORTS[CITY]}/{CITY}?sslmode=disable"

app = FastAPI(title=f"EV Reservation System - {CITY}")

@app.get("/health")
def health():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as conn:
            ports = conn.execute("SELECT count(*) FROM ports").fetchone()[0]
        return {"city":CITY, "db":"up", "ports": ports}
    except Exception as e:
        return {"city":CITY, "db":"down", "error": str(e)}
