"""Persistence layer: write parsed rows into the normalized schema.

Every loader upserts (ON CONFLICT DO UPDATE) so re-ingesting the same file is
idempotent. Callers must respect FK ordering (dimensions before facts, races
before laps, laps before lap_events); ingest.py encodes that order.
"""
from psycopg.types.json import Jsonb

from .parsers import (
    ParsedCar,
    ParsedDriver,
    ParsedLap,
    ParsedLapEvent,
    ParsedLeague,
    ParsedLeagueEntry,
    ParsedRace,
    ParsedRaceResult,
    ParsedRaceSummary,
    ParsedReasonCode,
    ParsedSeason,
    ParsedTrack,
    ParsedTrackCategory,
    ParsedTrackState,
    ParsedWeather,
)


def load_raw_json(conn, subsession_id: int, file_type: str, raw_json: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_results (subsession_id, file_type, raw_json, ingested_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (subsession_id, file_type) DO UPDATE
                SET raw_json = EXCLUDED.raw_json, ingested_at = now();
            """,
            (subsession_id, file_type, Jsonb(raw_json)),
        )


# Dimensions -----------------------------------------------------------------

def load_league(conn, league: ParsedLeague) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leagues (league_id, league_name)
            VALUES (%s, %s)
            ON CONFLICT (league_id) DO UPDATE
                SET league_name = EXCLUDED.league_name;
            """,
            (league.league_id, league.league_name),
        )


def load_season(conn, season: ParsedSeason) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO seasons (season_id, season_name, league_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (season_id) DO UPDATE
                SET season_name = EXCLUDED.season_name,
                    league_id = EXCLUDED.league_id;
            """,
            (season.season_id, season.season_name, season.league_id),
        )


def load_track_category(conn, category: ParsedTrackCategory) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO track_categories (category_id, category)
            VALUES (%s, %s)
            ON CONFLICT (category_id) DO UPDATE
                SET category = EXCLUDED.category;
            """,
            (category.category_id, category.category),
        )


def load_track(conn, track: ParsedTrack) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tracks
                (track_id, track_name, track_config_name, category_id, track_config_length)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (track_id) DO UPDATE
                SET track_name = EXCLUDED.track_name,
                    track_config_name = EXCLUDED.track_config_name,
                    category_id = EXCLUDED.category_id,
                    track_config_length = EXCLUDED.track_config_length;
            """,
            (
                track.track_id,
                track.track_name,
                track.track_config_name,
                track.category_id,
                track.track_config_length,
            ),
        )


def load_cars(conn, cars: list[ParsedCar]) -> None:
    if not cars:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO cars (car_id, car_name)
            VALUES (%s, %s)
            ON CONFLICT (car_id) DO UPDATE
                SET car_name = EXCLUDED.car_name;
            """,
            [(c.car_id, c.car_name) for c in cars],
        )


def load_drivers(conn, drivers: list[ParsedDriver]) -> None:
    if not drivers:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO drivers (cust_id, driver_name)
            VALUES (%s, %s)
            ON CONFLICT (cust_id) DO UPDATE
                SET driver_name = EXCLUDED.driver_name;
            """,
            [(d.cust_id, d.driver_name) for d in drivers],
        )


def load_reason_codes(conn, codes: list[ParsedReasonCode]) -> None:
    if not codes:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO reason_codes (reason_out_id, reason_out)
            VALUES (%s, %s)
            ON CONFLICT (reason_out_id) DO UPDATE
                SET reason_out = EXCLUDED.reason_out;
            """,
            [(r.reason_out_id, r.reason_out) for r in codes],
        )


def load_league_entries(conn, entries: list[ParsedLeagueEntry]) -> None:
    if not entries:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO league_entries (league_id, cust_id, car_num, member_since)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (league_id, cust_id) DO UPDATE
                SET car_num = EXCLUDED.car_num,
                    member_since = EXCLUDED.member_since;
            """,
            [(e.league_id, e.cust_id, e.car_num, e.member_since) for e in entries],
        )


# Facts ----------------------------------------------------------------------

def load_race(conn, race: ParsedRace) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO races (subsession_id, season_id, track_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (subsession_id) DO UPDATE
                SET season_id = EXCLUDED.season_id,
                    track_id = EXCLUDED.track_id;
            """,
            (race.subsession_id, race.season_id, race.track_id),
        )


def load_race_summary(conn, summary: ParsedRaceSummary) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO race_summary
                (subsession_id, average_lap, laps_completed, num_cautions,
                 num_caution_laps, num_lead_changes, sof)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (subsession_id) DO UPDATE
                SET average_lap = EXCLUDED.average_lap,
                    laps_completed = EXCLUDED.laps_completed,
                    num_cautions = EXCLUDED.num_cautions,
                    num_caution_laps = EXCLUDED.num_caution_laps,
                    num_lead_changes = EXCLUDED.num_lead_changes,
                    sof = EXCLUDED.sof;
            """,
            (
                summary.subsession_id,
                summary.average_lap,
                summary.laps_completed,
                summary.num_cautions,
                summary.num_caution_laps,
                summary.num_lead_changes,
                summary.sof,
            ),
        )


def load_track_state(conn, state: ParsedTrackState) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO track_state (subsession_id, leave_marbles, race_rubber)
            VALUES (%s, %s, %s)
            ON CONFLICT (subsession_id) DO UPDATE
                SET leave_marbles = EXCLUDED.leave_marbles,
                    race_rubber = EXCLUDED.race_rubber;
            """,
            (state.subsession_id, state.leave_marbles, state.race_rubber),
        )


