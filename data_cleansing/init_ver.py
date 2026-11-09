import json
import pandas as pd

with open("../data/acndata_sessions.json") as f:
    data = json.load(f)

print("top-level keys:", list(data.keys()))
print("meta:", data.get("_meta"))

df = pd.DataFrame(data["_items"])
print("rows loaded:", len(df))

df["connectionTime"] = pd.to_datetime(df["connectionTime"], utc=True)
df["disconnectTime"] = pd.to_datetime(df["disconnectTime"], utc=True)
print("date range:", df["connectionTime"].min(), "to", df["connectionTime"].max())

print("distinct stationIDs:", df["stationID"].nunique())
print("siteIDs present:", df["siteID"].unique())

# slim version for the loader and generator
keep = ["sessionID", "siteID", "stationID", "spaceID",
        "connectionTime", "disconnectTime", "timezone"]
df[keep].to_csv("../data/caltech_sessions_slim.csv", index=False)