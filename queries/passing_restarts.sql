-- Restart passing: who capitalizes on restarts and who struggles.
--
-- A restart is the first green lap after one or more caution laps; the restart
-- period is that lap and the next (the first 2 laps after the restart). Green
-- passes made/conceded during those laps measure restart racecraft, normalized
-- per restart the driver took part in. (The green-flag start of the race is not
-- counted as a restart.)
--
-- Requires a driver to have taken part in at least `min_restarts` restarts to
-- appear (tune in the params CTE).

WITH params AS (
    SELECT 8 AS min_restarts
),
lap_flags AS (
    SELECT DISTINCT subsession_id, lap_num, under_caution FROM lap_gaps
),
restart_laps AS (
    SELECT f.subsession_id, f.lap_num AS restart_lap
    FROM lap_flags f
    JOIN lap_flags p ON p.subsession_id = f.subsession_id AND p.lap_num = f.lap_num - 1
    WHERE NOT f.under_caution AND p.under_caution
),
period AS (   -- the two laps of each restart period
    SELECT subsession_id, restart_lap, restart_lap     AS lap_num FROM restart_laps
    UNION
    SELECT subsession_id, restart_lap, restart_lap + 1 AS lap_num FROM restart_laps
),
presence AS (   -- which drivers actually ran each restart period
    SELECT DISTINCT ra.season_id, pe.subsession_id, pe.restart_lap, l.cust_id
    FROM period pe
    JOIN laps l  ON l.subsession_id = pe.subsession_id AND l.lap_num = pe.lap_num
    JOIN races ra ON ra.subsession_id = pe.subsession_id
),
involved AS (
    SELECT season_id, cust_id, count(DISTINCT restart_lap) AS restarts
    FROM presence GROUP BY season_id, cust_id
),
green_restart AS (   -- green passes that happened inside a restart period
    SELECT ra.season_id, p.passer_cust_id, p.passed_cust_id
    FROM passes p
    JOIN period pe ON pe.subsession_id = p.subsession_id AND pe.lap_num = p.lap_num
    JOIN races ra  ON ra.subsession_id = p.subsession_id
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
made AS (
    SELECT season_id, passer_cust_id AS cust_id, count(*) AS n
    FROM green_restart GROUP BY season_id, passer_cust_id
),
conceded AS (
    SELECT season_id, passed_cust_id AS cust_id, count(*) AS n
    FROM green_restart GROUP BY season_id, passed_cust_id
)
SELECT
    s.season_name,
    d.driver_name,
    i.restarts,
    COALESCE(m.n, 0)                                                        AS restart_passes_made,
    COALESCE(c.n, 0)                                                        AS restart_passes_conceded,
    COALESCE(m.n, 0) - COALESCE(c.n, 0)                                     AS net,
    ROUND((COALESCE(m.n, 0) - COALESCE(c.n, 0))::numeric / i.restarts, 2)   AS net_per_restart,
    ROUND(COALESCE(m.n, 0)::numeric / i.restarts, 2)                        AS made_per_restart
FROM involved i
JOIN drivers d ON d.cust_id = i.cust_id
JOIN seasons s ON s.season_id = i.season_id
LEFT JOIN made     m ON m.season_id = i.season_id AND m.cust_id = i.cust_id
LEFT JOIN conceded c ON c.season_id = i.season_id AND c.cust_id = i.cust_id
CROSS JOIN params
WHERE i.restarts >= params.min_restarts
ORDER BY net_per_restart DESC;