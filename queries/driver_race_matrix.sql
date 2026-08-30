-- Per driver, per race: every counting stat the Time frame page needs.
--
-- Grain is (subsession_id, cust_id) and everything here is a COUNT or a raw
-- value, never a ratio -- so any date range is just a row filter, and rates
-- (conversion rate, defense rate, net per race) are recomputed by summing numerator
-- and denominator over the selected races. That is what lets the range picker
-- re-slice without re-querying.
--
-- Definitions match the season-grained queries:
--   green pass       -- queries/passing_leaderboard.sql (not pit_cycle, not under_caution)
--   opportunity      -- queries/passing_score.sql (same-lap, green, gap_pct < max_gap_pct)
--   restart window   -- queries/passing_score.sql (the restart lap and the one after)
--   pit delta        -- queries/pit_cycle_ranking.sql (green window, outliers excluded)
--
-- Lap times stay in raw ten-thousandths; pit columns are milliseconds.

WITH params AS (
    SELECT 0.01::float AS max_gap_pct
),
scope AS (
    SELECT ra.subsession_id, ra.season_id, ra.start_time,
           ROW_NUMBER() OVER (PARTITION BY ra.season_id ORDER BY ra.start_time) AS round,
           t.track_name, t.track_config_name
    FROM races ra
    JOIN tracks t ON t.track_id = ra.track_id
    WHERE %(season_id)s::int IS NULL
       OR ra.season_id = %(season_id)s::int
),
green AS (
    SELECT p.* FROM passes p
    JOIN scope s ON s.subsession_id = p.subsession_id
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
made AS (
    SELECT subsession_id, passer_cust_id AS cust_id, count(*) AS passes_made
    FROM green GROUP BY 1, 2
),
conceded AS (
    SELECT subsession_id, passed_cust_id AS cust_id,
           count(*) AS passes_conceded,
           count(*) FILTER (WHERE reverted) AS passes_defended_revert
    FROM green GROUP BY 1, 2
),
opp AS (
    SELECT g.subsession_id, g.lap_num, g.cust_id, g.car_ahead_cust_id
    FROM lap_gaps g
    JOIN scope s ON s.subsession_id = g.subsession_id
    CROSS JOIN params
    WHERE g.same_lap AND NOT g.under_caution AND NOT g.pit_cycle
      AND g.car_ahead_cust_id IS NOT NULL
      AND g.gap_pct > 0 AND g.gap_pct < params.max_gap_pct
),
conv AS (
    SELECT o.*, (p.pass_id IS NOT NULL) AS converted
    FROM opp o
    LEFT JOIN passes p
      ON p.subsession_id = o.subsession_id AND p.lap_num = o.lap_num + 1
     AND p.passer_cust_id = o.cust_id AND p.passed_cust_id = o.car_ahead_cust_id
     AND NOT p.pit_cycle AND NOT p.under_caution
),
attack AS (
    SELECT subsession_id, cust_id,
           count(*) AS opportunities,
           count(*) FILTER (WHERE converted) AS conversions
    FROM conv GROUP BY 1, 2
),
defense AS (
    SELECT subsession_id, car_ahead_cust_id AS cust_id,
           count(*) AS faced,
           count(*) FILTER (WHERE NOT converted) AS defended
    FROM conv GROUP BY 1, 2
),
lap_flags AS (
    SELECT DISTINCT g.subsession_id, g.lap_num, g.under_caution
    FROM lap_gaps g JOIN scope s ON s.subsession_id = g.subsession_id
),
restart_laps AS (
    SELECT f.subsession_id, f.lap_num AS restart_lap
    FROM lap_flags f
    JOIN lap_flags p ON p.subsession_id = f.subsession_id AND p.lap_num = f.lap_num - 1
    WHERE NOT f.under_caution AND p.under_caution
),
period AS (
    SELECT subsession_id, restart_lap, restart_lap     AS lap_num FROM restart_laps
    UNION
    SELECT subsession_id, restart_lap, restart_lap + 1 AS lap_num FROM restart_laps
),
rs_involved AS (
    SELECT pe.subsession_id, l.cust_id, count(DISTINCT pe.restart_lap) AS restarts
    FROM period pe
    JOIN laps l ON l.subsession_id = pe.subsession_id AND l.lap_num = pe.lap_num
    GROUP BY 1, 2
),
rs_green AS (
    SELECT p.subsession_id, p.passer_cust_id, p.passed_cust_id
    FROM passes p
    JOIN period pe ON pe.subsession_id = p.subsession_id AND pe.lap_num = p.lap_num
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
rs_made AS (
    SELECT subsession_id, passer_cust_id AS cust_id, count(*) AS restart_made
    FROM rs_green GROUP BY 1, 2
),
rs_conc AS (
    SELECT subsession_id, passed_cust_id AS cust_id, count(*) AS restart_conceded
    FROM rs_green GROUP BY 1, 2
),
pit AS (
    SELECT pc.subsession_id, pc.cust_id,
           count(*) AS green_stops,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY pc.time_lost_ms) AS median_time_lost_ms
    FROM pit_cycles pc
    JOIN scope s ON s.subsession_id = pc.subsession_id
    WHERE pc.in_green_window AND NOT pc.is_outlier
    GROUP BY 1, 2
)
SELECT
    sc.season_id,
    sc.subsession_id,
    sc.round,
    sc.start_time,
    sc.track_name,
    sc.track_config_name,
    rr.cust_id,
    d.driver_name,
    rr.finish_pos + 1                       AS finish,
    rr.start_pos + 1                        AS start,
    rr.start_pos - rr.finish_pos            AS pos_gain,
    rr.league_points,
    rr.laps_completed,
    rr.laps_led,
    rr.incidents,
    COALESCE(m.passes_made, 0)              AS passes_made,
    COALESCE(c.passes_conceded, 0)          AS passes_conceded,
    COALESCE(m.passes_made, 0)
        - COALESCE(c.passes_conceded, 0)    AS net_passes,
    COALESCE(a.opportunities, 0)            AS opportunities,
    COALESCE(a.conversions, 0)              AS conversions,
    COALESCE(df.faced, 0)                   AS faced,
    COALESCE(df.defended, 0)                AS defended,
    COALESCE(ri.restarts, 0)                AS restarts,
    COALESCE(rm.restart_made, 0)            AS restart_made,
    COALESCE(rc.restart_conceded, 0)        AS restart_conceded,
    p.green_stops,
    p.median_time_lost_ms
FROM race_results rr
JOIN scope sc        ON sc.subsession_id = rr.subsession_id
JOIN drivers d       ON d.cust_id = rr.cust_id
LEFT JOIN made m     ON m.subsession_id = rr.subsession_id AND m.cust_id = rr.cust_id
LEFT JOIN conceded c ON c.subsession_id = rr.subsession_id AND c.cust_id = rr.cust_id
LEFT JOIN attack a   ON a.subsession_id = rr.subsession_id AND a.cust_id = rr.cust_id
LEFT JOIN defense df ON df.subsession_id = rr.subsession_id AND df.cust_id = rr.cust_id
LEFT JOIN rs_involved ri ON ri.subsession_id = rr.subsession_id AND ri.cust_id = rr.cust_id
LEFT JOIN rs_made rm ON rm.subsession_id = rr.subsession_id AND rm.cust_id = rr.cust_id
LEFT JOIN rs_conc rc ON rc.subsession_id = rr.subsession_id AND rc.cust_id = rr.cust_id
LEFT JOIN pit p      ON p.subsession_id = rr.subsession_id AND p.cust_id = rr.cust_id
ORDER BY sc.round, rr.finish_pos;
