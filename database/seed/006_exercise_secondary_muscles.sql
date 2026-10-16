-- DB-04: secondary muscle groups of the exercises (exercise_secondary_muscle_group).
-- The injury rule 3 (docs/algorithms.md 4.3) uses these: a moderate or severe injury rules out exercises that
-- load the injured group as a secondary one. Isolation exercises list none. Unknown names abort the load.
DROP TABLE IF EXISTS _secondary_seed;
CREATE TEMP TABLE _secondary_seed (exercise text, grp text);
INSERT INTO _secondary_seed VALUES
('Push-up','triceps'),('Push-up','shoulders'),('Push-up','core'),
('Incline push-up','triceps'),('Incline push-up','shoulders'),
('Decline push-up','triceps'),('Decline push-up','shoulders'),
('Archer push-up','triceps'),('Archer push-up','shoulders'),
('Dumbbell floor press','triceps'),('Dumbbell floor press','shoulders'),
('Machine chest press','triceps'),('Machine chest press','shoulders'),
('Barbell bench press','triceps'),('Barbell bench press','shoulders'),
('Incline dumbbell press','triceps'),('Incline dumbbell press','shoulders'),
('Chest dip','triceps'),('Chest dip','shoulders'),
('Table inverted row','biceps'),('Table inverted row','core'),
('Dumbbell one-arm row','biceps'),('Resistance band row','biceps'),
('Pull-up','biceps'),('Pull-up','core'),('Chin-up','biceps'),('Chin-up','core'),
('Lat pulldown','biceps'),('Seated cable row','biceps'),
('Barbell bent-over row','biceps'),('Barbell bent-over row','hamstrings'),('Barbell bent-over row','core'),
('T-bar row','biceps'),('T-bar row','core'),
('Pike push-up','triceps'),('Pike push-up','core'),
('Dumbbell shoulder press','triceps'),('Machine shoulder press','triceps'),
('Barbell overhead press','triceps'),('Barbell overhead press','core'),
('Bench dip','shoulders'),('Bench dip','chest'),
('Close-grip push-up','chest'),('Close-grip push-up','shoulders'),
('Close-grip bench press','chest'),('Close-grip bench press','shoulders'),
('Parallel bar dip','chest'),('Parallel bar dip','shoulders'),
('Bodyweight squat','glutes'),('Bodyweight squat','hamstrings'),('Bodyweight squat','core'),
('Reverse lunge','glutes'),('Reverse lunge','hamstrings'),
('Bulgarian split squat','glutes'),('Bulgarian split squat','hamstrings'),
('Jump squat','glutes'),('Jump squat','calves'),
('Pistol squat','glutes'),('Pistol squat','core'),
('Goblet squat','glutes'),('Goblet squat','core'),
('Dumbbell lunge','glutes'),('Dumbbell lunge','hamstrings'),
('Dumbbell step-up','glutes'),('Dumbbell step-up','hamstrings'),
('Leg press','glutes'),('Leg press','hamstrings'),
('Barbell back squat','glutes'),('Barbell back squat','hamstrings'),('Barbell back squat','core'),
('Barbell front squat','glutes'),('Barbell front squat','core'),
('Bodyweight good morning','glutes'),('Bodyweight good morning','back'),
('Bodyweight single-leg Romanian deadlift','glutes'),('Bodyweight single-leg Romanian deadlift','core'),
('Dumbbell Romanian deadlift','glutes'),('Dumbbell Romanian deadlift','back'),
('Dumbbell single-leg Romanian deadlift','glutes'),('Dumbbell single-leg Romanian deadlift','core'),
('Barbell Romanian deadlift','glutes'),('Barbell Romanian deadlift','back'),
('Conventional deadlift','glutes'),('Conventional deadlift','back'),('Conventional deadlift','quadriceps'),
('Dumbbell hip thrust','hamstrings'),('Barbell hip thrust','hamstrings'),
('Dumbbell sumo squat','quadriceps'),('Dumbbell sumo squat','hamstrings'),
('Mountain climber','shoulders'),('Mountain climber','quadriceps'),
('Plank','shoulders'),('Side plank','shoulders'),
('Ab wheel rollout','shoulders'),('Ab wheel rollout','back'),
('Hanging knee raise','back'),('Hanging leg raise','back'),
('Superman','glutes'),('Bird dog','glutes'),('Bird dog','shoulders');

DO $$
DECLARE missing text;
BEGIN
  SELECT string_agg(DISTINCT s.exercise || ' / ' || s.grp, '; ') INTO missing
    FROM _secondary_seed s
    LEFT JOIN exercise e ON e.name = s.exercise
    LEFT JOIN muscle_group mg ON mg.name = s.grp
   WHERE e.id IS NULL OR mg.id IS NULL;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'secondary muscle seed references unknown names: %', missing;
  END IF;
END $$;

-- The seed owns the secondary groups of the exercises it lists: replace them so removals take effect.
DELETE FROM exercise_secondary_muscle_group
 WHERE exercise_id IN (SELECT e.id FROM exercise e JOIN _secondary_seed s ON s.exercise = e.name);

INSERT INTO exercise_secondary_muscle_group (exercise_id, muscle_group_id)
SELECT DISTINCT e.id, mg.id
  FROM _secondary_seed s JOIN exercise e ON e.name = s.exercise JOIN muscle_group mg ON mg.name = s.grp
 WHERE mg.id <> e.main_muscle_group_id;

DROP TABLE _secondary_seed;
