# Growth-Playbook Audit — *Encyclopedic Compendium of Platform Engineering* vs. the TUG engine

**Date:** 2026-06-14
**Source:** an 18-module + execution-matrix YouTube-growth playbook (dropped into Downloads).
**Lens:** **The Untold Game** — a *brand-new, faceless, sports-history* channel.
**Purpose:** sort the playbook's tactics into what the engine already does, what's worth building, what's a manual Studio step, and what to ignore. This is a strategy note, not an ADR — it records an external source's claims against our system; it decides nothing on its own.

Verdicts were checked against the **actual engine code** (file:line cited), not memory.

## Verdict legend

**System-fit** — does the TUG pipeline do this?
| | |
|---|---|
| ✅ Done | Already implemented in the engine |
| 🔧 Gap | Not done, but code-buildable and worth considering |
| 🙋 Manual | A human-in-Studio step; no code |
| ⛔ Skip | Don't do it (myth, irrelevant to this channel, or TOS-risk) |

**Credibility** — is the claim true?
| | |
|---|---|
| 🟢 Evidence | Well-supported by how YouTube actually works |
| 🟡 Plausible | Reasonable but unproven / arbitrary specifics |
| 🔴 Lore-myth | Creator folklore presented as fact; no real mechanism |
| ☣️ TOS-risk | Violates YouTube terms or invites suppression |

**Gate rule (mirrors the project fact-gate):** a tactic only becomes a *recommended action* if it is **not 🔴 / ☣️**. Credibility gates system-fit.

---

## TL;DR — what to actually do now (ranked)

For a channel with ~zero data, optimization knobs pay nothing. Three things move the needle: **packaging** (title+thumbnail), **the first 30 seconds**, and **volume + a real feedback loop**. Act on this short list; defer the rest.

1. **Packaging is the bottleneck, and it's where the cheapest wins are.** The thumbnail and title decide whether a new video gets a chance at all. The engine is already strong here (`thumbnail.py`, `metadata.py`) — close the two small gaps: a **thumbnail↔title complementarity check** (don't repeat the title's words on the image) and run the **2-second flash test** by hand before every publish. *(Bucket B small + Bucket C)*
2. **Outlier-driven titles + scope-reduction in ideation.** The single highest-leverage *code* gap: the ideate agents generate topics but don't (a) borrow proven viral title frameworks from outside sports, or (b) shrink a macro-topic to an uncontested micro-angle. Both directly improve packaging. *(Bucket B)*
3. **Retention bridges + kill the outro in the script prompt.** Two small prompt edits: pre-frame the next section before ending the current one, and ban "in conclusion / that's all for today" endings. Real retention win, ~an afternoon. *(Bucket B small)*
4. **Per-upload manual checklist.** Set the real Studio toggles once, pin a tension-question comment, point the end screen at the logical next video. *(Bucket C — see below)*
5. **Publish consistently.** Volume is the actual unlock — it's the only way to generate the data that makes any of the optimization machinery meaningful.
6. **Defer the analytics/swap loop.** CTR/retention-driven title swaps are real and valuable *eventually* (Stage 3), but building them now optimizes nothing. Gate discipline says wait until enough videos are published to have signal. *(Bucket B — deferred)*
7. **Hard-skip the myths and TOS-risk** regardless of how confident the doc sounds: the 20-second Shorts cap, one-upload-per-24h, delete-and-reupload, account "warming", secondary-channel self-seeding, and "the List." *(Bucket D)*

---

## Bucket A — Already in the engine ✅

These are done. Listed with the file that proves it, so we confirm rather than assume.

| Tactic (module) | Cred. | Evidence in code |
|---|---|---|
| Front-load the hook; earn the click in 15s, no logo/tagline intro (M4, M19) | 🟢 | `engine/pipeline/script.py:20-30` — *"Earn the click in 15 seconds — front-load the mystery, not the data … lead with the stakes and the unanswered question."* |
| Curiosity loop in the opening (M4) | 🟢 | `script.py:20-26` — arc "setup → turning point → revelation … withholds the resolution." |
| Anti-bloat / tight cut, cut throat-clearing (M14) | 🟢 | `script.py:29-30` — *"BE TIGHT … every sentence must earn its place."* |
| Shorts 2-second hook, scroll-stopper, no pronoun open (M5) | 🟢 | `script.py:104-108` — *"FIRST line must hit the central conflict … EIGHT WORDS OR FEWER … the viewer gives you ~2 seconds."* |
| Thumbnail one-idea rule, 2-4 bold words, uppercase (M6, M16) | 🟢 | `thumbnail.py:190` — *"2-4 words, UPPERCASE, ultra-condensed punch."* |
| Thumbnail avoids bottom-right timestamp / mobile UI (M6) | 🟢 | `thumbnail.py:27-31` — `V_BOTTOM_MARGIN = 150 px`; marker anchors to text block. |
| Thumbnail withholds the payoff (curiosity gap, not a spoiler) (M6) | 🟢 | `thumbnail.py:190` — *"Open the gap by withholding the resolution."* |
| Title opens a gap, no editorializing, ≤100 chars (M19) | 🟢 | `metadata.py:22-26`. |
| Primary keyword in first 2 lines of description (M10) | 🟢 | `metadata.py:27-29` — *"first 2 lines are the hook … then a short SEO paragraph naturally using the keywords."* |
| Tag discipline (not 50 tags) (M10) | 🟢 | `metadata.py:30` — `TAGS: <= 30, specific entities + search terms`. |
| Auto chapters from sections, first at 00:00 (M7) | 🟡 | `metadata.py:31-32` + post-render correction in `chapters.py:56-81`. |
| Music ducked under vocals (M16) | 🟡 | `engine/video/music.py:19` — `MUSIC_VOLUME = 0.08` (fixed 8%; not dB, but functionally a steady duck). |
| Visual/audio concept match for indexing (M16) | 🟡 | b-roll is beat-matched to script (props/`bClip`); captions auto-extracted at render. |

