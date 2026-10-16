-- DB-03: injury dictionary (FR-U6, FR-P2). The list and healing times are proposed defaults, see docs/questions.md.
-- Which exercises each type rules out is seeded together with the exercises (DB-04), because it needs their ids.
INSERT INTO injury_type (name, description, avg_healing_time_days) VALUES
  ('shoulder impingement',       'Pinching of rotator cuff tendons under the acromion; pain on overhead and lateral movements', 60),
  ('rotator cuff strain',        'Strain or partial tear of the rotator cuff tendons',                                           90),
  ('elbow tendinopathy',         'Tennis or golfer''s elbow: overuse of forearm tendons at the elbow',                           90),
  ('wrist sprain',              'Ligament sprain of the wrist; painful gripping and weight bearing',                            42),
  ('neck strain',               'Muscle strain of the neck or upper trapezius',                                                 21),
  ('lower back strain',         'Muscle or ligament strain of the lumbar region',                                               28),
  ('herniated disc',            'Disc protrusion with possible nerve irritation; spinal loading is painful',                    120),
  ('hip flexor strain',         'Strain of the hip flexors; painful hip flexion and running',                                   35),
  ('groin strain',              'Adductor muscle strain; painful leg abduction and lateral movement',                           42),
  ('hamstring strain',          'Strain of the hamstring muscles',                                                              42),
  ('quadriceps strain',         'Strain of the quadriceps muscles',                                                             35),
  ('patellar tendinopathy',     'Jumper''s knee: pain below the kneecap under load',                                            90),
  ('knee ligament injury',      'Sprain of the ACL, MCL or meniscus irritation; instability under load',                        120),
  ('shin splints',              'Pain along the tibia from repeated impact',                                                    42),
  ('ankle sprain',              'Ligament sprain of the ankle',                                                                 42),
  ('achilles tendinopathy',     'Overuse injury of the Achilles tendon',                                                        90),
  ('rib or chest wall strain',  'Intercostal or chest wall muscle strain; painful pressing and deep breathing',                 28)
ON CONFLICT (name) DO UPDATE
  SET description = EXCLUDED.description, avg_healing_time_days = EXCLUDED.avg_healing_time_days;
