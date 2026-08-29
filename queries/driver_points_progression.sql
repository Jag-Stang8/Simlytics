-- Cumulative championship points after each round, per driver.
--
-- Races are ordered chronologically by subsession_id (iRacing assigns these
-- monotonically, so a higher id is a later race); `round` is the 1-based race
-- number within the season. Use this to chart how the title fight evolved.

SELECT
    s.season_name,
    DENSE_RANK() OVER (
        PARTITION BY ra.season_id ORDER BY ra.subsession_id
    )                                            AS round,
    ra.subsession_id,
    d.driver_name,
    rr.finish_pos + 1                            AS finish,
    rr.league_points                             AS race_points,
    SUM(rr.league_points) OVER (
        PARTITION BY ra.season_id, rr.cust_id
        ORDER BY ra.subsession_id
    )                                            AS cumulative_points
FROM race_results rr
JOIN races ra   ON ra.subsession_id = rr.subsession_id
JOIN drivers d  ON d.cust_id = rr.cust_id
JOIN seasons s  ON s.season_id = ra.season_id
ORDER BY ra.season_id, round, cumulative_points DESC;