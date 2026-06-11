// Channel typography. @remotion/google-fonts loads these deterministically for render.
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadOswald} from '@remotion/google-fonts/Oswald';

// Load only the weights/subset we use (avoids dozens of font requests per render).
export const anton = loadAnton('normal', {weights: ['400'], subsets: ['latin']}).fontFamily;
export const oswald = loadOswald('normal', {weights: ['400', '600', '700'], subsets: ['latin']}).fontFamily;

export const GOLD = '#d98a3d';
export const CREAM = '#f4f1ea';
