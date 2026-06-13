import subprocess, sys


def test_fix_flag_is_gone():
    # argparse should reject --fix now that auto-correct is removed.
    r = subprocess.run([sys.executable, "-m", "engine.run_factcheck", "--id", "x", "--fix"],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "unrecognized arguments: --fix" in r.stderr
