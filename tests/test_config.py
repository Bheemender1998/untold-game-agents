from engine import config


def test_brand_constants():
    assert config.CHANNEL_HANDLE == "@untoldgamemedia"
    assert config.MUSIC_CREDIT_DEFAULT  # non-empty courtesy credit
