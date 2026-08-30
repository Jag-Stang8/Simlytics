-- The finishing table for ONE race, with green passing and pit-cycle joined in.
--
-- driver_standings.sql is season-grained; this is the per-subsession equivalent
-- that the Session page's Result tab reads.
--
-- Positions in the data are 0-based (finish_pos = 0 is a win); `finish` and
-- `start` below are 1-based for display. `pos_gain` is places gained, so
-- positive is good.
--
-- Passing counts use the same green definition as queries/passing_*.sql: not a
-- pit-cycle artefact, not under caution. Pit delta uses the same basis as
-- pit_cycle_ranking.sql: green-window stops only, outliers excluded, median so a
-- single repair stop doesn't distort the driver.
--
-- Lap times (best_lap_time, avg_lap) stay in raw ten-thousandths of a second;
-- app/lib/fmt.py formats them.

WITH green AS (
    SELECT *
    FROM passes
    WHERE subsession_id = %(subsession_id)s
      AND NOT pit_cycle
      AND NOT under_caution
),
made AS (
    SELECT passer_cust_id AS cust_id,
           count(*)                                AS passes_made,
           count(*) FILTER (WHERE is_lead_change)  AS lead_passes
    FROM green GROUP BY passer_cust_id
),
conceded AS (
    SELECT passed_cust_id AS cust_id,
           count(*)                        AS passes_conceded,
           count(*) FILTER (WHERE reverted) AS passes_defended
    FROM green GROUP BY passed_cust_id
),
pit AS (
    SELECT cust_id,
           count(*)                                                       AS green_stops,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY time_lost_ms)      AS median_time_lost_ms,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY cycle_time_ms)     AS median_cycle_ms
    FROM pit_cycles
    WHERE subsession_id = %(subsession_id)s
      AND in_green_window
      AND NOT is_outlier
    GROUP BY cust_id
)
SELECT
    rr.cust_id,
    d.driver_name,
    rr.car_num,
    rr.finish_pos + 1                                   AS finish,
    rr.start_pos + 1                                    AS start,
    rr.start_pos - rr.finish_pos                        AS pos_gain,
    rr.laps_completed,
    rr.laps_led,
    rr.league_points,
    rr.incidents,
    rr.interval,
    rr.best_lap_time,
    rr.avg_lap,
    rc.reason_out,
    COALESCE(m.passes_made, 0)                          AS passes_made,
    COALESCE(c.passes_conceded, 0)                      AS passes_conceded,
    COALESCE(m.passes_made, 0)
        - COALESCE(c.passes_conceded, 0)                AS net_passes,
    COALESCE(c.passes_defended, 0)                      AS passes_defended,
    COALESCE(m.lead_passes, 0)                          AS lead_passes,
    p.green_stops,
    p.median_time_lost_ms,
    p.median_cycle_ms
FROM race_results rr
JOIN drivers d       ON d.cust_id = rr.cust_id
LEFT JOIN reason_codes rc ON rc.reason_out_id = rr.reason_out_id
LEFT JOIN made m     ON m.cust_id = rr.cust_id
LEFT JOIN conceded c ON c.cust_id = rr.cust_id
LEFT JOIN pit p      ON p.cust_id = rr.cust_id
WHERE rr.subsession_id = %(subsession_id)s
ORDER BY rr.finish_pos;
