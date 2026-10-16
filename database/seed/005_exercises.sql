-- DB-04: exercises (FR-P1, FR-P2, FR-P3, FR-P8). Entered manually per the schema; text is original wording.
-- Columns: name, main muscle group, difficulty (beginner|intermediate|advanced), equipment (none|home|gym),
-- is_compound, is_bodyweight, description, instruction.
-- Equipment: none = bodyweight/chair/wall/towel, home = dumbbells, bands, pull-up bar, bench, gym = machines/barbells.
-- Idempotent: the natural key is the exercise name. Unknown muscle group names abort the load.
DROP TABLE IF EXISTS _exercise_seed;
CREATE TEMP TABLE _exercise_seed (
  name text, grp text, level text, equip text, compound boolean, bodyweight boolean, descr text, instr text
);
INSERT INTO _exercise_seed VALUES
-- ------------------------------------------------------------------ chest
('Push-up','chest','beginner','none',true,true,'Classic horizontal press with bodyweight.','Hands slightly wider than shoulders, body in a straight line. Lower the chest to the floor, then press back up without sagging the hips.'),
('Incline push-up','chest','beginner','none',true,true,'Easier push-up with hands raised on a stable surface.','Place hands on a table or sturdy chair, body straight. Lower the chest to the edge, then push away.'),
('Decline push-up','chest','intermediate','none',true,true,'Push-up with feet raised to load the upper chest.','Put feet on a chair, hands on the floor. Lower under control until the chest nearly touches, then press up.'),
('Archer push-up','chest','advanced','none',true,true,'Wide push-up shifting load to one arm at a time.','Hands wide. Lower toward one hand while the other arm stays straight, push up, and alternate sides.'),
('Dumbbell floor press','chest','beginner','home',true,false,'Dumbbell press lying on the floor, safe range of motion.','Lie on your back, knees bent. Press the dumbbells up over the chest, lower until the upper arms touch the floor.'),
('Dumbbell fly','chest','intermediate','home',false,false,'Chest isolation with a wide arc.','Lying on a bench or floor, arms slightly bent. Open the arms to chest level, then bring the dumbbells together above the chest.'),
('Machine chest press','chest','beginner','gym',true,false,'Guided seated press, easy to learn.','Adjust the seat so handles are at mid-chest. Press forward until the arms are almost straight, return slowly.'),
('Barbell bench press','chest','intermediate','gym',true,false,'Primary heavy chest press.','Eyes under the bar, shoulder blades pinched. Lower the bar to the mid-chest, press up. Use a spotter or safety arms.'),
('Incline dumbbell press','chest','intermediate','gym',true,false,'Press on an incline bench for the upper chest.','Bench at 30 degrees. Press the dumbbells up and slightly together, lower to chest level under control.'),
('Cable crossover','chest','intermediate','gym',false,false,'Cable chest isolation with constant tension.','Cables set high, slight forward lean. Sweep the handles down and together in front of the hips, return slowly.'),
('Chest dip','chest','advanced','gym',true,true,'Bodyweight dip leaning forward to target the chest.','On parallel bars lean the torso forward. Lower until the shoulders are below the elbows, then press up.'),
-- ------------------------------------------------------------------ back
('Superman','back','beginner','none',false,true,'Lying back extension for the spinal erectors.','Lie face down, arms forward. Lift arms and legs together a few centimetres, hold one second, lower slowly.'),
('Table inverted row','back','intermediate','none',true,true,'Bodyweight row under a sturdy table.','Lie under a strong table and grip the edge. Keep the body straight and pull the chest up to the table.'),
('Dumbbell one-arm row','back','beginner','home',true,false,'Unilateral row supported on a bench or chair.','One hand and knee on a bench. Pull the dumbbell toward the hip, squeeze the shoulder blade, lower fully.'),
('Resistance band row','back','beginner','home',true,false,'Seated row with a band around the feet.','Sit with legs extended and the band around the feet. Pull the handles to the lower ribs, return slowly.'),
('Band pull-apart','back','beginner','home',false,false,'Rear upper back activation with a band.','Hold the band at shoulder height with straight arms. Pull it apart until it touches the chest, return slowly.'),
('Pull-up','back','intermediate','home',true,true,'Vertical pull on a bar with an overhand grip.','Hang with hands slightly wider than shoulders. Pull until the chin passes the bar, lower to full extension.'),
('Chin-up','back','intermediate','home',true,true,'Vertical pull with an underhand grip.','Hang with palms facing you, shoulder width. Pull the chin above the bar, lower under control.'),
('Lat pulldown','back','beginner','gym',true,false,'Machine vertical pull, a pull-up progression.','Thighs under the pad. Pull the bar to the upper chest with elbows down, return slowly.'),
('Seated cable row','back','beginner','gym',true,false,'Horizontal cable row with a neutral spine.','Sit tall, feet braced. Pull the handle to the stomach, squeeze the shoulder blades, extend with control.'),
('Barbell bent-over row','back','intermediate','gym',true,false,'Heavy horizontal row with a hip hinge.','Hinge to about 45 degrees, flat back. Row the bar to the lower ribs, lower without rounding the back.'),
('T-bar row','back','intermediate','gym',true,false,'Chest-supported or standing row for back thickness.','Straddle the bar, hinge forward. Pull the handle to the chest, hold briefly, lower under control.'),
('Straight-arm pulldown','back','intermediate','gym',false,false,'Cable lat isolation with straight arms.','Stand facing the cable, arms straight. Sweep the bar down to the thighs using the lats, return slowly.'),
-- ------------------------------------------------------------------ shoulders
('Wall slide','shoulders','beginner','none',false,true,'Scapular control drill against a wall.','Back and forearms on a wall. Slide the arms up and down keeping contact with the wall.'),
('Pike push-up','shoulders','intermediate','none',true,true,'Bodyweight overhead press pattern.','Hips high in an inverted V. Bend the elbows to lower the head toward the floor, then press back up.'),
('Dumbbell shoulder press','shoulders','beginner','home',true,false,'Seated or standing overhead dumbbell press.','Dumbbells at shoulder height. Press overhead without arching the back, lower to the starting position.'),
('Dumbbell lateral raise','shoulders','beginner','home',false,false,'Side delt isolation.','Slight elbow bend. Raise the arms to shoulder height, pause, lower slowly. Use light weight.'),
('Dumbbell front raise','shoulders','beginner','home',false,false,'Front delt isolation.','Raise a dumbbell in front of you to eye level with a straight arm, lower slowly, alternate arms.'),
('Dumbbell rear delt fly','shoulders','intermediate','home',false,false,'Rear delt isolation bent over.','Hinge forward with a flat back. Raise the dumbbells out to the sides to shoulder height, lower slowly.'),
('Band face pull','shoulders','beginner','home',false,false,'Rear delt and upper back work with a band.','Anchor the band at face height. Pull toward the face with elbows high, squeeze, return slowly.'),
('Machine shoulder press','shoulders','beginner','gym',true,false,'Guided overhead press.','Set the seat so the handles start at shoulder height. Press up until the arms are nearly straight, lower slowly.'),
('Barbell overhead press','shoulders','intermediate','gym',true,false,'Standing barbell press, builds shoulder strength.','Bar at the collarbone, glutes tight. Press overhead, move the head through, lower to the collarbone.'),
('Cable lateral raise','shoulders','intermediate','gym',false,false,'Side delt isolation with constant tension.','Stand beside the cable low pulley. Raise the arm out to the side to shoulder height, lower slowly.'),
('Cable face pull','shoulders','intermediate','gym',false,false,'Rear delt and rotator cuff health exercise.','Rope at face height. Pull toward the forehead with elbows high and hands apart, return slowly.'),
-- ------------------------------------------------------------------ biceps
('Isometric towel curl','biceps','beginner','none',false,true,'Self-resisted curl using a towel.','Stand on a towel looped under one foot. Pull up on the ends while resisting with the foot for 5 seconds.'),
('Dumbbell curl','biceps','beginner','home',false,false,'Standard supinated curl.','Elbows at the sides. Curl the dumbbells up, squeeze, lower fully with control.'),
('Hammer curl','biceps','beginner','home',false,false,'Neutral-grip curl for brachialis and forearm.','Palms facing each other. Curl up without swinging the torso, lower slowly.'),
('Concentration curl','biceps','intermediate','home',false,false,'Seated single-arm curl with elbow braced.','Brace the elbow against the inner thigh. Curl up, squeeze, lower under control.'),
('Resistance band curl','biceps','beginner','home',false,false,'Curl using a band under the feet.','Stand on the band, hold the ends. Curl up with elbows fixed, lower slowly.'),
('Barbell curl','biceps','beginner','gym',false,false,'Standard barbell curl.','Shoulder-width grip, elbows tight to the ribs. Curl to shoulder height, lower slowly without leaning back.'),
('EZ-bar preacher curl','biceps','intermediate','gym',false,false,'Strict curl on a preacher bench.','Arms on the pad. Curl up, do not fully lock out at the bottom, lower slowly.'),
('Cable curl','biceps','beginner','gym',false,false,'Curl with constant cable tension.','Low pulley, elbows at the sides. Curl up, squeeze, return under control.'),
('Incline dumbbell curl','biceps','intermediate','gym',false,false,'Stretched curl on an incline bench.','Bench at 60 degrees, arms hanging back. Curl up without moving the upper arms, lower fully.'),
-- ------------------------------------------------------------------ triceps
('Bench dip','triceps','beginner','none',true,true,'Dip using a chair or bench behind you.','Hands on the edge, legs forward. Lower until the elbows reach about 90 degrees, press up.'),
('Close-grip push-up','triceps','intermediate','none',true,true,'Push-up with hands under the chest.','Hands shoulder width or narrower, elbows close to the body. Lower and press back up.'),
('Dumbbell overhead extension','triceps','beginner','home',false,false,'Two-handed overhead triceps extension.','Hold one dumbbell overhead. Bend the elbows to lower it behind the head, extend back up.'),
('Dumbbell kickback','triceps','beginner','home',false,false,'Bent-over single-arm extension.','Hinge forward, upper arm parallel to the floor. Extend the elbow fully, return slowly.'),
('Resistance band pushdown','triceps','beginner','home',false,false,'Pushdown with a band anchored overhead.','Anchor the band high. Elbows at the sides, push down to full extension, return slowly.'),
('Dumbbell skull crusher','triceps','intermediate','home',false,false,'Lying triceps extension.','Lie on a bench, arms up. Bend the elbows to lower the dumbbells beside the head, extend.'),
('Cable triceps pushdown','triceps','beginner','gym',false,false,'Standard cable pushdown.','Elbows pinned at the sides. Push the bar or rope down to full extension, return slowly.'),
('Cable overhead triceps extension','triceps','intermediate','gym',false,false,'Overhead rope extension for the long head.','Face away from the cable, rope behind the head. Extend the arms forward and up, return slowly.'),
('Close-grip bench press','triceps','intermediate','gym',true,false,'Bench press with a narrower grip.','Grip about shoulder width. Lower to the lower chest with elbows tucked, press up.'),
('Parallel bar dip','triceps','advanced','gym',true,true,'Upright bodyweight dip.','Keep the torso upright on parallel bars. Lower until the upper arms are parallel to the floor, press up.'),
-- ------------------------------------------------------------------ quadriceps
('Bodyweight squat','quadriceps','beginner','none',true,true,'Basic squat pattern.','Feet shoulder width. Sit back and down to parallel with the chest up, drive through the heels to stand.'),
('Reverse lunge','quadriceps','beginner','none',true,true,'Step-back lunge, knee friendly.','Step back, lower until both knees are about 90 degrees, push through the front heel to return.'),
('Wall sit','quadriceps','beginner','none',false,true,'Isometric quadriceps hold.','Back against a wall, thighs parallel to the floor. Hold for the target time.'),
('Bulgarian split squat','quadriceps','intermediate','none',true,true,'Single-leg squat with the rear foot raised.','Rear foot on a chair. Lower straight down until the front thigh is parallel, drive up.'),
('Jump squat','quadriceps','intermediate','none',true,true,'Explosive squat for power.','Squat down, jump up explosively, land softly with bent knees and repeat.'),
('Pistol squat','quadriceps','advanced','none',true,true,'Single-leg full squat.','Stand on one leg, other leg extended forward. Squat down under control and stand up. Hold support if needed.'),
('Goblet squat','quadriceps','beginner','home',true,false,'Front-loaded squat with one dumbbell.','Hold a dumbbell at the chest. Squat deep with an upright torso, stand up through the heels.'),
('Dumbbell lunge','quadriceps','beginner','home',true,false,'Lunge holding dumbbells.','Dumbbells at the sides. Step forward, lower the back knee toward the floor, push back to the start.'),
('Dumbbell step-up','quadriceps','beginner','home',true,false,'Step onto a box or sturdy bench.','Place the whole foot on the box. Drive through that heel to stand tall, lower under control.'),
('Leg press','quadriceps','beginner','gym',true,false,'Machine press for the legs.','Feet shoulder width on the platform. Lower until the knees are about 90 degrees, press without locking the knees.'),
('Barbell back squat','quadriceps','intermediate','gym',true,false,'Primary lower-body strength lift.','Bar on the upper back, brace the core. Squat to parallel or deeper and stand up with a neutral spine.'),
('Leg extension','quadriceps','beginner','gym',false,false,'Machine quadriceps isolation.','Adjust the pad above the ankles. Extend the knees, pause, lower slowly.'),
('Barbell front squat','quadriceps','advanced','gym',true,false,'Front-rack squat, upright torso.','Bar on the front shoulders, elbows high. Squat down keeping the torso vertical, stand up.'),
-- ------------------------------------------------------------------ hamstrings
('Bodyweight good morning','hamstrings','beginner','none',true,true,'Hip hinge practice.','Hands behind the head, soft knees. Push the hips back until the torso is near parallel, return.'),
('Hamstring slider curl','hamstrings','intermediate','none',false,true,'Heel slide curl on a towel.','Lie on your back, heels on towels on a smooth floor. Lift the hips, slide the heels out and curl back in.'),
('Bodyweight single-leg Romanian deadlift','hamstrings','beginner','none',true,true,'Balance hinge on one leg.','Stand on one leg, hinge forward with the other leg back until the torso is parallel, return.'),
('Nordic curl','hamstrings','advanced','none',false,true,'Eccentric hamstring exercise.','Kneel with feet anchored. Lower the body forward as slowly as possible, catch with the hands, push back up.'),
('Dumbbell Romanian deadlift','hamstrings','beginner','home',true,false,'Hip hinge with dumbbells.','Soft knees, dumbbells along the thighs. Push the hips back until you feel a hamstring stretch, drive hips forward.'),
('Resistance band hamstring curl','hamstrings','beginner','home',false,false,'Standing or lying curl against a band.','Anchor the band at the ankle. Curl the heel toward the glute, return slowly.'),
('Dumbbell single-leg Romanian deadlift','hamstrings','intermediate','home',true,false,'Loaded single-leg hinge.','Hold a dumbbell, hinge on one leg with the back leg extended. Keep hips square, return to standing.'),
('Lying leg curl','hamstrings','beginner','gym',false,false,'Machine hamstring curl.','Pad above the heels. Curl toward the glutes, pause, lower slowly.'),
('Seated leg curl','hamstrings','beginner','gym',false,false,'Seated machine curl.','Pad on the lower calf, thigh restraint snug. Curl down and back, return slowly.'),
('Barbell Romanian deadlift','hamstrings','intermediate','gym',true,false,'Loaded hip hinge with a barbell.','Bar at the thighs, soft knees. Push the hips back with a flat back until mid-shin, drive the hips forward.'),
('Conventional deadlift','hamstrings','advanced','gym',true,false,'Full-body pull from the floor.','Bar over mid-foot, flat back, brace. Push the floor away, lock the hips at the top, lower with control.'),
-- ------------------------------------------------------------------ glutes
('Glute bridge','glutes','beginner','none',false,true,'Basic hip extension.','On your back, knees bent. Drive the hips up squeezing the glutes, hold, lower slowly.'),
('Single-leg glute bridge','glutes','intermediate','none',false,true,'Unilateral bridge.','One foot on the floor, other leg extended. Lift the hips level, hold, lower.'),
('Donkey kick','glutes','beginner','none',false,true,'Quadruped glute extension.','On hands and knees. Kick one heel toward the ceiling keeping the knee bent, lower slowly.'),
('Fire hydrant','glutes','beginner','none',false,true,'Quadruped hip abduction.','On hands and knees. Raise the bent knee out to the side without rotating the torso, lower slowly.'),
('Dumbbell hip thrust','glutes','beginner','home',true,false,'Hip thrust with a dumbbell on the hips.','Upper back on a bench, dumbbell across the hips. Drive up until the torso is level, squeeze, lower.'),
('Dumbbell sumo squat','glutes','beginner','home',true,false,'Wide-stance squat with a dumbbell.','Feet wide, toes out, dumbbell between the legs. Squat deep, drive up squeezing the glutes.'),
('Resistance band lateral walk','glutes','beginner','home',false,false,'Band walk for the gluteus medius.','Band above the knees, small squat. Take steps sideways keeping tension in the band.'),
('Barbell hip thrust','glutes','intermediate','gym',true,false,'Heavy glute exercise.','Upper back on a bench, bar over the hips. Drive up to a level torso, chin tucked, lower under control.'),
('Cable glute kickback','glutes','intermediate','gym',false,false,'Standing cable hip extension.','Strap at the ankle. Extend the leg back squeezing the glute without arching the back, return slowly.'),
('Hip abduction machine','glutes','beginner','gym',false,false,'Seated outward leg press.','Pads outside the knees. Push the legs apart, pause, return slowly.'),
-- ------------------------------------------------------------------ calves
('Bodyweight calf raise','calves','beginner','none',false,true,'Standing calf raise on the floor.','Rise onto the toes as high as possible, pause, lower slowly.'),
('Single-leg calf raise','calves','intermediate','none',false,true,'One-leg calf raise.','Stand on one foot, hold a support. Rise to the toes, pause, lower slowly.'),
('Step calf raise','calves','intermediate','none',false,true,'Calf raise with a full stretch on a step.','Balls of the feet on a step. Lower the heels below the step, rise as high as you can.'),
('Dumbbell standing calf raise','calves','beginner','home',false,false,'Loaded calf raise.','Hold dumbbells at the sides. Rise to the toes, pause, lower slowly.'),
('Single-leg dumbbell calf raise','calves','intermediate','home',false,false,'Loaded one-leg calf raise.','One dumbbell in the working hand, other hand on a support. Rise and lower with control.'),
('Standing calf raise machine','calves','beginner','gym',false,false,'Machine standing calf raise.','Shoulders under the pads. Lower the heels deeply, rise to the toes, pause at the top.'),
('Seated calf raise machine','calves','beginner','gym',false,false,'Targets the soleus.','Pads on the thighs. Lower the heels, rise to full contraction, return slowly.'),
('Leg press calf raise','calves','intermediate','gym',false,false,'Calf raise on the leg press.','Balls of the feet on the lower platform, legs almost straight. Press through the toes and return.'),
('Donkey calf raise','calves','advanced','gym',false,false,'Bent-over loaded calf raise.','Hinge at the hips with a partner or machine load on the lower back. Full stretch, then rise.'),
-- ------------------------------------------------------------------ core
('Plank','core','beginner','none',false,true,'Front isometric hold.','Forearms on the floor, body in a straight line. Brace the abs and hold without sagging.'),
('Dead bug','core','beginner','none',false,true,'Anti-extension coordination drill.','On your back, arms up and knees at 90 degrees. Lower the opposite arm and leg while the lower back stays flat.'),
('Bird dog','core','beginner','none',false,true,'Quadruped stability exercise.','On hands and knees. Extend the opposite arm and leg, hold briefly, return and alternate.'),
('Crunch','core','beginner','none',false,true,'Basic abdominal flexion.','Lie on your back, knees bent. Curl the shoulders off the floor, pause, lower slowly.'),
('Bicycle crunch','core','beginner','none',false,true,'Alternating crunch with rotation.','Hands behind the head. Bring opposite elbow and knee together while extending the other leg, alternate.'),
('Mountain climber','core','intermediate','none',false,true,'Dynamic plank drill.','High plank. Drive the knees alternately toward the chest at a steady pace.'),
('Side plank','core','intermediate','none',false,true,'Lateral isometric hold.','Support on one forearm, body in a straight line, hips lifted. Hold and switch sides.'),
('Hollow body hold','core','intermediate','none',false,true,'Full-body tension hold.','On your back, lift shoulders and straight legs slightly off the floor with the lower back pressed down. Hold.'),
('Lying leg raise','core','intermediate','none',false,true,'Lower abdominal exercise.','Lie flat, legs straight. Raise the legs to vertical, lower slowly without arching the back.'),
('V-up','core','advanced','none',false,true,'Dynamic jackknife crunch.','Lie flat. Raise the straight legs and torso at the same time to touch the toes, lower under control.'),
('Dumbbell Russian twist','core','intermediate','home',false,false,'Rotational core exercise.','Seated, feet raised, lean back slightly. Rotate the dumbbell from side to side.'),
('Ab wheel rollout','core','advanced','home',false,true,'Anti-extension core exercise.','Kneel holding the wheel. Roll forward keeping the spine neutral, then pull back using the abs.'),
('Hanging knee raise','core','intermediate','home',false,true,'Pull-up bar knee raise.','Hang from a bar. Raise the knees toward the chest without swinging, lower slowly.'),
('Hanging leg raise','core','advanced','home',false,true,'Straight-leg hanging raise.','Hang from a bar. Raise straight legs to hip height or higher, lower slowly.'),
('Cable crunch','core','intermediate','gym',false,false,'Weighted kneeling crunch.','Kneel facing a high pulley, rope at the head. Curl the ribs toward the pelvis, return slowly.'),
('Pallof press','core','intermediate','gym',false,false,'Anti-rotation cable press.','Stand side-on to a cable at chest height. Press the handle straight out, resist the rotation, return.');

DO $$
DECLARE missing text;
BEGIN
  SELECT string_agg(DISTINCT s.grp, ', ') INTO missing
    FROM _exercise_seed s LEFT JOIN muscle_group mg ON mg.name = s.grp WHERE mg.id IS NULL;
  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'exercise seed references unknown muscle groups: %', missing;
  END IF;
END $$;

INSERT INTO exercise (name, main_muscle_group_id, difficulty_level, equipment, is_compound, is_bodyweight, description, instruction)
SELECT s.name, mg.id, s.level::experience_level_t, s.equip::equipment_t, s.compound, s.bodyweight, s.descr, s.instr
  FROM _exercise_seed s JOIN muscle_group mg ON mg.name = s.grp
ON CONFLICT (name) DO UPDATE SET
  main_muscle_group_id = EXCLUDED.main_muscle_group_id, difficulty_level = EXCLUDED.difficulty_level,
  equipment = EXCLUDED.equipment, is_compound = EXCLUDED.is_compound, is_bodyweight = EXCLUDED.is_bodyweight,
  description = EXCLUDED.description, instruction = EXCLUDED.instruction;

DROP TABLE _exercise_seed;
