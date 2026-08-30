-- Every green-window pit stop in ONE race, INCLUDING outliers, with the flag
-- exposed so the caller can mask them client-side.
--
-- This is deliberately not queries/pit_cycle_by_race.sql: that one excludes
-- outliers in SQL (its documented contract, which notebooks rely on) and so
-- cannot drive a "show outliers" toggle. Same source table, same green-window
-- basis; the only difference is that the filter moves to the caller.
--
-- Times are milliseconds, as stored on pit_cycles.

SELECT
    pc.cust_id,
    d.driver_name,
    pc.stop_num,
    pc.in_lap,
    pc.out_lap,
    pc.n_pit_laps,
    pc.in_lap_time_ms,
    pc.out_lap_time_ms,
    pc.cycle_time_ms,
    pc.time_lost_ms,
    pc.window_pitters,
    pc.is_outlier
FROM pit_cycles pc
JOIN drivers d ON d.cust_id = pc.cust_id
WHERE pc.subsession_id = %(subsession_id)s
  AND pc.in_green_window
ORDER BY pc.time_lost_ms ASC;
