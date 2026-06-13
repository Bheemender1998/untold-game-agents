import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {HANDLE, LOGO} from '../brand';
import {anton, oswald, GOLD, CREAM} from '../fonts';

// Closing Like/Comment/Subscribe card with the channel logo + handle.
export const EndCTA: React.FC<{vertical?: boolean}> = ({vertical}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f, fps, config: {damping: 200}});
  const y = interpolate(appear, [0, 1], [30, 0]);
  return (
    <AbsoluteFill
      style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column', opacity: appear}}
    >
      <Img
        src={staticFile(LOGO)}
        style={{
          width: vertical ? 160 : 120,
          height: vertical ? 160 : 120,
          borderRadius: '50%',
          marginBottom: 28,
          transform: `translateY(${y}px)`,
        }}
      />
      <div
        style={{
          fontFamily: anton,
          fontSize: vertical ? 64 : 80,
          color: CREAM,
          textTransform: 'uppercase',
          textAlign: 'center',
          lineHeight: 1.08,
          transform: `translateY(${y}px)`,
          textShadow: '0 6px 40px rgba(0,0,0,0.7)',
        }}
      >
        LIKE · COMMENT
        <br />
        SUBSCRIBE
      </div>
      <div
        style={{
          fontFamily: oswald,
          fontWeight: 600,
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
          fontSize: vertical ? 34 : 30,
          color: GOLD,
          marginTop: 24,
          transform: `translateY(${y}px)`,
        }}
      >
        {HANDLE}
      </div>
      <div style={{fontFamily: oswald, fontSize: vertical ? 26 : 24, color: CREAM, opacity: 0.8, marginTop: 14}}>
        for more untold stories.
      </div>
      {vertical ? (
        <div
          style={{
            fontFamily: oswald,
            fontSize: 38,
            color: GOLD,
            textTransform: 'uppercase',
            textAlign: 'center',
            letterSpacing: '0.04em',
            marginTop: 28,
            transform: `translateY(${y}px)`,
            textShadow: '0 4px 24px rgba(0,0,0,0.85)',
          }}
        >
          Full story on our channel
          <br />
          link in description
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
