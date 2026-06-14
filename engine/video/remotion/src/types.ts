// Input props for the UntoldVideo composition — emitted by engine/run_video.py as props.json.

export type CaptionWord = {
  text: string;
  startMs: number;  // relative to narration start (0 = first spoken word)
  endMs: number;
};

export type Chapter = {
  headline: string;
  startMs: number;   // relative to narration start
  endMs: number;
  bClip?: string;    // filename in public/ (atmospheric Pexels clip); omitted → gradient fallback
  bClipMs?: number;  // clip length, so we can loop it under a longer chapter
};

export type BBeat = {
  startMs: number;       // relative to narration start
  endMs: number;
  src?: string | null;   // filename in public/ (atmospheric clip); null/omitted → gradient shows through
  zoomDir: 'in' | 'out'; // Ken-Burns direction for this beat
  clipMs?: number | null; // source media length, so a clip shorter than the beat tiles (not freezes)
};

export type UntoldProps = {
  title: string;
  kicker: string;        // "THE UNTOLD GAME"
  audioSrc: string;      // narration filename in public/
  fps: number;
  width: number;
  height: number;
  introMs: number;
  outroMs: number;
  endHoldMs?: number;    // Shorts: hold the final story shot + music this long before the EndCTA (default 0)
  narrationMs: number;   // length of the narration audio
  captions: CaptionWord[];
  chapters: Chapter[];
  bBeats?: BBeat[];      // beat-level b-roll track; preferred over per-chapter `chapters[].bClip`
  musicSrc?: string;     // background bed filename in public/ (Shorts only); omitted → silent
  musicVolume?: number;  // peak bed volume under the narration (e.g. 0.12)
};
