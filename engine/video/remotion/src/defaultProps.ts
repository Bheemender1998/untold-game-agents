// Sample props so `remotion studio` previews without real assets (no b-roll → gradient fallback).
import type {UntoldProps} from './types';

export const defaultProps: UntoldProps = {
  title: 'The Goal That Got Him Killed',
  kicker: 'THE UNTOLD GAME',
  audioSrc: 'narration.wav',
  fps: 30,
  width: 1920,
  height: 1080,
  introMs: 4000,
  outroMs: 3500,
  narrationMs: 9000,
  captions: [
    {text: 'July', startMs: 0, endMs: 500},
    {text: 'second,', startMs: 500, endMs: 1100},
    {text: 'nineteen', startMs: 1100, endMs: 1700},
    {text: 'ninety', startMs: 1700, endMs: 2200},
    {text: 'four.', startMs: 2200, endMs: 2900},
    {text: 'A', startMs: 3200, endMs: 3400},
    {text: 'nation', startMs: 3400, endMs: 3900},
    {text: 'held', startMs: 3900, endMs: 4300},
    {text: 'its', startMs: 4300, endMs: 4600},
    {text: 'breath.', startMs: 4600, endMs: 5400},
  ],
  chapters: [
    {headline: 'THE NIGHT IT ENDED', startMs: 0, endMs: 4500},
    {headline: 'A NATION WATCHED', startMs: 4500, endMs: 9000},
  ],
};
