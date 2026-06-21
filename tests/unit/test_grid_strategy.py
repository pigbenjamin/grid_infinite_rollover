"""網格策略單元測試"""
import pytest
from datetime import datetime, timedelta
from core.grid_strategy import GridConfig, GridStrategy


@pytest.fixture
def strategy():
    cfg = GridConfig(
        min_position=2, max_position=8,
        tiers=[(4, 1.0), (6, 2.0), (8, 4.0)],
        sell_step_pct=2.0,
        intraday_drop_pct=2.0,
        intraday_cooldown_min=30,
    )
    return GridStrategy(cfg)


def test_buy_step_tier_1(strategy):
    assert strategy.get_buy_step_pct(0) == 1.0
    assert strategy.get_buy_step_pct(3) == 1.0


def test_buy_step_tier_2(strategy):
    assert strategy.get_buy_step_pct(4) == 2.0
    assert strategy.get_buy_step_pct(5) == 2.0


def test_buy_step_tier_3(strategy):
    assert strategy.get_buy_step_pct(6) == 4.0
    assert strategy.get_buy_step_pct(7) == 4.0


def test_buy_step_paused_at_max(strategy):
    assert strategy.get_buy_step_pct(8) is None
    assert strategy.get_buy_step_pct(10) is None


def test_next_buy_price(strategy):
    price = strategy.next_buy_price(21000, 0)
    assert price == 21000 * 0.99


def test_next_sell_price_at_min(strategy):
    assert strategy.next_sell_price(21000, 2) is None


def test_next_sell_price(strategy):
    price = strategy.next_sell_price(21000, 4)
    assert price == 21000 * 1.02


def test_intraday_intercept(strategy):
    now = datetime.now()
    strategy.update_intraday_high(21000)
    assert strategy.should_intercept_intraday(20580, now)
    assert not strategy.should_intercept_intraday(20790, now)


def test_cooldown_blocks_intercept(strategy):
    now = datetime.now()
    strategy.update_intraday_high(21000)
    strategy.trigger_intercept_cooldown(now)
    assert not strategy.should_intercept_intraday(20000, now + timedelta(minutes=10))
    assert strategy.should_intercept_intraday(20000, now + timedelta(minutes=31))
