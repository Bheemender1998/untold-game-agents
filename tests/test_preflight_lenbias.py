import json
import os

from engine.video import preflight

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "lenbias_props_excerpt.json")


def test_lenbias_split_number_is_repaired():
    props = json.load(open(FIXTURE))
    fixed, report = preflight.lint_props(props, fps=props["fps"],
                                         narration_ms=props["narrationMs"])
    texts = [c["text"] for c in fixed["captions"]]
    # the three fragments collapse into one clean money token, no stray ',000'
    assert "$1,000,000." in texts
    assert ",000" not in texts and ",000." not in texts
    # no zero/sub-frame durations survive
    assert all(preflight._frame_index(c["endMs"], props["fps"])
               > preflight._frame_index(c["startMs"], props["fps"])
               for c in fixed["captions"])
    # the merge is recorded in the audit trail and nothing blocks
    assert any(m["type"] == "merge" and m["into"] == "$1,000,000." for m in report["mutations"])
    assert report["blocked"] is False
