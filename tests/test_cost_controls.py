from engine import config

def test_model_light_default_is_haiku():
    assert config.MODEL_LIGHT == "claude-haiku-4-5"
