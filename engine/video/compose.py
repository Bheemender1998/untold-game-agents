"""
Build a HyperFrames composition (index.html) from a produced idea.

Two modes share this builder:
  - text     : kinetic typography — condensed punchy lines over a gradient bg,
               no audio. Fully covered by the open-source toolkit (HyperFrames only).
  - narrated : a narration <audio> track + a HYBRID on-screen layout — a distilled
               section HEADLINE up top and a verbatim CAPTION line below it, both
               synced to the Kokoro/say voice via faster-whisper word timings (or a
               graceful reading-time estimate when whisper isn't installed).

text mode distills the script to ~22 punchy beats (the full 3,000-word narration is
unreadable on screen). narrated mode keeps a thinner set of section headlines (the
"chapters") and lets the synced captions carry the words.
"""
from __future__ import annotations
import json
import os
import html as _html

import anthropic
from engine.config import MODEL
from engine.video import captions as _captions
from engine.video import footage as _footage
from engine.video import tts as _tts

# ── Storyboard: script → timed on-screen text beats ──────────────────────────

_STORYBOARD_SYSTEM = """You are a kinetic-typography editor for "The Untold Game"
(sports-history channel). Condense a documentary script into punchy on-screen TEXT
beats for a text-driven video (no voiceover). Each beat is one or two short lines
that land hard on screen — the hook, the turning point, the gut-punch facts, the
closing line. Cut everything that only works spoken. Keep the dramatic arc."""

_STORYBOARD_SCHEMA = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kicker": {"type": "string"},   # small label above the line (may be "")
                    "text": {"type": "string"},      # the on-screen line(s)
                    "seconds": {"type": "number"},   # how long it holds (2-6)
                },
                "required": ["kicker", "text", "seconds"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["beats"],
    "additionalProperties": False,
}


