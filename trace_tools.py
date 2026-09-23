import pandas as pd


def load_data(file_path):
    """Load the Trace dataset."""
    df = pd.read_csv(file_path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def calculate_signal(df, cutoff_date="2026-09-15"):
    """Calculate the overall conversion change."""

    before = df[df["date"] < cutoff_date]
    after = df[df["date"] >= cutoff_date]

    before_rate = (
        before["conversions"].sum()
        / before["sessions"].sum()
    )

    after_rate = (
        after["conversions"].sum()
        / after["sessions"].sum()
    )

    return {
        "before_conversion_rate": before_rate,
        "after_conversion_rate": after_rate,
        "conversion_change": after_rate - before_rate
    }


def find_top_segment(df, cutoff_date="2026-09-15"):
    """Find the segment with the largest conversion decline."""

    before = df[df["date"] < cutoff_date]
    after = df[df["date"] >= cutoff_date]

    dimensions = [
        "platform",
        "customer_type",
        "payment_method"
    ]

    before_segment = (
        before
        .groupby(dimensions)
        .agg(
            sessions=("sessions", "sum"),
            conversions=("conversions", "sum"),
            payment_failures=("payment_failures", "sum")
        )
    )

    after_segment = (
        after
        .groupby(dimensions)
        .agg(
            sessions=("sessions", "sum"),
            conversions=("conversions", "sum"),
            payment_failures=("payment_failures", "sum")
        )
    )

    before_segment["conversion_rate"] = (
        before_segment["conversions"]
        / before_segment["sessions"]
    )

    after_segment["conversion_rate"] = (
        after_segment["conversions"]
        / after_segment["sessions"]
    )

    before_segment["failure_rate"] = (
        before_segment["payment_failures"]
        / before_segment["sessions"]
    )

    after_segment["failure_rate"] = (
        after_segment["payment_failures"]
        / after_segment["sessions"]
    )

    comparison = before_segment[
        ["conversion_rate", "failure_rate"]
    ].rename(
        columns={
            "conversion_rate": "before_rate",
            "failure_rate": "before_failure_rate"
        }
    ).join(
        after_segment[
            ["conversion_rate", "failure_rate"]
        ].rename(
            columns={
                "conversion_rate": "after_rate",
                "failure_rate": "after_failure_rate"
            }
        )
    )

    comparison["conversion_change"] = (
        comparison["after_rate"]
        - comparison["before_rate"]
    )

    comparison["failure_rate_change"] = (
        comparison["after_failure_rate"]
        - comparison["before_failure_rate"]
    )

    comparison = comparison.sort_values(
        "conversion_change"
    )

    top = comparison.iloc[0]
    segment = comparison.index[0]

    return {
        "platform": segment[0],
        "customer_type": segment[1],
        "payment_method": segment[2],
        "before_conversion_rate": top["before_rate"],
        "after_conversion_rate": top["after_rate"],
        "conversion_change": top["conversion_change"],
        "before_failure_rate": top["before_failure_rate"],
        "after_failure_rate": top["after_failure_rate"],
        "failure_rate_change": top["failure_rate_change"]
    }


def investigate_by_country(
    df,
    platform,
    customer_type,
    payment_method,
    cutoff_date="2026-09-15"
):
    """Investigate the selected segment by country."""

    before = df[
        (df["date"] < cutoff_date)
        & (df["platform"] == platform)
        & (df["customer_type"] == customer_type)
        & (df["payment_method"] == payment_method)
    ]

    after = df[
        (df["date"] >= cutoff_date)
        & (df["platform"] == platform)
        & (df["customer_type"] == customer_type)
        & (df["payment_method"] == payment_method)
    ]

    before_country = (
        before
        .groupby(["country"])
        .agg(
            sessions=("sessions", "sum"),
            conversions=("conversions", "sum"),
            payment_failures=("payment_failures", "sum")
        )
    )

    after_country = (
        after
        .groupby(["country"])
        .agg(
            sessions=("sessions", "sum"),
            conversions=("conversions", "sum"),
            payment_failures=("payment_failures", "sum")
        )
    )

    before_country["conversion_rate"] = (
        before_country["conversions"]
        / before_country["sessions"]
    )

    after_country["conversion_rate"] = (
        after_country["conversions"]
        / after_country["sessions"]
    )

    before_country["failure_rate"] = (
        before_country["payment_failures"]
        / before_country["sessions"]
    )

    after_country["failure_rate"] = (
        after_country["payment_failures"]
        / after_country["sessions"]
    )

    comparison = before_country[
        ["conversion_rate", "failure_rate"]
    ].rename(
        columns={
            "conversion_rate": "before_rate",
            "failure_rate": "before_failure_rate"
        }
    ).join(
        after_country[
            ["conversion_rate", "failure_rate"]
        ].rename(
            columns={
                "conversion_rate": "after_rate",
                "failure_rate": "after_failure_rate"
            }
        ),
        how="outer"
    )

    comparison["conversion_change"] = (
        comparison["after_rate"]
        - comparison["before_rate"]
    )

    comparison["failure_rate_change"] = (
        comparison["after_failure_rate"]
        - comparison["before_failure_rate"]
    )

    return comparison.sort_values("conversion_change")


def investigate_over_time(
    df,
    platform,
    customer_type,
    payment_method
):
    """Investigate the selected segment over time."""

    segment = df[
        (df["platform"] == platform)
        & (df["customer_type"] == customer_type)
        & (df["payment_method"] == payment_method)
    ]

    daily = (
        segment
        .groupby("date")
        .agg(
            sessions=("sessions", "sum"),
            conversions=("conversions", "sum"),
            payment_failures=("payment_failures", "sum")
        )
    )

    daily["conversion_rate"] = (
        daily["conversions"]
        / daily["sessions"]
    )

    daily["failure_rate"] = (
        daily["payment_failures"]
        / daily["sessions"]
    )

    return daily.sort_index()