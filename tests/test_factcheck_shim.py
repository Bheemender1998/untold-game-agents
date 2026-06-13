import engine.pipeline.factcheck as fc
from engine.pipeline import fact_gate


def test_shim_reexports_factcheck():
    assert fc.factcheck is fact_gate.factcheck


def test_shim_drops_correct_script():
    assert not hasattr(fc, "correct_script")   # auto-correct removed (human-only)
