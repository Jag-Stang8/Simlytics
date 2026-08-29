-- "What-if" standings: net points and championship position at 0, 1, 2, and 3
-- drops, side by side, so you can see how the title picture shifts with the drop
-- count. Rows are ordered by the no-drops (gross) standings; pos_gain_0_to_3 is
-- how many places a driver climbs going from 0 drops to 3 (negative = falls).
--
-- Drops are the worst results by points (iRacing-flagged drop_race rows drop
-- first and count toward the total); ties drop the worse finish first.

WITH ranked AS (
    SELECT
        ra.season_id,
        rr.cust_id,
        rr.league_points,
        rr.drop_race,
        ROW_NUMBER() OVER (
            PARTITION BY ra.season_id, rr.cust_id
            ORDER BY rr.drop_race DESC, rr.league_points ASC, rr.finish_pos DESC
        ) AS worst_rank
    FROM race_results rr
    JOIN races ra ON ra.subsession_id = rr.subsession_id
),
netted AS (
    SELECT
        season_id,
        cust_id,
        COALESCE(SUM(league_points) FILTER (WHERE NOT drop_race), 0)                    AS net_d0,
        COALESCE(SUM(league_points) FILTER (WHERE NOT (drop_race OR worst_rank <= 1)), 0) AS net_d1,
        COALESCE(SUM(league_points) FILTER (WHERE NOT (drop_race OR worst_rank <= 2)), 0) AS net_d2,
        COALESCE(SUM(league_points) FILTER (WHERE NOT (drop_race OR worst_rank <= 3)), 0) AS net_d3
    FROM ranked
    GROUP BY season_id, cust_id
),
ranks AS (
    SELECT
        n.*,
        RANK() OVER (PARTITION BY season_id ORDER BY net_d0 DESC) AS pos_d0,
        RANK() OVER (PARTITION BY season_id ORDER BY net_d1 DESC) AS pos_d1,
        RANK() OVER (PARTITION BY season_id ORDER BY net_d2 DESC) AS pos_d2,
        RANK() OVER (PARTITION BY season_id ORDER BY net_d3 DESC) AS pos_d3
    FROM netted n
)
SELECT
    s.season_name,
    d.driver_name,
    r.pos_d0, r.net_d0,
    r.pos_d1, r.net_d1,
    r.pos_d2, r.net_d2,
    r.pos_d3, r.net_d3,
    (r.pos_d0 - r.pos_d3) AS pos_gain_0_to_3
FROM ranks r
JOIN drivers d ON d.cust_id = r.cust_id
JOIN seasons s ON s.season_id = r.season_id
ORDER BY r.season_id, r.net_d0 DESC;