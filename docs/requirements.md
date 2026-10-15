# Requirements

Condensed from thesis chapter 4 and the use case scenarios (6.1). The numbers here are binding for implementation. Reference IDs in PRs (e.g. "Implements FR-U7").

## Actor

User – a person using the mobile app. Enters biometric data, reports progress, follows generated plans. External system: Vision API (meal photo recognition).

## Functional requirements

### FR-U: User management

| ID    | Requirement                                                                                                         |
| ----- | ------------------------------------------------------------------------------------------------------------------- |
| FR-U1 | Register with email and password                                                                                    |
| FR-U2 | Log in; session handled with JWT                                                                                    |
| FR-U3 | Reset password via verification link sent by email                                                                  |
| FR-U4 | Change email and password in profile settings                                                                       |
| FR-U5 | Delete account together with all related data (GDPR)                                                                |
| FR-U6 | Enter and edit biometric profile: age, sex, weight, height, activity level (PAL), injuries and physical limitations |
| FR-U7 | Validate biometric data (weight 30–300 kg, age 16–100, height 120–250 cm); show a clear error message for invalid or missing values |
| FR-U8 | Sign in with Google or Apple in addition to email and password (accounts linked by verified email)                  |

### FR-P: Plan generation

| ID    | Requirement                                                                                                                                                                                |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| FR-P1 | Generate a training plan (exercises, sets, reps) based on goal, number of training days, experience level (beginner / intermediate / advanced) and available equipment (gym / home / none) |
| FR-P2 | Acceptance: the plan contains at least one exercise per main muscle group of the chosen goal and no exercise excluded by the user's injuries                                               |
| FR-P3 | If there are not enough exercises for a muscle group, inform the user and suggest changing the goal or equipment                                                                           |
| FR-P4 | Calculate daily calorie need (TDEE) from biometric data and PAL                                                                                                                            |
| FR-P5 | Calculate macronutrient split (protein, fat, carbs) according to the goal                                                                                                                  |
| FR-P6 | Generate a diet plan from goal, preferences, allergies and calculated targets                                                                                                              |
| FR-P7 | User reviews the plan and accepts it or regenerates it after changing preferences                                                                                                          |
| FR-P8 | Browse exercise library with text instructions and food database with nutrition values                                                                                                     |
| FR-P9 | Schedule training days and meal times with reminders (local notifications on the device; server push through Expo push for report and achievement messages)                                |

### FR-A: Adaptation and progression

| ID    | Requirement                                                                                                                                                                           |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-A1 | Swap an exercise for an alternative targeting the same muscle group                                                                                                                   |
| FR-A2 | Report workout difficulty as RPE (1–10)                                                                                                                                               |
| FR-A3 | Report hunger level during the diet                                                                                                                                                   |
| FR-A4 | Automatically reduce volume or intensity of the next session only after an explicit signal: RPE ≥ 9 or a set that could not be completed. Never modify the plan without such a signal |
| FR-A5 | Automatically increase load (linear progression) when sets are completed with reserve                                                                                                 |

### FR-N: Meal recognition (AI)

| ID    | Requirement                                                                                                                                                 |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-N1 | Upload a meal photo (camera or gallery)                                                                                                                     |
| FR-N2 | Return a list of recognized products with grams, calories and macronutrients                                                                                |
| FR-N3 | Check the recognized meal against the user's intolerances and allergies                                                                                     |
| FR-N4 | User can correct products and grams before saving. Unconfirmed result is stored in MongoDB (expires automatically); confirmed result is saved to PostgreSQL |
| FR-N5 | Real-time meal suggestions: propose foods and portions that bring the day's intake to the remaining targets                                                 |

### FR-R: Analytics and reports

| ID    | Requirement                                                                       |
| ----- | --------------------------------------------------------------------------------- |
| FR-R1 | Weekly and monthly report: weight change, strength in key exercises               |
| FR-R2 | Plan compliance in % (diet and workouts)                                          |
| FR-R3 | Charts: weight progress, training tonnage, workouts per week, calorie intake      |
| FR-R4 | Predict the goal date from the current progress pace; warn when data is irregular |
| FR-R5 | Reports require at least 7 days of data; otherwise show "not enough data" message |
| FR-R6 | Export a report to PDF or CSV                                                     |
| FR-R7 | Automatic weekly report generated by a scheduled job, with a push notification    |

## Non-functional requirements

| Area          | Requirement                                                              |
| ------------- | ------------------------------------------------------------------------ |
| Performance   | UI response to interaction ≤ 300 ms                                      |
| Performance   | Plan generation ≤ 3 s                                                    |
| Performance   | Meal photo analysis ≤ 10 s (4G / Wi-Fi)                                  |
| Scalability   | 500 concurrent sessions with response time degradation ≤ 20%             |
| Compatibility | Android 10+, 4 GB RAM, ~200 MB install size; screens 4.7–6.7 in          |
| Security      | Passwords hashed with bcrypt; HTTPS only; JWT authentication             |
| Security      | Input validation; SQL injection prevented by parameterized queries (ORM) |
| Reliability   | Data consistency guaranteed by PostgreSQL transactions                   |
| Usability     | Main functions visible on screen; consistent with Nielsen's heuristics   |
| UI            | Light and dark mode                                                      |
| Offline (NFR-OFF) | Plans, workout logs, nutrition logs and body metrics work offline and synchronize when the connection returns, without data loss or duplicates |

## Decisions on former open questions (closed at G0; change only through a change request)

| Question | Decision |
| --- | --- |
| Age and height ranges | age 16–100, height 120–250 cm (confirm 16 as the digital-consent age) |
| "Set with reserve" | every planned rep completed on every set with RPE <= 7 |
| Progression / reduction steps | +2.5 kg upper body, +5 kg lower body; reduction -10 % load rounded to 2.5 kg or -1 set (constants in `algorithms.md`) |
| Real-time meal suggestions | in scope, FR-N5 |
| Report export | PDF and CSV, FR-R6 |
| Google / Apple sign-in | in scope, FR-U8 (Apple needs an Apple Developer account) |
| Automatic weekly report | in scope, FR-R7 |
| Mongo failed status | not stored; AI errors are returned directly |
| Photo storage | local Docker volume; unconfirmed photos removed by cleanup job after expiry |
| Mongo expiry | 6 h |
| Offline scope | plans (read), workout logs, nutrition logs, body metrics; plan generation, recognition and reports are online-only |
