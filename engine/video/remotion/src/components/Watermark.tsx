import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {HANDLE, LOGO} from '../brand';
import {oswald, CREAM} from '../fonts';

// Persistent channel watermark: logo + handle, bottom-right, subtle.
export const Watermark: React.FC<{vertical?: boolean}> = ({vertical}) => {
  const logo = vertical ? 64 : 56;
  const bottom = vertical ? 140 : 48; // lift above the Short caption zone / Shorts UI
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-end', opacity: 0.6}}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: `0 ${vertical ? 36 : 48}px ${bottom}px 0`,
        }}
      >
        <Img src={staticFile(LOGO)} style={{width: logo, height: logo, borderRadius: '50%'}} />
        <span
          style={{
            fontFamily: oswald,
            fontWeight: 600,
            fontSize: vertical ? 30 : 26,
            color: CREAM,
            letterSpacing: '0.04em',
            textShadow: '0 2px 12px rgba(0,0,0,0.8)',
          }}
        >
          {HANDLE}
        </span>
      </div>
    </AbsoluteFill>
  );
};
