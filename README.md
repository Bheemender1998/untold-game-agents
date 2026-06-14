# The Untold Game — Content Engine

Automated YouTube content system for **The Untold Game** (multi-sport history channel).
Architecture modeled on ConvictionFinder: an `engine/` that generates video ideas,
you review/approve them, and (Stage 2+) it scripts, publishes, and learns from
real performance.

## Pipeline

```
engine/ideate/    4 agents generate scored video ideas (FREE web search)   ← LIVE
       ↓          review dashboard: approve / reject
engine/pipeline/  script → thumbnail → banner → metadata → schedule          ← script/metadata/thumbnail/banner LIVE; schedule Stage 2
       ↓
engine/publish/   upload to YouTube (Data API v3, OAuth)                     ← Stage 2
       ↓
engine/outcomes/  track views/CTR/retention vs predicted viral score        ← Stage 3
```

## Setup

```bash
python3 -m pip install -r requirements.txt

# Anthropic key — reuse ConvictionFinder's (lives in Railway, not on disk):
cp .env.example .env
#   then pull it without pasting by hand (from the CF-linked dir):
#   cd ../ConvictionFinder && railway variables --kv | grep ANTHROPIC_API_KEY > /tmp/k \
#     && cat /tmp/k >> ../untold_game_agents/.env && rm /tmp/k
```

No paid web-search add-on needed — search is **free** via DuckDuckGo (`ddgs`).

## Run

```bash
python3 -m engine.run_pipeline             # all 4 agents → review dashboard
python3 run_pipeline.py                     # same (root shim)
python3 -m engine.run_pipeline --agent 1    # one agent: 1=history 2=trending 3=gaps 4=evergreen
python3 -m engine.run_pipeline --review     # review existing queue, no generation
python3 -m engine.run_pipeline --stats      # queue stats
python3 -m engine.run_subject --id <id> [--format short]   # auto-source subject.png (Wikipedia lead image → Pexels fallback; human photo wins)
```

Ideas are stored in `queue/idea_queue.json` (gitignored). The review dashboard is
interactive — approve / reject / skip each idea in your terminal.

## Layout

See [`CLAUDE.md`](CLAUDE.md) for the full map and conventions, [`HANDOFF.md`](HANDOFF.md)
for current state, and [`docs/`](docs/) for decisions and the roadmap.

## Cost

Per run = **Claude tokens only** (Sonnet 4.6). Web search is free. The Anthropic
key is shared with ConvictionFinder.
