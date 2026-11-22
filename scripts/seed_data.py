from pathlib import Path
import psycopg
import json


DATA_DIR = Path("data")

CITIES = {
    "city1": {"sql_port": 26258, "total_ports": 310},
    "city2": {"sql_port": 26259, "total_ports": 200},
    "city3": {"sql_port": 26260, "total_ports": 112},
}

REAL_CITY = "city1"
REAL_LOT_NAME = "Caltech"
EXPECTED_STATIONS = 55
PORTS_PER_SYNTHETIC_LOT = 10

def db_url(city):
    return f"postgresql://root@localhost:{CITIES[city]['sql_port']}/{city}?sslmode=disable"

def load_real_stations():
    files = sorted(DATA_DIR.glob("acn_*.json"))
    if not files:
        raise SystemExit("No data found. Make sure to run from project root (ev-project).")
    
    station_ids = set()
    site_ids = set()
    for path in files:
        with open(path) as f:
            for s in json.load(f):
                if s.get("stationID") is not None:
                    station_ids.add(str(s["stationID"]))
                site_ids.add(str(s.get("siteID")).zfill(4))
    assert len(site_ids) == 1, f"{site_ids} fetched"
    if len(station_ids) != EXPECTED_STATIONS:
        raise SystemExit(f"Expected {EXPECTED_STATIONS} stations, got {len(station_ids)}.")
    return site_ids.pop(), sorted(station_ids)

def synthetic_plan(city, n_ports):
    tag = city.replace("city", "c")
    lots, ports = [], []
    for i in range(n_ports):
        lot_num = i//PORTS_PER_SYNTHETIC_LOT + 1
        slot = i % PORTS_PER_SYNTHETIC_LOT + 1
        lot_id = f"syn-{tag}-{lot_num:02d}"
        if slot == 1:
            lots.append((lot_id, f"Synthetic lot {tag}-{lot_num:02d}", city))
        ports.append((f"{lot_id}-p{slot:02d}", lot_id, city, city))
    return lots, ports

def seed_city(city, lots, ports, real=None):
    with psycopg.connect(db_url(city)) as conn:
        with conn.cursor() as cur:
            if real:
                real_lot_id, stations = real
                cur.execute(
                    "INSERT INTO lots (lot_id, lot_name, city) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (real_lot_id, REAL_LOT_NAME, city), 
                )
                cur.executemany(
                    "INSERT INTO ports (port_id, lot_id, home_city, booking_city) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", [(s, real_lot_id, city, city) for s in stations],
                )
            cur.executemany(
                "INSERT INTO lots (lot_id, lot_name, city) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", lots,
            )
            cur.executemany(
                "INSERT INTO ports (port_id, lot_id, home_city, booking_city) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING", ports,
            )
            cur.execute("SELECT count(*) FROM ports")
            return cur.fetchone()[0]
                

if __name__ == "__main__":
    # for city in CITIES:
    #     print(city, db_url(city), CITIES[city]["total_ports"])
    lot_id, stations = load_real_stations()
    print("real lot:", lot_id, "| stations: ", len(stations))
    # print("first: ", stations[0], "| last: ", stations[-1])
    
    for city, cfg in CITIES.items():
        # n_real = len(stations) if city == REAL_CITY else 0
        # lots, ports = synthetic_plan(city, cfg["total_ports"] - n_real)
        # print(f"{city}: {n_real} real + {len(ports)} synthetic in {len(lots)} lots"
        #       f"= {n_real + len(ports)} (target {cfg['total_ports']})")
        # print("\t\tfirst: ", ports[0][0], "| last: ", ports[-1][0])
        is_real = city == REAL_CITY
        n_real = len(stations) if is_real else 0
        lots, ports = synthetic_plan(city, cfg["total_ports"] - n_real)
        count = seed_city(city, lots, ports, real=(lot_id, stations) if is_real else None)
        status = "ok" if count == cfg["total_ports"] else "MISMATCH"
        print(f"{city}: {count} ports, target {cfg['total_ports']}, {status}")
                