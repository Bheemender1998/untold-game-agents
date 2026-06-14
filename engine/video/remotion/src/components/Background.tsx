import React from 'react';
import {
  AbsoluteFill, Loop, OffthreadVideo, Sequence, interpolate, staticFile,
  useCurrentFrame, useVideoConfig,
} from 'remotion';
import type {Chapter, BBeat} from '../types';

const ms2f = (ms: number, fps: number) => Math.round((ms / 1000) * fps);

// Slowly drifting gradient field — the base layer, so nothing is ever flat black even
// when a chapter has no b-roll clip.
const GradientField: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const x = 50 + Math.sin(t * 0.12) * 16;
  const y = 38 + Math.cos(t * 0.09) * 12;
  const x2 = 30 + Math.cos(t * 0.07) * 18;
  // Warm, designed field (never flat black) — a moving key glow over a deep base, plus a
  // second cooler pool for depth. Kept bright enough to survive the scrim on no-footage moments.
  return (
    <AbsoluteFill
      style={{
        background: [
          `radial-gradient(circle at ${x}% ${y}%, rgba(122,84,48,0.55) 0%, rgba(60,42,26,0) 46%)`,
          `radial-gradient(circle at ${x2}% 78%, rgba(38,46,66,0.45) 0%, rgba(20,24,34,0) 50%)`,
          'radial-gradient(circle at 50% 40%, #3a2a1c 0%, #1f160f 52%, #100b09 86%)',
        ].join(', '),
      }}
    />
  );
};

// Crossfade wrapper for a chapter's b-roll.
const Fade: React.FC<{durationInFrames: number; children: React.ReactNode}> = ({
  durationInFrames,
  children,
}) => {
  const f = useCurrentFrame();
  // Remotion's interpolate requires a STRICTLY increasing input range. For a tiny clip,
  // skip the fade; otherwise cap F so 0 < F < dur-F < dur holds for any length.
  if (durationInFrames < 4) {
    return <AbsoluteFill>{children}</AbsoluteFill>;
  }
  const F = Math.min(12, Math.floor((durationInFrames - 1) / 2));
  const opacity = interpolate(
    f,
    [0, F, durationInFrames - F, durationInFrames],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

// A single b-roll beat: hard cut in (tiny 3-frame fade so there's no black flash), looped
// to fill the beat, with a slow Ken-Burns zoom in the beat's direction.
const BeatClip: React.FC<{src: string; durationInFrames: number; zoomDir: 'in' | 'out';
  clipMs?: number | null}> = ({
  src,
  durationInFrames,
  zoomDir,
  clipMs,
}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fadeF = Math.min(3, Math.max(1, Math.floor(durationInFrames / 2)));
  const opacity = interpolate(f, [0, fadeF], [0, 1], {extrapolateRight: 'clamp'});
  const p = durationInFrames > 1 ? f / (durationInFrames - 1) : 0;
  const scale = zoomDir === 'in'
    ? interpolate(p, [0, 1], [1.0, 1.08], {extrapolateRight: 'clamp'})
    : interpolate(p, [0, 1], [1.08, 1.0], {extrapolateRight: 'clamp'});
  // Loop period = the source media length so a clip SHORTER than the beat tiles instead of
  // freezing on its last frame (matters for the long-form first beat ≈ introMs+beatMs).
  // Unknown length → fall back to the beat window.
  const loopF = clipMs ? Math.max(1, ms2f(clipMs, fps)) : durationInFrames;
  return (
    <AbsoluteFill style={{opacity}}>
      <AbsoluteFill
        style={{
          filter: 'brightness(1.22) contrast(1.03) sepia(0.18) saturate(1.18) hue-rotate(-6deg)',
          transform: `scale(${scale})`,
        }}
      >
        <Loop durationInFrames={loopF}>
          <OffthreadVideo
            src={staticFile(src)}
            muted
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </Loop>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const Background: React.FC<{chapters: Chapter[]; introMs: number; bBeats?: BBeat[]}> = ({
  chapters,
  introMs,
  bBeats,
}) => {
  const {fps} = useVideoConfig();
  const introF = ms2f(introMs, fps);

  return (
    <AbsoluteFill>
      <GradientField />

      {bBeats && bBeats.length > 0
        ? bBeats.map((b, i) => {
            if (!b.src) return null;                       // gradient shows through this beat
            const from = i === 0 ? 0 : introF + ms2f(b.startMs, fps);
            const to = introF + ms2f(b.endMs, fps);
            const dur = Math.max(1, to - from);
            return (
              <Sequence key={i} from={from} durationInFrames={dur} name={`beat ${i + 1}`}>
                <BeatClip src={b.src} durationInFrames={dur} zoomDir={b.zoomDir} clipMs={b.clipMs} />
              </Sequence>
            );
          })
        : chapters.map((c, i) => {
            if (!c.bClip) return null;
            const from = i === 0 ? 0 : introF + ms2f(c.startMs, fps);
            const to = introF + ms2f(c.endMs, fps);
            const dur = Math.max(1, to - from);
            const clipF = c.bClipMs ? Math.max(1, ms2f(c.bClipMs, fps)) : dur;
            return (
              <Sequence key={i} from={from} durationInFrames={dur} name={`bg ${i + 1}`}>
                <Fade durationInFrames={dur}>
                  <AbsoluteFill style={{filter: 'brightness(1.22) contrast(1.03) sepia(0.18) saturate(1.18) hue-rotate(-6deg)'}}>
                    <Loop durationInFrames={clipF}>
                      <OffthreadVideo
                        src={staticFile(c.bClip)}
                        muted
                        style={{width: '100%', height: '100%', objectFit: 'cover'}}
                      />
                    </Loop>
                  </AbsoluteFill>
                </Fade>
              </Sequence>
            );
          })}

      {/* light vignette + bottom-weighted scrim (unchanged) */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 44%, rgba(0,0,0,0) 46%, rgba(20,11,3,0.30) 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(8,7,5,0.28) 0%, rgba(8,7,5,0) 24%, rgba(8,7,5,0) 60%, rgba(8,7,5,0.55) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
