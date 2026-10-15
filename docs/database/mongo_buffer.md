# MongoDB buffer for meal recognition (D-02)

Based on decision D3, `docs/algorithms.md` section 11 and the recognition endpoints in `docs/api/openapi.yaml`. This file replaces the earlier version.

## Purpose
MongoDB stores only unconfirmed results of meal photo recognition. After confirmation the data is normalized into PostgreSQL (`recognition_ai`, `nutrition_log`, `nutrition_log_food_item`) and the document is deleted. Unconfirmed documents expire after 6 hours.

## Lifecycle
1. `POST /meals/recognitions` (multipart): validate type and size, strip EXIF, store the photo, call `ai-service`, map labels to foods, write a document with `status: "pending"`.
2. The user edits items through `POST /meals/recognitions/{id}/items`, `PATCH|DELETE /meals/recognitions/{id}/items/{index}`. Every edit recalculates nutrition and sets `corrected: true` where relevant.
3. `POST /meals/recognitions/{id}/confirm` writes the PostgreSQL rows in ONE transaction, then deletes the document. If the transaction fails, PostgreSQL is unchanged and the document stays.
4. Unconfirmed documents are removed by the TTL index. A cleanup job also deletes their photo files (the TTL index cannot).
5. AI errors are returned directly to the client (HTTP 503 `ai_unavailable`); no `failed` document is stored.

## Collection `meal_recognitions`

| Field | Type | Description |
| --- | --- | --- |
| `_id` | ObjectId | Exposed in the API as the recognition id (string) |
| `userId` | int | Owner in PostgreSQL; every query filters by it (object-level authorization) |
| `status` | string | always `pending` |
| `mealType` | string | `breakfast`, `lunch`, `dinner`, `snack` |
| `photoPath` | string | relative path in the photo volume, `meals/<userId>/<uuid>.jpg` |
| `modelName`, `modelVersion` | string | from the `ai-service` response |
| `overallConfidence` | double | confidence of the top candidate, 0-1 |
| `recognisedItems` | array | see below |
| `createdAt` | date | creation time |
| `expiresAt` | date | `createdAt + 6 h` |

Element of `recognisedItems`:

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | display name (food name if matched, otherwise the model label) |
| `foodItemId` | int / null | matched `food_item.id`; null when no match (the user must choose a food) |
| `label` | string / null | model label that produced the item; null for manually added items |
| `labelCandidates` | array | top-K `{label, confidence, foodItemId}` from the model (K = 3); lets the user switch to another candidate |
| `grams` | int | starting value is `default_portion_g` |
| `defaultPortionUsed` | bool | true until the user changes grams |
| `confidence` | double | 0-1 |
| `lowConfidence` | bool | confidence < 0.30 |
| `allergyWarning` | bool | the food shares an allergen with the user's allergens |
| `allergens` | array of string | allergen codes that triggered the warning |
| `nutrition` | object | `kcal`, `protein`, `fat`, `carbs` for the given grams |
| `corrected` | bool | the user changed the item |

## Indexes
```js
db.meal_recognitions.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 })   // TTL
db.meal_recognitions.createIndex({ userId: 1, status: 1 })
```
The TTL monitor runs about once a minute. The backend must ignore documents whose `expiresAt` is in the past.

## Photo storage and cleanup
- Photos live in a Docker volume mounted into the backend (`PHOTO_DIR`), never served as static files; the API streams them to the owner only.
- Cleanup job (every 15 min): delete photo files under `meals/` that are not referenced by any Mongo document and not by a `recognition_ai.image_url` row and are older than 6 h.
- Confirmed photos are kept until account deletion; account deletion removes `meals/<userId>/` and the user's Mongo documents.

## Resolved questions
Photo storage = local volume; no `failed` status; expiry = 6 h.
