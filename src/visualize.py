"""Generate all README visualizations for the compensation equity audit."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.simulate import simulate_workforce
from src.audit import run_audit

DOCS = Path(__file__).resolve().parents[1] / "docs"
DOCS.mkdir(exist_ok=True)

plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 160, "font.size": 11})


def plot_raw_vs_adjusted_gap(df: pd.DataFrame, result) -> None:
    """Show the 'before vs after' story: raw median gap → adjusted gap."""
    by_gender = df[df["gender"].isin(["Female", "Male"])].groupby("gender")["salary"].median()
    raw_gap = 1 - by_gender["Female"] / by_gender["Male"]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = ["Raw median gap\n(unadjusted)", "Adjusted gap\n(after legitimate controls)"]
    y = [raw_gap * 100, result.gender_gap_pct * 100]
    colors = ["#e74c3c", "#8e44ad"]

    bars = ax.bar(x, y, color=colors, width=0.55)
    ax.set_ylabel("Pay gap (%)")
    ax.set_title(
        "Gender pay gap: before and after controlling for legitimate drivers",
        fontweight="bold",
    )
    ax.axhline(0, color="k", lw=0.8)
    ax.grid(axis="y", alpha=0.3)

    for bar, val in zip(bars, y):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15,
            f"{val:.1f}%",
            ha="center",
            fontweight="bold",
            fontsize=13,
        )

    ax.text(
        0.02,
        -0.15,
        "Controls: level, function, location, tenure, experience, "
        "performance rating, manager status.",
        transform=ax.transAxes,
        fontsize=9,
        color="gray",
    )
    fig.tight_layout()
    fig.savefig(DOCS / "raw_vs_adjusted_gap.png", bbox_inches="tight")
    plt.close(fig)


def plot_residual_distribution(df: pd.DataFrame, result) -> None:
    """KDE of model residuals by gender — the visual 'smoking gun'."""
    df = df.copy()
    df["residual_pct"] = result.residuals * 100  # ~percentage off predicted

    fig, ax = plt.subplots(figsize=(10, 5))
    for g, color in zip(["Male", "Female"], ["#2c7fb8", "#d35400"]):
        sub = df[df["gender"] == g]["residual_pct"]
        sns.kdeplot(sub, ax=ax, label=f"{g} (n={len(sub)})", color=color, lw=2, fill=True, alpha=0.25)

    ax.axvline(0, color="k", ls="--", lw=0.8, alpha=0.5, label="Model prediction (no gap)")
    ax.set_xlabel("Residual (% of predicted salary)  ← underpaid | overpaid →")
    ax.set_ylabel("Density")
    ax.set_title(
        "Pay residuals by gender — the unexplained variance that matters",
        fontweight="bold",
    )
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(DOCS / "residual_distribution.png", bbox_inches="tight")
    plt.close(fig)


def plot_gap_by_level(df: pd.DataFrame, result) -> None:
    """Where in the org is the gap concentrated?"""
    df = df.copy()
    df["residual"] = result.residuals
    by_level = (
        df[df["gender"].isin(["Female", "Male"])]
        .groupby(["level", "gender"])["residual"]
        .mean()
        .unstack()
    )
    gap_by_level = (by_level["Male"] - by_level["Female"]) * 100

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(gap_by_level.index, gap_by_level.values, color="#8e44ad")
    ax.set_xlabel("Level")
    ax.set_ylabel("Unexplained gap (Male − Female, %)")
    ax.set_title("Unexplained pay gap by level", fontweight="bold")
    ax.axhline(0, color="k", lw=0.8)
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, gap_by_level.values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.15 if val >= 0 else bar.get_height() - 0.35,
            f"{val:.1f}%",
            ha="center",
            fontweight="bold",
            fontsize=10,
        )
    fig.tight_layout()
    fig.savefig(DOCS / "gap_by_level.png", bbox_inches="tight")
    plt.close(fig)


def run() -> None:
    df = simulate_workforce()
    result = run_audit(df)

    plot_raw_vs_adjusted_gap(df, result)
    plot_residual_distribution(df, result)
    plot_gap_by_level(df, result)
    print(f"Figures saved to {DOCS}/")


if __name__ == "__main__":
    run()
