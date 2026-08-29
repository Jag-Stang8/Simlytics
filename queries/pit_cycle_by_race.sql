-- Green-flag pit-cycle data for a single race. Pass :subsession_id as a parameter
-- (e.g. run_query_file('pit_cycle_by_race.sql', {'subsession_id': 83742118})).
--
-- One row per green stop made inside a real pit window, ranked by time lost
-- (cycle time minus what the in-lap + out-lap would have taken at the median
-- green lap). A driver can appear more than once if they made multiple stops.

SELECT
    d.driver_name,
    pc.stop_num,
    pc.in_lap,
    pc.out_lap,
    pc.n_pit_laps,
    round((pc.in_lap_time_ms  / 1000)::numeric, 2) AS in_lap_s,
    round((pc.out_lap_time_ms / 1000)::numeric, 2) AS out_lap_s,
    round((pc.cycle_time_ms   / 1000)::numeric, 2) AS cycle_s,
    round((pc.time_lost_ms    / 1000)::numeric, 2) AS time_lost_s,
    pc.window_pitters
FROM pit_cycles pc
JOIN drivers d ON d.cust_id = pc.cust_id
WHERE pc.subsession_id = %(subsession_id)s
  AND pc.in_green_window
  AND NOT pc.is_outlier      -- repair/stall/penalty stops excluded (see stats/pit_cycles.py)
ORDER BY pc.time_lost_ms ASC;