// Remotion render config. Kept light for an M2/8GB box (b-roll decoding is the heavy part).
import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// Concurrency is also overridable via the CLI (--concurrency); keep a safe default here.
Config.setConcurrency(2);
