from dataclasses import dataclass
from datetime import datetime

# The iRacing event-result JSON wraps everything under a top-level "data" key,
# while the lap-chart JSON does not. Parsers accept the raw file dict and unwrap
# as needed.
#
# "season" here means the *league* season (league_season_id / league_season_name):
# the plain season_id is 0 for hosted league races and is not a usable key.


@dataclass
class ParsedRaceResult:
    cust_id: int
    subsession_id: int
    avg_lap: int
    best_lap_num: int
    best_lap_time: int
    car_id: int
    finish_pos: int
    incidents: int
    interval: int
    laps_completed: int
    laps_led: int
    league_points: int
    reason_out_id: int
    start_pos: int
    car_num: str
    drop_race: bool

@dataclass
class ParsedRaceSummary:
    subsession_id: int
    average_lap: int
    laps_completed: int
    num_cautions: int
    num_caution_laps: int
    num_lead_changes: int
    sof: int

@dataclass
class ParsedTrackState:
    subsession_id: int
    leave_marbles: bool
    race_rubber: int

@dataclass
class ParsedWeather:
    subsession_id: int
    allow_fog: bool
    fog: int
    precip_before_final_session: int
    precip_final_session: int
    precip_option: int
    precip_time_pct: int
    rel_humidity: int
    simulated_start_time: datetime
    skies: int
    temp_units: int
    temp_values: int
    time_of_day: int
    track_water: int
    type: int
    version: int
    weather_var_initial: int
    weather_var_ongoing: int
    wind_dir: int
    wind_units: int
    wind_value: int

@dataclass
class ParsedLeagueEntry:
    league_id: int
    cust_id: int
    car_num: str
    member_since: datetime | None = None

@dataclass
class ParsedLap:
    cust_id: int
    subsession_id: int
    lap_num: int
    flags: int
    incident: bool
    session_time: int
    laptime: int
    position: int
    interval: int | None
    interval_units: str | None

@dataclass
class ParsedLapEvent:
    subsession_id: int
    cust_id: int
    lap_num: int
    lap_event: str

@dataclass
class ParsedDriver:
    cust_id: int
    driver_name: str

@dataclass
class ParsedCar:
    car_id: int
    car_name: str

@dataclass
class ParsedRace:
    subsession_id: int
    season_id: int
    track_id: int
    start_time: str

@dataclass
class ParsedReasonCode:
    reason_out_id: int
    reason_out: str

@dataclass
class ParsedTrack:
    track_id: int
    track_name: str
    track_config_name: str
    category_id: int
    track_config_length: float | None = None

@dataclass
class ParsedSeason:
    season_id: int
    season_name: str
    league_id: int

@dataclass
class ParsedLeague:
    league_id: int
    league_name: str

@dataclass
class ParsedTrackCategory:
    category_id: int
    category: str

def _data(raw_json: dict) -> dict:
    """Unwrap the top-level "data" key from an event-result payload."""
    return raw_json.get("data", raw_json)


def _race_session(data: dict) -> dict:
    """Return the Race simsession from an event-result payload (empty if none)."""
    for session in data.get("session_results", []):
        if session.get("simsession_type_name") == "Race":
            return session
    return {}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_race_results(raw_json: dict) -> list[ParsedRaceResult]:
    data = _data(raw_json)
    subsession_id = data["subsession_id"]
    results = []
    for r in _race_session(data).get("results", []):
        results.append(
            ParsedRaceResult(
                cust_id=r["cust_id"],
                subsession_id=subsession_id,
                avg_lap=r.get("average_lap"),
                best_lap_num=r.get("best_lap_num"),
                best_lap_time=r.get("best_lap_time"),
                car_id=r.get("car_id"),
                finish_pos=r.get("finish_position"),
                incidents=r.get("incidents"),
                interval=r.get("interval"),
                laps_completed=r.get("laps_complete"),
                laps_led=r.get("laps_lead") or 0,
                league_points=r.get("league_points") or 0,
                reason_out_id=r.get("reason_out_id"),
                start_pos=r.get("starting_position"),
                car_num=r.get("livery", {}).get("car_number", ""),
                drop_race=r.get("drop_race", False),
            )
        )
    return results


def parse_race_summary(raw_json: dict) -> ParsedRaceSummary:
    data = _data(raw_json)
    summary = data.get("race_summary", {})
    return ParsedRaceSummary(
        subsession_id=data["subsession_id"],
        average_lap=summary.get("average_lap"),
        laps_completed=summary.get("laps_complete"),
        num_cautions=summary.get("num_cautions"),
        num_caution_laps=summary.get("num_caution_laps"),
        num_lead_changes=summary.get("num_lead_changes"),
        sof=summary.get("field_strength"),
    )


def parse_track_state(raw_json: dict) -> ParsedTrackState:
    data = _data(raw_json)
    state = data.get("track_state", {})
    return ParsedTrackState(
        subsession_id=data["subsession_id"],
        leave_marbles=state.get("leave_marbles"),
        race_rubber=state.get("race_rubber"),
    )


