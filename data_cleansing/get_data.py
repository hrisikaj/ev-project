import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from acnportal.acndata import DataClient

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = "caltech"

load_dotenv(ROOT / ".env")
TOKEN = os.getenv("ACN_API_KEY")
if not TOKEN:
    sys.exit("No API key found. Check the variable name in .env")

# usage: fetch sessions
if len(sys.argv) > 1:
    years = [int(sys.argv[1])]
else:
    years = list(range(2011, 2026))

client = DataClient(TOKEN)
DATA.mkdir(exist_ok=True)
summary = []

for year in years:
    out_path = DATA / f"acn_{year}.json"
    if out_path.exists():
        print(f"{year}: {out_path.name} already exists, skipping (delete it to refetch)")
        continue

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    print(f"{year}: fetching...", flush=True)
    sessions = list(client.get_sessions_by_time(SITE, start=start, end=end))
    print(f"{year}: fetched {len(sessions)}", flush=True)

    if not sessions:
        print(f"{year}: no sessions, not saving")
        continue

    with open(out_path, "w") as f:
        json.dump(sessions, f, default=str)
    summary.append((year, len(sessions)))

print("\nSummary")
for year, fetched in summary:
    print(f"  {year}: {fetched}")
print("Total fetched:", sum(s[1] for s in summary))