-- Passing profile per track: how much (and what kind of) passing each venue
-- produces, plus the opportunity conversion rate there.
--
-- green_per_race normalizes by the number of races with lap data at the track.
-- conversion_pct uses the same 1%-of-a-lap opportunity threshold as
-- passing_conversion.sql (tune in the params CTE); note the threshold means
-- something tighter at short tracks than at superspeedways.

WITH params AS (
    SELECT 0.01::float AS max_gap_pct
),
per_track_pass AS (
    SELECT
        ra.track_id,
        count(DISTINCT p.subsession_id)                                        AS races,
        count(*) FILTER (WHERE NOT p.under_caution AND NOT p.pit_cycle)         AS green_passes,
        count(*) FILTER (WHERE p.pit_cycle AND NOT p.under_caution)            AS pit_passes,
        count(*) FILTER (WHERE p.under_caution)                                AS caution_passes
    FROM passes p
    JOIN races ra ON ra.subsession_id = p.subsession_id
    GROUP BY ra.track_id
),
opp AS (
    SELECT ra.track_id, g.subsession_id, g.lap_num, g.cust_id, g.car_ahead_cust_id
    FROM lap_gaps g
    JOIN races ra ON ra.subsession_id = g.subsession_id
    CROSS JOIN params
    WHERE g.same_lap AND NOT g.under_caution AND NOT g.pit_cycle
      AND g.car_ahead_cust_id IS NOT NULL
      AND g.gap_pct IS NOT NULL AND g.gap_pct > 0 AND g.gap_pct < params.max_gap_pct
),
opp_conv AS (
    SELECT o.track_id,
           count(*)         AS opportunities,
           count(p.pass_id) AS converted
    FROM opp o
    LEFT JOIN passes p
      ON p.subsession_id = o.subsession_id
     AND p.lap_num = o.lap_num + 1
     AND p.passer_cust_id = o.cust_id
     AND p.passed_cust_id = o.car_ahead_cust_id
     AND NOT p.pit_cycle AND NOT p.under_caution
    GROUP BY o.track_id
)
SELECT
    t.track_name,
    t.track_config_name,
    tc.category,
    ptp.races,
    ptp.green_passes,
    ROUND(ptp.green_passes::numeric / ptp.races, 1)                        AS green_per_race,
    ptp.pit_passes,
    ptp.caution_passes,
    oc.opportunities,
    ROUND(100.0 * oc.converted / NULLIF(oc.opportunities, 0), 1)          AS conversion_pct
FROM per_track_pass ptp
JOIN tracks t ON t.track_id = ptp.track_id
LEFT JOIN track_categories tc ON tc.category_id = t.category_id
LEFT JOIN opp_conv oc ON oc.track_id = ptp.track_id
ORDER BY green_per_race DESC;