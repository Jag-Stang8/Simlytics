-- Drop-week driver standings: each driver's worst N results are dropped, and the
-- championship is ranked on the remaining (net) points.
--
-- Set the number of drops in the `params` CTE below.
--
-- Drops are COMPUTED here from finishing points (worst results first), not read
-- from race_results.drop_race: iRacing leaves that flag false in the current data.
-- A race already flagged drop_race = true by iRacing is always dropped, and counts
-- toward the N; ties in points drop the worse finish first.

WITH params AS (
    SELECT 2 AS drops              -- <-- number of worst results to drop per driver
),
ranked AS (
    SELECT
        ra.season_id,
        rr.cust_id,
        rr.subsession_id,
        rr.league_points,
        rr.finish_pos,
        rr.drop_race,
        ROW_NUMBER() OVER (
            PARTITION BY ra.season_id, rr.cust_id
            -- iRacing-flagged drops sort first, then worst points, then worst finish
            ORDER BY rr.drop_race DESC, rr.league_points ASC, rr.finish_pos DESC
        ) AS worst_rank
    FROM race_results rr
    JOIN races ra ON ra.subsession_id = rr.subsession_id
),
scored AS (
    SELECT
        r.*,
        (r.drop_race OR r.worst_rank <= (SELECT drops FROM params)) AS dropped
    FROM ranked r
)
SELECT
    s.season_name,
    RANK() OVER (
        PARTITION BY sc.season_id
        ORDER BY COALESCE(SUM(sc.league_points) FILTER (WHERE NOT sc.dropped), 0) DESC
    )                                                          AS pos,
    d.driver_name,
    COUNT(*)                                                   AS races,
    COUNT(*) FILTER (WHERE sc.dropped)                         AS races_dropped,
    SUM(sc.league_points)                                      AS gross_points,
    COALESCE(SUM(sc.league_points) FILTER (WHERE sc.dropped), 0)     AS points_dropped,
    COALESCE(SUM(sc.league_points) FILTER (WHERE NOT sc.dropped), 0) AS net_points
FROM scored sc
JOIN drivers d ON d.cust_id = sc.cust_id
JOIN seasons s ON s.season_id = sc.season_id
GROUP BY s.season_name, sc.season_id, d.cust_id, d.driver_name
ORDER BY sc.season_id, net_points DESC, gross_points DESC;