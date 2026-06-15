# Long-form caption & headline alignment — design spec

**Date:** 2026-06-15
**Status:** Design (ready for implementation plan)
**Origin:** User review of the 1972 Olympics long render (`adfea6c1`) surfaced five quality defects. Forensics root-caused them; see [[long-form-quality-feedback]].

## Problem

The rendered 1972 Olympics long had: messy captions, spelling/name errors, "headlines a mess," multiple headlines on screen at once, and a ~6s word-loop. Forensics on `produced/adfea6c1/long/video/{captions.srt,props.json}` traced all five to mostly **one shared root cause** plus one independent one.

**Root cause A — captions/words come from free Whisper ASR of the Kokoro TTS audio, not from the script.** `engine/video/captions.py::transcribe()` runs faster-whisper (`small`) over the narration audio with `word_timestamps=True`, biased only by a weak `initial_prompt` proper-noun glossary. The script is correct; the ASR drifts:

- Caption text artifacts: `Sixty -three`, `U .S.`, `non -official`, `21 -year -old` (token-join/hyphen artifacts).
- Name mis-transcriptions: **"Iba" → "Eber"** (3×), "Edeshko" → "Odeshko", "Aleksandr" → "Alexander".
- **Headline mis-placement.** `engine/video/compose.py::assign_headline_times(sections, words, …)` places each chapter headline at the time its verbatim ANCHOR (first 4–8 narration words) appears **in the Whisper word stream**. When an anchor word was mangled by ASR, the match fails. Result in `adfea6c1`: chapters 3–11 collapsed into a ~17s cluster at 9.3 min (~1.8s each → flashing / "at the same time"), chapter 2 ("IBA VS THE SOVIETS") stretched 81s→559s (~8 min stuck), and that headline duplicated. The headline *text* in `props.json` is correct; only the `startMs`/`endMs` are broken.

**Root cause B — Kokoro TTS stutters on staccato repeated lines.** The script line `"Possession. Pass. Possession. Pass."` produced ~6s of garbled/looped audio (178.9s–185.1s) with zero captions — the "loop of words." Independent of A. (b-roll is clean: no repeated/back-to-back clips.)

Already-fixed (do NOT re-touch): `digitize_number_words()` correctly renders numbers as digits ("1972", "63", "49"); b-roll distribution is fine in this render.

## Goals

1. Caption text is **exactly the script narration** (correct names, punctuation, hyphens), timed to the audio.
2. Chapter headlines are placed at the **correct narration moment**, never overlapping, never duplicated, never collapsed.
3. The TTS no longer loops on short repeated staccato phrases.
4. No new heavy `.venv-video` dependency; reuse faster-whisper.

## Non-goals

- Replacing the TTS or ASR engine. - Re-auditing the older Senna-feedback items (already addressed). - Timing-precision beyond what faster-whisper already provides (the defect is text, not timing).

## Design

Three independent units, each testable in isolation.

### 1. Script-anchored word alignment (the core fix) — `engine/video/captions.py`

Keep faster-whisper for **timing only**; make the **script the source of truth for text**.

- New function `align_to_script(whisper_words: list[dict], narration_text: str) -> list[dict]`.
- Tokenize `narration_text` (the already-stripped spoken text from `script_to_narration_text`) into words.
- Align the Whisper token sequence to the script token sequence with `difflib.SequenceMatcher` (operating on lowercased, punctuation-normalized tokens for matching only).
- **Project script words onto Whisper timings:**
  - `equal`/`replace` blocks: map each script word to the corresponding Whisper word's `start`/`end` (for `replace`, distribute the block's Whisper time span across the script words proportionally by character length).
  - `insert` (script has words Whisper dropped): interpolate timings linearly between the surrounding anchored words.
  - `delete` (Whisper heard words not in the script — rare): drop them.
- Return word dicts `{text, startMs, endMs}` whose **text is the script word**, ordered, monotonic timestamps.
- `transcribe()` callers switch to: `words = align_to_script(transcribe(audio,…), narration_text)`. Caption chunking (`chunk_words_to_captions`) and headline anchoring (`assign_headline_times`) then consume script-true words unchanged.

**Why this fixes headlines too:** anchors are script text, words are now script text → `assign_headline_times` anchor lookups always match exactly, so placement can't collapse.

**Fallback:** if faster-whisper is unavailable, keep the existing `estimate_word_timings` path (already script-true text, evenly spread). No regression.

### 2. TTS staccato-loop guard — `engine/video/tts.py`

In the narration-chunking step (`_split_sentences` / `script_to_narration_text`), detect a **run of ≥3 very short sentences (≤2 words) that repeat** (e.g. `Possession. / Pass. / Possession. / Pass.`). Mitigation (pick in plan, prove with a render): synthesize each short fragment as its **own Kokoro call** and concatenate, rather than feeding the repetitive run as one chunk — Kokoro loops when a chunk is short+repetitive. Guard is self-stubbing: on any detection/synthesis edge, fall back to current behavior.

### 3. Headline de-dup + min-duration clamp — `engine/video/compose.py`

Belt-and-suspenders after `assign_headline_times`, independent of alignment:
- **De-dup:** merge consecutive headlines with identical text into one span.
- **Min-duration clamp:** enforce a floor `HEADLINE_MIN_MS` (e.g. 3000). Any headline below it merges into its neighbour (prefer extending the previous). Guarantees you can never get 9 headlines in 17s even if alignment ever misses.

## Data flow

`script.md → script_to_narration_text → Kokoro TTS (+staccato guard) → narration.wav → faster-whisper transcribe → align_to_script(narration_text) → script-true words → {chunk_words_to_captions → captions, assign_headline_times → headlines (+dedup/clamp)} → props.json → Remotion render`

## Testing strategy

Unit tests (`tests/`, run under `python3`, no render, no GPU):

- `align_to_script`: synthetic Whisper words with deliberate errors (Iba→Eber, dropped word, inserted word, `U .S.` split) against a known narration → assert output text == script words, timestamps monotonic and within the audio span. Edge: empty whisper, empty script, total mismatch.
- staccato guard: detects `Possession./Pass./Possession./Pass.`; leaves normal prose untouched; n=0/1 short-sentence cases safe.
- headline de-dup/clamp: consecutive duplicate merges; a sub-floor headline merges into its neighbour; already-spaced headlines untouched; the real `adfea6c1` chapter list (chapter 2 huge + 3–11 clustered) collapses to a sane set.

## Verification (render gate)

Re-render `adfea6c1` long after the fix and confirm: captions read "Iba"/"U.S."/"Sixty-three"; the `props.json` chapter `startMs` are spread across the timeline with none below the floor and no duplicate; the 178–185s region has captions and no audio loop. The 45-min render is **not** a CI gate — verify via unit tests + the still-preview trick first.

## Risks / edge cases

- **Alignment drift on long mismatches:** if Whisper text diverges badly, interpolation could mistime a stretch. Mitigation: proportional distribution + monotonic clamp; the `small` model is accurate enough on clean TTS that large divergences are rare.
- **Staccato guard over-eager:** restrict to ≤2-word sentences repeated ≥3× in a row; prose and lists won't trigger.
- **Two-venv discipline:** alignment runs in `.venv-video` (with faster-whisper) but `align_to_script` is pure-python and unit-tested under `python3`. Keep the function dependency-free so tests don't need the venv.

## Ship rail

`engine/*.py` changes → `ship-video-change` (branch, `pytest tests/`, dual adversarial review, PR trailer). Render verification is local (launchd/M5), never in CI/hook.
