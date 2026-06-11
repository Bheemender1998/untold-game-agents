import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {createTikTokStyleCaptions, type Caption} from '@remotion/captions';
import {oswald, GOLD, CREAM} from '../fonts';
import type {CaptionWord} from '../types';

// Word-by-word kinetic captions, synced to the voice. We feed our own faster-whisper
// word timings into @remotion/captions' TikTok-style grouping (no whisper re-run).
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
    return createTikTokStyleCaptions({captions: caps, combineTokensWithinMilliseconds: 1200}).pages;
  }, [captions]);

  const page = pages.find((p) => nowMs >= p.startMs && nowMs < p.startMs + p.durationMs);
  if (!page) return null;

  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 150}}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '0 18px',
          maxWidth: 1400,
          padding: '0 80px',
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = nowMs >= tok.fromMs && nowMs < tok.toMs;
          const appeared = nowMs >= tok.fromMs;
          return (
            <span
              key={i}
              style={{
                fontFamily: oswald,
                fontWeight: 700,
                fontSize: 64,
                lineHeight: 1.2,
                textTransform: 'uppercase',
                letterSpacing: '0.01em',
                color: active ? GOLD : CREAM,
                opacity: appeared ? 1 : 0.35,
                transform: active ? 'translateY(-4px) scale(1.06)' : 'none',
                textShadow: '0 3px 20px rgba(0,0,0,0.9)',
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
