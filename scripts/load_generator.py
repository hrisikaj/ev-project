
"""
load_generator.py

Step 3: Reservation Request Format

Converts ACN workload CSV records into JSON payloads
compatible with Hrisika's reservation API schema.

Required CSV fields:
    _id
    sessionID
    spaceID
    siteID
    connectionTime
    disconnectTime
    timezone

Usage:
    python3 scripts/load_generator.py --csv PATH_TO_CSV

Optional API testing:
    python3 scripts/load_generator.py --csv PATH_TO_CSV --send
"""

import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd


SITE_TO_CITY = {
    "2": "city1"
}


SPACE_TO_PORT = {}

# API endpoints for the three city servers.
CITY_API_URLS = {
    "city1": "http://localhost:8001",
    "city2": "http://localhost:8002",
    "city3": "http://localhost:8003",
}

REQUIRED_COLUMNS = [
    "_id",
    "sessionID",
    "spaceID",
    "siteID",
    "connectionTime",
    "disconnectTime",
    "timezone",
]


def generate_user_id(session_id):
    """
    Generates a deterministic integer user ID
    from the ACN session ID.

    The same session ID always produces the same user ID.
    """

    hashed = hashlib.sha256(
        str(session_id).encode("utf-8")
    ).hexdigest()

    return int(hashed[:8], 16)


def convert_timestamp(timestamp, timezone):
    """
    Converts an ACN timestamp into an ISO 8601 string.

    If the timestamp is timezone-naive, the timezone
    provided by the ACN dataset is applied.
    """

    if pd.isna(timestamp):
        raise ValueError("Missing timestamp")

    parsed = pd.Timestamp(timestamp)

    if parsed.tzinfo is None:
        if pd.isna(timezone) or not str(timezone).strip():
            raise ValueError("Missing timezone for timestamp")

        parsed = parsed.tz_localize(str(timezone))

    return parsed.isoformat()

def build_reservation_request(row):
    """
    Converts one ACN CSV record into the JSON payload
    expected by the reservation API.
    """

    site_id = str(row["siteID"])

    if site_id not in SITE_TO_CITY:
        raise ValueError(
            f"No city mapping configured for siteID: {site_id}"
        )

    city = SITE_TO_CITY.get(str(row["siteID"]))
    space_id = str(row["spaceID"])

    # Use an explicit port mapping if one exists.
    # Otherwise, use the original ACN spaceID.
    port_id = SPACE_TO_PORT.get(space_id, space_id)

    request = {
        "req_id": str(row["_id"]),
        "u_id": generate_user_id(row["sessionID"]),
        "home_city": city,
        "port_id": port_id,
        "start_time": convert_timestamp(
            row["connectionTime"],
            row["timezone"]
        ),
        "end_time": convert_timestamp(
            row["disconnectTime"],
            row["timezone"]
        )
    }

    return request

def validate_request(request):
    """
    Validates the generated reservation request.
    """

    assert request["req_id"], "Missing request ID"

    assert isinstance(
        request["u_id"], int
    ), "User ID must be an integer"

    assert request["home_city"] in (
        "city1", "city2", "city3"
    ), "Invalid home city"

    assert request["port_id"], "Missing port ID"

    start = pd.Timestamp(request["start_time"])
    end = pd.Timestamp(request["end_time"])

    assert end > start, "End time must be after start time"

    return True



def load_workload(csv_path):
    """
    Loads the ACN workload CSV and verifies its columns.
    """

    df = pd.read_csv(csv_path)

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"CSV is missing required columns: {missing_columns}"
        )

    print(f"Loaded {len(df)} workload records.")

    return df


def generate_requests(df):
    """
    Converts CSV records into reservation requests.

    Invalid records are skipped and reported.
    """

    requests = []
    invalid_records = 0

    seen_ids = set()

    for index, row in df.iterrows():

        try:
            request = build_reservation_request(row)

            validate_request(request)

            if request["req_id"] in seen_ids:
                raise ValueError("Duplicate request ID")

            seen_ids.add(request["req_id"])
            requests.append(request)

        except (ValueError, AssertionError, TypeError) as error:

            print(
                f"Skipping row {index}: {error}"
            )

            invalid_records += 1

    print("\nRequest Generation Summary")
    print("--------------------------")
    print(f"Total CSV records:       {len(df)}")
    print(f"Valid requests:          {len(requests)}")
    print(f"Invalid records:         {invalid_records}")

    return requests


def submit_request(request):
    """
    Sends a reservation request to its home city API.

    The API endpoint is assumed to be POST /reserve.
    """

    import httpx

    city = request["home_city"]

    api_url = CITY_API_URLS[city]

    response = httpx.post(
        f"{api_url}/reserve",
        json=request,
        timeout=10.0
    )

    response.raise_for_status()

    return response.json()


def main():

    parser = argparse.ArgumentParser(
        description="Generate ACN reservation requests."
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the synthetic ACN workload CSV."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of sample requests to display."
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Submit requests to the city APIs."
    )

    args = parser.parse_args()

    # Load CSV
    df = load_workload(args.csv)

    # Display available site IDs for configuring mappings
    print("\nAvailable ACN site IDs:")
    print(df["siteID"].dropna().astype(str).unique())

    if not SITE_TO_CITY:
        raise ValueError(
            "\nConfigure SITE_TO_CITY at the top of "
            "load_generator.py before generating requests."
        )

    # Generate requests
    requests = generate_requests(df)

    # Display sample requests
    print("\nSample Reservation Requests")
    print("---------------------------")

    for request in requests[:args.limit]:
        print(json.dumps(request, indent=4))

    # Optional API submission
    if args.send:

        print("\nSubmitting reservation requests...")

        successful = 0
        failed = 0

        for request in requests:

            try:
                result = submit_request(request)

                print(
                    f"{request['req_id']}: "
                    f"{result.get('status', 'unknown')}"
                )

                successful += 1

            except Exception as error:

                print(
                    f"{request['req_id']}: ERROR - {error}"
                )

                failed += 1

        print("\nAPI Submission Summary")
        print("----------------------")
        print(f"Successful: {successful}")
        print(f"Failed:     {failed}")


if __name__ == "__main__":
    main()
