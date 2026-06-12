#!/usr/bin/env bash
# Synthesize the "soft impact" SFX for chapter/intro title cards — a felt, low boom that
# lands as the title springs in (NOT a fast-cut whoosh). Fully synthesized with ffmpeg's
# aevalsrc, so it's CC0/owned and reproducible; no external sample to license.
#
# Each variant is a downward pitch sweep (a chirp) with an exponential amplitude decay:
#   phase(t) = 2*PI*(f0*t + (f1-f0)/(2*d) * t^2)   -> inst. freq glides f0 -> f1 over d sec
#   amp(t)   = exp(-k*t)                            -> the "boom" tail
# A short afade kills the end click; weighty adds a subtle echo tail for a room feel.
#
# Usage:
#   engine/video/make_impact_sfx.sh            # -> auditions in engine/video/sfx_auditions/
#   engine/video/make_impact_sfx.sh <name>     # also copies that variant to the chosen path
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$HERE/sfx_auditions"
FINAL="$HERE/remotion/public/sfx/impact.wav"
SR=48000
mkdir -p "$OUT"

synth() {  # synth <name> <duration> <aevalsrc-expr> [extra-filter]
  local name="$1" dur="$2" expr="$3" extra="${4:-anull}"
  local fadest; fadest=$(awk "BEGIN{printf \"%.3f\", $dur - 0.08}")
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "aevalsrc=${expr}:d=${dur}:s=${SR}" \
    -af "${extra},afade=t=out:st=${fadest}:d=0.08,aformat=channel_layouts=stereo" \
    -c:a pcm_s16le "$OUT/impact_${name}.wav"
  echo "  wrote $OUT/impact_${name}.wav  (${dur}s)"
}

echo "Synthesizing impact auditions -> $OUT"

# soft — gentle, short, dry. 130 -> 50 Hz over 0.7s, fast-ish decay.
synth soft 0.70 \
  "0.85*exp(-6*t)*sin(2*PI*(130*t-57.14*t*t))"

# weighty — deeper + a sub octave for body + a small echo tail. 110 -> 40 Hz over 1.0s, slow decay.
synth weighty 1.00 \
  "0.62*exp(-3.2*t)*sin(2*PI*(110*t-35*t*t)) + 0.30*exp(-2.8*t)*sin(2*PI*(55*t-17.5*t*t))" \
  "aecho=0.8:0.6:55:0.22"

# tight — punchy, very short, dry. 150 -> 60 Hz over 0.45s, quick decay.
synth tight 0.45 \
  "0.90*exp(-8*t)*sin(2*PI*(150*t-100*t*t))"

echo "Done. Audition the three, then re-run with the winner to install it:"
echo "  $0 soft|weighty|tight"

# If a variant name was passed, peak-normalize it to ~ -1 dBFS and install it as the
# composition's impact.wav (predictable loudness vs. the narration).
if [[ "${1:-}" != "" ]]; then
  pick="$OUT/impact_${1}.wav"
  [[ -f "$pick" ]] || { echo "no such variant: $1" >&2; exit 1; }
  maxdb=$(ffmpeg -hide_banner -i "$pick" -af volumedetect -f null - 2>&1 \
            | grep -oE "max_volume: [-0-9.]+ dB" | grep -oE "[-0-9.]+")
  [[ -n "$maxdb" ]] || { echo "volumedetect parse failed for $pick" >&2; exit 1; }
  gain=$(awk "BEGIN{printf \"%.2f\", -1.0 - ($maxdb)}")
  mkdir -p "$(dirname "$FINAL")"
  ffmpeg -hide_banner -loglevel error -y -i "$pick" -af "volume=${gain}dB" \
    -c:a pcm_s16le "$FINAL"
  echo "Installed $1 -> $FINAL  (peak-normalized ${gain}dB to ~ -1 dBFS)"
fi
