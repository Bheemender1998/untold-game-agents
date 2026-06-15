from engine import config

def test_config_has_db_and_cap_knobs():
    assert hasattr(config, "DATABASE_URL")          # None when env unset
    assert isinstance(config.CRON_PER_RUN_CAP_USD, float)
    assert isinstance(config.CRON_MONTHLY_CAP_USD, float)
