-- Seasons with ingested races, newest first. Pass league_id = NULL for all.
--
-- "season" here is the *league* season (seasons.season_id maps from the payload's
-- league_season_id); the plain iRacing season_id is 0 and is not a usable key.

SELECT
    s.season_id,
    s.season_name,
    s.league_id,
    l.league_name,
    count(ra.subsession_id)  AS races,
    min(ra.start_time)       AS first_race,
    max(ra.start_time)       AS last_race
FROM seasons s
JOIN leagues l ON l.league_id = s.league_id
JOIN races ra  ON ra.season_id = s.season_id
WHERE %(league_id)s::int IS NULL
   OR s.league_id = %(league_id)s::int
GROUP BY s.season_id, s.season_name, s.league_id, l.league_name
ORDER BY last_race DESC;