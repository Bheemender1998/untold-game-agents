import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {UntoldProps} from './types';
import {Background} from './components/Background';
import {ShortCaptions} from './components/ShortCaptions';

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
      </Sequence>
      <Sequence from={introF} name="Captions">
        <ShortCaptions
          captions={props.captions}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
