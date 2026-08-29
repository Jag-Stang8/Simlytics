-- Overall passing score: a weighted blend of four standardized passing skills,
-- one row per driver per season, ranked.
--
-- Components (all green-flag; per driver per season):
--   racecraft -> net green passes per race
--   attack    -> opportunity conversion %
--   defense   -> % of opportunities faced that were repelled
--   restart   -> net green passes per restart (first 2 laps after a restart)
--
-- Each component is turned into a z-score across the season's drivers (0 =
-- average, +1 = one std dev better), then combined with the weights in params.
-- The z_* columns are emitted so a notebook can re-weight without re-querying.
-- Only drivers with >= min_races are scored (small samples distort z-scores);
-- a driver missing a component (e.g. no restarts) scores neutral on it.

WITH params AS (
    SELECT 0.01::float AS max_gap_pct,
           5           AS min_races,
           0.35::float AS w_net,
           0.20::float AS w_conv,
           0.20::float AS w_def,
           0.25::float AS w_restart
),
races_run AS (
    SELECT ra.season_id, rr.cust_id, count(DISTINCT rr.subsession_id) AS races
    FROM race_results rr JOIN races ra ON ra.subsession_id = rr.subsession_id
    GROUP BY ra.season_id, rr.cust_id
),
green AS (
    SELECT ra.season_id, p.passer_cust_id, p.passed_cust_id
    FROM passes p JOIN races ra ON ra.subsession_id = p.subsession_id
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
g_made AS (SELECT season_id, passer_cust_id AS cust_id, count(*) n FROM green GROUP BY 1, 2),
g_conc AS (SELECT season_id, passed_cust_id AS cust_id, count(*) n FROM green GROUP BY 1, 2),
opp AS (
    SELECT ra.season_id, g.subsession_id, g.lap_num, g.cust_id, g.car_ahead_cust_id
    FROM lap_gaps g JOIN races ra ON ra.subsession_id = g.subsession_id
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
    SELECT season_id, cust_id AS cust_id, count(*) opps, count(*) FILTER (WHERE converted) conv
    FROM conv GROUP BY season_id, cust_id
),
defense AS (
    SELECT season_id, car_ahead_cust_id AS cust_id,
           count(*) faced, count(*) FILTER (WHERE NOT converted) defended
    FROM conv GROUP BY season_id, car_ahead_cust_id
),
lap_flags AS (SELECT DISTINCT subsession_id, lap_num, under_caution FROM lap_gaps),
restart_laps AS (
    SELECT f.subsession_id, f.lap_num AS restart_lap
    FROM lap_flags f JOIN lap_flags p
      ON p.subsession_id = f.subsession_id AND p.lap_num = f.lap_num - 1
    WHERE NOT f.under_caution AND p.under_caution
),
period AS (
    SELECT subsession_id, restart_lap, restart_lap     AS lap_num FROM restart_laps
    UNION
    SELECT subsession_id, restart_lap, restart_lap + 1 AS lap_num FROM restart_laps
),
rs_involved AS (
    SELECT ra.season_id, l.cust_id, count(DISTINCT pe.restart_lap) restarts
    FROM period pe
    JOIN laps l   ON l.subsession_id = pe.subsession_id AND l.lap_num = pe.lap_num
    JOIN races ra ON ra.subsession_id = pe.subsession_id
    GROUP BY ra.season_id, l.cust_id
),
rs_green AS (
    SELECT ra.season_id, p.passer_cust_id, p.passed_cust_id
    FROM passes p
    JOIN period pe ON pe.subsession_id = p.subsession_id AND pe.lap_num = p.lap_num
    JOIN races ra  ON ra.subsession_id = p.subsession_id
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
rs_made AS (SELECT season_id, passer_cust_id AS cust_id, count(*) n FROM rs_green GROUP BY 1, 2),
rs_conc AS (SELECT season_id, passed_cust_id AS cust_id, count(*) n FROM rs_green GROUP BY 1, 2),
components AS (
    SELECT
        r.season_id, r.cust_id, r.races,
        (COALESCE(gm.n, 0) - COALESCE(gc.n, 0))::numeric / r.races          AS net_per_race,
        100.0 * COALESCE(a.conv, 0)     / NULLIF(a.opps, 0)                  AS conversion_pct,
        100.0 * COALESCE(df.defended, 0) / NULLIF(df.faced, 0)              AS defense_pct,
        (COALESCE(rm.n, 0) - COALESCE(rc.n, 0))::numeric / NULLIF(ri.restarts, 0) AS restart_net
    FROM races_run r
    LEFT JOIN g_made gm      ON gm.season_id = r.season_id AND gm.cust_id = r.cust_id
    LEFT JOIN g_conc gc      ON gc.season_id = r.season_id AND gc.cust_id = r.cust_id
    LEFT JOIN attack a       ON a.season_id = r.season_id AND a.cust_id = r.cust_id
    LEFT JOIN defense df     ON df.season_id = r.season_id AND df.cust_id = r.cust_id
    LEFT JOIN rs_involved ri ON ri.season_id = r.season_id AND ri.cust_id = r.cust_id
    LEFT JOIN rs_made rm     ON rm.season_id = r.season_id AND rm.cust_id = r.cust_id
    LEFT JOIN rs_conc rc     ON rc.season_id = r.season_id AND rc.cust_id = r.cust_id
    CROSS JOIN params
    WHERE r.races >= params.min_races
),
filled AS (   -- NULL component -> season mean, so it scores neutral (z = 0)
    SELECT c.season_id, c.cust_id, c.races,
        c.net_per_race, c.conversion_pct, c.defense_pct, c.restart_net,
        COALESCE(c.net_per_race,   AVG(c.net_per_race)   OVER w) AS nr,
        COALESCE(c.conversion_pct, AVG(c.conversion_pct) OVER w) AS cv,
        COALESCE(c.defense_pct,    AVG(c.defense_pct)    OVER w) AS df2,
        COALESCE(c.restart_net,    AVG(c.restart_net)    OVER w) AS rn
    FROM components c
    WINDOW w AS (PARTITION BY c.season_id)
),
z AS (
    SELECT f.*,
        (nr  - AVG(nr)  OVER w) / NULLIF(STDDEV_SAMP(nr)  OVER w, 0) AS z_net,
        (cv  - AVG(cv)  OVER w) / NULLIF(STDDEV_SAMP(cv)  OVER w, 0) AS z_conv,
        (df2 - AVG(df2) OVER w) / NULLIF(STDDEV_SAMP(df2) OVER w, 0) AS z_def,
        (rn  - AVG(rn)  OVER w) / NULLIF(STDDEV_SAMP(rn)  OVER w, 0) AS z_restart
    FROM filled f
    WINDOW w AS (PARTITION BY f.season_id)
)
SELECT
    s.season_name,
    d.driver_name,
    z.races,
    ROUND(z.net_per_race, 2)     AS net_per_race,
    ROUND(z.conversion_pct, 1)   AS conversion_pct,
    ROUND(z.defense_pct, 1)      AS defense_pct,
    ROUND(z.restart_net, 2)      AS restart_net_per_restart,
    ROUND(COALESCE(z.z_net, 0), 3)     AS z_net,
    ROUND(COALESCE(z.z_conv, 0), 3)    AS z_conv,
    ROUND(COALESCE(z.z_def, 0), 3)     AS z_def,
    ROUND(COALESCE(z.z_restart, 0), 3) AS z_restart,
    ROUND((p.w_net * COALESCE(z.z_net, 0) + p.w_conv * COALESCE(z.z_conv, 0)
         + p.w_def * COALESCE(z.z_def, 0) + p.w_restart * COALESCE(z.z_restart, 0))::numeric, 3)
        AS passing_score,
    RANK() OVER (PARTITION BY z.season_id ORDER BY
        p.w_net * COALESCE(z.z_net, 0) + p.w_conv * COALESCE(z.z_conv, 0)
      + p.w_def * COALESCE(z.z_def, 0) + p.w_restart * COALESCE(z.z_restart, 0) DESC)
        AS passing_rank
FROM z
JOIN drivers d ON d.cust_id = z.cust_id
JOIN seasons s ON s.season_id = z.season_id
CROSS JOIN params p
ORDER BY z.season_id, passing_score DESC;