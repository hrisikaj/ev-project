from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from app.reserve import try_reserve
import psycopg

CITY = "city3"
DB_URL = "postgresql://root@localhost:26260/city3?sslmode=disable"
N_REQUESTS = 400
WORKERS = 50

DOUBLE_BOOK_SQL = """ SELECT count(*) FROM reservations a JOIN reservations b ON a.port_id = b.port_id AND a.r_id < b.r_id AND a.start_time < b.end_time AND a.end_time > b.start_time"""

def main():
    with psycopg.connect(DB_URL) as conn:
        conn.execute("DELETE FROM reservations")
        
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(hours=1)
    
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda u: try_reserve(DB_URL, CITY, u, start, end), range(N_REQUESTS)))
    accepted = sum(1 for port, _ in results if port is not None)
    retries = sum(r for _, r in results)
    
    with psycopg.connect(DB_URL) as conn:
        stored = conn.execute("SELECT count(*) FROM reservations").fetchone()[0]
        doubles = conn.execute(DOUBLE_BOOK_SQL).fetchone()[0]
        
    print(f"accepted: {accepted} | rejected: {N_REQUESTS - accepted} | stored: {stored}")
    print(f"serialization retries: {retries} | double bookings: {doubles}")
    ok = accepted == stored == 112 and doubles == 0
    print("Pass" if ok else "Fail")

if __name__ == "__main__":
    main()        
    