> Note on Shorts length: the playbook's "**keep Shorts under 20s**" rule is **not** followed — the engine deliberately targets ~50-55s (`config.py:63`). That's a *correct* deviation; see Bucket D.

---

## Bucket B — Code gaps worth building 🔧

Prioritized. Each is a candidate for its own brainstorm→spec→plan; none is started here.

| # | Tactic (module) | Cred. | Gap & why it's worth it |
|---|---|---|---|
| B1 | **Scope reduction / micro-angle** in ideation (M2, Matrix) | 🟢 | Ideate agents produce topics but never shrink a saturated macro-topic to an uncontested micro-angle. This is *the* faceless-channel packaging multiplier. Add as a rubric/prompt stage. `engine/ideate/*` + `config.py:67-74`. |
| B2 | **Outlier transfer** — borrow viral title/thumbnail frameworks from outside sports (M2, Matrix) | 🟡 | No agent studies non-niche outliers and overlays the framework. Real technique, genuine gap; pairs with B1. Web search is already free in-engine. |
| B3 | **Retention bridges** between script sections (M19) | 🟢 | `script.py` has the hook+arc but no "pre-frame the next payoff before ending this point" instruction. Small prompt edit, measurable retention effect. |
| B4 | **Ban outros / clean conclusion** (M14) | 🟡 | No rule against "in conclusion / that's all for today." One-line prompt addition. |
| B5 | **Thumbnail↔title complementarity check** (M6) | 🟢 | Thumbnail text and title are generated independently with no cross-check; they can echo each other. Add a guard so the image doesn't repeat the title's words. |
| B6 | **Problem-Agitate-Solve framing option** (M17) | 🟡 | Not present. Lower priority — narrative sports-history already implies stakes; only worth it if a topic is "tip"-shaped. |
| B7 | **CCN audience tagging** (core/casual/new) (M15) | 🟢 | Viral rubric scores 5 dims (`config.py:67-74`) but doesn't tag which viewer ring an idea serves. Useful for balancing the slate; not urgent. |
| B8 | **Analytics → metadata-swap loop** (M8, Matrix Phase 4) | 🟡 | `engine/ingest/youtube_analytics_loader.py:6` and `engine/outcomes/snapshot.py:6` are Stage-3 stubs (`return {}`). CTR/retention-driven title/thumbnail swaps are real and valuable **but premature** — **DEFER** until enough videos are published to have signal. Gated by project Stage discipline. |
| B9 | **Double-title pipe format** (`Hook \| SEO phrase`) (M18) | 🟡 | Not implemented. **Probably skip** for this channel: the pipe formula serves *search/tutorial* content; sports-history lives on the *browse* feed where a clean curiosity title wins. Build only if a search-intent format is added. |

---

## Bucket C — Manual Studio checklist 🙋

Real human steps, no code. Distil into a per-upload routine (could become a `publish-video` skill addendum). Ordered for a single upload:

**One-time channel setup (do once):**
- Set Video Language + Title/Description Language to English (M11) — 🟢 saves the algorithm guessing the linguistic cohort. *(Note: `uploader.py` already pushes category=17/Sports and could set language too — see B-list if we want to automate.)*
- Pick one channel category and stay consistent (M11) — 🟡.
- Business email separate from the login email (M13) — 🟢 basic opsec, real and free.
- Caption certification "never aired on US TV" (M11) — 🟡 correct value, **zero growth effect**; set once and forget.

**Per upload (first ~6 hours):**
- Confirm the description's first 2 lines carry the keyword (engine already does this — just verify).
- Pin a comment asking one **polarizing/specific** question tied to the video's tension (M8, M10) — 🟡 harmless, can help early engagement. No external links.
- Point the **end screen at the logical next video** ("answers the next question") (M10) — 🟢.
- Don't place cards in the first half of the runtime (M10) — 🟡.
- Reply to / heart early comments while you can (M8) — 🟡 harmless; don't overthink the "first 120 minutes" precision.
- Turn on auto-chapters / AI summary if you like the SEO surface (M7) — 🟡 the "huge SEO boost" claim is overstated, but it's free and harmless.

