-- Who passed whom in ONE race: green passes only, passer x passed.
--
-- Powers the Passing tab's heatmap. `first_lap` and `last_lap` let a cell click
-- jump the Timeline to where the battle happened.

SELECT
    p.passer_cust_id,
    pd.driver_name       AS passer_name,
    p.passed_cust_id,
    sd.driver_name       AS passed_name,
    count(*)                                   AS passes,
    count(*) FILTER (WHERE p.reverted)         AS reverted,
    count(*) FILTER (WHERE p.is_lead_change)   AS lead_changes,
    min(p.lap_num)                             AS first_lap,
    max(p.lap_num)                             AS last_lap
FROM passes p
JOIN drivers pd ON pd.cust_id = p.passer_cust_id
JOIN drivers sd ON sd.cust_id = p.passed_cust_id
WHERE p.subsession_id = %(subsession_id)s
  AND NOT p.pit_cycle
  AND NOT p.under_caution
GROUP BY p.passer_cust_id, pd.driver_name, p.passed_cust_id, sd.driver_name
ORDER BY passes DESC;
