import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {anton, oswald, GOLD, CREAM} from '../fonts';

// Opening title card — kicker + title over the (already-playing) first b-roll clip.
export const Intro: React.FC<{title: string; kicker: string}> = ({title, kicker}) => {
  const f = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const out = interpolate(f, [durationInFrames - 16, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = appear * out;
  const y = interpolate(appear, [0, 1], [30, 0]);
  const titleBlur = interpolate(appear, [0, 1], [10, 0]); // title resolves out of a soft blur

  return (
    <AbsoluteFill
      style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', opacity}}
    >
      <div
        style={{
          fontFamily: oswald,
          fontWeight: 600,
          letterSpacing: '0.42em',
          textTransform: 'uppercase',
          fontSize: 30,
          color: GOLD,
          marginBottom: 34,
          transform: `translateY(${y}px)`,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          fontFamily: anton,
          fontSize: 96,
          color: CREAM,
          textTransform: 'uppercase',
          textAlign: 'center',
          lineHeight: 1.05,
          maxWidth: 1500,
          padding: '0 160px',
          transform: `translateY(${y}px)`,
          filter: `blur(${titleBlur}px)`,
          textShadow: '0 6px 40px rgba(0,0,0,0.7)',
        }}
      >
        {title}
      </div>
    </AbsoluteFill>
  );
};
