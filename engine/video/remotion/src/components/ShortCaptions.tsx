import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions, type Caption} from '@remotion/captions';
import {oswald, GOLD, CREAM} from '../fonts';
import type {CaptionWord} from '../types';

// Vertical (1080×1920) caption block for YouTube Shorts.
// No chapter-headline suppression — Shorts have no chapter cards.
// Positioned in the safe band: clear of the top channel-name strip (~12%)
// and the bottom buttons strip (~18%). Block sits ~42-52% down the frame.

export const ShortCaptions: React.FC<{captions: CaptionWord[]; chapterStartsMs?: number[]}> = ({
  captions,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const nowMs = (frame / fps) * 1000;

  // Font size is proportional to the frame width so it stays legible at any resolution.
  // At 1080px wide, this yields ~96px — big and mobile-readable.
  const fontSize = Math.round(width * 0.089);

  // Safe-band positioning: top of safe zone starts at ~12% (channel name strip),
  // bottom safe limit is ~82% (above the Shorts buttons strip).
  // We push the block to ~42% from the top — centred in the usable middle zone.
  const safeTopPx = Math.round(height * 0.12);
  const safeBottomPx = Math.round(height * 0.82);
  const safeBandH = safeBottomPx - safeTopPx;
  // Caption block top: 40% into the safe band
  const blockTop = safeTopPx + Math.round(safeBandH * 0.40);

  const pages = useMemo(() => {
    const caps: Caption[] = captions.map((w) => ({
      text: ' ' + w.text,
      startMs: w.startMs,
      endMs: w.endMs,
      timestampMs: (w.startMs + w.endMs) / 2,
      confidence: null,
    }));
    // Slightly tighter window than the long-form version (2s vs 3s) so fewer words
    // stack per page — the narrower 1080px frame wraps sooner and too many words
    // would flood the screen.
    return createTikTokStyleCaptions({captions: caps, combineTokensWithinMilliseconds: 2000}).pages;
  }, [captions]);

  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.startMs + p.durationMs);
  if (!page) return null;

  const intoPage = nowMs - page.startMs;
  const leftInPage = page.startMs + page.durationMs - nowMs;
  const pageOpacity = Math.min(
    interpolate(intoPage, [0, 140], [0, 1], {extrapolateRight: 'clamp'}),
    interpolate(leftInPage, [0, 120], [0, 1], {extrapolateLeft: 'clamp'}),
  );

  // Scrim vertical center: caption block top + half a nominal line height so the
  // gradient pool is centred on where the text actually sits, not the block's top edge.
  // At 1920px: blockTop ≈ 768px → scrimCenterPct ≈ 44-46% — well inside the safe band.
  const scrimCenterPct = ((blockTop + fontSize * 1.6) / height) * 100;

  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start'}}>
      {/* Soft feathered scrim behind caption text — rescues legibility on bright b-roll */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: `${scrimCenterPct}%`,
          transform: 'translateY(-50%)',
          height: 360,
          background:
            'radial-gradient(ellipse 78% 70% at 50% 50%, rgba(0,0,0,0.60) 0%, rgba(0,0,0,0.32) 55%, rgba(0,0,0,0) 78%)',
          pointerEvents: 'none',
          zIndex: 1,
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: blockTop,
          left: 0,
          right: 0,
          paddingLeft: 60,
          paddingRight: 60,
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignContent: 'center',
          gap: `10px ${Math.round(fontSize * 0.25)}px`,
          maxWidth: 960,
          margin: '0 auto',
          opacity: pageOpacity,
          zIndex: 2,
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = nowMs >= tok.fromMs && nowMs < tok.toMs;
          const sinceF = ((nowMs - tok.fromMs) / 1000) * fps;
          const appeared = sinceF >= 0;
          const enter = appeared
            ? spring({frame: sinceF, fps, config: {damping: 13, mass: 0.5, stiffness: 170}})
            : 0;
          const scale = (0.55 + enter * 0.45) * (active ? 1.06 : 1);
          const blur = appeared ? (1 - Math.min(enter, 1)) * 12 : 14;
          const driftY = appeared ? (1 - Math.min(enter, 1)) * 16 : 16;
          const lift = active ? -8 : 0;
          const glow = active ? ', 0 0 28px rgba(217,138,61,0.55)' : '';
          return (
            <span
              key={i}
              style={{
                fontFamily: oswald,
                fontWeight: 700,
                fontSize,
                lineHeight: 1.08,
                textTransform: 'uppercase',
                letterSpacing: '0.01em',
                color: active ? GOLD : CREAM,
                opacity: appeared ? 0.3 + enter * 0.7 : 0.16,
                filter: `blur(${blur}px)`,
                transform: `translateY(${lift + driftY}px) scale(${scale})`,
                transformOrigin: 'center bottom',
                textShadow: `0 4px 22px rgba(0,0,0,0.90), 0 2px 5px rgba(0,0,0,0.85)${glow}`,
                WebkitTextStroke: '1px rgba(0,0,0,0.28)',
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