def load_weather(conn, weather: ParsedWeather) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO weather
                (subsession_id, allow_fog, fog, precip_before_final_session,
                 precip_final_session, precip_option, precip_time_pct, rel_humidity,
                 simulated_start_time, skies, temp_units, temp_values, time_of_day,
                 track_water, type, version, weather_var_initial, weather_var_ongoing,
                 wind_dir, wind_units, wind_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s)
            ON CONFLICT (subsession_id) DO UPDATE SET
                allow_fog = EXCLUDED.allow_fog,
                fog = EXCLUDED.fog,
                precip_before_final_session = EXCLUDED.precip_before_final_session,
                precip_final_session = EXCLUDED.precip_final_session,
                precip_option = EXCLUDED.precip_option,
                precip_time_pct = EXCLUDED.precip_time_pct,
                rel_humidity = EXCLUDED.rel_humidity,
                simulated_start_time = EXCLUDED.simulated_start_time,
                skies = EXCLUDED.skies,
                temp_units = EXCLUDED.temp_units,
                temp_values = EXCLUDED.temp_values,
                time_of_day = EXCLUDED.time_of_day,
                track_water = EXCLUDED.track_water,
                type = EXCLUDED.type,
                version = EXCLUDED.version,
                weather_var_initial = EXCLUDED.weather_var_initial,
                weather_var_ongoing = EXCLUDED.weather_var_ongoing,
                wind_dir = EXCLUDED.wind_dir,
                wind_units = EXCLUDED.wind_units,
                wind_value = EXCLUDED.wind_value;
            """,
            (
                weather.subsession_id,
                weather.allow_fog,
                weather.fog,
                weather.precip_before_final_session,
                weather.precip_final_session,
                weather.precip_option,
                weather.precip_time_pct,
                weather.rel_humidity,
                weather.simulated_start_time,
                weather.skies,
                weather.temp_units,
                weather.temp_values,
                weather.time_of_day,
                weather.track_water,
                weather.type,
                weather.version,
                weather.weather_var_initial,
                weather.weather_var_ongoing,
                weather.wind_dir,
                weather.wind_units,
                weather.wind_value,
            ),
        )


def load_race_results(conn, results: list[ParsedRaceResult]) -> None:
    if not results:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO race_results
                (subsession_id, cust_id, avg_lap, best_lap_num, best_lap_time, car_id,
                 finish_pos, incidents, interval, laps_completed, laps_led,
                 league_points, reason_out_id, start_pos, car_num, drop_race)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (subsession_id, cust_id) DO UPDATE SET
                avg_lap = EXCLUDED.avg_lap,
                best_lap_num = EXCLUDED.best_lap_num,
                best_lap_time = EXCLUDED.best_lap_time,
                car_id = EXCLUDED.car_id,
                finish_pos = EXCLUDED.finish_pos,
                incidents = EXCLUDED.incidents,
                interval = EXCLUDED.interval,
                laps_completed = EXCLUDED.laps_completed,
                laps_led = EXCLUDED.laps_led,
                league_points = EXCLUDED.league_points,
                reason_out_id = EXCLUDED.reason_out_id,
                start_pos = EXCLUDED.start_pos,
                car_num = EXCLUDED.car_num,
                drop_race = EXCLUDED.drop_race;
            """,
            [
                (
                    r.subsession_id,
                    r.cust_id,
                    r.avg_lap,
                    r.best_lap_num,
                    r.best_lap_time,
                    r.car_id,
                    r.finish_pos,
                    r.incidents,
                    r.interval,
                    r.laps_completed,
                    r.laps_led,
                    r.league_points,
                    r.reason_out_id,
                    r.start_pos,
                    r.car_num,
                    r.drop_race,
                )
                for r in results
            ],
        )


def load_laps(conn, laps: list[ParsedLap]) -> None:
    if not laps:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO laps
                (subsession_id, cust_id, lap_num, flags, incident, session_time,
                 laptime, position, interval, interval_units)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (subsession_id, cust_id, lap_num) DO UPDATE SET
                flags = EXCLUDED.flags,
                incident = EXCLUDED.incident,
                session_time = EXCLUDED.session_time,
                laptime = EXCLUDED.laptime,
                position = EXCLUDED.position,
                interval = EXCLUDED.interval,
                interval_units = EXCLUDED.interval_units;
            """,
            [
                (
                    lap.subsession_id,
                    lap.cust_id,
                    lap.lap_num,
                    lap.flags,
                    lap.incident,
                    lap.session_time,
                    lap.laptime,
                    lap.position,
                    # null on grid/pit cells with no interval; stored as-is.
                    lap.interval,
                    lap.interval_units,
                )
                for lap in laps
            ],
        )


def load_lap_events(conn, subsession_id: int, events: list[ParsedLapEvent]) -> None:
    # lap_events has a surrogate PK and a composite FK onto laps, so re-ingesting
    # replaces the subsession's rows wholesale rather than upserting.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM lap_events WHERE subsession_id = %s;", (subsession_id,))
        if not events:
            return
        cur.executemany(
            """
            INSERT INTO lap_events (subsession_id, cust_id, lap_num, lap_event)
            VALUES (%s, %s, %s, %s);
            """,
            [(e.subsession_id, e.cust_id, e.lap_num, e.lap_event) for e in events],
        )