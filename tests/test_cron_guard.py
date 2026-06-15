from engine import config

def test_config_has_db_and_cap_knobs():
    assert hasattr(config, "DATABASE_URL")          # None when env unset
    assert isinstance(config.CRON_PER_RUN_CAP_USD, float)
    assert isinstance(config.CRON_MONTHLY_CAP_USD, float)


from engine import cron_guard

def test_should_skip_when_month_over_cap():
    assert cron_guard.should_skip_monthly(spent=16.0, cap=15.0) is True
    assert cron_guard.should_skip_monthly(spent=10.0, cap=15.0) is False

def test_over_run_cap():
    assert cron_guard.over_run_cap(run_spent=2.5, cap=2.0) is True
    assert cron_guard.over_run_cap(run_spent=1.0, cap=2.0) is False
