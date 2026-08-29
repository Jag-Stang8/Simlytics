-- Green-flag passing leaderboard, one row per driver per season.
--
-- Counts only clean on-track passes: pit-cycle and caution-period order changes
-- (passes.pit_cycle / under_caution) are excluded. `passes_defended` is passes a
-- driver conceded but retook within the revert window (see stats/passes.py).

WITH green AS (
    SELECT p.*, ra.season_id
    FROM passes p
    JOIN races ra ON ra.subsession_id = p.subsession_id
    WHERE NOT p.pit_cycle AND NOT p.under_caution
),
base AS (
    SELECT DISTINCT ra.season_id, rr.cust_id
    FROM race_results rr
    JOIN races ra ON ra.subsession_id = rr.subsession_id
),
made AS (
    SELECT season_id, passer_cust_id AS cust_id,
           count(*) AS n,
           count(*) FILTER (WHERE is_lead_change) AS lead_passes
    FROM green GROUP BY season_id, passer_cust_id
),
conceded AS (
    SELECT season_id, passed_cust_id AS cust_id,
           count(*) AS n,
           count(*) FILTER (WHERE reverted) AS defended
    FROM green GROUP BY season_id, passed_cust_id
)
SELECT
    s.season_name,
    d.driver_name,
    COALESCE(m.n, 0)                        AS passes_made,
    COALESCE(c.n, 0)                        AS passes_conceded,
    COALESCE(m.n, 0) - COALESCE(c.n, 0)     AS net_passes,
    COALESCE(c.defended, 0)                 AS passes_defended,
    COALESCE(m.lead_passes, 0)              AS lead_change_passes
FROM base b
JOIN drivers d ON d.cust_id = b.cust_id
JOIN seasons s ON s.season_id = b.season_id
LEFT JOIN made     m ON m.season_id = b.season_id AND m.cust_id = b.cust_id
LEFT JOIN conceded c ON c.season_id = b.season_id AND c.cust_id = b.cust_id
ORDER BY b.season_id, net_passes DESC;