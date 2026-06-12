// Sample props for the UntoldShort (1080×1920) composition.
// No b-roll clips → Background falls back to the animated gradient.
// audioSrc won't resolve during a still render — that's fine; Audio is ignored for stills.
import type {UntoldProps} from './types';

export const shortDefaultProps: UntoldProps = {
  title: 'The Goal That Got Him Killed',
  kicker: 'THE UNTOLD GAME',
  audioSrc: 'narration.wav',
  fps: 30,
  width: 1080,
  height: 1920,
  introMs: 0,         // Shorts: no intro delay — captions start at frame 0
  outroMs: 0,
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
    // No bClip → gradient fallback
    {headline: 'THE NIGHT IT ENDED', startMs: 0, endMs: 4500},
    {headline: 'A NATION WATCHED', startMs: 4500, endMs: 9000},
  ],
};
