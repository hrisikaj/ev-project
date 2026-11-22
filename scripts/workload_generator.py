"""
This script generates synthetic EV charging-session data and writes them to CSV.

No input files are needed. Values are generated based on the formatting found in the real ACN dataset

Output schema (same 13 columns as the ACN files):
    _id, userInputs, sessionID, stationID, spaceID, siteID, clusterID, connectionTime, disconnectTime, kWhDelivered, doneChargingTime, timezone, userID

Examples of running the file:
    python workload_generator.py                      # 10,000 sessions
    python workload_generator.py --count 5000 --seed 7
    python workload_generator.py --count 5000 --start 2019-01-01 --end 2019-12-31 --output data/acn_synthetic.csv
"""

import argparse
import csv
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = [
    "_id",
    "userInputs",
    "sessionID",
    "stationID",
    "spaceID",
    "siteID",
    "clusterID",
    "connectionTime",
    "disconnectTime",
    "kWhDelivered",
    "doneChargingTime",
    "timezone",
    "userID",
]

# These fields only had one value in the dataset, so we can hard-code them.
LA = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc
SITE_ID = "0002"
CLUSTER_ID = "0039"
TZ_NAME = "America/Los_Angeles"

# stationID -> spaceID, in the ACN formats
STATIONS = {
    "2-39-78-362": "CA-496", "2-39-95-27": "CA-319", "2-39-79-380": "CA-489",
    "2-39-79-379": "CA-327", "2-39-79-381": "CA-490", "2-39-139-28": "CA-303",
    "2-39-91-441": "CA-499", "2-39-79-377": "CA-325", "2-39-79-382": "CA-491",
    "2-39-78-366": "CA-323", "2-39-91-437": "CA-317", "2-39-78-361": "CA-493",
    "2-39-78-360": "CA-322", "2-39-125-21": "CA-311", "2-39-78-365": "CA-321",
    "2-39-138-29": "CA-304", "2-39-130-31": "CA-306", "2-39-138-566": "CA-512",
    "2-39-79-378": "CA-326", "2-39-127-19": "CA-309", "2-39-123-23": "CA-313",
    "2-39-79-376": "CA-324", "2-39-131-30": "CA-305", "2-39-126-20": "CA-310",
    "2-39-79-383": "CA-492", "2-39-78-367": "CA-494", "2-39-90-440": "CA-500",
    "2-39-81-4550": "11900388", "2-39-83-386": "CA-212", "2-39-89-25": "CA-315",
    "2-39-129-17": "CA-307",
}

N_USERS = 300
USER_ID_MAX = 10500
P_USER_INPUTS = 0.52     # share of sessions that have userInputs and userIDs that are not null
P_MISSING_DONE = 0.065   # share of sessions without doneChargingTime
MIN_KWH, MAX_KWH = 0.5, 77.7


def fmt_time(dt):
    #'2018-04-25 04:08:04-07:00' - example date format
    return dt.astimezone(LA).replace(microsecond=0).isoformat(sep=" ")


def random_wh_per_mile():
    # Typical Wh/mile of a car, 400 is the most common value.
    r = random.random()
    if r < 0.45:
        return 400
    if r < 0.60:
        return random.choice([250, 300, 350, 375])
    return random.randint(200, 600)


def random_kwh():
    kwh = random.lognormvariate(math.log(6.5), 0.9)
    return min(max(kwh, MIN_KWH), MAX_KWH)


def random_connection_time(start, end):
    # Pick a day and an arrival hour, places emphasis on weekdays because they are more likely than weekends
    num_days = (end - start).days + 1
    while True:
        day = start + timedelta(days=random.randrange(num_days))
        if day.weekday() < 5 or random.random() < 0.2:
            break
    if random.random() < 0.7:
        hour = random.gauss(8.5, 1.5)          # morning arrival
    else:
        hour = random.uniform(10, 19)          # later in the day
    hour = min(max(hour, 0), 23.99)
    local = datetime.combine(day, time(), tzinfo=LA) + timedelta(hours=hour)
    return local.astimezone(UTC), hour


