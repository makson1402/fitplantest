-- DB-03: muscle groups (docs/algorithms.md section 3). Idempotent: re-running updates in place.
INSERT INTO muscle_group (name, description, body_region) VALUES
  ('chest',      'Pectoral muscles: pressing movements and flyes',            'upper'),
  ('back',       'Lats, rhomboids, traps and spinal erectors: pulling movements', 'upper'),
  ('shoulders',  'Deltoids: overhead presses and raises',                     'upper'),
  ('biceps',     'Front of the upper arm: curls',                             'upper'),
  ('triceps',    'Back of the upper arm: extensions and pushdowns',           'upper'),
  ('quadriceps', 'Front of the thigh: squats, lunges, leg press',             'lower'),
  ('hamstrings', 'Back of the thigh: deadlift variations and leg curls',      'lower'),
  ('glutes',     'Gluteal muscles: hip thrusts, bridges and hinges',          'lower'),
  ('calves',     'Lower leg: calf raises',                                    'lower'),
  ('core',       'Abdominals and obliques: planks, crunches, carries',        'core')
ON CONFLICT (name) DO UPDATE
  SET description = EXCLUDED.description, body_region = EXCLUDED.body_region;
