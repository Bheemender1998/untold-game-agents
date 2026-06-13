import React from 'react';
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {UntoldProps} from './types';
import {Background} from './components/Background';
import {ShortCaptions} from './components/ShortCaptions';
import {Watermark} from './components/Watermark';
import {EndCTA} from './components/EndCTA';

const ms2f = (ms: number, fps: number) => Math.round((ms / 1000) * fps);

// Vertical (1080×1920) YouTube Shorts composition.
// No intro card, no chapter cards, no outro — captions + footage start at frame 1.
// Pass introMs=0 in props so ms2f(0, fps) === 0 and Sequences start immediately.
export const UntoldShort: React.FC<UntoldProps> = (props) => {
  const {fps} = useVideoConfig();
  const introF = ms2f(props.introMs, fps); // shorts pass introMs=0 → starts at frame 0

  return (
    <AbsoluteFill style={{backgroundColor: '#0a0a0a'}}>
      <Background chapters={props.chapters} introMs={props.introMs} />
      <Sequence from={introF} name="Narration">
        <Audio src={staticFile(props.audioSrc)} />
        {props.musicSrc ? (
          <Audio
            src={staticFile(props.musicSrc)}
            loop
            volume={(f) => {
              const peak = props.musicVolume ?? 0.08;
              const total = ms2f(props.introMs + props.narrationMs + props.outroMs, fps);
              const fadeIn = Math.round(1.5 * fps);
              const fadeOut = Math.round(2.5 * fps);
              return interpolate(
                f,
                [0, fadeIn, Math.max(fadeIn, total - fadeOut), total],
                [0, peak, peak, 0],
                {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
              );
            }}
          />
        ) : null}
      </Sequence>
      <Sequence from={introF} name="Captions">
        <ShortCaptions
          captions={props.captions}
        />
      </Sequence>
      <Sequence from={introF + ms2f(props.narrationMs, fps)} name="EndCTA">
        <EndCTA vertical />
      </Sequence>
      <Watermark vertical />
    </AbsoluteFill>
  );
};