**Diagnostics (read, don't panic):**
- At 24-48h, if CTR is well below your channel average, a thumbnail/title swap is legitimate — **but only if the video is not currently climbing** (M12 is right that mid-wave metadata edits reset distribution) — 🟢.
- Read the retention graph; a vertical drop in the first 30s means the hook missed the packaging promise — log it for the *next* script (M8) — 🟢.

> Everything in Bucket C is low-leverage next to Bucket B's packaging work. Do it, but don't mistake it for growth.

---

## Bucket D — Skip ⛔ (myth or TOS-risk)

Do **not** build or do these, regardless of the doc's confident tone.

| Tactic (module) | Why skip |
|---|---|
| **"Keep Shorts under 20s" cap** (M5) | 🔴 No such mechanism. Retention % matters, not a runtime ceiling. The engine's ~50-55s target is fine. |
| **One Short per 24h for <100k subs** (M5) | 🔴 YouTube has publicly stated extra uploads don't "split" distribution. Folklore. |
| **Delete-and-reupload a flat Short** (M5, M8, Matrix) | 🔴/☣️ Invites duplicate/spam filters — **and the same doc contradicts itself** (M12: *"Constantly deleting and re-uploading … triggers automated duplicate-content and spam filters"*). Leave videos up; iterate the next one. |
| **Secondary / twin-account self-seeding** — watch + like + comment your own video (M8, M13) | ☣️ Artificial-engagement / fake-traffic territory; explicit TOS-risk. Hard no. |
| **Account "warming" 2-3 weeks before uploading** (M13) | 🔴 Myth for a legitimate channel. Just upload good videos. |
| **Sub-for-sub / giveaways / bought metrics** (M12) | ☣️ The doc itself says avoid — agreed, listed only for completeness. |
| **Fixed "70% stay / 80% breakout" thresholds** (M5) | 🔴 Invented precision; YouTube publishes no such numbers. Optimize retention directionally, not to a magic line. |
| **"The List" / low-distribution penalty box** (M3, M9) | 🔴 No documented mechanism by that name. Weak videos simply get less reach; there's no flag to "recover" from. |
| **4-5 video Recovery Blueprint** (M9) | ⛔ N/A — you're a *new* channel, not a suppressed one. Nothing to recover. |
| **Search-flywheel / V.A.S.T. / affiliate stacking** (M18) | ⛔ N/A — that's a *tutorial/utility/review* channel strategy. Sports-history is browse-driven storytelling. |
| **Exact "-18 to -24 dB" ducking spec** (M16) | 🟡 Arbitrary specificity; the engine's steady duck already satisfies the real goal (clean transcript). No action. |
| **"AI Model Data Training OFF protects your scripts" / "Strict moderation prevents security flags on your data profile"** (M7) | 🔴 The growth/SEO/"data-profile" framing is invented. The toggles exist and are harmless preferences — just not growth levers. |

---

## Module coverage map

Every module accounted for, so nothing is silently dropped.

| Module | Primary bucket |
|---|---|
| M1 Market positioning / strategy canvas | B (informs B1/B2 ideation) |
| M2 Content engineering / ideation science | **B1, B2** |
| M3 Algorithmic architecture / "data profile" / tiers | A (hook) + **D** ("the List") |
| M4 Scripting mechanics (30s rule, CTA paradox) | **A** + B3/B4 |
| M5 Shorts engineering / velocity | A (hook) + **D** (20s cap, 1/24h, reupload, thresholds) |
| M6 Graphic / click-through psychology | **A** + B5 + C (flash test) |
| M7 Dashboard settings | **C** (+ D framing) |
| M8 Post-upload velocity checklist | **C** + D (reupload) |
| M9 Recovery blueprint | **D** (N/A — new channel) |
| M10 "14 Things" metadata lockdown | A (desc/tags) + **C** (pin, end screen, cards) |
| M11 "7 Hidden Settings" | **C** (+ D framing) |
| M12 "NEVER do this" landmines | mostly 🟢 — see C diagnostics + D |
| M13 Opsec / twin-account | C (business email) + **D/☣️** (warming, self-seed) |
| M14 2026 satisfaction engine (anti-bloat, pacing, no outro) | **A** + B4 |
| M15 CCN audience framework | **B7** |
| M16 Multimodal AI indexer | **A** (partial) + D (dB number) |
| M17 Film Booth narrative / P.A.S. | **B6** |
| M18 Think Media search flywheel | **D** (N/A) + B9 (pipe title, optional) |
| M19 Derral Eves / retention bridge | **A** + **B3** |
| Execution Matrix (Phases 1-4) | B1/B2 (ideation) + C (post-upload) + D (Phase-4 reupload) |

---

## Bottom line

The engine is **already strong on production and scripting** — the playbook's genuinely-good ideas (front-loaded hook, tight cut, one-idea thumbnail, gap-opening titles, keyword-first descriptions) are mostly shipped. The real, buildable wins are a small cluster in **packaging + ideation** (B1, B2, B5, B3/B4). Everything else is a manual checklist, premature optimization to defer (B8), or folklore to ignore (Bucket D).

The thing the playbook can't give you and the engine can't fake: **publish consistently, then read what actually worked.** That feedback loop — not any single tactic — is the growth engine.
