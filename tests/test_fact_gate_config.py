import os
from engine import config


def test_factcache_and_shadow_config_present():
    assert config.FACTCACHE_PATH.endswith(".factcache.json")
    assert os.path.isabs(config.FACTCACHE_PATH)
    assert isinstance(config.FACTCACHE_TTL_DAYS, int) and config.FACTCACHE_TTL_DAYS == 30
    assert config.FACT_GATE_SHADOW is True


def test_cache_and_shadow_artifacts_are_gitignored():
    root = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
    gi = open(os.path.join(root, ".gitignore")).read()
    assert ".factcache.json" in gi
    assert ".factgate-shadow.jsonl" in gi
