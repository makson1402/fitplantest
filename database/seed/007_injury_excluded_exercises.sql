-- DB-04: exercises each injury type explicitly rules out (injury_type_excluded_exercise, FR-P2).
-- Added to the two generic rules of docs/algorithms.md 4.3 (main group equals the injured group; secondary group
-- at moderate or severe). These are conservative proposals for a human to review (see docs/questions.md).
-- Unknown names abort the load.
DROP TABLE IF EXISTS _exclusion_seed;
CREATE TEMP TABLE _exclusion_seed (injury text, exercise text);
INSERT INTO _exclusion_seed VALUES
-- shoulder impingement: overhead and abduction loading
('shoulder impingement','Barbell overhead press'),('shoulder impingement','Dumbbell shoulder press'),
('shoulder impingement','Machine shoulder press'),('shoulder impingement','Pike push-up'),
('shoulder impingement','Dumbbell lateral raise'),('shoulder impingement','Cable lateral raise'),
('shoulder impingement','Chest dip'),('shoulder impingement','Parallel bar dip'),
('shoulder impingement','Bench dip'),('shoulder impingement','Decline push-up'),
('shoulder impingement','Pull-up'),('shoulder impingement','Dumbbell fly'),
-- rotator cuff strain
('rotator cuff strain','Barbell overhead press'),('rotator cuff strain','Dumbbell shoulder press'),
('rotator cuff strain','Machine shoulder press'),('rotator cuff strain','Pike push-up'),
('rotator cuff strain','Dumbbell lateral raise'),('rotator cuff strain','Dumbbell front raise'),
('rotator cuff strain','Cable lateral raise'),('rotator cuff strain','Dumbbell rear delt fly'),
('rotator cuff strain','Dumbbell fly'),('rotator cuff strain','Cable crossover'),
('rotator cuff strain','Barbell bench press'),('rotator cuff strain','Chest dip'),
('rotator cuff strain','Parallel bar dip'),('rotator cuff strain','Bench dip'),
('rotator cuff strain','Pull-up'),('rotator cuff strain','Chin-up'),
('rotator cuff strain','Archer push-up'),
-- elbow tendinopathy: gripping, curling and elbow-extension loading
('elbow tendinopathy','Pull-up'),('elbow tendinopathy','Chin-up'),
('elbow tendinopathy','Barbell curl'),('elbow tendinopathy','EZ-bar preacher curl'),
('elbow tendinopathy','Dumbbell curl'),('elbow tendinopathy','Hammer curl'),
('elbow tendinopathy','Dumbbell skull crusher'),('elbow tendinopathy','Dumbbell overhead extension'),
('elbow tendinopathy','Cable overhead triceps extension'),('elbow tendinopathy','Close-grip bench press'),
('elbow tendinopathy','Parallel bar dip'),('elbow tendinopathy','Bench dip'),
('elbow tendinopathy','Conventional deadlift'),
-- wrist sprain: weight bearing on the hands and heavy grip
('wrist sprain','Push-up'),('wrist sprain','Incline push-up'),('wrist sprain','Decline push-up'),
('wrist sprain','Archer push-up'),('wrist sprain','Close-grip push-up'),('wrist sprain','Pike push-up'),
('wrist sprain','Plank'),('wrist sprain','Side plank'),('wrist sprain','Mountain climber'),
('wrist sprain','Ab wheel rollout'),('wrist sprain','Barbell front squat'),
('wrist sprain','Barbell curl'),('wrist sprain','Pull-up'),('wrist sprain','Chin-up'),
('wrist sprain','Bench dip'),('wrist sprain','Parallel bar dip'),('wrist sprain','Chest dip'),
-- neck strain: loading the upper back and neck flexion
('neck strain','Barbell overhead press'),('neck strain','Barbell back squat'),
('neck strain','Crunch'),('neck strain','Bicycle crunch'),('neck strain','Superman'),
('neck strain','Barbell front squat'),('neck strain','V-up'),
-- lower back strain: axial loading and spinal flexion/extension
('lower back strain','Conventional deadlift'),('lower back strain','Barbell Romanian deadlift'),
('lower back strain','Bodyweight good morning'),('lower back strain','Barbell bent-over row'),
('lower back strain','T-bar row'),('lower back strain','Barbell back squat'),
('lower back strain','Barbell front squat'),('lower back strain','Superman'),
('lower back strain','V-up'),('lower back strain','Hollow body hold'),
('lower back strain','Ab wheel rollout'),('lower back strain','Dumbbell Russian twist'),
('lower back strain','Hanging leg raise'),('lower back strain','Lying leg raise'),
-- herniated disc: everything above plus spinal flexion and rotation under load
('herniated disc','Conventional deadlift'),('herniated disc','Barbell Romanian deadlift'),
('herniated disc','Dumbbell Romanian deadlift'),('herniated disc','Dumbbell single-leg Romanian deadlift'),
('herniated disc','Bodyweight good morning'),('herniated disc','Barbell bent-over row'),
('herniated disc','T-bar row'),('herniated disc','Barbell back squat'),
('herniated disc','Barbell front squat'),('herniated disc','Goblet squat'),
('herniated disc','Superman'),('herniated disc','V-up'),('herniated disc','Crunch'),
('herniated disc','Bicycle crunch'),('herniated disc','Hollow body hold'),
('herniated disc','Ab wheel rollout'),('herniated disc','Dumbbell Russian twist'),
('herniated disc','Cable crunch'),('herniated disc','Hanging leg raise'),
('herniated disc','Lying leg raise'),('herniated disc','Jump squat'),
('herniated disc','Barbell overhead press'),
-- hip flexor strain
('hip flexor strain','V-up'),('hip flexor strain','Lying leg raise'),
('hip flexor strain','Hanging leg raise'),('hip flexor strain','Hanging knee raise'),
('hip flexor strain','Mountain climber'),('hip flexor strain','Hollow body hold'),
('hip flexor strain','Bulgarian split squat'),('hip flexor strain','Dumbbell lunge'),
('hip flexor strain','Jump squat'),
-- groin strain: adduction and wide stances
('groin strain','Dumbbell sumo squat'),('groin strain','Hip abduction machine'),
('groin strain','Resistance band lateral walk'),('groin strain','Fire hydrant'),
('groin strain','Bulgarian split squat'),('groin strain','Dumbbell lunge'),
('groin strain','Reverse lunge'),
-- hamstring strain
('hamstring strain','Nordic curl'),('hamstring strain','Lying leg curl'),
('hamstring strain','Seated leg curl'),('hamstring strain','Hamstring slider curl'),
('hamstring strain','Resistance band hamstring curl'),('hamstring strain','Barbell Romanian deadlift'),
('hamstring strain','Dumbbell Romanian deadlift'),('hamstring strain','Dumbbell single-leg Romanian deadlift'),
('hamstring strain','Bodyweight single-leg Romanian deadlift'),('hamstring strain','Bodyweight good morning'),
('hamstring strain','Conventional deadlift'),('hamstring strain','Jump squat'),
-- quadriceps strain
('quadriceps strain','Leg extension'),('quadriceps strain','Barbell back squat'),
('quadriceps strain','Barbell front squat'),('quadriceps strain','Pistol squat'),
('quadriceps strain','Jump squat'),('quadriceps strain','Bulgarian split squat'),
('quadriceps strain','Wall sit'),('quadriceps strain','Leg press'),
('quadriceps strain','Dumbbell step-up'),
-- patellar tendinopathy
('patellar tendinopathy','Jump squat'),('patellar tendinopathy','Leg extension'),
('patellar tendinopathy','Pistol squat'),('patellar tendinopathy','Bulgarian split squat'),
('patellar tendinopathy','Barbell front squat'),('patellar tendinopathy','Barbell back squat'),
('patellar tendinopathy','Dumbbell lunge'),('patellar tendinopathy','Wall sit'),
-- knee ligament injury
('knee ligament injury','Jump squat'),('knee ligament injury','Pistol squat'),
('knee ligament injury','Bulgarian split squat'),('knee ligament injury','Dumbbell lunge'),
('knee ligament injury','Reverse lunge'),('knee ligament injury','Barbell back squat'),
('knee ligament injury','Barbell front squat'),('knee ligament injury','Leg extension'),
('knee ligament injury','Dumbbell step-up'),('knee ligament injury','Mountain climber'),
-- shin splints
('shin splints','Jump squat'),('shin splints','Mountain climber'),
('shin splints','Bodyweight calf raise'),('shin splints','Single-leg calf raise'),
('shin splints','Step calf raise'),('shin splints','Dumbbell standing calf raise'),
('shin splints','Single-leg dumbbell calf raise'),('shin splints','Standing calf raise machine'),
('shin splints','Donkey calf raise'),
-- ankle sprain
('ankle sprain','Single-leg calf raise'),('ankle sprain','Step calf raise'),
('ankle sprain','Single-leg dumbbell calf raise'),('ankle sprain','Jump squat'),
('ankle sprain','Pistol squat'),('ankle sprain','Bulgarian split squat'),
('ankle sprain','Reverse lunge'),('ankle sprain','Dumbbell lunge'),
('ankle sprain','Bodyweight single-leg Romanian deadlift'),
('ankle sprain','Dumbbell single-leg Romanian deadlift'),
('ankle sprain','Resistance band lateral walk'),('ankle sprain','Mountain climber'),
-- achilles tendinopathy
('achilles tendinopathy','Bodyweight calf raise'),('achilles tendinopathy','Single-leg calf raise'),
('achilles tendinopathy','Step calf raise'),('achilles tendinopathy','Dumbbell standing calf raise'),
('achilles tendinopathy','Single-leg dumbbell calf raise'),('achilles tendinopathy','Standing calf raise machine'),
('achilles tendinopathy','Seated calf raise machine'),('achilles tendinopathy','Leg press calf raise'),
('achilles tendinopathy','Donkey calf raise'),('achilles tendinopathy','Jump squat'),
('achilles tendinopathy','Mountain climber'),
-- rib or chest wall strain
('rib or chest wall strain','Push-up'),('rib or chest wall strain','Incline push-up'),
('rib or chest wall strain','Decline push-up'),('rib or chest wall strain','Archer push-up'),
('rib or chest wall strain','Dumbbell floor press'),('rib or chest wall strain','Dumbbell fly'),
('rib or chest wall strain','Machine chest press'),('rib or chest wall strain','Barbell bench press'),
('rib or chest wall strain','Incline dumbbell press'),('rib or chest wall strain','Cable crossover'),
('rib or chest wall strain','Chest dip'),('rib or chest wall strain','Bench dip'),
('rib or chest wall strain','Dumbbell Russian twist'),('rib or chest wall strain','Bicycle crunch'),
('rib or chest wall strain','Crunch'),('rib or chest wall strain','Cable crunch'),
('rib or chest wall strain','Side plank');

DO $$
DECLARE missing text;
BEGIN
  SELECT string_agg(DISTINCT s.injury || ' / ' || s.exercise, '; ') INTO missing
    FROM _exclusion_seed s
    LEFT JOIN injury_type it ON it.name = s.injury
    LEFT JOIN exercise e ON e.name = s.exercise
   WHERE it.id IS NULL OR e.id IS NULL;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'exclusion seed references unknown names: %', missing;
  END IF;
END $$;

-- The seed owns the exclusions of every injury type it lists.
DELETE FROM injury_type_excluded_exercise
 WHERE injury_type_id IN (SELECT it.id FROM injury_type it JOIN _exclusion_seed s ON s.injury = it.name);

INSERT INTO injury_type_excluded_exercise (injury_type_id, exercise_id)
SELECT DISTINCT it.id, e.id
  FROM _exclusion_seed s JOIN injury_type it ON it.name = s.injury JOIN exercise e ON e.name = s.exercise;

DROP TABLE _exclusion_seed;
