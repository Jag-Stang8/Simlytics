-- One ordered feed of everything that happened in a race: passes, pit stops,
-- caution starts and restarts. Powers the Timeline tab's event list.
--
-- Every row is (lap_num, kind, cust_id, other_cust_id, detail, sort_key) so the
-- feed is one list the UI can filter by kind, and a lap slice is a row filter.
--
-- Caution and restart laps come from lap_gaps.under_caution, the same source the
-- position lines shade -- see queries/race_running_order.sql for why that is read
-- back rather than re-derived. Note it is a heuristic (stats/passes.py), so these
-- are derived cautions, not the sanctioning body's.

WITH lap_state AS (
    SELECT lap_num, bool_or(under_caution) AS under_caution
    FROM lap_gaps
    WHERE subsession_id = %(subsession_id)s
    GROUP BY lap_num
),
flagged AS (
    SELECT lap_num, under_caution,
           LAG(under_caution) OVER (ORDER BY lap_num) AS prev_caution
    FROM lap_state
),
passes_feed AS (
    SELECT p.lap_num,
           CASE WHEN p.is_lead_change THEN 'lead_change' ELSE 'pass' END AS kind,
           p.passer_cust_id  AS cust_id,
           p.passed_cust_id  AS other_cust_id,
           CASE WHEN p.reverted THEN 'reverted' ELSE NULL END AS detail,
           p.passer_pos + 1  AS position,
           2                 AS sort_key
    FROM passes p
    WHERE p.subsession_id = %(subsession_id)s
      AND NOT p.pit_cycle AND NOT p.under_caution
),
pit_feed AS (
    SELECT pc.in_lap AS lap_num,
           'pit'     AS kind,
           pc.cust_id,
           NULL::int AS other_cust_id,
           CASE WHEN pc.is_outlier THEN 'outlier'
                WHEN pc.in_green_window THEN 'green window'
                ELSE NULL END AS detail,
           NULL::int AS position,
           3         AS sort_key
    FROM pit_cycles pc
    WHERE pc.subsession_id = %(subsession_id)s
),
caution_feed AS (
    SELECT lap_num, 'caution' AS kind, NULL::int, NULL::int, NULL::text, NULL::int, 0
    FROM flagged
    WHERE under_caution AND (prev_caution IS DISTINCT FROM true)
    UNION ALL
    SELECT lap_num, 'restart' AS kind, NULL::int, NULL::int, NULL::text, NULL::int, 1
    FROM flagged
    WHERE NOT under_caution AND prev_caution
)
SELECT f.lap_num, f.kind, f.cust_id, f.other_cust_id, f.detail, f.position,
       d.driver_name,
       o.driver_name AS other_driver_name
FROM (
    SELECT * FROM passes_feed
    UNION ALL SELECT * FROM pit_feed
    UNION ALL SELECT * FROM caution_feed
) f
LEFT JOIN drivers d ON d.cust_id = f.cust_id
LEFT JOIN drivers o ON o.cust_id = f.other_cust_id
ORDER BY f.lap_num, f.sort_key, f.position NULLS LAST;
