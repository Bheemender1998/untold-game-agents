import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {anton, oswald, GOLD, CREAM} from '../fonts';

// Closing subscribe call-to-action.
export const Outro: React.FC<{kicker: string}> = ({kicker}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const y = interpolate(appear, [0, 1], [30, 0]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        opacity: appear,
      }}
    >
      <div
        style={{
          fontFamily: oswald,
          fontWeight: 600,
          letterSpacing: '0.4em',
          textTransform: 'uppercase',
          fontSize: 28,
          color: GOLD,
          marginBottom: 28,
          transform: `translateY(${y}px)`,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          fontFamily: anton,
          fontSize: 92,
          color: CREAM,
          textTransform: 'uppercase',
          textAlign: 'center',
          lineHeight: 1.05,
          transform: `translateY(${y}px)`,
          textShadow: '0 6px 40px rgba(0,0,0,0.7)',
        }}
      >
        SUBSCRIBE FOR MORE
        <br />
        UNTOLD STORIES
      </div>
    </AbsoluteFill>
  );
};