def random_stay_hours(arrival_hour):
    # Most the cars stay until the end of the work day, the rest stay a few hours.
    if random.random() < 0.7:
        return max(1.0, random.gauss(17, 1.5) - arrival_hour)
    return random.lognormvariate(math.log(2.5), 0.6)


def make_entry(user_id, miles, wh_per_mile, modified, departure):
    minutes = max(60, math.ceil((departure - modified).total_seconds() / 60))
    return {
        "userID": user_id,
        "milesRequested": miles,
        "WhPerMile": wh_per_mile,
        "minutesAvailable": minutes,
        "modifiedAt": format_datetime(modified.replace(microsecond=0), usegmt=True),
        "paymentRequired": True,
        "requestedDeparture": format_datetime(departure.replace(microsecond=0), usegmt=True),
        "kWhRequested": round(miles * wh_per_mile / 1000, 2),
    }


def make_user_inputs(user_id, wh_per_mile, kwh, connected, disconnected):
    # What the driver typed into the app (a list with one or two entries).
    requested_kwh = kwh / random.uniform(0.5, 1.0)
    miles = max(10, round(requested_kwh * 1000 / wh_per_mile / 10) * 10)

    modified = connected + timedelta(minutes=random.uniform(0, 20))
    departure = disconnected + timedelta(minutes=random.gauss(0, 20))
    departure = max(departure, modified + timedelta(minutes=60))

    entries = [make_entry(user_id, miles, wh_per_mile, modified, departure)]
    if random.random() < 0.25:
        # the app default (20 miles, 400 Wh/mile, 60 minutes) before the driver edits it
        first = connected + timedelta(minutes=random.uniform(0, 5))
        default_departure = first + timedelta(minutes=60)
        entries.insert(0, make_entry(user_id, 20, 400, first, default_departure))
    return entries


def make_session(start, end, users, user_wh, counter):
    connected, hour = random_connection_time(start, end)
    kwh = random_kwh()

    # the stay has to be long enough to deliver the energy
    charge_hours = kwh / random.uniform(2.5, 6.5)
    stay_hours = max(random_stay_hours(hour), charge_hours * 1.05, 0.25)
    disconnected = connected + timedelta(hours=stay_hours)

    user_inputs, user_id = "", ""
    if random.random() < P_USER_INPUTS:
        uid = random.choice(users)
        user_inputs = str(make_user_inputs(uid, user_wh[uid], kwh, connected, disconnected))
        user_id = f"{uid:09d}"

    done = ""
    if random.random() >= P_MISSING_DONE:
        done = fmt_time(connected + timedelta(hours=charge_hours))

    station = random.choice(list(STATIONS))
    object_id = f"{int(disconnected.timestamp()):08x}f9af8b{random.randrange(0x10000):04x}{counter:06x}"

    return {
        "_id": object_id,
        "userInputs": user_inputs,
        "sessionID": f"{station.replace('-', '_')}_{connected.strftime('%Y-%m-%d %H:%M:%S.%f')}",
        "stationID": station,
        "spaceID": STATIONS[station],
        "siteID": SITE_ID,
        "clusterID": CLUSTER_ID,
        "connectionTime": fmt_time(connected),
        "disconnectTime": fmt_time(disconnected),
        "kWhDelivered": f"{kwh:.3f}",
        "doneChargingTime": done,
        "timezone": TZ_NAME,
        "userID": user_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic ACN-style charging sessions.")
    parser.add_argument("--count", type=int, default=10000, help="number of sessions (default 10000)")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2018, 4, 25), help="first day, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, default=date(2021, 9, 14), help="last day, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible output")
    parser.add_argument("--output", type=Path, default=Path("data/acn_synthetic.csv"))
    args = parser.parse_args()

    random.seed(args.seed)
    users = random.sample(range(1, USER_ID_MAX + 1), N_USERS)
    user_wh = {uid: random_wh_per_mile() for uid in users}

    counter = random.randrange(0x1000000)
    rows = []
    for _ in range(args.count):
        counter = (counter + 1) % 0x1000000
        rows.append(make_session(args.start, args.end, users, user_wh, counter))
    rows.sort(key=lambda row: row["connectionTime"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} rows to {args.output}")


if __name__ == "__main__":
    main()