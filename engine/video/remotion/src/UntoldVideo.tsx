import React from 'react';
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {UntoldProps} from './types';
import {Background} from './components/Background';
import {ChapterCard} from './components/ChapterCard';
import {Captions} from './components/Captions';
import {Intro} from './components/Intro';
import {EndCTA} from './components/EndCTA';
import {Watermark} from './components/Watermark';

const ms2f = (ms: number, fps: number) => Math.round((ms / 1000) * fps);

// Soft low-end impact under each title reveal (intro + chapter cards). Remotion mixes it
// alongside the narration; kept low so it sits under the voice. Tune IMPACT_VOL by ear.
const IMPACT_VOL = 0.4;
const Impact: React.FC = () => (
  <Audio src={staticFile('sfx/impact.wav')} volume={IMPACT_VOL} />
);

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
        <Impact />
      </Sequence>

      {/* narration starts after the intro; mood-matched music bed under it */}
      <Sequence from={introF} name="Narration">
        <Audio src={staticFile(props.audioSrc)} />
        {props.musicSrc ? (
          <Audio
            src={staticFile(props.musicSrc)}
            loop
            volume={(f) => {
              const peak = props.musicVolume ?? 0.12;
              const total = ms2f(props.introMs + props.narrationMs + props.outroMs, fps) - introF;
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

      {/* chapter title cards (headline holds ~3s then fades, leaving b-roll + captions) */}
      {props.chapters.map((c, i) => (
        <Sequence
          key={i}
          from={introF + ms2f(c.startMs, fps)}
          durationInFrames={Math.max(1, ms2f(c.endMs - c.startMs, fps))}
          name={`Chapter ${i + 1}`}
        >
          <ChapterCard headline={c.headline} />
          <Impact />
        </Sequence>
      ))}

      {/* kinetic word-by-word captions, synced to the voice (offset by the intro) */}
      <Sequence from={introF} name="Captions">
        <Captions
          captions={props.captions}
          chapterStartsMs={props.chapters.map((c) => c.startMs)}
        />
      </Sequence>

      {/* like/comment/subscribe end card after the narration ends */}
      <Sequence from={introF + narrF} name="EndCTA">
        <EndCTA />
      </Sequence>

      {/* persistent channel watermark (bottom-right) */}
      <Watermark />
    </AbsoluteFill>
  );
};
