import random, time, psycopg
from psycopg import errors

MAX_RETRIES = 20

LEND_SQL = """UPDATE ports SET booking_city = %(to_city)s WHERE port_id IN(
    SELECT p.port_id FROM ports p WHERE p.home_city = %(city)s AND p.booking_city = %(city)s AND NOT EXISTS (
        SELECT 1 FROM reservations r WHERE r.port_id = p.port_id AND r.end_time > now()
        )
    ORDER BY random()
    LIMIT %(n)s
    )
RETURNING port_id, lot_id"""

def lend_ports(db_url, city, to_city, n):
    retries = 0
    with psycopg.connect(db_url) as conn:
        conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        while True:
            try:
                with conn.transaction():
                    rows = conn.execute(
                        LEND_SQL, {"city": city, "to_city": to_city, "n": n}).fetchall()
                    return rows
            except errors.SerializationFailure:
                retries += 1
                if retries > MAX_RETRIES:
                    raise
                time.sleep(random.uniform(0, 0.02*retries))
                
def receive_ports(db_url, city, from_city, ports):
    with psycopg.connect(db_url) as conn:
        with conn.transaction():
            for lot_id in {lot for _, lot in ports}:
                conn.execute(
                    "INSERT INTO lots (lot_id, lot_name, city) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING", (lot_id, lot_id, from_city)
                )
            for port_id, lot_id in ports:
                conn.execute(
                    "INSERT INTO ports(port_id, lot_id, home_city, booking_city) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (port_id) DO UPDATE SET booking_city = excluded.booking_city", (port_id, lot_id, from_city, city)
                )
    return len(ports)