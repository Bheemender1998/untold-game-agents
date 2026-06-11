# The Untold Game — Dashboard (planned)

Next.js / Vercel review UI, modeled on ConvictionFinder's dashboard. Planned views:
- **Idea queue** — approve/reject pending ideas (replaces the terminal dashboard)
- **Pipeline** — ideas by stage: idea → scripted → thumbnail → scheduled → published
- **Outcomes** — published-video performance vs predicted viral score

Data source: `queue/idea_queue.json` today; `engine/db/` (SQLite/Postgres) at Stage 3.
Scaffold with `npx create-next-app@latest .` here when Stage 2 is underway.
