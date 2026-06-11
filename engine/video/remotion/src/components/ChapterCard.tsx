import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {anton, CREAM} from '../fonts';

// Chapter headline: springs in, holds ~3s, then fades — leaving the b-roll + captions.
export const ChapterCard: React.FC<{headline: string}> = ({headline}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const y = interpolate(appear, [0, 1], [40, 0]);
  const HOLD = fps * 3.0;
  const OUT = fps * 0.6;
  const out = interpolate(f, [HOLD, HOLD + OUT], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = appear * out;

  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: 280}}>
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
          opacity,
          textShadow: '0 6px 40px rgba(0,0,0,0.75)',
        }}
      >
        {headline}
      </div>
    </AbsoluteFill>
  );
};
