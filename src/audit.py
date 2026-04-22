"""Regression-based compensation equity audit.

Methodology
-----------
This is the standard approach used by comp consulting firms (Mercer, Willis
Towers Watson, Aon) and by large-company comp teams for annual pay equity
review:

1. Build a multivariate regression of log(salary) on *legitimate* drivers:
   level, function, location, tenure, experience, performance, manager status.

2. Extract the residuals — i.e. the portion of pay *not* explained by those
   legitimate drivers.

3. Regress those residuals on the protected class indicators (gender, race).
   Any statistically significant coefficient there is *unexplained* pay
   variation associated with protected class — the thing we care about.

4. Report effect size with confidence interval, and translate into dollar
   remediation cost.

Important caveats (HR/legal):
    - The statistical model does not prove discrimination. It identifies
      unexplained variance that warrants investigation.
    - "Legitimate drivers" is a business / legal judgment, not a data one.
      This module treats level, function, location, tenure, experience,
      performance, and management status as legitimate. If any of *those*
      vary by protected class (e.g. women systematically under-leveled),
      the gap hides inside them — which is a second-order analysis.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.formula.api import ols


@dataclass
class AuditResult:
    gender_gap_pct: float
    gender_gap_ci: tuple[float, float]
    gender_gap_p: float
    gender_n_underpaid: int
    gender_remediation_cost: float

    race_gap_pct: float
    race_gap_ci: tuple[float, float]
    race_gap_p: float

    r_squared: float
    n: int

    residuals: pd.Series


def _fit_log_salary_model(df: pd.DataFrame):
    """Regress log(salary) on legitimate drivers only.

    We use a log transform because comp effects are multiplicative (a 10%
    level premium is 10% whether you're an L2 or an L7). The residuals are
    then in log-dollar units, which translate to approximate percentage pay
    deltas near 0.
    """
    formula = (
        "np.log(salary) ~ C(level) + C(function) + C(location) "
        "+ years_at_company + years_experience + C(performance_rating) "
        "+ is_people_manager"
    )
    model = ols(formula, data=df).fit()
    return model


def run_audit(df: pd.DataFrame) -> AuditResult:
    """Run the full audit on a workforce DataFrame.

    Expects columns:
        salary, gender, race, level, function, location,
        years_at_company, years_experience, performance_rating,
        is_people_manager.
    """
    base_model = _fit_log_salary_model(df)
    df = df.copy()
    df["residual"] = base_model.resid

    # ------------------------------------------------------------------
    # Gender gap (Female vs Male, reference = Male).
    # We filter to binary gender for the headline statistic; non-binary
    # sample sizes are typically too small for stable inference in most
    # workforces and would be reported separately.
    # ------------------------------------------------------------------
    bin_df = df[df["gender"].isin(["Female", "Male"])].copy()
    bin_df["is_female"] = (bin_df["gender"] == "Female").astype(int)
    gender_model = ols("residual ~ is_female", data=bin_df).fit()
    coef = gender_model.params["is_female"]
    ci_low, ci_high = gender_model.conf_int().loc["is_female"].tolist()
    gender_pval = gender_model.pvalues["is_female"]

    # Convert log residual to % (valid small-angle approximation since
    # residuals are already near zero).
    gender_gap_pct = -coef  # negative coef = lower pay → positive "gap"
    gender_ci = (-ci_high, -ci_low)

    # --- URM race gap ---------------------------------------------------
    df["is_urm"] = df["race"].isin(["Black", "Hispanic", "Other/Multi"]).astype(int)
    race_model = ols("residual ~ is_urm", data=df).fit()
    rcoef = race_model.params["is_urm"]
    rci_low, rci_high = race_model.conf_int().loc["is_urm"].tolist()
    race_pval = race_model.pvalues["is_urm"]

    # --- Remediation cost (point estimate) ------------------------------
    # For each Female employee whose residual is below zero, the dollar
    # shortfall is approximately salary * |residual|. Summing gives an
    # upper-bound remediation estimate.
    female_mask = (df["gender"] == "Female") & (df["residual"] < 0)
    n_underpaid = int(female_mask.sum())
    # Log residual → multiplicative: dollar_needed ≈ salary * (exp(-r) - 1)
    dollar_shortfall = df.loc[female_mask, "salary"] * (
        np.exp(-df.loc[female_mask, "residual"]) - 1
    )
    remediation_cost = float(dollar_shortfall.sum())

    return AuditResult(
        gender_gap_pct=float(gender_gap_pct),
        gender_gap_ci=(float(gender_ci[0]), float(gender_ci[1])),
        gender_gap_p=float(gender_pval),
        gender_n_underpaid=n_underpaid,
        gender_remediation_cost=remediation_cost,
        race_gap_pct=float(-rcoef),
        race_gap_ci=(float(-rci_high), float(-rci_low)),
        race_gap_p=float(race_pval),
        r_squared=float(base_model.rsquared),
        n=int(len(df)),
        residuals=df["residual"],
    )


def format_report(result: AuditResult) -> str:
    def pct(x: float) -> str:
        return f"{x * 100:+.2f}%"

    return f"""Compensation Equity Audit — Summary
=====================================

Population: {result.n:,} employees
Legitimate-driver model R² = {result.r_squared:.3f}
(These drivers explain {result.r_squared:.0%} of log-salary variance.)

--- Gender (Female vs Male) ---
  Unexplained gap:        {pct(result.gender_gap_pct)}
  95% CI:                 [{pct(result.gender_gap_ci[0])}, {pct(result.gender_gap_ci[1])}]
  p-value:                {result.gender_gap_p:.4f}
  Employees below parity: {result.gender_n_underpaid}
  Remediation cost:       ${result.gender_remediation_cost:,.0f}

--- Race (URM vs non-URM) ---
  Unexplained gap:        {pct(result.race_gap_pct)}
  95% CI:                 [{pct(result.race_gap_ci[0])}, {pct(result.race_gap_ci[1])}]
  p-value:                {result.race_gap_p:.4f}

Interpretation: A gap outside the 95% CI around zero with p < 0.05 is
evidence of pay variation unexplained by legitimate drivers. It does not
establish discrimination, but it is material enough to warrant a
targeted review by Comp, HRBP, and Legal.
"""


if __name__ == "__main__":
    from src.simulate import simulate_workforce
    df = simulate_workforce()
    result = run_audit(df)
    print(format_report(result))
