# Open questions

Agents append here when a spec is silent or contradictory. Format: `- [task id] question. Proposed default: ... (status: open/answered)`.

- [G0] Is 16 the correct minimum age (digital-consent age in Poland)? Proposed default: 16. (status: open)
- [G0] FR-P2 versus injuries: a main muscle group fully blocked by an injury is skipped and reported, not an error (algorithms.md 4.3). (status: open, confirm)
- [D-05] The Hugging Face model weights could not be verified when this package was written; run the feasibility check before any AI code. (status: open)
- [B-02] Refresh-token lifetime under rotation: does each rotated token get a fresh 30 days (sliding), or does the family keep the 30 days from login (absolute)? Proposed default: sliding, implemented that way. (status: open)
- [B-02] Rate limiting and lockout numbers are not specified (D-06 not written yet). Proposed default: 10 requests per 60 s per client IP and route on register/login (later forgot), 429 `rate_limited` with `Retry-After`; no per-account lockout (it lets an attacker lock out a victim). Configurable via `AUTH_RATE_LIMIT`, `AUTH_RATE_WINDOW_SECONDS`. (status: open)
- [B-02] bcrypt cost factor not specified. Proposed default: 12 (`BCRYPT_ROUNDS`). (status: open)
- [B-03] Logout with a refresh token that belongs to another user or is unknown: the contract lists only 204/401. Proposed default: 401 `unauthorized`, nothing revoked; the caller's own token (even already rotated) revokes its whole family and gives 204. (status: open)
- [B-03] Access tokens stay valid until expiry (max 15 min) after logout; only refresh tokens are revoked. Proposed default: accept this (stateless JWT, no deny list). (status: open)
