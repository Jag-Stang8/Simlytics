-- Lap-by-lap running order for ONE race: the Timeline tab's position lines,
-- the running-order table at a chosen lap, and the caution bands.
--
-- Caution state is NOT re-derived here. stats/passes.py already classified every
-- lap (a lap whose median laptime exceeds the race median by CAUTION_LAP_FACTOR)
-- and persisted the result on lap_gaps.under_caution, so reading it back keeps
-- the timeline's yellow bands consistent with the pass classification. Laps with
-- no lap_gaps row (lap 0, and the leader on any lap) fall back to the race-wide
-- per-lap verdict in `caution_laps`.
--
-- Positions are 0-based in the data; `position` below is 1-based.
-- laptime stays in raw ten-thousandths; gap_ms is milliseconds.

WITH caution_laps AS (
    -- one verdict per lap for the whole field, from the per-car rows
    SELECT lap_num, bool_or(under_caution) AS under_caution
    FROM lap_gaps
    WHERE subsession_id = %(subsession_id)s
    GROUP BY lap_num
),
pitted AS (
    SELECT DISTINCT cust_id, lap_num
    FROM lap_events
    WHERE subsession_id = %(subsession_id)s AND lap_event = 'pitted'
)
SELECT
    l.lap_num,
    l.cust_id,
    d.driver_name,
    rr.car_num,
    l.position + 1                              AS position,
    l.laptime,
    l.session_time,
    l.incident,
    g.gap_ms,
    g.gap_pct,
    g.car_ahead_cust_id,
    COALESCE(g.under_caution, cl.under_caution, false) AS under_caution,
    COALESCE(g.pit_cycle, false)                AS pit_cycle,
    (p.cust_id IS NOT NULL)                     AS pitted
FROM laps l
JOIN drivers d       ON d.cust_id = l.cust_id
JOIN race_results rr ON rr.subsession_id = l.subsession_id AND rr.cust_id = l.cust_id
LEFT JOIN lap_gaps g ON g.subsession_id = l.subsession_id
                    AND g.lap_num = l.lap_num AND g.cust_id = l.cust_id
LEFT JOIN caution_laps cl ON cl.lap_num = l.lap_num
LEFT JOIN pitted p   ON p.cust_id = l.cust_id AND p.lap_num = l.lap_num
WHERE l.subsession_id = %(subsession_id)s
  AND l.lap_num > 0
ORDER BY l.lap_num, l.position;
