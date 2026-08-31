-- Clean green-flag racing laps: one row per driver per lap of representative race
-- pace. Excludes caution laps, pit in-laps and out-laps, the standing-start lap,
-- and invalid (<=0) lap times. laptime is in 1/10000 s (divide by 10000 for
-- seconds). Basis for per-driver lap-time distribution analysis.
--
-- Pass subsession_id = NULL for every race (the season-wide form that
-- stats/driver_features.py uses), or an id to scope to one race.

SELECT
    l.subsession_id,
    l.cust_id,
    d.driver_name,
    l.lap_num,
    l.laptime
FROM laps l
JOIN drivers d  ON d.cust_id = l.cust_id
JOIN lap_gaps g ON g.subsession_id = l.subsession_id
               AND g.cust_id = l.cust_id
               AND g.lap_num = l.lap_num
WHERE l.laptime > 0
  AND (%(subsession_id)s::int IS NULL OR l.subsession_id = %(subsession_id)s::int)
  AND l.lap_num > 1                 -- skip the standing-start lap
  AND NOT g.under_caution           -- green laps only
  AND NOT EXISTS (                  -- exclude pit in-lap and out-lap
      SELECT 1 FROM lap_events e
      WHERE e.subsession_id = l.subsession_id
        AND e.cust_id = l.cust_id
        AND e.lap_event = 'pitted'
        AND e.lap_num IN (l.lap_num, l.lap_num - 1)
  )
ORDER BY l.cust_id, l.subsession_id, l.lap_num;
