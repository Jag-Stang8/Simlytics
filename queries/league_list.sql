-- Leagues that actually have ingested races, newest activity first.

SELECT
    l.league_id,
    l.league_name,
    count(DISTINCT s.season_id)  AS seasons,
    count(ra.subsession_id)      AS races,
    max(ra.start_time)           AS last_race
FROM leagues l
JOIN seasons s ON s.league_id = l.league_id
JOIN races ra  ON ra.season_id = s.season_id
GROUP BY l.league_id, l.league_name
ORDER BY last_race DESC;