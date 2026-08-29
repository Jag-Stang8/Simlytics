-- Green-flag pit-cycle ranking: who cycles through the pits fastest.
--
-- Uses only stops flagged in_green_window (a real green pit cycle where a
-- significant portion of the field pit within a few laps), from pit_cycles.
-- Ranks by MEDIAN time lost per driver -- median so a one-off damage/repair stop
-- doesn't distort the driver, and time_lost (cycle minus what those laps would
-- have taken at the median green lap) so tracks with different lap lengths are
-- comparable. Requires >= min_stops green stops to appear.

WITH params AS (
    SELECT 4 AS min_stops
),
pc AS (
    SELECT ra.season_id, pc.cust_id, pc.cycle_time_ms, pc.time_lost_ms
    FROM pit_cycles pc
    JOIN races ra ON ra.subsession_id = pc.subsession_id
    WHERE pc.in_green_window AND NOT pc.is_outlier
)
SELECT
    s.season_name,
    d.driver_name,
    count(*)                                                                        AS green_stops,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY pc.cycle_time_ms) / 1000)::numeric, 2)  AS median_cycle_s,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY pc.time_lost_ms) / 1000)::numeric, 2)   AS median_time_lost_s,
    round((min(pc.time_lost_ms) / 1000)::numeric, 2)                                AS best_time_lost_s,
    round((avg(pc.time_lost_ms) / 1000)::numeric, 2)                                AS avg_time_lost_s
FROM pc
JOIN drivers d ON d.cust_id = pc.cust_id
JOIN seasons s ON s.season_id = pc.season_id
CROSS JOIN params
GROUP BY s.season_name, pc.season_id, d.cust_id, d.driver_name, params.min_stops
HAVING count(*) >= params.min_stops
ORDER BY pc.season_id, median_time_lost_s ASC;