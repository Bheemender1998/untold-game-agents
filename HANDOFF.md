# The Untold Game — HANDOFF

Session wrap log. Newest first. Use the `handoff` skill to append a new entry.

---

## Session 7 (2026-06-11) — Remotion pivot + first video PUBLISHED + repo created

**BIGGEST THING — this project now has its own git repo.** It was previously an
**untracked folder inside the PatternFinding working tree** (git root was `~`, remote
`patternfinding.git`). `git init` here + first commits + pushed PRIVATE to
**github.com/Bheemender1998/untold-game-agents** (`origin/main`). Never commit Untold
Game code into patternfinding. Heavy/secret paths are gitignored (`.env*`, `token.json`,
`produced/`, `queue/`, `node_modules/`, `.venv-video/`, `engine/video/models/`, media).

**Video engine pivoted HyperFrames → Remotion** (user rejected flat/colored backgrounds,
asked for designed templates). `engine/video/remotion/` is a Remotion 4.x project (free
for solo): `UntoldVideo` composition = graded atmospheric **Pexels b-roll per chapter** +
**kinetic TikTok-style captions** (`@remotion/captions`, fed by our whisper word-timings) +
chapter cards + intro/outro. `run_video.py` now defaults `--engine remotion`; HyperFrames
kept as `--engine hyperframes`. Python bridge: `remotion_build.py` (props) + `render_remotion.py`
(stage `public/` + `npx remotion render`). Render ~40–45 min for a 13-min video on the M2.

**Full narrated pipeline is LIVE end-to-end:**
- TTS = **Kokoro** (`tts.py`, in `.venv-video`; models in `engine/video/models/`). macOS
  `say` is the zero-install fallback. Run renders with `.venv-video/bin/python -m engine.run_video`.
- Captions = **faster-whisper** word timings + **proper-noun glossary** bias (`captions.proper_nouns`)
  so names spell right (fixed "Madeleine"→"Medellín").
- Footage = **Pexels** (`footage.py`): no-people query rules, browser User-Agent (Cloudflare
  1010 fix), **randomized pick + cross-video dedup** (`used_clips.json`).
- Grade = **warm-subtle** (Background.tsx), brightened so footage is never near-black.

**First video PUBLISHED (unlisted): https://youtu.be/fL8XA6D8NvQ** (Escobar, bdffcdb7).
Chapters on the live video + `metadata.json` corrected to the real 13:38 runtime (were
authored for ~30 min). Codex caught + fixed 3 real bugs pre-render: `transcribe()` dict vs
list, Background fade non-monotonic, Pexels UA 403.

### NEXT SESSION = **B: automation infra** (user chose human-approve-before-publish, ~2/day)
1. `run_auto.py` orchestrator — unattended `ideate → produce(fact-gate) → render → QC →
   mark awaiting_approval`, N videos/run.
2. `qc.py` auto-QC — brightness band, caption coverage, render integrity, **Claude-vision
   people-check per clip** (auto-reject faces). Failures flag, never ship.
3. Approval queue → one-tap approve → auto-publish (uploader exists).
4. Scheduler — **launchd on the M2** (render must run locally; Railway can't do the
   45-min Chromium render). Renders overnight.

### Also queued (not blocking B)
- **Composition pointers** — `docs/next-video-improvements.md`: more headings, bigger/
  multi-column captions (`remotion/src/components/Captions.tsx`), newspaper-clipping stills,
  sources+links in the YouTube description.
- **Shorts/TikTok/IG** — vertical (1080×1920) Remotion comp + short-script condenser
  (hook → one fact → "full story on YouTube"); per-platform posting is the heavier part.
- **Voice graininess** on some words (Kokoro) — try alt voice/speed; cosmetic.

