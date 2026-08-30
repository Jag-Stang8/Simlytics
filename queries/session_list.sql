-- One row per race in a season: the season rail, the session selectbox, and the
-- header metric strip on the Session page all read from this.
--
-- `round` is derived, not stored — iRacing gives no round number, so races are
-- numbered by start_time within the season.
--
-- Pass season_id = NULL for every season (ordered season, then round).
--
-- Green passes use the same definition as queries/passing_*.sql: a pass that is
-- neither a pit-cycle artefact nor made under caution. `reverted` ones are
-- included in the green count and also reported separately.

SELECT
    ra.subsession_id,
    ra.season_id,
    s.season_name,
    ROW_NUMBER() OVER (
        PARTITION BY ra.season_id
        ORDER BY ra.start_time
    )                                                   AS round,
    ra.start_time,
    t.track_id,
    t.track_name,
    t.track_config_name,
    rs.laps_completed,
    rs.sof,
    rs.num_cautions,
    rs.num_caution_laps,
    rs.num_lead_changes,
    (SELECT count(*) FROM race_results rr
      WHERE rr.subsession_id = ra.subsession_id)        AS entries,
    (SELECT count(*) FROM passes p
      WHERE p.subsession_id = ra.subsession_id
        AND NOT p.pit_cycle
        AND NOT p.under_caution)                        AS green_passes,
    (SELECT count(*) FROM passes p
      WHERE p.subsession_id = ra.subsession_id
        AND NOT p.pit_cycle
        AND NOT p.under_caution
        AND p.reverted)                                 AS reverted_passes
FROM races ra
JOIN seasons s      ON s.season_id = ra.season_id
JOIN tracks t       ON t.track_id = ra.track_id
LEFT JOIN race_summary rs ON rs.subsession_id = ra.subsession_id
WHERE %(season_id)s::int IS NULL
   OR ra.season_id = %(season_id)s::int
ORDER BY ra.season_id, round;
