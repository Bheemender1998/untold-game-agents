import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions, type Caption} from '@remotion/captions';
import {oswald, GOLD, CREAM} from '../fonts';
import type {CaptionWord} from '../types';

// Word-by-word kinetic captions, synced to the voice. Large, centered, multi-line block:
// a wider grouping window packs a fuller phrase per page, which wraps into 2-3 big lines
// that fill the canvas (vs. the old single small phrase at the bottom).
// Captions are always shown (including during title cards); anchored to the lower third
// so they never collide with the top-anchored chapter title card.
export const Captions: React.FC<{captions: CaptionWord[]}> = ({captions}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;

  const pages = useMemo(() => {
    const caps: Caption[] = captions.map((w) => ({
      text: ' ' + w.text,
      startMs: w.startMs,
      endMs: w.endMs,
      timestampMs: (w.startMs + w.endMs) / 2,
      confidence: null,
    }));
    // Wider window (was 1200ms) → ~8-10 words per page → wraps into a stacked block.
    return createTikTokStyleCaptions({captions: caps, combineTokensWithinMilliseconds: 3000}).pages;
  }, [captions]);

  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.startMs + p.durationMs);
  if (!page) return null;

  // Page-level fade: ease the whole block in/out instead of hard-cutting (matters most at the
  // chapter-headline boundaries, where captions resume/suppress). Kept short so contiguous
  // pages mid-narration only dip briefly at a natural phrase beat.
  const intoPage = nowMs - page.startMs;
  const leftInPage = page.startMs + page.durationMs - nowMs;
  const pageOpacity = Math.min(
    interpolate(intoPage, [0, 140], [0, 1], {extrapolateRight: 'clamp'}),
    interpolate(leftInPage, [0, 120], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
  );

  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', padding: '0 120px 160px'}}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignContent: 'center',
          gap: '10px 26px',
          maxWidth: 1500,
          opacity: pageOpacity,
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = nowMs >= tok.fromMs && nowMs < tok.toMs;
          // Per-word spring pop-in: frame-pure (a function of the frame, so it renders
          // deterministically), driven by how long since THIS word was spoken.
          const sinceF = ((nowMs - tok.fromMs) / 1000) * fps;
          const appeared = sinceF >= 0;
          const enter = appeared
            ? spring({frame: sinceF, fps, config: {damping: 13, mass: 0.5, stiffness: 170}})
            : 0; // 0 → ~1 with a slight overshoot = the "pop"
          const scale = (0.55 + enter * 0.45) * (active ? 1.06 : 1); // grows in, active lifts more
          // Settle cues that read as "premium": the word resolves OUT of a blur and rises into
          // place as it pops, instead of just scaling. Both are pure functions of `enter`.
          const blur = appeared ? (1 - Math.min(enter, 1)) * 12 : 14; // px, → 0 as it lands
          const driftY = appeared ? (1 - Math.min(enter, 1)) * 16 : 16; // rises up into place
          const lift = active ? -8 : 0;
          // Active word gets a warm gold glow on top of the legibility shadow.
          const glow = active ? ', 0 0 28px rgba(217,138,61,0.55)' : '';
          return (
            <span
              key={i}
              style={{
                fontFamily: oswald,
                fontWeight: 700,
                fontSize: 104,
                lineHeight: 1.08,
                textTransform: 'uppercase',
                letterSpacing: '0.01em',
                color: active ? GOLD : CREAM,
                opacity: appeared ? 0.3 + enter * 0.7 : 0.16, // future faint → pops to full
                filter: `blur(${blur}px)`,
                transform: `translateY(${lift + driftY}px) scale(${scale})`,
                transformOrigin: 'center bottom',
                textShadow: `0 4px 24px rgba(0,0,0,0.92)${glow}`,
              }}
            >
              {tok.text.trim()}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
