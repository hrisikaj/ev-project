import os, psycopg
from fastapi import FastAPI
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from app.reserve import try_reserve

CITY = os.environ.get("CITY", "city1")

SQL_PORTS = {"city1": 26258, "city2": 26259, "city3": 26260}
DB_URL = f"postgresql://root@localhost:{SQL_PORTS[CITY]}/{CITY}?sslmode=disable"

app = FastAPI(title=f"EV Reservation System - {CITY}")

class ReserveRequest(BaseModel):
    u_id: int
    arrive_in_min: int = Field(default = 0, ge = 0, le = 10)
    duration_min: int = Field(default = 60, gt = 0)
    
def log_request(u_id, requested_at, retries, status, reject_reason=None):
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            """INSERT INTO requests (u_id, requested_at, home_city, handled_by, redirect_count, retries, status, reject_reason) VALUES (%s, %s, %s, %s, 0, %s, %s, %s)""", (u_id, requested_at, CITY, CITY, retries, status, reject_reason),
        )
        
@app.post("/reserve")
def reserve(req: ReserveRequest):
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=req.arrive_in_min)
    end = start + timedelta(minutes=req.duration_min)
    
    try:
        port_id, retries = try_reserve(DB_URL, CITY, req.u_id, start, end)
    except psycopg.errors.SerializationFailure:
        log_request(req.u_id, now, 0, "rejected", "contention")
        return {"status": "rejected", "reason": "contention", "city": CITY}
    
    if port_id is None:
        log_request(req.u_id, now, retries, "rejected", "full")
        return {"status": "rejected", "reason": "full", "city": CITY}
    
    log_request(req.u_id, now, retries, "accepted")
    return {"status": "accepted", "port_id": port_id, "city": CITY, "start": start.isoformat(), "end": end.isoformat(), "retries": retries}

@app.get("/health")
def health():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as conn:
            ports = conn.execute("SELECT count(*) FROM ports").fetchone()[0]
        return {"city":CITY, "db":"up", "ports": ports}
    except Exception as e:
        return {"city":CITY, "db":"down", "error": str(e)}
    


