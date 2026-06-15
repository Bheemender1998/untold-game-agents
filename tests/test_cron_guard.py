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


from engine import run_cron

def test_cron_skips_when_monthly_cap_exceeded(monkeypatch):
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: 99.0)
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 15.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 0 and ran == []          # skipped cleanly, no agents ran

def test_cron_runs_all_four_when_under_caps(monkeypatch):
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: 0.0)
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 15.0)
    monkeypatch.setattr(run_cron.config, "CRON_PER_RUN_CAP_USD", 2.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 0 and ran == [1, 2, 3, 4]

def test_cron_stops_remaining_agents_when_per_run_cap_hit(monkeypatch):
    # spend grows past the per-run cap right after the first agent
    seq = iter([0.0, 5.0, 5.0, 5.0, 5.0])      # before-run, then after each agent
    monkeypatch.setattr(run_cron.cron_guard, "monthly_spent_usd", lambda: next(seq))
    monkeypatch.setattr(run_cron.config, "CRON_MONTHLY_CAP_USD", 100.0)
    monkeypatch.setattr(run_cron.config, "CRON_PER_RUN_CAP_USD", 2.0)
    ran = []
    monkeypatch.setattr(run_cron, "run_single_agent", lambda n: ran.append(n))
    rc = run_cron.main()
    assert rc == 2 and ran == [1]              # stopped after the first agent
