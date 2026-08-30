-- Every on-track meeting between two drivers across a season: one row per pass
-- in either direction.
--
-- Scoped to the season, not to a race list, so the Head-to-head page can slice it
-- to the selected range in pandas the same way it slices driver_race_matrix.sql
-- -- one cached query, instant range changes.
--
-- `direction` is from A's point of view: 'a_over_b' when A passed B.
-- All flag states are returned; the caller filters. Green is
-- NOT pit_cycle AND NOT under_caution, as everywhere else.

SELECT
    ra.subsession_id,
    DENSE_RANK() OVER (ORDER BY ra.start_time)          AS round,
    p.lap_num,
    CASE WHEN p.passer_cust_id = %(a)s::int THEN 'a_over_b' ELSE 'b_over_a' END AS direction,
    p.passer_cust_id,
    p.passed_cust_id,
    p.passer_pos + 1 AS passer_pos,
    p.passed_pos + 1 AS passed_pos,
    p.gap_ms,
    p.is_lead_change,
    p.reverted,
    p.pit_cycle,
    p.under_caution,
    (NOT p.pit_cycle AND NOT p.under_caution) AS is_green,
    t.track_name,
    ra.start_time
FROM passes p
JOIN races ra ON ra.subsession_id = p.subsession_id
JOIN tracks t ON t.track_id = ra.track_id
WHERE ra.season_id = %(season_id)s::int
  AND (
        (p.passer_cust_id = %(a)s::int AND p.passed_cust_id = %(b)s::int)
     OR (p.passer_cust_id = %(b)s::int AND p.passed_cust_id = %(a)s::int)
  )
ORDER BY ra.start_time, p.lap_num;
