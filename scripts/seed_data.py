import json
from pathlib import Path
from collections import Counter, defaultdict

import psycopg

DATA_DIR = Path("data")
DB_URL = "postgresql://root@localhost:26258/city1?sslmode=disable"
LOT_NAME = "Caltech"
CITY = "city1"
EXPECTED_STATIONS = 55


def load_sessions():
    """Return session dicts from every data/acn_*.json file."""
    files = sorted(DATA_DIR.glob("acn_*.json"))
    if not files:
        raise SystemExit("No data/acn_*.json found. Run from ~/ev-project.")
    sessions = []
    for path in files:
        with open(path) as f:
            batch = json.load(f)
        print(f"{path.name}: {len(batch)} sessions")
        sessions.extend(batch)
    return sessions


def collect_station_ids(sessions):
    """Return the set of distinct stationID values as strings."""
    raw = {s.get("stationID") for s in sessions}
    if None in raw:
        print("warning: some sessions have a null stationID; ignoring them")
        raw.discard(None)
    return {str(x) for x in raw}


def collect_site_id(sessions):
    """Return the single siteID in the data (expect '0002')."""
    sites = {str(s.get("siteID")).zfill(4) for s in sessions}
    assert len(sites) == 1, f"expected one siteID, got {sites}"
    return sites.pop()


def seed(lot_id, station_ids):
    rows = [(station, lot_id, CITY) for station in sorted(station_ids)]
    with psycopg.connect(DB_URL) as conn:  # commits on clean exit
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lots (lot_id, lot_name, city) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (lot_id, LOT_NAME, CITY),
            )
            cur.executemany(
                "INSERT INTO ports (port_id, lot_id, booking_city) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                rows,
            )
            cur.execute("SELECT count(*) FROM ports")
            print("ports in city1 after seeding:", cur.fetchone()[0])


def main():
    sessions = load_sessions()
    print("sessions loaded:", len(sessions))

    station_ids = collect_station_ids(sessions)
    lot_id = collect_site_id(sessions)
    print("distinct stations:", len(station_ids))
    print("site id:", lot_id)

    # TEMP diagnostic: remove once the 55 vs 54 question is settled
    counts = Counter()
    years = defaultdict(set)
    for path in sorted(DATA_DIR.glob("acn_*.json")):
        year = path.stem.split("_")[1]
        for s in json.load(open(path)):
            sid = str(s.get("stationID"))
            counts[sid] += 1
            years[sid].add(year)

    for sid in sorted(counts):
        print(repr(sid), counts[sid], sorted(years[sid]))

    if len(station_ids) != EXPECTED_STATIONS:
        raise SystemExit(
            f"Expected {EXPECTED_STATIONS} stations, got {len(station_ids)}. "
            "Check the data before seeding."
        )

    seed(lot_id, station_ids)
    print("seeded")

if __name__ == "__main__":
    main()