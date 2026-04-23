"""Tests for the compensation equity audit."""
from __future__ import annotations

from src.audit import run_audit
from src.simulate import GapConfig, simulate_workforce


def test_simulator_is_deterministic():
    df1 = simulate_workforce(seed=42)
    df2 = simulate_workforce(seed=42)
    assert df1.equals(df2)


def test_audit_recovers_injected_gender_gap():
    df = simulate_workforce(gap=GapConfig(gender_gap_pct=0.05, race_gap_pct=0.03))
    result = run_audit(df)
    # Should recover the injected 5 % gap within ±1 pp.
    assert 0.04 < result.gender_gap_pct < 0.06
    assert result.gender_gap_p < 0.01


def test_audit_null_effect_check():
    """With zero injected gap the audit should not detect significance."""
    df = simulate_workforce(
        gap=GapConfig(gender_gap_pct=0.0, race_gap_pct=0.0), seed=99
    )
    result = run_audit(df)
    assert abs(result.gender_gap_pct) < 0.015
    # Typically p > 0.05 in the null case, but we use a looser bound to
    # avoid flakiness from the finite random sample.
    assert result.gender_gap_p > 0.10


def test_r_squared_is_high():
    """The legitimate-driver model should explain most of log-salary variance."""
    df = simulate_workforce()
    result = run_audit(df)
    assert result.r_squared > 0.90


def test_remediation_cost_nonnegative():
    df = simulate_workforce(gap=GapConfig(gender_gap_pct=0.05, race_gap_pct=0.03))
    result = run_audit(df)
    assert result.gender_remediation_cost >= 0
    assert result.gender_n_underpaid >= 0
