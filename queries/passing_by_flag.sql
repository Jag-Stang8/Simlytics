-- Passes made and conceded per driver per season, split by flag state.
--
-- Each pass is placed in exactly one category (precedence caution > pit > green):
--   caution -> the pass happened on a caution lap
--   pit     -> not caution, but either car was in its pit cycle
--   green   -> a clean on-track pass
-- so the three made columns sum to total_made (likewise for conceded).

WITH cat AS (
    SELECT
        ra.season_id,
        p.passer_cust_id,
        p.passed_cust_id,
        CASE WHEN p.under_caution THEN 'caution'
             WHEN p.pit_cycle     THEN 'pit'
             ELSE 'green' END AS category
    FROM passes p
    JOIN races ra ON ra.subsession_id = p.subsession_id
),
events AS (
    SELECT season_id, passer_cust_id AS cust_id, 'made'     AS dir, category FROM cat
    UNION ALL
    SELECT season_id, passed_cust_id AS cust_id, 'conceded' AS dir, category FROM cat
),
agg AS (
    SELECT season_id, cust_id,
        count(*) FILTER (WHERE dir = 'made'     AND category = 'green')   AS made_green,
        count(*) FILTER (WHERE dir = 'made'     AND category = 'pit')     AS made_pit,
        count(*) FILTER (WHERE dir = 'made'     AND category = 'caution') AS made_caution,
        count(*) FILTER (WHERE dir = 'conceded' AND category = 'green')   AS conceded_green,
        count(*) FILTER (WHERE dir = 'conceded' AND category = 'pit')     AS conceded_pit,
        count(*) FILTER (WHERE dir = 'conceded' AND category = 'caution') AS conceded_caution
    FROM events
    GROUP BY season_id, cust_id
)
SELECT
    s.season_name,
    d.driver_name,
    agg.made_green, agg.made_pit, agg.made_caution,
    agg.conceded_green, agg.conceded_pit, agg.conceded_caution,
    agg.made_green + agg.made_pit + agg.made_caution             AS total_made,
    agg.conceded_green + agg.conceded_pit + agg.conceded_caution AS total_conceded
FROM agg
JOIN drivers d ON d.cust_id = agg.cust_id
JOIN seasons s ON s.season_id = agg.season_id
ORDER BY agg.season_id, total_made DESC;