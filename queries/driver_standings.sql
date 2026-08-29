-- Driver championship standings, one row per driver per season.
--
-- Points are the sum of race_results.league_points. Positions in the data are
-- 0-based: finish_pos = 0 is a win, start_pos = 0 is pole; the avg/best columns
-- below add 1 so the output reads as human 1-based positions.
--
-- NOTE: this sums every race. iRacing "drop weeks" are not applied because the
-- per-result drop_race flag is not currently stored in race_results.

WITH results AS (
    SELECT rr.*, ra.season_id
    FROM race_results rr
    JOIN races ra ON ra.subsession_id = rr.subsession_id
)
SELECT
    s.season_name,
    RANK() OVER (
        PARTITION BY r.season_id
        ORDER BY SUM(r.league_points) DESC
    )                                            AS pos,
    d.driver_name,
    COUNT(*)                                     AS races,
    SUM(r.league_points)                         AS points,
    COUNT(*) FILTER (WHERE r.finish_pos = 0)     AS wins,
    COUNT(*) FILTER (WHERE r.finish_pos <= 2)    AS podiums,
    COUNT(*) FILTER (WHERE r.finish_pos <= 4)    AS top5,
    COUNT(*) FILTER (WHERE r.finish_pos <= 9)    AS top10,
    COUNT(*) FILTER (WHERE r.start_pos = 0)      AS poles,
    SUM(r.laps_led)                              AS laps_led,
    SUM(r.incidents)                             AS incidents,
    ROUND(AVG(r.finish_pos + 1), 2)              AS avg_finish,
    ROUND(AVG(r.start_pos + 1), 2)               AS avg_start,
    MIN(r.finish_pos) + 1                        AS best_finish
FROM results r
JOIN drivers d ON d.cust_id = r.cust_id
JOIN seasons s ON s.season_id = r.season_id
GROUP BY s.season_name, r.season_id, d.cust_id, d.driver_name
ORDER BY r.season_id, points DESC, wins DESC, podiums DESC, avg_finish ASC;