def parse_weather(raw_json: dict) -> ParsedWeather:
    data = _data(raw_json)
    w = data.get("weather", {})
    return ParsedWeather(
        subsession_id=data["subsession_id"],
        allow_fog=w.get("allow_fog"),
        fog=w.get("fog"),
        precip_before_final_session=w.get("precip_mm2hr_before_final_session"),
        precip_final_session=w.get("precip_mm_final_session"),
        precip_option=w.get("precip_option"),
        precip_time_pct=w.get("precip_time_pct"),
        rel_humidity=w.get("rel_humidity"),
        simulated_start_time=_parse_dt(w.get("simulated_start_time")),
        skies=w.get("skies"),
        temp_units=w.get("temp_units"),
        temp_values=w.get("temp_value"),
        time_of_day=w.get("time_of_day"),
        track_water=w.get("track_water"),
        type=w.get("type"),
        version=w.get("version"),
        weather_var_initial=w.get("weather_var_initial"),
        weather_var_ongoing=w.get("weather_var_ongoing"),
        wind_dir=w.get("wind_dir"),
        wind_units=w.get("wind_units"),
        wind_value=w.get("wind_value"),
    )


def parse_race(raw_json: dict) -> ParsedRace:
    data = _data(raw_json)
    return ParsedRace(
        subsession_id=data["subsession_id"],
        season_id=data.get("league_season_id"),
        track_id=data.get("track", {}).get("track_id"),
        start_time=data.get("start_time"),
    )


def parse_track(raw_json: dict) -> ParsedTrack:
    data = _data(raw_json)
    track = data.get("track", {})
    return ParsedTrack(
        track_id=track.get("track_id"),
        track_name=track.get("track_name"),
        track_config_name=track.get("config_name"),
        category_id=track.get("category_id"),
        track_config_length=track.get("track_config_length"),
    )


def parse_track_category(raw_json: dict) -> ParsedTrackCategory:
    data = _data(raw_json)
    track = data.get("track", {})
    return ParsedTrackCategory(
        category_id=track.get("category_id"),
        category=track.get("category"),
    )


def parse_season(raw_json: dict) -> ParsedSeason:
    data = _data(raw_json)
    return ParsedSeason(
        season_id=data.get("league_season_id"),
        season_name=data.get("league_season_name"),
        league_id=data.get("league_id"),
    )


def parse_league(raw_json: dict) -> ParsedLeague:
    data = _data(raw_json)
    return ParsedLeague(
        league_id=data.get("league_id"),
        league_name=data.get("league_name"),
    )


def parse_drivers(raw_json: dict) -> list[ParsedDriver]:
    data = _data(raw_json)
    drivers: dict[int, ParsedDriver] = {}
    for r in _race_session(data).get("results", []):
        cust_id = r["cust_id"]
        if cust_id not in drivers:
            drivers[cust_id] = ParsedDriver(
                cust_id=cust_id,
                driver_name=r.get("display_name"),
            )
    return list(drivers.values())


def parse_cars(raw_json: dict) -> list[ParsedCar]:
    data = _data(raw_json)
    cars: dict[int, ParsedCar] = {}
    for r in _race_session(data).get("results", []):
        car_id = r.get("car_id")
        if car_id is not None and car_id not in cars:
            cars[car_id] = ParsedCar(car_id=car_id, car_name=r.get("car_name"))
    return list(cars.values())


def parse_reason_codes(raw_json: dict) -> list[ParsedReasonCode]:
    data = _data(raw_json)
    codes: dict[int, ParsedReasonCode] = {}
    for r in _race_session(data).get("results", []):
        reason_out_id = r.get("reason_out_id")
        if reason_out_id is not None and reason_out_id not in codes:
            codes[reason_out_id] = ParsedReasonCode(
                reason_out_id=reason_out_id,
                reason_out=r.get("reason_out"),
            )
    return list(codes.values())


def parse_league_entries(raw_json: dict) -> list[ParsedLeagueEntry]:
    data = _data(raw_json)
    league_id = data.get("league_id")
    entries: dict[int, ParsedLeagueEntry] = {}
    for r in _race_session(data).get("results", []):
        cust_id = r["cust_id"]
        if cust_id not in entries:
            entries[cust_id] = ParsedLeagueEntry(
                league_id=league_id,
                cust_id=cust_id,
                car_num=r.get("livery", {}).get("car_number", ""),
            )
    return list(entries.values())


def parse_laps(raw_json: dict) -> list[ParsedLap]:
    """Parse the wide-format lap-chart payload into one row per driver-lap."""
    data = _data(raw_json)
    subsession_id = data["subsession_id"]
    laps = []
    for driver in data.get("lapData", []):
        for key, cell in driver.items():
            if not key.startswith("lap_") or not isinstance(cell, dict):
                continue
            laps.append(
                ParsedLap(
                    cust_id=cell["cust_id"],
                    subsession_id=subsession_id,
                    lap_num=cell.get("lap_number"),
                    flags=cell.get("flags"),
                    incident=cell.get("incident"),
                    session_time=cell.get("session_time"),
                    laptime=cell.get("lap_time"),
                    position=cell.get("lap_position"),
                    interval=cell.get("interval"),
                    interval_units=cell.get("interval_units"),
                )
            )
    return laps


def parse_lap_events(raw_json: dict) -> list[ParsedLapEvent]:
    """Extract one row per event tagged on a lap (pitted, off-track, etc.)."""
    data = _data(raw_json)
    subsession_id = data["subsession_id"]
    events = []
    for driver in data.get("lapData", []):
        for key, cell in driver.items():
            if not key.startswith("lap_") or not isinstance(cell, dict):
                continue
            for event in cell.get("lap_events", []):
                events.append(
                    ParsedLapEvent(
                        subsession_id=subsession_id,
                        cust_id=cell["cust_id"],
                        lap_num=cell.get("lap_number"),
                        lap_event=event,
                    )
                )
    return events
