import json
import os

from engine.video import music


def test_module_constants():
    assert music.MUSIC_VOLUME == 0.12
    assert music.MOODS == ("tense", "triumphant", "somber", "hype")
    assert music.MUSIC_DIR.endswith("engine/video/music")


def test_build_manifest_groups_by_mood_and_ignores_unused(tmp_path):
    root = tmp_path / "music"
    for mood in ("tense", "somber"):
        (root / mood).mkdir(parents=True)
    (root / "tense" / "dark.mp3").write_bytes(b"x")
    (root / "somber" / "sad.mp3").write_bytes(b"x")
    (root / "somber" / "notes.txt").write_text("ignore me")   # non-audio ignored
    (root / "_unused").mkdir()
    (root / "_unused" / "boogie.mp3").write_bytes(b"x")        # off-tone, excluded
    (root / "attribution.json").write_text('{"sad.mp3": "Music by X (CC BY 4.0)"}')

    man = music.build_manifest(str(root))

    assert man["tense"] == [{"file": "tense/dark.mp3", "attribution": ""}]
    assert man["somber"] == [{"file": "somber/sad.mp3",
                              "attribution": "Music by X (CC BY 4.0)"}]
    assert "_unused" not in man
    assert json.loads((root / "manifest.json").read_text())["tense"][0]["file"] == "tense/dark.mp3"


def _seed_tree(tmp_path):
    root = tmp_path / "music"
    (root / "tense").mkdir(parents=True)
    (root / "tense" / "a.mp3").write_bytes(b"x")
    (root / "tense" / "b.mp3").write_bytes(b"x")
    (root / "tense" / "c.mp3").write_bytes(b"x")
    (root / "somber").mkdir()           # empty mood
    music.build_manifest(str(root))
    return str(root)


def test_pick_track_deterministic_for_same_seed(tmp_path):
    root = _seed_tree(tmp_path)
    a = music.pick_track("tense", "idea-123", root)
    b = music.pick_track("tense", "idea-123", root)
    assert a == b
    assert os.path.isabs(a["path"]) and a["path"].endswith(".mp3")
    assert a["attribution"] == ""


def test_pick_track_rotates_across_seeds(tmp_path):
    root = _seed_tree(tmp_path)
    picks = {os.path.basename(music.pick_track("tense", f"id-{i}", root)["path"])
             for i in range(20)}
    assert len(picks) >= 2     # not all seeds map to one track


def test_pick_track_none_for_empty_or_unknown_mood(tmp_path):
    root = _seed_tree(tmp_path)
    assert music.pick_track("somber", "idea-123", root) is None   # empty folder
    assert music.pick_track("nonsense", "idea-123", root) is None  # unknown mood
    assert music.pick_track("", "idea-123", root) is None


def test_short_music_props_returns_fragment_asset_credit(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    idea = {"id": "idea-123", "mood": "tense"}
    frag, asset, credit = music.short_music_props(idea)
    assert frag["musicVolume"] == music.MUSIC_VOLUME
    assert frag["musicSrc"] == os.path.basename(asset)
    assert asset.endswith(".mp3") and os.path.isabs(asset)
    from engine import config
    assert credit == config.MUSIC_CREDIT_DEFAULT  # CC0 track → default courtesy credit


def test_short_music_props_empty_when_no_mood_track(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    frag, asset, credit = music.short_music_props({"id": "x", "mood": "somber"})  # empty mood
    assert frag == {} and asset is None and credit == ""


def test_write_credit_appends_once_and_writes_sidecar(tmp_path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"description": "A story."}))

    music.write_credit(str(video_dir), str(meta), "Music by X (CC BY 4.0)")
    music.write_credit(str(video_dir), str(meta), "Music by X (CC BY 4.0)")  # idempotent

    desc = json.loads(meta.read_text())["description"]
    assert desc.count("Music: Music by X (CC BY 4.0)") == 1
    assert (video_dir / "music_credit.txt").read_text() == "Music by X (CC BY 4.0)"


def test_write_credit_noop_on_empty(tmp_path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"description": "A story."}))
    music.write_credit(str(video_dir), str(meta), "")
    assert json.loads(meta.read_text())["description"] == "A story."
    assert not (video_dir / "music_credit.txt").exists()


def test_short_music_props_derives_pillar_mood_for_longform(tmp_path, monkeypatch):
    root = _seed_tree(tmp_path)           # 'tense' folder has tracks
    monkeypatch.setattr(music, "MUSIC_DIR", root)
    from engine.video import tts
    monkeypatch.setattr(tts, "mood_for_pillar", lambda p: "tense")
    frag, asset, credit = music.short_music_props({"id": "x", "pillar": "verdict_revisited"})
    assert asset is not None and frag["musicSrc"]
