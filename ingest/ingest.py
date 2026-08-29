import argparse
import json
from pathlib import Path

from db.connection import connection
from . import loader, parsers

EVENTRESULT = "eventresult"
LAP_CHART = "lap_chart"


def detect_file_type(raw_json: dict) -> str:
    """Classify an iRacing JSON payload by its shape."""
    if "lapData" in raw_json:
        return LAP_CHART
    if "data" in raw_json and "session_results" in raw_json["data"]:
        return EVENTRESULT
    raise ValueError("Unrecognized iRacing JSON: expected a lap chart or event result")


def ingest_eventresult_json(conn, raw_json: dict) -> int:
    """Load an event-result payload: raw JSON, then dimensions, then facts."""
    subsession_id = raw_json["data"]["subsession_id"]
    loader.load_raw_json(conn, subsession_id, EVENTRESULT, raw_json)

    # Dimensions first (FK targets for the facts below).
    loader.load_league(conn, parsers.parse_league(raw_json))
    loader.load_season(conn, parsers.parse_season(raw_json))
    loader.load_track_category(conn, parsers.parse_track_category(raw_json))
    loader.load_track(conn, parsers.parse_track(raw_json))
    loader.load_cars(conn, parsers.parse_cars(raw_json))
    loader.load_drivers(conn, parsers.parse_drivers(raw_json))
    loader.load_reason_codes(conn, parsers.parse_reason_codes(raw_json))

    # Facts.
    loader.load_race(conn, parsers.parse_race(raw_json))
    loader.load_race_summary(conn, parsers.parse_race_summary(raw_json))
    loader.load_track_state(conn, parsers.parse_track_state(raw_json))
    loader.load_weather(conn, parsers.parse_weather(raw_json))
    loader.load_race_results(conn, parsers.parse_race_results(raw_json))
    loader.load_league_entries(conn, parsers.parse_league_entries(raw_json))
    return subsession_id


def ingest_lap_chart_json(conn, raw_json: dict) -> int:
    """Load a lap-chart payload. The matching event result must already be
    ingested, since laps/lap_events have FKs onto races, drivers, and laps."""
    subsession_id = raw_json["subsession_id"]
    loader.load_raw_json(conn, subsession_id, LAP_CHART, raw_json)
    loader.load_laps(conn, parsers.parse_laps(raw_json))
    loader.load_lap_events(conn, subsession_id, parsers.parse_lap_events(raw_json))
    return subsession_id


def ingest_file(path: Path) -> None:
    """Ingest a single JSON file in its own transaction."""
    raw_json = json.loads(path.read_text(encoding="utf-8"))
    file_type = detect_file_type(raw_json)
    with connection() as conn:
        if file_type == EVENTRESULT:
            subsession_id = ingest_eventresult_json(conn, raw_json)
        else:
            subsession_id = ingest_lap_chart_json(conn, raw_json)
    print(f"Ingested {file_type} for subsession {subsession_id} ({path.name})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest iRacing result JSON into Postgres")
    ap.add_argument("paths", type=Path, nargs="+", help="JSON file(s) to ingest")
    args = ap.parse_args()

    # Event results must land before lap charts so the FK targets exist; sort so a
    # mixed batch (e.g. a whole directory) ingests in a valid order.
    def sort_key(path: Path) -> int:
        try:
            raw_json = json.loads(path.read_text(encoding="utf-8"))
            return 0 if detect_file_type(raw_json) == EVENTRESULT else 1
        except (ValueError, json.JSONDecodeError):
            return 2  # let ingest_file surface the real error

    for path in sorted(args.paths, key=sort_key):
        try:
            ingest_file(path)
        except Exception as exc:  # keep going on a bad file in a batch
            print(f"FAILED {path.name}: {exc}")


if __name__ == "__main__":
    main()