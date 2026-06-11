# The Untold Game — Execution Plan

## North star
Decide *what video to make next* with data, produce it, publish on cadence, and
learn from real performance — the ConvictionFinder loop applied to a YouTube channel.

## Stages
1. **Ideate (DONE / LIVE)** — 4 agents generate scored, web-researched ideas;
   human review/approve. Free DuckDuckGo search; Claude Sonnet 4.6.
2. **Produce (Stage 2)** — `pipeline/`: script → thumbnail → metadata → schedule.
3. **Publish (Stage 2)** — `publish/`: YouTube Data API v3 upload (OAuth), cadence-aware.
4. **Learn (Stage 3)** — `ingest/` + `outcomes/`: pull post-publish metrics, feed
   predicted-vs-actual back so the agents/scorer improve.
5. **Dashboard** — Next.js review UI (queue, pipeline, outcomes).

## Gate before each stage
Prove the prior stage's value first. Stage 1 is proven (real, makeable ideas).
Stage 2 is justified only once a batch of ideas is approved and worth publishing.
