from engine import config


def test_channel_constants():
    assert config.CHANNEL_NAME == "The Untold Game"
    assert config.CHANNEL_SUBTITLE == "The Archive of Lost Sports History"


def test_description_leads_with_canonical_line():
    assert config.CHANNEL_DESCRIPTION.strip().startswith(
        "The Untold Game — The Archive of Lost Sports History.")
    assert "30-for-30" in config.CHANNEL_DESCRIPTION
    assert "@untoldgamemedia" in config.CHANNEL_DESCRIPTION


def test_canonical_tagline_in_agent_context():
    assert "The Archive of Lost Sports History" in config.CHANNEL_CONTEXT


def test_channel_yaml_carries_canonical_tagline():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
    text = open(os.path.join(root, "engine", "profiles", "channel.yaml")).read()
    assert "The Archive of Lost Sports History" in text
