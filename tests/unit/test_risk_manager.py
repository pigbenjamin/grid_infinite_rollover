"""風控模組單元測試"""
import pytest
from core.risk_manager import LeverageLevel, RiskConfig, RiskManager


@pytest.fixture
def risk():
    return RiskManager(RiskConfig(leverage_warn=5.0, leverage_reduce=7.0, leverage_critical=9.0, min_position=2))


def test_safe_leverage(risk):
    assert risk.assess(3.0) == LeverageLevel.SAFE


def test_warn_level(risk):
    assert risk.assess(5.5) == LeverageLevel.WARN


def test_reduce_level(risk):
    assert risk.assess(7.5) == LeverageLevel.REDUCE


def test_critical_level(risk):
    assert risk.assess(9.5) == LeverageLevel.CRITICAL


def test_reduce_qty_reduce_level(risk):
    qty = risk.calc_reduce_qty(8, LeverageLevel.REDUCE)
    assert qty == 2  # 8 // 4 = 2


def test_reduce_qty_critical(risk):
    qty = risk.calc_reduce_qty(8, LeverageLevel.CRITICAL)
    assert qty == 6  # 8 - min_position(2)


def test_min_equity_calculation():
    result = RiskManager.min_equity_for_drawdown(
        max_qty=8, contract_value=1_050_000,
        drawdown_pct=0.15, maint_margin=36_000
    )
    assert result == pytest.approx(8 * 1_050_000 * 0.15 + 8 * 36_000, rel=1e-4)
