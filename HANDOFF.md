# The Untold Game — HANDOFF

Session wrap log. Newest first. Use the `handoff` skill to append a new entry.

---

## Session 14 (2026-06-14) — Short-form pacing: "let it breathe"

Triggered by human feedback on two freshly-rendered shorts: *"good, but very hurried, narration too fast,
and it came to a conclusion abruptly."* Built brainstorm→spec→plan→subagent-driven-development, dual
adversarial review (Claude whole-impl `a1e845ffc2242e05a` + Codex `aadd28ba964ce8a94`, 0 Critical / 0 Important
after fix rounds). Spec/plan: `docs/superpowers/{specs,plans}/2026-06-14-shortform-pacing-breathe*`.

### Shipped to main
- **#42 (MERGED, `815d91e`)** — short pacing, all gated to `format == short` (long-form byte-identical):
  - `engine/config.py`: `SHORT_NARRATION_SPEED` 1.12→**1.05**, `SHORT_NARRATION_GAP_S` 0.12→**0.20**, new
    `SHORT_END_GAP_S=0.6`, `SHORT_END_HOLD_MS=1000`.
  - `engine/video/tts.py`: pure `_gap_schedule(n, gap_s, end_gap_s)` helper + threaded `end_gap_s` through
    `narration_pace` (now a **3-tuple**) → `synthesize` → `_synth_kokoro` — longer silence **before the final
    (payoff) sentence**. `end_gap_s=None` (long-form default) is behavior-preserving.
  - Remotion: new optional `endHoldMs` prop (default 0) threaded config→`run_video`→`build_props`→props→
    `types.ts`/`Root.tsx`/`UntoldShort.tsx`/`shortDefaultProps.ts`. EndCTA pushed later by `endHoldMs`.
    **Key gotcha (fixed):** Remotion `Sequence`s *unmount* at duration-end (they don't freeze), and b-roll beats
    are capped at `narration_ms` — so `build_props` now **stretches the last beat THAT HAS A CLIP** to
    `narration_ms + end_hold_ms` so real story footage (looped by `BeatClip`), not the gradient, carries the breath.
  - `engine/pipeline/script.py`: both short writers' PAYOFF beat → **1–2 resolving sentences** (integrity rule intact).
- All three existing shorts **re-rendered with the new pacing** (verified `endHoldMs=1000` + stretched final beat):
  `050d8550` (preview, human-approved), `9bbd24cd`, `bb8585d1`.

### Open / next
1. **Re-renders reuse existing scripts** → they carry pacing + end-breath but **not** the fuller-payoff *wording*
   (Task 4 only affects a fresh `run_produce`). Regenerate scripts if the new payoff wording is wanted on these three.
2. The 3 re-rendered shorts are **local files only** — pushing to YouTube is a separate manual step.
3. **Minor, intentionally not fixed** (see PR #42 body): 2-sentence payoff makes the pre-payoff pause land before
   the *last* line (not the payoff block); `endHoldMs:0` emitted for long-form too (render byte-identical). QC note:
   `endHoldMs`+`outroMs` are video-only, so the short QC duration-drift floor moved ~25s→~35s of narration (passes
   at the ~50–55s target, ~6–7% drift vs 10% tol).

### Watch-outs
- **Don't wait on renders with `pgrep -f "run_video --id X"`** — the waiter shell's own argv contains that string,
  so the loop self-matches and deadlocks. Use `kill -0 $PID` on the captured render PID instead.
- Render path: `.venv-video/bin/python -m engine.run_video --id <id> --render --mode narrated --format short`
  (the canonical invocation `engine/run_auto.py` uses; never run a render in a hook/CI).

### Suggested skills next session
`ship-video-change` (any engine change), `run-pipeline`/`review-ideas` (queue work), `fact-review` (if a produce flags).

---

## Session 13 (2026-06-14) — API cost tracking for automation runs

Triggered by "is our automation kicked off?": the 1am run **was** firing (PATH fix from #33 held) but
**production failed on `Anthropic credit balance too low`** with zero cost telemetry. User topped up credits
and asked for per-run cost tracking + a budget alert. Built brainstorm→spec→plan→subagent-driven-development,
dual adversarial review (Claude `af14de3560b7157b2` + Codex `a0ffb0cc25fcf4027`, 0 Critical / 0 Important).

### Shipped to main
- **#37 (MERGED)** — API cost tracking. Spec/plan: `docs/superpowers/{specs,plans}/2026-06-14-api-cost-tracking*`.
  - `engine/usage.py` — `logged_create(client, stage, **kwargs)` wraps every `messages.create`, prices
    `resp.usage` (Sonnet 4.6 table, incl. cache rates), appends a row to `logs/api-cost.jsonl`. **Self-stubbing**:
    `record()` never raises; the API call sits *outside* the try so real API errors still propagate.
  - `engine/run_cost_report.py` — aggregates the ledger by `TUG_RUN_ID`, prints a per-stage summary, emits a
    `⚠️ BUDGET` line (warn-only, never aborts) when a run exceeds `config.COST_ALERT_USD` (**$10**).
  - All **8 Anthropic call sites** routed through `logged_create` (stage = `self.name` in `base_agent._call`,
    so `script_writer` shows as the cost driver; explicit labels elsewhere).
  - `scripts/overnight.sh` stamps `TUG_RUN_ID` once + prints the cost summary into the daily log (`|| true`).

### Open / next
1. **Verify tonight's run** (`logs/overnight-2026-06-15.log`): production actually produced (credits topped) AND
   the `── API cost — run … ──` summary appears. That's the real proof the original failure is closed.
2. **Tune `COST_ALERT_USD`** (`engine/config.py`, currently $10) after ~a week of baseline. Observed: a normal
   3-video run ≈ **$0.42**; a 20-script runaway hits ~$15 (trips the alert).
3. No code pending — feature complete.

### Watch-outs
- The Session 12 "parallel api-cost-tracking worktree" item is now **resolved & merged**. The shared-checkout
  tangle bit again mid-session: `feat/subject-autosource` **merged to `main`** while this work was isolated, so
  the branch had to be **rebased onto the moved `main`** before the PR (else the diff looked like it deleted the
  just-merged subject files). Both features are cleanly on `main`, no cross-contamination. Reinforces
  [[parallel-agents-use-worktrees]] **and** the corollary: rebase onto current `main` before opening the PR.

### Suggested skills next session
`diagnose` (if tonight's run misbehaves), `ship-video-change` (threshold tuning / any engine change).

---

## Session 12 (2026-06-14) — Short-form v2 · vertical thumbnails · subject autosource · docs-sync hook

8 PRs merged via the `ship-video-change` rail (dual adversarial: Claude + Codex, 0 Critical / 0 Important
after fix rounds). Specs/plans in `docs/superpowers/{specs,plans}/2026-06-1{3,4}-*`. Memory: [[shortform-v2-pacing-broll]],
[[subject-autosource]], [[keep-docs-in-sync]].

### Shipped to main
- **#31** — short-form v2: conflict-first **no-pronoun** hook (open on action/image/stakes), ~50-55s length
  (`SHORT_SCRIPT_WORDS` 110-135), brisk pace (`SHORT_NARRATION_SPEED` 1.12 / gap 0.12), mood-driven b-roll
  **beat track** (`bBeats`, a fresh deduped clip every 4s short / 7s long, Ken-Burns zoom, no single-clip loop,
  both formats), caption punch-in, **+ scaffold-leak fix** (`tts.is_scaffold_line` + `_parse_short` last-MOOD →
  clean `script.md`, no hand-editing).
- **#32** — vertical 9:16 thumbnail `thumbnail.compose_vertical` (real photo + bold bottom-stacked Anton, last
  line red accent); `generate_thumbnail`/`run_thumbnail --format short` route to it. **#38** added explicit-`\n`
  line breaks in `_wrap` (hand-authored splits via persisted `thumbnail_text`).
- **#35** — **subject autosource**: `run_subject --id --format` → `wikipedia.lead_image` (lead portrait +
  CC/PD credit) → `footage.fetch_photo` (Pexels fallback) → none; human `subject.png` always wins; writes
  `subject_credit.txt`. **#36** fixed `lead_image` to gate on `max(w,h)≥400` (was width≥600 → rejected tall-narrow
  portraits like Senna 438×584).
- **#33** — overnight launchd fix: `scripts/overnight.sh` PATH puts `/usr/bin:/bin` before `/usr/local/bin`.
  Root cause (kernel AMFI log): `/usr/local/bin` holds Apple platform coreutils copies that get `Killed: 9`
  (not in trust cache) — the 1am job died at the first `mkdir` and had **never once completed**.
- **#34** — `scripts/docs-staleness-gate.sh` PreToolUse hook on `gh pr create`: blocks a PR when `engine/**`
  changed but no docs did; bypass with `Docs-Synced: <reason>`. Enforces [[keep-docs-in-sync]].

### Done (assets ready, on disk — produced/ is gitignored)
- All **8 published shorts** have a reviewed subject photo (6 auto Wikipedia/Pexels + credit, 2 human) and an
  **8/8 generated 1080×1920 cover** (`run_thumbnail --format short`). Senna/Prost cover uses persisted
  `thumbnail_text="RED FLAG\nNO EXPLANATION"`.
- **8/8 covers PUSHED LIVE** to the Shorts via `youtube.thumbnails().set` (videoId from each idea's
  `short_youtube_url`; OAuth `client_secrets.json`+`token.json`). Idempotent — re-run to re-push after a cover
  change. Pattern: see `scripts/fix_live_timestamps_and_thumbs.py` (set-thumbnail loop).

### Decisions
- **Thumbnails = REAL photos only, NO AI** (user confirmed; ADR-0005). The reference-grid AI-deepfake style is
  off-brand + platform-risky. Will iterate on thumbnail *design* later (richer composition).
- Short-form punch comes from structure/pacing/visuals, **integrity held** (no rounding, no unverified superlatives).

### Open / next
1. **Long-form thumbnails** — the 5 longs still have their old 16:9 covers; a similar `run_subject` +
   `run_thumbnail` (long) pass + live push could refresh them (optional).
2. **Overnight reliability** — PATH fixed, but a full render still needs **AC power** + the scheduled wake aligned
   to the job (`sudo pmset repeat wakeorpoweron MTWRFSU 00:59:00`; user ran a pmset change this session).
3. **Railway ideate cron is declared (`railway.toml`) but NOT deployed** — no Untold Game Railway project, so
   cloud idea-gen isn't running. (Docs corrected to stop implying it runs.)
4. 🐛 **docs-staleness-gate reads only inline `--body`, not `--body-file`** — a `Docs-Synced:` marker in a body
   file is missed. Quick patch: parse `--body-file <path>` too.
5. **Slice 2 (deferred):** SFX/whoosh/impact audio layer for shorts (needs a licensed sound library).

### Watch-outs
- **Parallel `api-cost-tracking` session** runs in its own worktree (`/Users/bheemendergurram/tug-cost-tracking`,
  branch `feat/api-cost-tracking-clean`, adds `engine/usage.py`). An early shared-checkout tangle (commits
  interleaved across both features) was resolved by rebuilding each feature cleanly in a worktree — reinforces
  [[parallel-agents-use-worktrees]]: **every concurrent session MUST use its own worktree.**

### Suggested skills next session
`ship-video-change` (engine PRs), `superpowers:brainstorming` (thumbnail-design v2 / uploader thumbnail-set),
`fact-review` (when produce flags `needs_review`).

## Session 11 (2026-06-13) — Packaging feedback → 3 slices shipped (text · thumbnails · positioning)

External "make it viral / fix the identity crisis" feedback decomposed into slices ([[packaging-feedback-slices]]
memory has the full map). **4 PRs merged** via the full `ship-video-change` rail (dual adversarial review —
Claude + Codex, both PASS after fix rounds). Specs/plans in `docs/superpowers/{specs,plans}/2026-06-13-*`.

### Shipped to main
- **#22** — text layer: front-loaded "mystery-first" hooks + withholding (not editorializing) titles +
  dedicated short-title pass guarded by a digit-only containment backstop (`script.title_numbers_within`).
- **#24** — thumbnail engine "Prestige Feed Killer": `engine/pipeline/thumbnail.py` Pillow compositor
  (archival grade + grain + vignette + UNTOLD stamp + withholding tension line w/ text-anchored red marker)
  + `run_thumbnail` CLI + `cmd_approve` wiring. Pillow added to `python3`; OFL fonts bundled.
- **#27** — channel positioning "Editorial Archive": `engine/pipeline/banner.py` (2560×1440) + `run_banner`
  CLI; canonical line **"The Archive of Lost Sports History"** in `config.CHANNEL_SUBTITLE`/`CHANNEL_CONTEXT`/
  `channel.yaml`; `config.CHANNEL_DESCRIPTION` (public About copy).
- **#28** — `scripts/source_thumbnails.py` (Wikipedia subject photo → 6 thumbnails) +
  `scripts/fix_live_timestamps_and_thumbs.py` (push thumbs + fix chapter timestamps on published videos).

Tests: `python3 -m pytest tests/ -q` → **233 passing**. Working tree clean.

### Open — manual actions (assets/code ready; human applies)
1. `python3 -m engine.run_banner` → upload `channel/banner.png` as channel art + paste `channel/description.txt`
   into "About" in YouTube Studio.
2. Thumbnails for the published batch: `python3 scripts/source_thumbnails.py` (review the 6) →
   `PYTHONPATH=. python3 scripts/fix_live_timestamps_and_thumbs.py`. New people/sports: add their Wikipedia
   article to the `SUBJECTS` map.
3. Retitle unpublished ideas: `python3 -m engine.run_produce --id <id> --metadata-only` (+ `--format short`).
   New titles flow automatically for not-yet-produced ideas; published videos need the title applied in Studio.

### Open — deferred slices (render layer, gate on the 45-min Remotion loop; each needs its own brainstorm→spec→plan)
- Long-form pacing (chapter cards w/ sound, music swells, holding on silence) — overlaps [[long-form-quality-feedback]].
- Shorts visual cadence (pattern interrupts, animated on-screen text, faster cuts).

### Decisions / watch-outs
- Issue **#21** tracks publish-gate hardening: a fabricated proper-noun in a short title / thumbnail tension
  line isn't deterministically caught (digit-only backstop by design; publish requires manual `--approve`).
- **Worktree/branching:** `main` is held by the parallel fact-gate worktree (`../untold_game_agents-wt-fact-gate`).
  Don't `git checkout main` in the primary checkout — branch from `origin/main`. ([[parallel-agents-use-worktrees]])
- Parallel fact-gate session is live (own branch); also tracking Massa thumbs / engine title-case / worktree
  cleanup ([[first-longform-batch-published]]). Coordinate before touching `engine/run_auto.py` / `config.py` / publish path.

---

## Session 10 (2026-06-12/13) — Shorts→YouTube end-to-end + template/branding/long-form/automation

Huge session. **1 PR merged (#14, squash `5b6aa84`)** via the full `ship-video-change` rail (dual
adversarial review — Claude + Codex, both PASS after a fix round). Reference the durable artifacts
below; don't re-read this for detail.

### Shipped to YouTube
- **5 Shorts produced → fact-reviewed → rendered → published** (user did the final review):
  Senna `yhClmmEGEHM` · World Cup `y0nw8wBn6ok` · O.J. `1vrjioS4sls` · Barry Sanders `k6dGc65jTJA` ·
  Sachin `mB1Gaz5QAGY`. Channel **The Untold Game** (`@untoldgamemedia`). OAuth already configured
  (`client_secrets.json` + `token.json`, gitignored). `run_auto --approve <id>` = unlisted; never `--public`.

### Shipped (PR #14 → `main`) — see specs/plans in `docs/superpowers/{specs,plans}/2026-06-12-*`
- **Mood music** on both formats (`engine/video/music.py`; pillar→mood fallback for long-form).
- **TTS/script fixes** (`tts.py`, `pipeline/script.py`, `factcheck.py`): no narrated `MOOD:`/preamble;
  comma-number spelling (millions/billions, skip currency/decimals); no gaps in initialisms/abbrevs.
- **Voices** → only `af_sarah` (somber) + `bm_george` (rest).
- **Sport-relevant b-roll** (`footage._sport_query` + `_HEADLINE_SYSTEM`) — keeps ADR-0005 ban.
- **Richer Short descriptions** (`metadata.generate_short_metadata`).
- **Branding:** `Watermark` + `EndCTA` components on both formats; `brand.ts`; logo at
  `engine/video/remotion/public/brand/logo.png` (cropped channel avatar — swap a transparent PNG anytime).
- **Curated music library** committed (28 tracks in mood folders + `manifest.json`; `_unused/` gitignored).

### Decisions / watch-outs
- **Overnight automation already existed** (PR #7: `scripts/overnight.sh` + `deploy/launchd/`). I built a
  redundant, PATH-broken rewrite — the review caught it; **reverted to the existing one**. It runs nightly
  **01:00** → `run_auto --count 3` (3 long videos). Now on `main`, so tonight uses the merged pipeline.
- **Music credit** is a neutral `"Royalty-free background music"` (library is mixed-source; set real
  per-track credits in `engine/video/music/attribution.json` to override).
- Process rule reaffirmed + broadened (memory `always-formal-spec-and-plan`): brainstorm→spec→plan→execute
  for **everything incl. bug fixes**. Also see memory `shorts-template-and-publish`.

### Open / next — Phase 2 (needs per-format artifact separation `produced/<id>/long|short/`)
1. **Companion shorts** that tease each long video (user's 3-long-then-3-short engagement loop).
2. **Long versions of the 5 published Shorts** (render-heavy, 5×~45min).
3. Optional: tune long-form narration to be more engaging in its own right.
The blocker for 1+2: one idea currently = one `produced/<id>/` dir, so long+short clobber — build the split first.

---

## Session 9 (2026-06-12) — title-impact SFX + caption/title-card motion polish

Polish session. **1 PR merged (#11)** via the full `ship-video-change` rail (dual adversarial
review). References the durable artifacts — open them, don't re-read this for detail.

### Shipped (PR #11 → `main`, squash `1ae1ef1`)
- **Title-impact SFX.** A soft low boom under each title reveal (intro + every chapter card),
  mixed *inside Remotion* via an `<Impact/>` `<Audio>` per `<Sequence>` (`IMPACT_VOL=0.4` in
  `engine/video/remotion/src/UntoldVideo.tsx`) — Remotion auto-mixes it under the narration, no
  ffmpeg post step. Sound is **synthesized** (ffmpeg `aevalsrc` chirp+decay, CC0/owned) by
  `engine/video/make_impact_sfx.sh`; chosen **`weighty`** variant, peak-normalized to −1 dBFS into
  the committed `engine/video/remotion/public/sfx/impact.wav`. Spec + plan:
  `docs/superpowers/specs/2026-06-12-title-impact-sfx-design.md`,
  `docs/superpowers/plans/2026-06-12-title-impact-sfx.md`.
- **Frame-pure caption/title motion polish** — `Captions.tsx` (per-word blur-in + upward drift on
  the spring pop, gold glow on active word, page-level fade that kills the hard cut at chapter
  boundaries), `ChapterCard.tsx` (blur-in + gold accent rule wipe), `Intro.tsx` (title blur-in).
  All pure functions of `useCurrentFrame()` — no new deps.
- **Staging guard** — `tests/test_render_remotion.py` locks that `_stage_assets` (clears only
  top-level `public/*.wav|*.mp4|*.mp3`) preserves the `public/sfx/` subdir. This is *why* the SFX
  lives in a subdir: top-level `public/*.wav` is gitignored + wiped per render; `public/sfx/` is not.

### Decisions / context
- **Process rule (saved to memory `always-formal-spec-and-plan`):** user wants the full
  brainstorm→**written spec**→**plan**→implement flow EVERY time, never shortcut even for small
  features. I shortcut once this session and was corrected — don't repeat.
- **Motion / Framer Motion (`motiondivision/motion`):** evaluated, **rejected for the Remotion
  render** (its RAF/stateful engine breaks Remotion's deterministic out-of-order frame render).
  Reserve it for the planned Next.js `dashboard/` (its real home). The caption polish above is the
  "richer motion within the frame-pure model" alternative.
- **Rejected the $33 Envato "Seamless Transitions for DaVinci Resolve" pack** — it's a Resolve/Fusion
  template, unusable in our Remotion (code) pipeline; its bundled SFX are license-tied to the template.

### Open / next
1. **Tune `IMPACT_VOL` on a REAL produced video.** The preview used `defaultProps` (real
   `narration.wav` + placeholder titles → audio/captions intentionally don't line up). Judge the
   boom level by ear once a real render exists (`run_auto`/`run_produce`), adjust `IMPACT_VOL` in
   `UntoldVideo.tsx`.
2. **`feat/shorts-render` local branch is redundant** (its commits are already-merged-equivalent on
   main). Safe to `git branch -D feat/shorts-render` — left intact this session per user.
3. **Untracked dirs still dangling:** `engine/video/music/` (empty mood-folder scaffold — the music
   bed is a separate future project) and `voice_samples/` (Project C voice auditions). Neither
   committed.
4. **PR #12** ("docs(plans): Project D thumbnails + Project E SFX sting") merged to main from another
   line — note `docs/superpowers/plans/2026-06-12-thumbnails.md` + `...-sfx-sting.md` now exist
   (the "SFX sting" is a *separate* planned project from this session's title-impact SFX).

### Watch-outs
- **Squash-merge SHA divergence is normal:** after `gh pr merge --squash`, local `main` (your local
  squash) and `origin/main` (GitHub's squash) have identical trees but different SHAs. Just
  `git fetch && git reset --hard origin/main`.
- The SFX `<Audio>` plays from each sequence's frame 0; Remotion truncates the ~1s wav to the
  sequence window. Short chapters (`Math.max(1,…)` guard) won't overflow.

---

## Session 8 (2026-06-11) — shorter videos + Stage B shipped + CF workflow adopted

Big session. **5 PRs merged (#1–#5)** through a newly-adopted PR workflow. Everything below
references the durable artifacts — don't re-read this for detail, open them.

### Shipped
- **Shorter videos** — `config.TARGET_SCRIPT_WORDS=1800` (~8–9 min) overrides the per-idea
  "18-25 min" format; `engine/pipeline/script.py` enforces it. (Girlfriend feedback: 13:38 too long.)
- **Video #2 — Kolkata 2001** (idea `85a68197`): produced at ~1,650 words, **hand-fact-checked
  against the Wikipedia scorecard** (fixed Mumbai winner / streak 15→16 / cold-open date; added
  Harbhajan's hat-trick), **rendered** (`produced/85a68197/video/video.mp4`), **QC-clean** (luma 91,
  captions 100%, 2% drift), status **`awaiting_approval`** + `human_reviewed=True`. **NOT published yet
  → `python3 -m engine.run_auto --approve 85a68197 [--public]`.** (Uses the OLD single-line captions —
  the caption upgrades below land on the NEXT render.)
- **Stage B core loop SHIPPED** — `engine/pipeline/qc.py` (local QC gate: render_integrity /
  brightness_band / caption_coverage, never-raises) + `engine/run_auto.py` (orchestrator:
  produce→render→QC→`awaiting_approval`, approval CLI `--list/--approve/--review/--reject/--render`).
  New statuses: `awaiting_approval`, `qc_failed`, `render_failed`. `human_reviewed` is an alternate
  clear-to-render signal; `--render <id>` is the override path (skips produce). 30 tests. Spec +
  plan: `docs/superpowers/specs/2026-06-11-stage-b-core-loop-design.md`,
  `docs/superpowers/plans/2026-06-11-stage-b-core-loop.md`. (PR #1 was the workflow, Stage B merged pre-PR-rail.)
- **ConvictionFinder workflow adopted** (PR #1, #5) — `.claude/settings.json` hooks + `ship-video-change`
  + `fact-review` skills + CLAUDE.md "Hard rules" / "PR + review workflow". **HOOK GOTCHA (PR #5):**
  the hook-level `if:` filter does NOT scope in this harness — hooks must **self-guard on the stdin
  command** (`.claude/hooks/push-guard.sh`, `scripts/pr-review-gate.sh`, `engine-test.sh`). The
  push-block only denies a real `git push` on `main`; work via branch+PR.
- **Wikipedia-RAG fact-gate** (PR #3) — `engine/ideate/wikipedia.py` (MediaWiki, no key, never-raises)
  feeds an authoritative extract to `factcheck.verify_claim` above noisy DDG (which false-flagged 8/11
  on Kolkata). `docs/external-references.md` = the 5-repo analysis (adopt cookbooks Wikipedia-RAG;
  skip swift-markdown/motion; defer claude-code-action).
- **Captions glow-up** (PR #4, `engine/video/remotion/src/components/Captions.tsx`) — big centered
  multi-line + chapter-card de-collision + **per-word spring pop-in** (frame-pure Remotion `spring`).
  Verified via `npx remotion still`/slice previews. **Applies to the NEXT render only.**

### Open / next
1. **Publish Kolkata** (`run_auto --approve 85a68197`) — touches YouTube OAuth, user's step.
2. **Voice ~10% slower** — Kokoro reads ~220 wpm (a touch fast); nudge the speed in
   `engine/video/tts.py` on the next produce+render.
3. Deferred (own builds): **launchd scheduler** (overnight renders), **Shorts/TikTok/IG**,
   **claude-code-action** CI review (cost-gated), Claude-vision people-check in QC, Next.js dashboard
   (where `motion` would actually fit).

### Watch-outs
- **Shared Anthropic key is cost-fragile** — hit a zero balance twice this session. Produce/fact-gate
  cost ~$0.25/video.
- **Render is LOCAL only** — `npx remotion render` (~45 min, Chromium), runs in the user's shell, not
  the harness sandbox / not Railway. Stills/slices are the cheap preview (`npx remotion still … --frame=N`).
- **Two-venv split:** `python3` (produce/qc/orchestration) vs `.venv-video` (render). Never import across.
- **Hooks need a `/hooks` open or restart** to go live after a settings.json change in-session.

### Suggested skills next session
- `ship-video-change` (any `engine/*.py` PR), `fact-review` (verify a flagged script),
  `run-pipeline` / `review-ideas` (ideas), `claude-api` (before any LLM/TTS wiring).

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
