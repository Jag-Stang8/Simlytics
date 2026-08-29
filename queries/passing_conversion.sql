-- Passing opportunity outcomes per driver per season: attacking conversion and
-- defensive hold rate.
--
-- An "opportunity" is a lap where a driver ran within `max_gap_pct` of a lap time
-- behind the car directly ahead, on the same lap, under green (from lap_gaps).
-- It "converts" if that driver completes a green pass of that car on the next lap.
-- Defense is the same opportunity seen from the car ahead: repelled if not passed.
--
-- Tune the threshold in the params CTE.

WITH params AS (
    SELECT 0.01::float AS max_gap_pct     -- <-- within 1% of a lap
),
opp AS (
    SELECT
        g.subsession_id,
        ra.season_id,
        g.lap_num,
        g.cust_id           AS attacker,
        g.car_ahead_cust_id AS defender
    FROM lap_gaps g
    JOIN races ra ON ra.subsession_id = g.subsession_id
    CROSS JOIN params
    WHERE g.same_lap AND NOT g.under_caution AND NOT g.pit_cycle
      AND g.car_ahead_cust_id IS NOT NULL
      AND g.gap_pct IS NOT NULL AND g.gap_pct > 0 AND g.gap_pct < params.max_gap_pct
),
conv AS (
    SELECT o.*, (p.pass_id IS NOT NULL) AS converted
    FROM opp o
    LEFT JOIN passes p
      ON p.subsession_id = o.subsession_id
     AND p.lap_num = o.lap_num + 1
     AND p.passer_cust_id = o.attacker
     AND p.passed_cust_id = o.defender
     AND NOT p.pit_cycle AND NOT p.under_caution
),
attack AS (
    SELECT season_id, attacker AS cust_id,
           count(*) AS opportunities,
           count(*) FILTER (WHERE converted) AS converted
    FROM conv GROUP BY season_id, attacker
),
defense AS (
    SELECT season_id, defender AS cust_id,
           count(*) AS opps_faced,
           count(*) FILTER (WHERE NOT converted) AS defended
    FROM conv GROUP BY season_id, defender
),
base AS (
    SELECT season_id, cust_id FROM attack
    UNION
    SELECT season_id, cust_id FROM defense
)
SELECT
    s.season_name,
    d.driver_name,
    COALESCE(a.opportunities, 0)                                              AS opportunities,
    COALESCE(a.converted, 0)                                                  AS converted,
    ROUND(100.0 * COALESCE(a.converted, 0) / NULLIF(a.opportunities, 0), 1)   AS conversion_pct,
    COALESCE(df.opps_faced, 0)                                                AS opps_faced,
    COALESCE(df.defended, 0)                                                  AS defended,
    ROUND(100.0 * COALESCE(df.defended, 0) / NULLIF(df.opps_faced, 0), 1)     AS defense_pct
FROM base b
JOIN drivers d ON d.cust_id = b.cust_id
JOIN seasons s ON s.season_id = b.season_id
LEFT JOIN attack  a  ON a.season_id = b.season_id AND a.cust_id = b.cust_id
LEFT JOIN defense df ON df.season_id = b.season_id AND df.cust_id = b.cust_id
ORDER BY b.season_id, opportunities DESC;