### Suggested skills next session
- `superpowers:brainstorming` then `writing-plans` for B (it's a multi-part build).
- `codex:rescue` for a second pass on the orchestrator/QC.
- `claude-api` before any Claude-vision wiring in qc.py.

### Key gotchas
- Render needs `npx` (user shell) — harness sandbox can't, but the user/launchd can.
- Run the venv python for narrated renders or Kokoro/whisper are missing.
- `PEXELS_API_KEY` is in `.env` (gitignored). Pexels needs the browser UA header.

---

## Session 6 (2026-06-11) — produce-pipeline hardening + WRAP

Six Codex stop-time findings fixed this session (all verified deterministically,
no API spend; real queue/artifacts untouched via temp-queue tests):

1. **Fact-gate is a real gate** — `factcheck()` returns `complete`/`passed`
   (`passed` = zero issues AND coverage complete; cap 14→25). `run_factcheck`
   warns on incomplete coverage, **re-verifies after `--fix`**, prints ✓PASSED/
   ✗NOT PASSED, and **exits non-zero** unless clean+complete. (was: could "pass"
   while claims unchecked or flagged.)
2. **No stale script artifact** — full produce now **always overwrites** `script.md`
   (was: only-if-absent → re-runs recorded the old file).
3. **Atomic + crash-safe** — all artifact writes and `queue_manager._save` use
   temp-file + `os.replace`; `produce()` does **invalidate-first / commit-last**
   (marks `producing`, `fact_passed=False` before touching the script; commits the
   real verdict only after everything's on disk).
4. **No stale publishable paths** — invalidation also clears `script_path`/
   `metadata_path`/`factcheck_path`/`video_path`; re-committed only on success
   (a new script clears `video_path` → forces re-render). `youtube_url` kept as
   historical pointer.

Net: an interrupted produce leaves the idea honestly `producing` with **no**
publishable artifacts; a successful one commits `in_production` only when verified.

### Pending artifacts (next session picks up here)
- **Live unlisted video is STALE** — `https://youtu.be/OubjZSOTh68` was rendered
  from the PRE-fact-gate script (had the "parking lot / shot once" errors). The
  corrected script is at `produced/bdffcdb7/script.md` (`.bak` = original). Must
  **re-render + re-upload** before it ever goes public.
- **Idea `bdffcdb7`** (Escobar): script corrected + fact-checked; `video_path`
  cleared → needs re-render.
- **`competitor_gap` agent → 0 ideas** (429'd on the 30k-TPM tier earlier). Re-run
  `python3 -m engine.run_pipeline --agent 3 --sequential`.
- Queue: 15 ideas (sports 5, trending 5, evergreen 5); only `bdffcdb7` produced.

### Next-session focus (decisions locked: Kokoro TTS + atmospheric-only visuals)
1. Re-render corrected Escobar (now has dissolves + subscribe outro) → re-upload unlisted:
   `python3 -m engine.run_video --id bdffcdb7 --render`
2. **Narrated build** — first run `python3 -m pip install kokoro-onnx faster-whisper`,
   then wire `tts.py` (Kokoro) → `captions.py` (faster-whisper word timings) →
   `compose.py` narrated mode (audio track + headlines synced to voice + atmospheric
   visuals) → `run_video --mode narrated`. Verify each step against a render.
3. Visuals: atmospheric/symbolic only (CC stock), **never fabricated real people/events**.

### Suggested skills next session
- `run-pipeline` / `review-ideas` (project skills) for generating/reviewing ideas.
- `claude-api` before any Anthropic/TTS-adjacent wiring.
- `codex:rescue` for a second set of eyes on the narrated-pipeline build.

### Key references (don't duplicate — read these)
- Architecture/conventions: `CLAUDE.md` · ADRs: `docs/adr/0001`–`0005`
  (0003 free search, 0004 video stack, 0005 fact-gate).
- Constraints: M2/8GB (no local SDXL); shared CF Anthropic key, 30k TPM → `--sequential`.

---

## Session 5 (2026-06-11) — fact-gate autochained + video continuity/CTA + decisions

**Shipped**
- **Fact-gate autochained into `run_produce`** — produces script → fact-checks →
  auto-corrects once → re-verifies → metadata. Idea marked `in_production` ONLY if
  the gate passes, else `needs_review` (records `fact_passed`, `factcheck_path`).
  Flags: `--no-factcheck`, `--no-autofix`, `--max-claims` (default 25). Verified:
  pass→in_production, fail-after-autofix→needs_review.
- **`compose.py` video upgrades** (text mode, no new deps, verified): cross-dissolve
  overlap between cards (continuous, not slideshow), subtle Ken-Burns scale on the
  headline, and a **"Subscribe for more untold stories." outro** appended to every
  composition.
- Fact-gate hardened earlier this session now reflected in CLAUDE.md.

**Decisions (went with recommendation):**
- **TTS = Kokoro** (free, local, runs on M2/8GB).
- **Visuals = atmospheric/symbolic only** (stadiums, rain, crowds, textures) from
  free CC stock — **never fabricated real people/events** (same integrity rule as
  the fact-gate; AI-faking reality is the visual equivalent of a false claim).

**Open / next — the narrated + visuals build (needs 2 user installs):**
1. `python3 -m pip install kokoro-onnx faster-whisper` (or `pip install -r requirements-video.txt`).
2. Then I wire: `tts.py` (Kokoro narration from script) → `captions.py` (faster-whisper
   word timings) → `compose.py` narrated mode (narration audio track + headlines synced
   to timings + atmospheric visuals) → `--mode narrated`. Verify each step with a render.
3. Re-render the corrected Escobar (`run_video --id bdffcdb7 --render`) — now with the
   subscribe outro + dissolves — and re-upload before going public.

## Session 4 (2026-06-11) — fact-verification gate (the existential one)

**Why:** the published Escobar teaser stated fabricated specifics about a real death
("Gallón found dead in a parking lot, shot once" — real death, wrong place + invented
count). User caught it.

**Shipped**
- `engine/pipeline/factcheck.py` + `engine/run_factcheck.py [--fix]`: extract every
  concrete claim (structured output) → free DDG search per claim → Claude judges
  supported/contradicted/unverified + correction + source. `--fix` rewrites script.md
  (backup .bak). Sequential (TPM-safe). ADR-0005; rule added to CLAUDE.md (mandatory
  before publish).
- **Ran on Escobar script: 14 claims, 7 flagged.** Real errors found & fixed: Gallón
  "acquitted"→never tried; Romania score direction; "Ernie"→"Earnie" Stewart; homicide
  rate 380→375; **fabricated Gallón "parking lot/shot once" removed** (now just "found
  dead in Mexico, Feb 2026"). Corrected `produced/bdffcdb7/script.md` (.bak kept).
- Gate is deliberately conservative (off-target search → flag); human review still required.

**Open / next**
1. **Re-render Escobar from the corrected script** — slides were built from the
   pre-gate script: `python3 -m engine.run_video --id bdffcdb7 --render`, re-upload,
   then it's safe to go public. (Current unlisted video has the errors — keep down.)
2. **Production upgrade** (user's asks, pending 2 decisions): voiceover narration +
   on-screen headlines synced + real visuals + subscribe-CTA outro + continuous feel
   (dissolves/Ken-Burns). Decisions needed: **TTS** = Kokoro(free-local)/ElevenLabs(paid);
   **visuals** = rights-cleared archival stills / atmospheric AI b-roll (no real people).
3. Wire factcheck into `run_produce` so produce→factcheck is automatic (currently separate).

---

## Session 3 (2026-06-11) — video stack adopted (open-source eval)

**Shipped**
- Evaluated 10 open repos to fill the script→video gap; locked the stack in
  `docs/adr/0004-open-source-video-stack.md`. Scaffolded `engine/video/`:
  `tts.py` (narration), `captions.py` (Whisper timing), `visuals.py` (imagery),
  `footage.py` (yt-dlp, rights-gated), `compose.py` (Claude→HyperFrames HTML),
  `render.py` (HyperFrames→MP4), `renderer/` (Node project + package.json).
  Pure helpers verified (narration-text stripping, [VISUAL] cue extraction).
- **Keystone = HyperFrames** (Apache-2.0): HTML→MP4, agent-driven, deterministic.
  Node 23 + ffmpeg 8.1 confirmed present → it can run here.
- Added `requirements-video.txt` (piper-tts / faster-whisper / scrapegraphai),
  gitignored video build artifacts.
- **Mode-switched spine BUILT** — `compose.py` now real: distills a script into
  ~22 on-screen text beats (structured output), renders a HyperFrames `index.html`
  (kinetic typography, gradient bg, GSAP, **SRI-pinned** gsap 3.13.0). `run_video.py`
  entrypoint: `--mode text|narrated`, `--id`, headless-safe (compose only — render is
  a manual step, see below; `render.py` is a deliberate not-yet-wired placeholder so
  we don't ship a `--render` that can't succeed). Timing is
  reading-time-derived (ignores the model's unreliable `seconds`), markdown stripped,
  newlines→`<br>`. **text mode runs on this machine with only HyperFrames — no TTS,
  no Fooocus.**
- **First real composition generated**: `produced/bdffcdb7/video/index.html` (Escobar,
  22 clips, ~120s, validated structure). Ready to render — just needs `npx hyperframes render`.

**Hard constraints found**
- Machine is **M2 / 8GB** → local SDXL (Fooocus) NOT viable (~12-16GB). Imagery
  must come from cloud gen or CC stock here. Render/Whisper/small-Qwen3 OK but not
  all at once.
- **TTS gap:** none of the 10 repos do text-to-speech (Whisper is the inverse).
  Need Piper/Kokoro (free local) or a cloud voice — undecided.
- **Footage rights:** yt-dlp gated to PD/CC/own only (copyright landmine).

**RENDER PROVEN + WIRED (2026-06-11):** User ran the first render → MP4 at
`engine/video/renderer/renders/renderer_<ts>.mp4`. Confirmed contract: HyperFrames
renders inside the initialized `engine/video/renderer/` project (`npm install && npx
hyperframes init .`), reads `index.html`, writes `renders/renderer_<ts>.mp4`.
`render.py` now wired to that contract; `run_video --render` stages the composition →
renders → copies to `produced/<id>/video/video.mp4` → records `video_path` on the idea.
(Runs in the user's shell; the harness sandbox can't exec npx but the user can.)
**The first Untold Game video already exists** (the Escobar composition rendered).

**🎉 FULL LOOP CLOSED (2026-06-11):** First video PUBLISHED — idea→script→metadata→
video→YouTube. `https://youtu.be/OubjZSOTh68` (unlisted) on **The Untold Game**
(channel UC0TQdznFMpnrrhLCjHVuB3Q). idea bdffcdb7 status=published.
- OAuth gotchas solved: (a) sign-in account must be added as a **Test user** in the
  OAuth consent screen (even the owner) or you get 403 access_denied; (b) the token
  binds to whichever channel you pick at "Choose your account / brand account" — must
  pick **The Untold Game** brand account, not the personal "Bheemender Gurram".
- Bug fixed: YouTube rejects tag sets >500 chars (`invalidTags`). `uploader._safe_tags`
  now trims to a ~480-char budget + strips `<`/`>` (30 tags → ~20).

**Open / next**
1. **CONTENT/PRODUCTION QUALITY** (user deferred, now the main thread): the published
   test is a 2-min text-on-screen teaser. Decide the real format/quality — narration
   (TTS), imagery (Fooocus/stock), pacing, length, cuts. The spine takes all of it.
2. Make it public when happy; produce more ideas (`run_produce`), render (`run_video
   --render`), publish.
2. (narrated mode) Pick a **TTS** (Piper/Kokoro local vs cloud), wire `tts.py`, then
   `run_video --mode narrated --audio narration.mp3`. Add Whisper captions.
3. (visuals) Add imagery layer to `compose.py` (Fooocus on a bigger box, or CC stock).

---

## Session 2 (2026-06-10) — Stage 2 publishing infra + PRODUCE stage + reliability

**Shipped**
- **PRODUCE stage LIVE** — `engine/pipeline/script.py` (documentary scriptwriter,
  Claude + free web search, cinematic voice + [VISUAL]/[ARCHIVAL] cues, preamble
  trimmed) and `engine/pipeline/metadata.py` (title/description/tags/chapters via
  **structured outputs** `output_config.format` — guaranteed valid JSON, no fragile
  regex). Entrypoint `engine/run_produce.py` (`--id` / `--top N` / `--metadata-only`,
  sequential, headless-safe). Artifacts → `produced/<id>/{script.md,metadata.json}`;
  idea marked `in_production` with paths. Queue helpers added: `get_by_status`,
  `get_by_id`, `update_idea`.
- **Verified end-to-end** on the Escobar idea (bdffcdb7): 2,998-word script + a
  publish-ready metadata package (86-char title, hook-first description, 30 tags,
  9 timestamped chapters incl. a web-search-sourced "2026: Second Chapter").
  Caught + fixed: metadata JSON parse error → switched to structured outputs.
- **Fixed the cron hang (Codex catch):** `run_pipeline` ended in an interactive
  `input()` prompt → headless Railway cron would EOFError/hang. Added `--no-review`,
  a `sys.stdin.isatty()` guard + EOFError catch; cron startCommand now passes
  `--no-review`. Verified the guard skips cleanly with no TTY.
- **Stage 2 publishing code (real):** `engine/publish/auth.py` (OAuth 2.0 flow,
  caches `token.json`, auto-refresh) + `engine/publish/uploader.py` (resumable
  `videos.insert`, scheduled-publish via `publishAt`, thumbnail set, CLI). Deps
  added (google-api-python-client, google-auth-oauthlib, google-auth-httplib2).
- **`client_secrets.json` already present** (Track A Google Cloud setup done).
  OAuth **consent not yet completed** (no `token.json`) — must be run once in a
  terminal with a browser: `python3 -m engine.publish.auth`.
- **Reliability fix:** agent runs were crashing on Anthropic **429 (30k TPM tier)**
  when run back-to-back with web-search context — `competitor_gap` produced 0 ideas
  that way. Set `anthropic.Anthropic(max_retries=5)` in base_agent so 429s back off
  and retry. **Use `--sequential`** (default parallel fires all 4 → guaranteed 429
  on this tier).

**Queue now:** 15 ideas (sports_history 5, trending_topics 5, evergreen 5).
competitor_gap still 0 — re-run `--agent 3 --sequential` once (it 429'd, not a bug).

**Open / next**
1. **Complete OAuth consent** (you, terminal w/ browser): `python3 -m engine.publish.auth`
   → approve → prints channel name, caches token.json.
2. **The remaining gap is the video itself** — script + metadata are produced, but a
   human (or a future render step) still has to make the actual .mp4 from the script.
   Once a video exists: `python3 -m engine.publish.uploader --video out.mp4 \
   --title "<from metadata.json>" --description "..." --privacy unlisted`. Wire a
   helper that reads `produced/<id>/metadata.json` into the uploader call.
3. Re-run `--agent 3 --sequential` to fill competitor_gap (it 429'd, not a bug).
4. Produce more: approve ideas (`--review`) then `python3 -m engine.run_produce`.

---

## Session 1 (2026-06-10) — Stage 1 LIVE + full architecture

**Shipped**
- **Stage 1 idea generation runs LIVE.** 10 real ideas generated across 2 agents
  (sports_history, trending_topics) — specific, makeable documentary premises
  (Andrés Escobar, Senna/Prost Monaco '84, India follow-on test, …).
- **Free web search** — replaced Anthropic's paid `web_search_20250305` add-on
  with `ddgs` (DuckDuckGo, open source, no key) in `engine/ideate/web_search.py`,
  wired as a client-side tool. Verified it injects *current* facts (Feb-2026
  Escobar follow-up). Net run cost = Claude tokens only.
- **Anthropic key** reused from ConvictionFinder's Railway service → `.env`
  (gitignored). Loaded via `python-dotenv` in `engine/config.py`.
- **Bug fixed:** `MAX_TOKENS` 2048 → 8192 (5 detailed ideas were truncating the
  JSON mid-array). Added a `max_tokens` truncation guard in `base_agent._call`.
- **Architecture migration** — flat layout → CF-style `engine/` package:
  - `config.py` / `queue_manager.py` / `run_pipeline.py` → `engine/`
  - `agents/` → `engine/ideate/` (the 4 working agents + web_search)
  - all imports rewritten to absolute `engine.*`; root `run_pipeline.py` shim kept
  - added forward layers: `pipeline/ publish/ ingest/ outcomes/ taxonomy/`,
    `profiles/*.yaml`, `db/schema.sql`
  - added docs (CLAUDE.md, this file, ADRs, execution-plan), deploy files
    (railway.toml, nixpacks.toml, runtime.txt), `.claude/skills`, dashboard plan
  - absorbed + deleted the standalone `ContentPilot/` scaffold (its blueprint now
    lives here, made real on the working agents)
- Verified: `python3 -m engine.run_pipeline --stats` and a live `--agent 2` run
  both green after the migration.

**Open / next**
1. **Review the 10 queued ideas** interactively: `python3 -m engine.run_pipeline --review`.
2. **Run the other 2 agents** (competitor_gap, evergreen) and judge their output.
3. **Stage 2 — YouTube publishing**: Google Cloud project → YouTube Data API v3 →
   OAuth consent (scopes: youtube.upload, youtube.readonly, youtube) →
   `client_secrets.json` in repo root (gitignored). Then implement
   `engine/publish/uploader.py`. See `docs/adr/0002-youtube-oauth.md`.
4. **Stage 3 — learning loop**: `engine/ingest/youtube_analytics_loader.py` +
   `engine/outcomes/snapshot.py` to track published-video performance vs score.
5. **Dashboard** — scaffold `dashboard/` (Next.js, CF-style) for queue review.

**Watch-outs**
- DuckDuckGo can rate-limit if all 4 agents fire many searches at once — you'll
  see `[web_search error ...]` notes (handled gracefully, not a crash). Add a
  small delay/cache only if it actually bites.
- ⚠️ The Anthropic key was printed once into the session-1 transcript during
  Railway debugging — consider rotating it (it's the shared CF/prod key).
- Idea viral scores cluster high (8.7–9.8); trust ranking + substance, not the
  absolute numbers.
