import pytest

from core.budget.budget_guard import BudgetExceededError, BudgetGuard


def test_check_passes_under_limit():
    guard = BudgetGuard()
    guard.limit = 10.0
    guard.check(estimated_cost=0.50)  # should not raise


def test_check_raises_over_limit():
    guard = BudgetGuard()
    guard.limit = 1.0
    guard.record(actual_cost=0.95)
    with pytest.raises(BudgetExceededError):
        guard.check(estimated_cost=0.10)


def test_record_accumulates():
    guard = BudgetGuard()
    guard.limit = 10.0
    guard.record(0.10)
    guard.record(0.20)
    assert abs(guard._hourly_spend() - 0.30) < 0.001
