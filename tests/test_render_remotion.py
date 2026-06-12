from engine.video import render_remotion


def test_stage_assets_preserves_sfx_subdir(tmp_path, monkeypatch):
    """The committed title-impact SFX lives in public/sfx/ so the per-render asset
    cleanup (which globs only top-level *.wav/*.mp4/*.mp3) must not delete it."""
    public = tmp_path / "public"
    sfx = public / "sfx"
    sfx.mkdir(parents=True)
    impact = sfx / "impact.wav"
    impact.write_bytes(b"IMPACT")              # the committed SFX asset
    (public / "stale.wav").write_bytes(b"old")  # a leftover from a previous render
    monkeypatch.setattr(render_remotion, "PUBLIC_DIR", str(public))

    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"voice")
    clip = tmp_path / "bg_00.mp4"
    clip.write_bytes(b"clip")

    render_remotion._stage_assets(str(audio), [str(clip)])

    assert impact.read_bytes() == b"IMPACT"          # SFX in subdir survived
    assert not (public / "stale.wav").exists()       # stale top-level wav cleared
    assert (public / "narration.wav").exists()       # this render's audio staged
    assert (public / "bg_00.mp4").exists()           # this render's clip staged
