import React from 'react';
import {Composition} from 'remotion';
import {UntoldVideo} from './UntoldVideo';
import {UntoldShort} from './UntoldShort';
import {defaultProps} from './defaultProps';
import {shortDefaultProps} from './shortDefaultProps';
import type {UntoldProps} from './types';

// Total runtime = intro + narration + outro. calculateMetadata derives the frame count
// from the props so each video sizes itself to its own narration length.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="UntoldVideo"
        component={UntoldVideo}
        defaultProps={defaultProps}
        calculateMetadata={({props}: {props: UntoldProps}) => {
          const fps = props.fps || 30;
          const totalMs = props.introMs + props.narrationMs + (props.endHoldMs ?? 0) + props.outroMs;
          return {
            durationInFrames: Math.max(1, Math.round((totalMs / 1000) * fps)),
            fps,
            width: props.width || 1920,
            height: props.height || 1080,
          };
        }}
      />
      <Composition
        id="UntoldShort"
        component={UntoldShort}
        defaultProps={shortDefaultProps}
        calculateMetadata={({props}: {props: UntoldProps}) => {
          const fps = props.fps || 30;
          const totalMs = props.introMs + props.narrationMs + (props.endHoldMs ?? 0) + props.outroMs;
          return {
            durationInFrames: Math.max(1, Math.round((totalMs / 1000) * fps)),
            fps,
            width: props.width || 1080,
            height: props.height || 1920,
          };
        }}
      />
    </>
  );
};
