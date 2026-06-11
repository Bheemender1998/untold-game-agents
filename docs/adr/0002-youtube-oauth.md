# ADR 0002 — YouTube publishing via OAuth 2.0 (Stage 2)

**Status:** Accepted, not yet implemented (2026-06-10)

## Context
Publishing/uploading a video acts *on behalf of* the channel's Google account —
an API key is insufficient; OAuth 2.0 is required.

## Decision
Stage-2 publishing uses the **YouTube Data API v3** with an OAuth 2.0 "Desktop app"
client. Setup: Google Cloud project → enable YouTube Data API v3 → OAuth client →
consent screen (scopes `youtube.upload`, `youtube.readonly`, `youtube`) → download
`client_secrets.json` to the repo root (gitignored). Token cached locally after
first auth. Implemented in `engine/publish/uploader.py`.

## Consequences
- One-time manual Google Cloud setup (free, reversible) before any upload code runs.
- `client_secrets.json` and `token.json` are gitignored secrets.
- While the OAuth app is in "Testing", only added test users can use it — fine for
  a personal channel tool.
