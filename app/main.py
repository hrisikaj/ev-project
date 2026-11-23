import os, psycopg, httpx
from fastapi import FastAPI
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from app.reserve import try_reserve
from app.lending import lend_ports, receive_ports

CITY = os.environ.get("CITY", "city1")

SQL_PORTS = {"city1": 26258, "city2": 26259, "city3": 26260}
DB_URL = f"postgresql://root@localhost:{SQL_PORTS[CITY]}/{CITY}?sslmode=disable"
API_PORTS = {"city1": 8001, "city2":8002, "city3": 8003}
NEIGHBORS = {"city1": ["city2", "city3"], "city2": ["city1", "city3"], "city3": ["city1", "city2"]}
MAX_REDIRECTS = int(os.environ.get("MAX_REDIRECTS", "1"))
LENDING = os.environ.get("LENDING", "off") == "on" # will be used to switch between Methods 1 and 2
LEND_BATCH = int(os.environ.get("LEND_BATCH", "5"))


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
        
def borrow_ports():
    for neighbor in NEIGHBORS[CITY]:
        try:
            r = httpx.post(f"http://localhost:{API_PORTS[neighbor]}/internal/lend", json={"to_city": CITY, "n": LEND_BATCH}, timeout = 10)
            r.raise_for_status()
            ports = [(p["port_id"], p["lot_id"]) for p in r.json()["ports"]]
        except httpx.HTTPError:
            continue
        if ports:
            return receive_ports(DB_URL, CITY, neighbor, ports)
    return 0
            
            
            
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
        
    if port_id is None and reason == "full" and LENDING and borrow_ports() > 0:
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


class LendRequest(BaseModel):
    to_city: str
    n: int = Field(default=5, gt=0)
    
@app.post("/internal/lend")
def lend(req: LendRequest):
    ports = lend_ports(DB_URL, CITY, req.to_city, req.n)
    return {"ports": [{"port_id": port, "lot_id": lot} for port, lot in ports]}


@app.get("/health")
def health():
    try:
        with psycopg.connect(DB_URL, connect_timeout=2) as conn:
            ports = conn.execute("SELECT count(*) FROM ports").fetchone()[0]
        return {"city":CITY, "db":"up", "ports": ports}
    except Exception as e:
        return {"city":CITY, "db":"down", "error": str(e)}
    


