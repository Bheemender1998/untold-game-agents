import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {anton, GOLD, CREAM} from '../fonts';

// Chapter headline: springs in (resolving out of a soft blur), holds ~3s, then fades — leaving
// the b-roll + captions. A gold accent rule wipes in beneath it for a documentary title feel.
export const ChapterCard: React.FC<{headline: string}> = ({headline}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const y = interpolate(appear, [0, 1], [40, 0]);
  const blur = interpolate(appear, [0, 1], [12, 0]); // text resolves out of a soft blur
  // Accent rule wipes open slightly after the headline lands.
  const rule = spring({frame: f, fps, config: {damping: 200}, delay: Math.round(fps * 0.18)});
  const HOLD = fps * 3.0;
  const OUT = fps * 0.6;
  const out = interpolate(f, [HOLD, HOLD + OUT], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = appear * out;

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-start',
        alignItems: 'center',
        flexDirection: 'column',
        paddingTop: 280,
      }}
    >
      <div
        style={{
          fontFamily: anton,
          fontSize: 100,
          color: CREAM,
          textTransform: 'uppercase',
          textAlign: 'center',
          lineHeight: 1.02,
          maxWidth: 1500,
          padding: '0 120px',
          transform: `translateY(${y}px)`,
          filter: `blur(${blur}px)`,
          opacity,
          textShadow: '0 6px 40px rgba(0,0,0,0.75)',
        }}
      >
        {headline}
      </div>
      <div
        style={{
          marginTop: 32,
          height: 5,
          width: interpolate(rule, [0, 1], [0, 220]),
          background: GOLD,
          borderRadius: 4,
          opacity: out,
          boxShadow: '0 0 20px rgba(217,138,61,0.5)',
        }}
      />
    </AbsoluteFill>
  );
};
