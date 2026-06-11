import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {UntoldProps} from './types';
import {Background} from './components/Background';
import {ChapterCard} from './components/ChapterCard';
import {Captions} from './components/Captions';
import {Intro} from './components/Intro';
import {Outro} from './components/Outro';

const ms2f = (ms: number, fps: number) => Math.round((ms / 1000) * fps);

export const UntoldVideo: React.FC<UntoldProps> = (props) => {
  const {fps} = useVideoConfig();
  const introF = ms2f(props.introMs, fps);
  const narrF = ms2f(props.narrationMs, fps);

  return (
    <AbsoluteFill style={{backgroundColor: '#0a0a0a'}}>
      {/* graded atmospheric b-roll per chapter + vignette/scrim (behind everything) */}
      <Background chapters={props.chapters} introMs={props.introMs} />

      {/* intro title card */}
      <Sequence durationInFrames={introF} name="Intro">
        <Intro title={props.title} kicker={props.kicker} />
      </Sequence>

      {/* narration starts after the intro */}
      <Sequence from={introF} name="Narration">
        <Audio src={staticFile(props.audioSrc)} />
      </Sequence>

      {/* chapter title cards (headline holds ~3s then fades, leaving b-roll + captions) */}
      {props.chapters.map((c, i) => (
        <Sequence
          key={i}
          from={introF + ms2f(c.startMs, fps)}
          durationInFrames={Math.max(1, ms2f(c.endMs - c.startMs, fps))}
          name={`Chapter ${i + 1}`}
        >
          <ChapterCard headline={c.headline} />
        </Sequence>
      ))}

      {/* kinetic word-by-word captions, synced to the voice (offset by the intro) */}
      <Sequence from={introF} name="Captions">
        <Captions captions={props.captions} />
      </Sequence>

      {/* subscribe outro after the narration ends */}
      <Sequence from={introF + narrF} name="Outro">
        <Outro kicker={props.kicker} />
      </Sequence>
    </AbsoluteFill>
  );
};
