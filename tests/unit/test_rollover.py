"""換倉模組單元測試"""
import pytest
from broker.paper_broker import PaperBroker
from core.rollover import RolloverManager


def test_rollover_not_triggered():
    broker = PaperBroker()
    mgr = RolloverManager(broker, ":memory:", multiplier=50, dte_threshold=5)
    result = mgr.check_and_rollover("MXTF202506", "MXTF202509", dte=10)
    assert result is False


def test_rollover_triggered_no_position():
    broker = PaperBroker()
    mgr = RolloverManager(broker, ":memory:", multiplier=50, dte_threshold=5)
    result = mgr.check_and_rollover("MXTF202506", "MXTF202509", dte=3)
    assert result is False
