"""Simulate a realistic workforce with a known, injected pay gap.

Why simulate (rather than use public data)?
    Real workforce compensation data is almost never public — and the public
    datasets that do exist (e.g. federal payroll) lack the demographic
    granularity needed to demonstrate a pay equity audit.

    Simulating with an injected gap has a key advantage for a demo: we
    *know* the ground truth. The equity audit's job is to recover a ~5%
    unexplained gap even after controlling for legitimate factors (level,
    tenure, performance, function). If the audit methodology is sound, the
    recovered residual gap will match the injected one within noise.

    All relationships (market slopes on tenure, level bumps, perf multipliers)
    are calibrated to mid-2020s U.S. professional services / tech comp bands.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)


@dataclass
class GapConfig:
    """Parameters for the injected demographic pay gap.

    Attributes
    ----------
    gender_gap_pct : Multiplicative discount applied to Female employees' pay.
        0.05 means Female pay is multiplied by 0.95 → a 5% unexplained gap.
    race_gap_pct : Same idea, applied to URM employees. Kept smaller in the
        default so the audit can recover two different effect sizes.
    """

    gender_gap_pct: float = 0.05
    race_gap_pct: float = 0.03


def simulate_workforce(
    n: int = 2500,
    gap: Optional[GapConfig] = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Return a synthetic workforce dataset with columns ready for audit.

    Columns:
        employee_id, gender, race, level (1-7), function, location,
        years_experience, years_at_company, performance_rating (1-5),
        is_people_manager, salary (USD), bonus, total_comp
    """
    rng = np.random.default_rng(seed)
    gap = gap or GapConfig()
    n = int(n)

    # Demographics -------------------------------------------------------------
    gender = rng.choice(["Female", "Male", "Non-binary"], size=n, p=[0.42, 0.56, 0.02])
    race = rng.choice(
        ["White", "Asian", "Black", "Hispanic", "Other/Multi"],
        size=n,
        p=[0.55, 0.20, 0.10, 0.12, 0.03],
    )
    urm = np.isin(race, ["Black", "Hispanic", "Other/Multi"])

    # Org structure ------------------------------------------------------------
    level = rng.integers(1, 8, size=n)  # 1 = IC1, 7 = Director+
    function = rng.choice(
        ["Engineering", "Product", "Sales", "Marketing", "Operations", "HR", "Finance"],
        size=n,
        p=[0.30, 0.10, 0.20, 0.10, 0.15, 0.05, 0.10],
    )
    location = rng.choice(
        ["SF", "NY", "Seattle", "Austin", "Denver", "Remote"],
        size=n,
        p=[0.15, 0.20, 0.15, 0.10, 0.10, 0.30],
    )
    is_manager = ((level >= 5) & (rng.random(n) < 0.55)).astype(int)

    # Tenure / experience ------------------------------------------------------
    years_experience = np.clip(rng.normal(level * 2.5 + 3, 2.5, size=n), 0, 30)
    years_at_company = np.clip(
        rng.beta(1.5, 3.0, size=n) * (years_experience + 1), 0, 15
    )
    performance_rating = np.clip(rng.normal(3.2, 0.7, size=n), 1, 5).round()

    # ------------------------------------------------------------------------
    # "True" salary model — legitimate drivers only.
    # Calibration: an L4 (mid-senior IC) in SF with 7 yrs exp, rating 3,
    # should land in the $150-175K base range, which roughly matches 2024
    # Radford / Levels.fyi / BLS SOC 15-2051 tech IC comp bands.
    # ------------------------------------------------------------------------
    base_by_level = {1: 65, 2: 85, 3: 105, 4: 130, 5: 165, 6: 210, 7: 275}  # $K
    base = np.array([base_by_level[int(lv)] for lv in level])

    location_mult = {
        "SF": 1.15,
        "NY": 1.15,
        "Seattle": 1.10,
        "Austin": 1.00,
        "Denver": 0.95,
        "Remote": 0.98,
    }
    loc_adj = np.array([location_mult[l] for l in location])

    function_mult = {
        "Engineering": 1.10,
        "Product": 1.08,
        "Sales": 1.05,  # sans commission, kept simple
        "Marketing": 1.00,
        "Operations": 0.95,
        "HR": 0.95,
        "Finance": 1.05,
    }
    func_adj = np.array([function_mult[f] for f in function])

    # Performance multiplier: 1.0 baseline at rating=3, ~±8% swing for 2 or 5.
    perf_adj = 0.92 + 0.04 * performance_rating

    # Tenure and experience: smaller effects than level, but present.
    tenure_adj = 1 + 0.01 * years_at_company
    exp_adj = 1 + 0.005 * (years_experience - level * 2)
    mgr_adj = 1 + 0.05 * is_manager

    noise = rng.normal(1.0, 0.04, size=n)

    true_salary_thousands = (
        base * loc_adj * func_adj * perf_adj * tenure_adj * exp_adj * mgr_adj * noise
    )

    # ------------------------------------------------------------------------
    # Injected demographic gap — what we want the audit to recover.
    # ------------------------------------------------------------------------
    gap_mult = np.ones(n)
    gap_mult[gender == "Female"] *= 1 - gap.gender_gap_pct
    gap_mult[urm] *= 1 - gap.race_gap_pct
    salary = true_salary_thousands * gap_mult * 1000  # back to $

    bonus_pct = 0.05 + 0.03 * (level - 1) + 0.02 * (performance_rating - 3)
    bonus = salary * np.clip(bonus_pct, 0, 0.5)
    total_comp = salary + bonus

    df = pd.DataFrame(
        {
            "employee_id": np.arange(1, n + 1),
            "gender": gender,
            "race": race,
            "level": level,
            "function": function,
            "location": location,
            "years_experience": years_experience.round(1),
            "years_at_company": years_at_company.round(1),
            "performance_rating": performance_rating.astype(int),
            "is_people_manager": is_manager,
            "salary": salary.round(0).astype(int),
            "bonus": bonus.round(0).astype(int),
            "total_comp": total_comp.round(0).astype(int),
        }
    )
    return df


if __name__ == "__main__":
    df = simulate_workforce()
    print(df.head())
    print(f"\nn = {len(df)}")
    print(f"Raw gender gap (Female vs Male median salary): "
          f"{1 - df.groupby('gender')['salary'].median()['Female'] / df.groupby('gender')['salary'].median()['Male']:.1%}")
