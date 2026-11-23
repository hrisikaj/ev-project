import os, psycopg, httpx
from fastapi import FastAPI
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from app.reserve import try_reserve

CITY = os.environ.get("CITY", "city1")

SQL_PORTS = {"city1": 26258, "city2": 26259, "city3": 26260}
DB_URL = f"postgresql://root@localhost:{SQL_PORTS[CITY]}/{CITY}?sslmode=disable"
API_PORTS = {"city1": 8001, "city2":8002, "city3": 8003}
NEIGHBORS = {"city1": ["city2", "city3"], "city2": ["city1", "city3"], "city3": ["city1", "city2"]}
MAX_REDIRECTS = int(os.environ.get("MAX_REDIRECTS", "1"))

app = FastAPI(title=f"EV Reservation System - {CITY}")

class ReserveRequest(BaseModel):
    u_id: int
    arrive_in_min: int = Field(default = 0, ge = 0, le = 10)
    duration_min: int = Field(default = 60, gt = 0)
    home_city: str | None = None
    redirect_count: int = 0
    
def log_request(u_id, requested_at, retries, status, reject_reason=None, home_city=None, redirect_count=0):
    with psycopg.connect(DB_URL) as conn:
        conn.execute(
            """INSERT INTO requests (u_id, requested_at, home_city, handled_by, redirect_count, retries, status, reject_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", (u_id, requested_at, home_city or CITY, CITY, redirect_count, retries, status, reject_reason),
        )
        
@app.post("/reserve")
def reserve(req: ReserveRequest):
    home = req.home_city or CITY
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=req.arrive_in_min)
    end = start + timedelta(minutes=req.duration_min)
    
    try:
        port_id, retries = try_reserve(DB_URL, CITY, req.u_id, start, end)
        reason = "full" if port_id is None else None
    except psycopg.errors.SerializationFailure:
        port_id, retries, reason = None, 0, "contention"
    
    if port_id is not None:
        log_request(req.u_id, now, retries, "accepted", None, home, req.redirect_count)
        return {"status": "accepted", "port_id": port_id, "city": CITY, "redirects": req.redirect_count, "start": start.isoformat(), "end": end.isoformat(), "retries": retries}

    if req.redirect_count < MAX_REDIRECTS:
        target = NEIGHBORS[home][req.redirect_count]
        try:
            r = httpx.post(
                f"http://localhost:{API_PORTS[target]}/reserve", json={"u_id": req.u_id, "arrive_in_min": req.arrive_in_min, "duration_min": req.duration_min, "home_city": home, "redirect_count": req.redirect_count + 1}, timeout=10)
            r.raise_for_status()
            log_request(req.u_id, now, retries, "rejected", "redirected", home, req.redirect_count)
            return r.json()
        except httpx.HTTPError:
            reason = "neighbor_down"
        
        log_request(req.u_id, now, retries, "rejected", reason, home, req.redirect_count)    
        return {"status": "rejected", "reason": reason, "city": CITY}    

@app.get("/health")
def health():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as conn:
            ports = conn.execute("SELECT count(*) FROM ports").fetchone()[0]
        return {"city":CITY, "db":"up", "ports": ports}
    except Exception as e:
        return {"city":CITY, "db":"down", "error": str(e)}
    


