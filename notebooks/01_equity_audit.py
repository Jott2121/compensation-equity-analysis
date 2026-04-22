# %% [markdown]
# # Compensation Equity Audit — Full Walkthrough
#
# This notebook demonstrates a standard regression-based pay equity audit —
# the methodology used by major comp consulting firms and by most large-
# employer comp teams for annual pay reviews.
#
# **The question we're answering:** after controlling for every *legitimate*
# driver of pay (level, function, location, tenure, experience, performance,
# management status), is there residual variation in pay associated with
# gender or race?
#
# **The methodology:**
# 1. Model log(salary) as a function of legitimate drivers only.
# 2. Extract residuals — the portion of pay *not* explained by those drivers.
# 3. Test whether those residuals differ systematically by gender/race.
# 4. Translate any detected gap into a dollar remediation estimate.

# %%
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.simulate import simulate_workforce, GapConfig
from src.audit import run_audit, format_report

sns.set_style("whitegrid")

# %% [markdown]
# ## 1. Generate a realistic workforce with a *known* injected gap
#
# Real comp data isn't public, and public pay datasets lack the granularity
# needed for an audit. Simulation has a key advantage for a demo: we know the
# ground truth. If the methodology is sound, it should *recover* the injected
# 5% gender gap within confidence intervals.

# %%
df = simulate_workforce(n=2500, gap=GapConfig(gender_gap_pct=0.05, race_gap_pct=0.03))
print(df.head())
print(f"\nPopulation: {len(df):,}")
print(f"Gender mix: {df['gender'].value_counts(normalize=True).round(2).to_dict()}")
print(f"Race mix: {df['race'].value_counts(normalize=True).round(2).to_dict()}")

# %% [markdown]
# ## 2. Naive view: raw median pay gap
#
# This is the number that shows up in headlines: *"women are paid X% less
# than men."* It's true, but it's not the whole story — it doesn't account
# for role mix, level mix, tenure, or any other legitimate driver.

# %%
by_gender = df[df["gender"].isin(["Female", "Male"])].groupby("gender")["salary"].median()
raw_gap = 1 - by_gender["Female"] / by_gender["Male"]
print(f"Raw median pay gap (Female vs Male): {raw_gap:.1%}")

# %% [markdown]
# ## 3. The adjusted view: regression-based audit
#
# We run the full audit: log(salary) ~ legitimate drivers → residuals →
# regress residuals on gender.

# %%
result = run_audit(df)
print(format_report(result))

# %% [markdown]
# ## 4. Interpreting the results
#
# The audit recovered the injected ~5% gender gap with a tight 95% confidence
# interval. The R² of the legitimate-driver model is ~0.99, meaning those
# controls explain nearly all the variance in log-salary — which is what we
# want. Any remaining gap associated with gender is, by construction, *not*
# attributable to those drivers.
#
# **Translation to dollars:** the audit estimates roughly $6.5M in
# remediation to close the identified gap at the individual employee level.
# That's the *upper bound* — in practice comp teams apply floors and prioritize
# the largest-gap employees first.

# %% [markdown]
# ## 5. Where in the org does the gap concentrate?
#
# The headline number hides important heterogeneity. Some levels, functions,
# or locations may have much larger gaps than others.

# %%
df_plot = df.copy()
df_plot["residual"] = result.residuals
by_level = (
    df_plot[df_plot["gender"].isin(["Female", "Male"])]
    .groupby(["level", "gender"])["residual"]
    .mean()
    .unstack()
)
gap_by_level = (by_level["Male"] - by_level["Female"]) * 100
print("Unexplained gap by level (percentage points):")
print(gap_by_level.round(2))

# %% [markdown]
# ## 6. Operational output: employee-level shortfall table
#
# The ultimate deliverable of a pay equity audit is the individual-level
# remediation list. For each underpaid Female employee, we estimate the
# dollar shortfall needed to bring them to model-predicted pay.

# %%
df_out = df.copy()
df_out["residual"] = result.residuals
underpaid = (
    df_out[(df_out["gender"] == "Female") & (df_out["residual"] < -0.02)]
    .assign(
        predicted_salary=lambda d: d["salary"] * np.exp(-d["residual"]),
        shortfall=lambda d: d["predicted_salary"] - d["salary"],
    )
    .sort_values("shortfall", ascending=False)
    .head(15)
)
print("Top 15 largest shortfalls (Female employees, >2% below predicted):")
print(
    underpaid[
        [
            "employee_id",
            "level",
            "function",
            "location",
            "performance_rating",
            "salary",
            "predicted_salary",
            "shortfall",
        ]
    ].round(0).to_string(index=False)
)

# %% [markdown]
# ## 7. What HR actually does with this
#
# | Phase | Action |
# |---|---|
# | **Methodology review** | Comp team + Legal validate the choice of "legitimate" controls. Example: is "level" itself free of bias? If women are systematically under-leveled, some gap hides there. |
# | **Individual review** | Top-shortfall employees get case-by-case review: manager input, market comparables, role history. |
# | **Remediation** | Pay adjustments, typically at the next comp cycle but sometimes immediately for largest gaps. Budget is capped; prioritize by shortfall size and retention risk. |
# | **Structural fix** | If a systematic driver is found (e.g. hiring-in below band for one demographic), the comp process itself changes. |
# | **Governance** | Annual re-audit, disclosed to leadership. Trend matters more than any single year. |

# %% [markdown]
# ## 8. Caveats a serious reviewer will raise
#
# 1. **"Legitimate drivers" is a judgment call.** Using level as a control
#    masks discrimination that manifests through leveling. A complete audit
#    also looks at *promotion velocity* and *leveling-in decisions* by
#    demographic group — the second-order audit.
#
# 2. **Small subgroup sizes.** With n=2,500 we can say something about the
#    overall Female/Male gap; we cannot reliably detect a Black Women gap if
#    there are only ~60 Black women in the sample (the CIs would be too
#    wide). Those analyses need larger populations or sector benchmarks.
#
# 3. **Correlation vs causation.** A statistically significant gap is
#    evidence of *something* — not automatically evidence of discrimination.
#    It could be unmeasured confounders (market pay differences, tenure
#    structure, etc). The audit's job is to surface it for investigation.
#
# 4. **The remediation estimate is an upper bound.** In practice comp
#    remediation applies thresholds (e.g. only gaps > 2%) and phased
#    budgets. The $6.5M figure is the naive "close every shortfall
#    completely" number.
