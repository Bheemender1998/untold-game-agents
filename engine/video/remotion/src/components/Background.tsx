import React from 'react';
import {
  AbsoluteFill, Loop, OffthreadVideo, Sequence, interpolate, staticFile,
  useCurrentFrame, useVideoConfig,
} from 'remotion';
import type {Chapter} from '../types';

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

export const Background: React.FC<{chapters: Chapter[]; introMs: number}> = ({
  chapters,
  introMs,
}) => {
  const {fps} = useVideoConfig();
  const introF = ms2f(introMs, fps);

  return (
    <AbsoluteFill>
      <GradientField />

      {chapters.map((c, i) => {
        if (!c.bClip) return null;
        // The first chapter's clip also plays under the intro (so the title sits over
        // motion, not black).
        const from = i === 0 ? 0 : introF + ms2f(c.startMs, fps);
        const to = introF + ms2f(c.endMs, fps);
        const dur = Math.max(1, to - from);
        const clipF = c.bClipMs ? Math.max(1, ms2f(c.bClipMs, fps)) : dur;
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`bg ${i + 1}`}>
            <Fade durationInFrames={dur}>
              <AbsoluteFill style={{filter: 'saturate(0.98) contrast(1.03) brightness(1.25)'}}>
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

      {/* light vignette + a bottom-weighted scrim only where the captions sit (the text
          has its own shadow, so the footage can stay visible) */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 44%, rgba(0,0,0,0) 46%, rgba(0,0,0,0.28) 100%)',
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
