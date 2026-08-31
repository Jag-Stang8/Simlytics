-- Passes made and conceded per driver in ONE race, split by flag state.
--
-- Same precedence as queries/passing_by_flag.sql (caution > pit > green), so
-- each pass lands in exactly one bucket and the three made columns sum to
-- total_made (likewise conceded).

WITH tagged AS (
    SELECT p.*,
           CASE WHEN p.under_caution THEN 'caution'
                WHEN p.pit_cycle     THEN 'pit'
                ELSE 'green' END AS flag
    FROM passes p
    WHERE p.subsession_id = %(subsession_id)s
),
made AS (
    SELECT passer_cust_id AS cust_id,
           count(*) FILTER (WHERE flag = 'green')   AS made_green,
           count(*) FILTER (WHERE flag = 'pit')     AS made_pit,
           count(*) FILTER (WHERE flag = 'caution') AS made_caution,
           count(*)                                 AS total_made
    FROM tagged GROUP BY passer_cust_id
),
conceded AS (
    SELECT passed_cust_id AS cust_id,
           count(*) FILTER (WHERE flag = 'green')   AS conceded_green,
           count(*) FILTER (WHERE flag = 'pit')     AS conceded_pit,
           count(*) FILTER (WHERE flag = 'caution') AS conceded_caution,
           count(*)                                 AS total_conceded
    FROM tagged GROUP BY passed_cust_id
)
SELECT
    rr.cust_id,
    d.driver_name,
    rr.finish_pos + 1                    AS finish,
    COALESCE(m.made_green, 0)            AS made_green,
    COALESCE(m.made_pit, 0)              AS made_pit,
    COALESCE(m.made_caution, 0)          AS made_caution,
    COALESCE(m.total_made, 0)            AS total_made,
    COALESCE(c.conceded_green, 0)        AS conceded_green,
    COALESCE(c.conceded_pit, 0)          AS conceded_pit,
    COALESCE(c.conceded_caution, 0)      AS conceded_caution,
    COALESCE(c.total_conceded, 0)        AS total_conceded
FROM race_results rr
JOIN drivers d       ON d.cust_id = rr.cust_id
LEFT JOIN made m     ON m.cust_id = rr.cust_id
LEFT JOIN conceded c ON c.cust_id = rr.cust_id
WHERE rr.subsession_id = %(subsession_id)s
ORDER BY rr.finish_pos;
