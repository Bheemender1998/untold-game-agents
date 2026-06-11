# Next-video improvements (from review of the first Escobar cut)

These are deferred enhancements for the **next** video, captured 2026-06-11 after the
first full Remotion render was approved as "almost there." Do NOT retrofit the Escobar
cut — apply on the next production.

1. **More chapter headings.** The current cut shows ~11 chapter cards over 13.5 min;
   add more on-screen headings so the structure reads more often.
2. **Bigger / multi-column captions.** Kinetic captions currently fill only ~5% of the
   frame. Use more of the canvas — larger type and/or a multi-column / multi-line layout
   so the words carry more visual weight. (Touch: `engine/video/remotion/src/components/Captions.tsx`.)
3. **Newspaper-clipping stills.** Add a visual layer of period newspaper articles about
   the incident (rights-cleared / public-domain only — same integrity rule: real archival
   documents are fine, fabricated/AI-faked people/events are not).
4. **Sources + links in the YouTube description.** Put the script's fact-check sources
   (already gathered by the fact-gate) and reference links into the video description at
   publish time. (Touch: `engine/pipeline/metadata.py` description + `engine/publish/uploader.py`.)

See also: the automation plan (orchestrate generate→render→QC→approve→publish, ~2/day,
human-approve-before-publish).
