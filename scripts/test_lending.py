from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import httpx, psycopg

SQL_PORTS = {"city1": 26258, "city2": 26259, "city3": 26260}
N_REQUESTS = 200

def url(city):
    return f"postgresql://root@localhost:{SQL_PORTS[city]}/{city}?sslmode=disable"

def reset():
    for city in SQL_PORTS:
        with psycopg.connect(url(city)) as conn:
            conn.execute("DELETE FROM reservations")
            conn.execute("DELETE FROM requests")
            conn.execute("DELETE FROM ports WHERE home_city <> %s", (city,))
            conn.execute("DELETE FROM lots WHERE city <> %s", (city,))
            conn.execute("UPDATE ports SET booking_city = home_city")

def send(u_id):
    r = httpx.post("http://localhost:8001/reserve", json={"u_id": u_id}, timeout=60)
    try:
        return r.json()
    except ValueError:
        return {"status": "error", "http": r.status_code, "reason": r.text[:60], "city": None}

def main():
    reset()
    with psycopg.connect(url("city1")) as conn:
        conn.execute(
            "INSERT INTO reservations (port_id, u_id, start_time, end_time, booked_by) "
            "SELECT port_id, 0, now(), now() + interval '2 hours', 'city1' FROM ports"
        )
    
    with ThreadPoolExecutor(max_workers=40) as pool:
        results = list(pool.map(send, range(1, N_REQUESTS + 1)))
        
    outcomes = Counter((r["status"], r.get("city"), r.get("redirects", 0), r.get("reason")) for r in results)
    
    print("outcomes (status, city, redirects, reason): count")
    for k, v in sorted(outcomes.items(), key=str):
        print(" ", k, v)
        
    by_port = defaultdict(list)
    for city in SQL_PORTS:
        with psycopg.connect(url(city)) as conn:
            for port_id, s, e, in conn.execute("SELECT port_id, start_time, end_time FROM reservations"):
                by_port[port_id].append((s, e, city))
    
    doubles = 0
    for port_id, rows in by_port.items():
        rows.sort()
        for (s1, e1, _), (s2, e2, _) in zip(rows, rows[1:]):
            if s2 < e1:
                doubles += 1
                print("DOUBLE BOOKING: ", port_id, rows)
    accepted = sum(1 for r in results if r["status"] == "accepted")
    
    print(f"accepted:{accepted}/{N_REQUESTS} | double bookings: {doubles}")
    print("pass" if doubles == 0 else "fail")
                
if __name__ == "__main__":
    main()