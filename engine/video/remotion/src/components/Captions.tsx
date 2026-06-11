import React, {useMemo} from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions, type Caption} from '@remotion/captions';
import {oswald, GOLD, CREAM} from '../fonts';
import type {CaptionWord} from '../types';

// Word-by-word kinetic captions, synced to the voice. Large, centered, multi-line block:
// a wider grouping window packs a fuller phrase per page, which wraps into 2-3 big lines
// that fill the canvas (vs. the old single small phrase at the bottom).
// Chapter headlines hold 3s then fade 0.6s; suppress captions during that window so the
// title owns the screen (the original "headline, then captions" intent), then resume.
const CHAPTER_HEADLINE_MS = 3600;

export const Captions: React.FC<{captions: CaptionWord[]; chapterStartsMs?: number[]}> = ({
  captions,
  chapterStartsMs = [],
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;

  // Hold for the chapter headline: don't draw captions while a title card is on screen.
  const inHeadline = chapterStartsMs.some(
    (s) => nowMs >= s && nowMs < s + CHAPTER_HEADLINE_MS,
  );

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
  if (!page || inHeadline) return null;

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', padding: '0 120px'}}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignContent: 'center',
          gap: '10px 26px',
          maxWidth: 1500,
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
                transform: `translateY(${active ? -8 : 0}px) scale(${scale})`,
                transformOrigin: 'center bottom',
                textShadow: '0 4px 24px rgba(0,0,0,0.92)',
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
