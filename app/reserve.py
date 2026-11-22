import random
import time
import psycopg
from psycopg import errors

MAX_RETRIES = 50

FREE_PORT_SQL = """SELECT p.port_id FROM ports p where p.booking_city = %(city)s AND NOT EXISTS (
    SELECT 1 FROM reservations r WHERE r.port_id = p.port_id AND r.start_time < %(end)s AND r.end_time > %(start)s
    ) ORDER BY random() LIMIT 1
    """
    
INSERT_SQL = """INSERT INTO RESERVATIONS (port_id, u_id, start_time, end_time, booked_by) VALUES (%(port)s, %(u_id)s, %(start)s, %(end)s, %(city)s)"""

def try_reserve(db_url, city, u_id, start, end):
    retries = 0
    params = {"city": city, "u_id": u_id, "start": start, "end": end}
    with psycopg.connect(db_url) as conn:
        conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        while True:
            try:
                with conn.transaction():
                    row = conn.execute(FREE_PORT_SQL, params).fetchone()
                    if row is None:
                        return None, retries
                    conn.execute(INSERT_SQL, {**params, "port": row[0]})
                    return row[0], retries
            except errors.SerializationFailure:
                retries += 1
                if retries > MAX_RETRIES:
                    raise
                time.sleep(random.uniform(0, 0.02*retries))