def build_storyboard(idea: dict, script_md: str, max_beats: int = 22) -> list[dict]:
    """Distill the script into timed on-screen text beats (structured output)."""
    client = anthropic.Anthropic(max_retries=5)
    prompt = (
        f"TITLE: {idea['title_variants'][0]}\nHOOK: {idea['hook']}\n"
        f"SPORT: {idea['sport']}  PILLAR: {idea['pillar']}\n\n"
        f"SCRIPT:\n{script_md}\n\n"
        f"Produce {max_beats} or fewer text beats for a ~60-90s text-driven video. "
        f"Open with the channel hook, end on a resonant line."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=4096, system=_STORYBOARD_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _STORYBOARD_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["beats"]


# ── HTML composition ─────────────────────────────────────────────────────────

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@400;600&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1920px; height:1080px; overflow:hidden; background:#0a0a0a; }}
  #stage {{ position:relative; width:1920px; height:1080px;
            background: radial-gradient(circle at 50% 35%, #1a1410 0%, #0a0a0a 70%); }}
  .card {{ position:absolute; inset:0; display:flex; flex-direction:column;
           align-items:center; justify-content:center; opacity:0;
           padding:0 220px; text-align:center; }}
  .kicker {{ font-family:'Oswald',sans-serif; font-weight:600; letter-spacing:.35em;
             text-transform:uppercase; font-size:34px; color:#d98a3d; margin-bottom:28px; }}
  .line {{ font-family:'Anton',sans-serif; color:#f4f1ea; line-height:1.04;
           font-size:96px; text-transform:uppercase; }}
  .bar {{ position:absolute; bottom:90px; left:50%; transform:translateX(-50%);
          font-family:'Oswald',sans-serif; letter-spacing:.3em; font-size:24px;
          color:#6b6b6b; text-transform:uppercase; }}
</style></head>
<body>
<div id="stage" data-composition-id="untold" data-start="0" data-width="1920" data-height="1080">
{cards}
  <div class="bar">THE UNTOLD GAME</div>
{audio}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.13.0/gsap.min.js" integrity="sha512-NcZdtrT77bJr4STcmsGAESr06BYGE8woZdSdEgqnpyqac7sugNO+Tr4bGwGF3MsnEkGKhU2KL2xh6Ec+BqsaHA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{timeline}
    window.__timelines = window.__timelines || {{}};
    window.__timelines.untold = tl;
  </script>
</div>
</body></html>
"""


import re as _re


def _hold(text: str) -> float:
    """Reading-time hold for a beat, in seconds (ignore the model's number — it's
    unreliable; derive from word count instead). ~0.45s/word, clamped 2.0-6.5s."""
    return min(6.5, max(2.0, len((text or "").split()) * 0.45 + 1.2))


def _clean(s: str) -> str:
    """Strip markdown emphasis, escape HTML, turn newlines into <br>."""
    s = _re.sub(r"[*_`]", "", (s or "").strip())
    return _html.escape(s).replace("\n", "<br>")


def render_composition_html(beats: list[dict], audio_path: str | None = None) -> str:
    """Assemble the index.html for the given beats. If audio_path is given
    (narrated mode), add it as an <audio> track sized to the full duration."""
    cards, tl, t = [], [], 0.0
    XF = 0.6  # cross-dissolve overlap (s) — cards overlap so it reads continuous, not cut
    for i, b in enumerate(beats):
        dur = _hold(b.get("text", ""))
        kicker = _clean(b.get("kicker", ""))
        line = _clean(b.get("text", ""))
        cards.append(
            f'  <div class="card clip" id="c{i}" data-start="{t:.2f}" '
            f'data-duration="{dur:.2f}" data-track-index="0">'
            f'<div class="kicker">{kicker}</div><div class="line">{line}</div></div>'
        )
        # Cross-dissolve: start fading IN before the previous card finishes fading
        # OUT (overlap = XF), so there are no black gaps — continuous, not a slideshow.
        fade_in_at = max(0.0, t - XF) if i > 0 else 0.0
        tl.append(f'    tl.fromTo("#c{i}", {{opacity:0, y:36}}, '
                  f'{{opacity:1, y:0, duration:{XF + 0.2:.2f}, ease:"power2.out"}}, {fade_in_at:.2f});')
        # Slow scale on the headline for subtle motion (Ken-Burns feel on text).
        tl.append(f'    tl.fromTo("#c{i} .line", {{scale:1.0}}, '
                  f'{{scale:1.05, duration:{dur:.2f}, ease:"none"}}, {t:.2f});')
        tl.append(f'    tl.to("#c{i}", {{opacity:0, duration:{XF:.2f}}}, {t + dur - XF:.2f});')
        t += dur

    audio = ""
    if audio_path:
        audio = (f'  <audio data-start="0" data-duration="{t:.2f}" '
                 f'data-track-index="1" data-volume="1.0" src="{_html.escape(audio_path)}"></audio>')

    return _PAGE.format(cards="\n".join(cards), audio=audio, timeline="\n".join(tl))


def build(idea: dict, script_md: str, out_html: str, mode: str = "text",
          audio_path: str | None = None, words: list[dict] | None = None,
          total_dur: float | None = None) -> dict:
    """Generate index.html for a produced idea. Returns {beats, duration, path}.

    mode='text'     → typography only (no audio).
    mode='narrated' → hybrid layout synced to audio_path. `words` = whisper word
                      timings (or None → reading-time estimate); `total_dur` = the
                      narration length in seconds (required for narrated).
    """
    if mode == "narrated":
        return _build_narrated(idea, script_md, out_html, audio_path, words, total_dur)

    beats = build_storyboard(idea, script_md)
    beats = beats + [SUBSCRIBE_BEAT]   # always end on the subscribe CTA outro
    html_str = render_composition_html(beats, audio_path=None)
    with open(out_html, "w") as f:
        f.write(html_str)
    duration = sum(_hold(b.get("text", "")) for b in beats)
    return {"beats": beats, "duration": round(duration, 1), "path": out_html}


def _build_narrated(idea: dict, script_md: str, out_html: str,
                    audio_path: str | None, words: list[dict] | None,
                    total_dur: float | None) -> dict:
    """Hybrid narrated composition: section headlines + verbatim synced captions."""
    if not audio_path or not total_dur:
        raise ValueError("narrated mode needs audio_path and total_dur")
    narration = _tts.script_to_narration_text(script_md)

    # Caption layer — verbatim, synced. From whisper words if we have them, else a
    # reading-time estimate spread over the real audio length.
    if words:
        caps = _captions.chunk_words_to_captions(words)
    else:
        caps = _captions.estimate_caption_timings(narration, total_dur)

    # Headline layer — distilled section "chapters", each anchored to where it's spoken.
    sections = build_section_headlines(idea, script_md)
    headlines = assign_headline_times(sections, words, total_dur, narration)

    # Background layer — one atmospheric Pexels clip per chapter (symbolic only). Missing
    # key / failed fetch → None → that chapter falls back to the gradient (never crashes).
    out_dir = os.path.dirname(out_html)
    clips = _footage.fetch_clips([s.get("visual", "") for s in sections], out_dir,
                                 sport=idea.get("sport"))
    bg_segments = []
    for h, clip in zip(headlines, clips):
        if clip:
            bg_segments.append({"src": os.path.basename(clip),
                                "start": h["start"], "end": h["end"]})
    n_bg = sum(1 for c in clips if c)

    html_str = render_hybrid_html(headlines, caps, audio_path, total_dur,
                                  intro_title=idea["title_variants"][0],
                                  bg_segments=bg_segments)
    with open(out_html, "w") as f:
        f.write(html_str)
    beats = [{"kicker": "", "text": h["headline"]} for h in headlines]
    return {"beats": beats, "duration": round(total_dur, 1), "path": out_html,
            "captions": caps, "headlines": headlines, "n_bg_clips": n_bg,
            "n_chapters": len(headlines)}


# Closing call-to-action card appended to every composition.
SUBSCRIBE_BEAT = {"kicker": "The Untold Game",
                  "text": "Subscribe for more untold stories.",
                  "seconds": 4}


# ── Narrated mode: section headlines + alignment ─────────────────────────────

_HEADLINE_SYSTEM = """You are a documentary editor for "The Untold Game" (sports-history
channel). Split a narration script into its natural CHAPTERS (sections). For each chapter give:
- HEADLINE: a punchy on-screen chapter title (2-5 words, uppercase-ready).
- ANCHOR: the first 4-8 words of that chapter copied VERBATIM from the narration, exactly
  as spoken, so we can find where it starts in the audio.
- VISUAL: a 2-4 word stock-video search query showing ANONYMOUS action, equipment, venue, or
  atmosphere FOR THE SPORT named above, that fits this chapter's moment. Examples — F1: "formula 1 car racing",
  "race track aerial", "pit lane", "rain race spray", "checkered flag"; soccer: "soccer ball
  net", "empty football stadium", "stadium floodlights"; cricket: "cricket pitch", "cricket
  stumps", "cricket bat swing"; basketball: "basketball hoop", "empty basketball court".
  Keep it GENERIC stock footage — NEVER an identifiable real person, named team, logo, jersey
  number, or any news/archival clip of the actual event or people in this story. When unsure,
  use a generic sport venue or equipment shot.
Keep chapters in order. 6-12 chapters."""

_HEADLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},   # 2-5 word on-screen chapter title
                    "anchor": {"type": "string"},      # first 4-8 narration words, verbatim
                    "visual": {"type": "string"},      # atmospheric/symbolic stock-video query
                },
                "required": ["headline", "anchor", "visual"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


def build_section_headlines(idea: dict, script_md: str) -> list[dict]:
    """Distill the script into ordered chapters [{headline, anchor}] (structured output)."""
    client = anthropic.Anthropic(max_retries=5)
    narration = _tts.script_to_narration_text(script_md)
    prompt = (
        f"TITLE: {idea['title_variants'][0]}\nHOOK: {idea['hook']}\n"
        f"SPORT: {idea['sport']}  PILLAR: {idea['pillar']}\n\n"
        f"NARRATION:\n{narration}\n\n"
        f"Return the chapters. Each anchor must be copied verbatim from the narration above."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=2048, system=_HEADLINE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _HEADLINE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["sections"]


def _norm(s: str) -> str:
    return _re.sub(r"[^a-z0-9]", "", (s or "").lower())


def locate_anchor(words: list[dict], anchor: str, start: int = 0) -> int | None:
    """Find where `anchor` (a verbatim phrase) begins in the whisper `words`, searching
    from index `start`. Returns the word index of the match, or None. Tolerant: matches
    on the first anchor token and a majority of the following tokens (whisper mishears)."""
    atoks = [t for t in (_norm(w) for w in anchor.split()) if t]
    if not atoks:
        return None
    wnorm = [_norm(w["word"]) for w in words]
    n = len(atoks)
    need = max(1, (n + 1) // 2)   # majority of the anchor tokens must line up
    for i in range(start, len(wnorm)):
        if wnorm[i] != atoks[0]:
            continue
        hit = sum(1 for k in range(n) if i + k < len(wnorm) and wnorm[i + k] == atoks[k])
        if hit >= need:
            return i
    return None


def assign_headline_times(sections: list[dict], words: list[dict] | None,
                          total_dur: float, narration: str) -> list[dict]:
    """Map each chapter to a [start, end] time span. With whisper `words`, locate each
    anchor in the audio; without, locate the anchor by token position in `narration` and
    scale to total_dur. Starts are coerced monotonic (first=0, last ends at total_dur)."""
    if not sections:
        return []   # never crash the run on an empty distillation (CLAUDE.md rule)
    raw: list[float | None] = []
    if words:
        cursor = 0
        for sec in sections:
            idx = locate_anchor(words, sec["anchor"], start=cursor)
            if idx is None:
                raw.append(None)
            else:
                raw.append(float(words[idx]["start"]))
                cursor = idx + 1
    else:
        ntoks = [_norm(t) for t in narration.split() if _norm(t)]
        ntotal = max(1, len(ntoks))
        cursor = 0
        for sec in sections:
            idx = locate_anchor([{"word": t} for t in ntoks], sec["anchor"], start=cursor)
            if idx is None:
                raw.append(None)
            else:
                raw.append(total_dur * idx / ntotal)
                cursor = idx + 1

    # Build a clean, monotonic timeline. The first chapter always starts at 0; a found
    # anchor pins its chapter to where it's spoken; an unfound anchor is INTERPOLATED
    # evenly between its nearest known neighbours (with total_dur as the trailing pin),
    # so a missing anchor never collapses the chapter before it to zero duration.
    n = len(raw)
    starts: list[float | None] = [None] * n
    starts[0] = 0.0
    for i in range(1, n):
        if raw[i] is not None:
            starts[i] = max(0.0, float(raw[i]))
    known = [(i, s) for i, s in enumerate(starts) if s is not None] + [(n, total_dur)]
    for ki in range(len(known) - 1):
        (li, lv), (ri, rv) = known[ki], known[ki + 1]
        for i in range(li + 1, ri):          # the Nones strictly between two pins
            starts[i] = lv + (rv - lv) * (i - li) / (ri - li)
    # enforce non-decreasing (interpolation already is, but guard against pinned-out-of-order)
    for i in range(1, n):
        if starts[i] < starts[i - 1]:
            starts[i] = starts[i - 1]
    out = []
    for i, sec in enumerate(sections):
        end = starts[i + 1] if i + 1 < len(starts) else total_dur
        out.append({"headline": sec["headline"], "start": round(starts[i], 3),
                    "end": round(max(end, starts[i]), 3)})
    return out


# ── Hybrid HTML (headline band + synced caption line + audio) ─────────────────

_PAGE_HYBRID = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@400;600&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1920px; height:1080px; overflow:hidden; background:#0a0a0a; }}
  #stage {{ position:relative; width:1920px; height:1080px;
            background: radial-gradient(circle at 50% 32%, #1a1410 0%, #0a0a0a 72%); }}
  .bg {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
         z-index:0; opacity:0; }}
  /* scrim over the footage so headline + captions stay legible */
  .scrim {{ position:absolute; inset:0; z-index:1; pointer-events:none;
            background: linear-gradient(180deg, rgba(8,7,5,.55) 0%, rgba(8,7,5,.28) 32%,
                        rgba(8,7,5,.42) 60%, rgba(8,7,5,.78) 100%); }}
  .headline {{ position:absolute; left:0; right:0; top:300px; opacity:0; text-align:center;
               z-index:3; padding:0 200px; font-family:'Anton',sans-serif; color:#f4f1ea;
               font-size:104px; line-height:1.02; text-transform:uppercase;
               text-shadow:0 6px 40px rgba(0,0,0,.7); }}
  .caption {{ position:absolute; left:0; right:0; bottom:190px; opacity:0; text-align:center;
              z-index:3; padding:0 300px; font-family:'Oswald',sans-serif; font-weight:400;
              color:#e8e2d6; font-size:48px; line-height:1.3; text-shadow:0 3px 22px rgba(0,0,0,.85); }}
  .bar {{ position:absolute; bottom:80px; left:50%; transform:translateX(-50%); z-index:3;
          font-family:'Oswald',sans-serif; letter-spacing:.3em; font-size:24px;
          color:#9a9a9a; text-transform:uppercase; }}
  .intro {{ position:absolute; inset:0; display:flex; flex-direction:column;
            align-items:center; justify-content:center; opacity:0; padding:0 220px; z-index:3; }}
  .intro .ik {{ font-family:'Oswald',sans-serif; font-weight:600; letter-spacing:.4em;
                text-transform:uppercase; font-size:30px; color:#d98a3d; margin-bottom:34px; }}
  .intro .it {{ font-family:'Anton',sans-serif; color:#f4f1ea; text-align:center;
                font-size:92px; line-height:1.05; text-transform:uppercase; }}
</style></head>
<body>
<div id="stage" data-composition-id="untold" data-start="0" data-width="1920" data-height="1080">
{bg}
{headlines}
{caps}
  <div class="bar">THE UNTOLD GAME</div>
{audio}
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.13.0/gsap.min.js" integrity="sha512-NcZdtrT77bJr4STcmsGAESr06BYGE8woZdSdEgqnpyqac7sugNO+Tr4bGwGF3MsnEkGKhU2KL2xh6Ec+BqsaHA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{timeline}
    window.__timelines = window.__timelines || {{}};
    window.__timelines.untold = tl;
  </script>
</div>
</body></html>
"""


def render_hybrid_html(headlines: list[dict], caps: list[dict],
                       audio_path: str | None, total_dur: float,
                       intro_title: str | None = None, intro_kicker: str = "THE UNTOLD GAME",
                       intro_dur: float = 4.5, bg_segments: list[dict] | None = None) -> str:
    """Assemble the hybrid index.html: an atmospheric VIDEO background per chapter, an
    INTRO title card, then a headline that swaps per chapter and a caption that swaps per
    spoken phrase (all on the GSAP timeline), narration audio on track 1, and a 3.5s
    subscribe outro after the voice ends.

    bg_segments: [{src, start, end}] muted looping clips behind the text (chapter times,
    pre-offset). If intro_title is set, a title card holds for intro_dur seconds and the
    narration + all headline/caption/background times are shifted by that much."""
    XF = 0.45
    off = intro_dur if intro_title else 0.0   # everything after the intro is shifted by `off`
    hl_cards, cap_cards, tl = [], [], []

    # Background layer — one muted, looping atmospheric clip per chapter, cross-dissolving.
    bg_segments = bg_segments or []
    bg_cards = []
    for k, seg in enumerate(bg_segments):
        bs, be = float(seg["start"]) + off, float(seg["end"]) + off
        # the intro shares the first chapter's clip so the title sits over motion, not black
        vis_start = 0.0 if k == 0 and intro_title else bs
        bdur = max(0.6, be - vis_start)
        bg_cards.append(
            f'  <video class="bg clip" id="bg{k}" data-start="{vis_start:.2f}" '
            f'data-duration="{bdur:.2f}" data-track-index="0" data-playback-start="0" '
            f'data-volume="0" data-loop="true" src="{_html.escape(seg["src"])}"></video>'
        )
        fade_in = max(0.0, vis_start - XF) if k > 0 else 0.0
        tl.append(f'    tl.fromTo("#bg{k}", {{opacity:0}}, '
                  f'{{opacity:1, duration:{XF + 0.3:.2f}}}, {fade_in:.2f});')
        tl.append(f'    tl.to("#bg{k}", {{opacity:0, duration:{XF:.2f}}}, {be - XF:.2f});')
    bg_block = "\n".join(bg_cards)
    if bg_cards:
        bg_block += '\n  <div class="scrim"></div>'

    # Intro title card — fades in, holds, fades out before the first chapter.
    if intro_title:
        tl.append(f'    tl.fromTo("#intro", {{opacity:0, y:24}}, '
                  f'{{opacity:1, y:0, duration:0.8, ease:"power2.out"}}, 0.4);')
        tl.append(f'    tl.to("#intro", {{opacity:0, duration:0.6}}, {off - 0.6:.2f});')

    # Headline band — one card per chapter, cross-dissolving.
    for i, h in enumerate(headlines):
        start, end = float(h["start"]) + off, float(h["end"]) + off
        dur = max(0.6, end - start)
        hl_cards.append(
            f'  <div class="headline clip" id="h{i}" data-start="{start:.2f}" '
            f'data-duration="{dur:.2f}" data-track-index="0">{_clean(h["headline"])}</div>'
        )
        fade_at = max(off, start - XF) if i > 0 else off
        tl.append(f'    tl.fromTo("#h{i}", {{opacity:0, y:28}}, '
                  f'{{opacity:1, y:0, duration:{XF + 0.2:.2f}, ease:"power2.out"}}, {fade_at:.2f});')
        tl.append(f'    tl.to("#h{i}", {{opacity:0, duration:{XF:.2f}}}, {end - XF:.2f});')

    # Caption line — one card per spoken phrase, quick fades, tight to the voice.
    CF = 0.18
    for j, c in enumerate(caps):
        start, end = float(c["start"]) + off, float(c["end"]) + off
        dur = max(0.4, end - start)
        cap_cards.append(
            f'  <div class="caption clip" id="cap{j}" data-start="{start:.2f}" '
            f'data-duration="{dur:.2f}" data-track-index="0">{_clean(c["text"])}</div>'
        )
        tl.append(f'    tl.fromTo("#cap{j}", {{opacity:0}}, '
                  f'{{opacity:1, duration:{CF:.2f}}}, {start:.2f});')
        tl.append(f'    tl.to("#cap{j}", {{opacity:0, duration:{CF:.2f}}}, {max(start, end - CF):.2f});')

    # Subscribe outro — a headline beat after the narration ends (silent tail).
    out_start, out_dur = total_dur + off, 3.5
    oid = len(headlines)
    hl_cards.append(
        f'  <div class="headline clip" id="h{oid}" data-start="{out_start:.2f}" '
        f'data-duration="{out_dur:.2f}" data-track-index="0">SUBSCRIBE FOR MORE<br>UNTOLD STORIES</div>'
    )
    tl.append(f'    tl.fromTo("#h{oid}", {{opacity:0, y:28}}, '
              f'{{opacity:1, y:0, duration:0.5, ease:"power2.out"}}, {out_start:.2f});')

    intro_html = ""
    if intro_title:
        intro_html = (
            f'  <div class="intro clip" id="intro" data-start="0" data-duration="{off:.2f}" '
            f'data-track-index="0"><div class="ik">{_clean(intro_kicker)}</div>'
            f'<div class="it">{_clean(intro_title)}</div></div>'
        )

    audio = ""
    if audio_path:
        # narration starts after the intro; data-start = off
        audio = (f'  <audio data-start="{off:.2f}" data-duration="{total_dur:.2f}" '
                 f'data-track-index="1" data-volume="1.0" src="{_html.escape(audio_path)}"></audio>')

    return _PAGE_HYBRID.format(bg=bg_block, headlines=intro_html + "\n" + "\n".join(hl_cards),
                              caps="\n".join(cap_cards), audio=audio, timeline="\n".join(tl))
