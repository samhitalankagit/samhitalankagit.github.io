import pandas as pd

# Load the Trace dataset
df = pd.read_csv("trace_data.csv")

# Convert date column to a real date
df["date"] = pd.to_datetime(df["date"])

# Calculate conversion rate
df["conversion_rate"] = df["conversions"] / df["sessions"]

# Define before and after periods
before = df[df["date"] < "2026-09-15"]
after = df[df["date"] >= "2026-09-15"]

# Overall conversion rates
before_rate = before["conversions"].sum() / before["sessions"].sum()
after_rate = after["conversions"].sum() / after["sessions"].sum()

print("\n=== TRACE INVESTIGATION ===")

print("\nOverall conversion rate:")
print(f"Before: {before_rate:.2%}")
print(f"After:  {after_rate:.2%}")

change = after_rate - before_rate
print(f"Change: {change:.2%}")

# Segment analysis
segment_columns = [
    "platform",
    "customer_type",
    "payment_method"
]

before_segment = (
    before
    .groupby(segment_columns)
    .agg(
        sessions=("sessions", "sum"),
        conversions=("conversions", "sum"),
        payment_failures=("payment_failures", "sum")
    )
)

after_segment = (
    after
    .groupby(segment_columns)
    .agg(
        sessions=("sessions", "sum"),
        conversions=("conversions", "sum"),
        payment_failures=("payment_failures", "sum")
    )
)

before_segment["conversion_rate"] = (
    before_segment["conversions"] / before_segment["sessions"]
)

after_segment["conversion_rate"] = (
    after_segment["conversions"] / after_segment["sessions"]
)

comparison = before_segment[["conversion_rate"]].rename(
    columns={"conversion_rate": "before_rate"}
).join(
    after_segment[["conversion_rate", "payment_failures"]].rename(
        columns={
            "conversion_rate": "after_rate",
            "payment_failures": "after_failures"
        }
    )
)

comparison["rate_change"] = (
    comparison["after_rate"] - comparison["before_rate"]
)
comparison = comparison.sort_values("rate_change")

# Calculate payment failure rates
before_segment["failure_rate"] = (
    before_segment["payment_failures"] / before_segment["sessions"]
)

after_segment["failure_rate"] = (
    after_segment["payment_failures"] / after_segment["sessions"]
)

comparison["before_failure_rate"] = before_segment["failure_rate"]
comparison["after_failure_rate"] = after_segment["failure_rate"]

comparison["failure_rate_change"] = (
    comparison["after_failure_rate"] - comparison["before_failure_rate"]
)

print("\n=== TRACE EVIDENCE ===")

top_segment = comparison.index[0]

print(f"\nLargest affected segment: {top_segment}")
print(f"Conversion rate before: {comparison.iloc[0]['before_rate']:.2%}")
print(f"Conversion rate after:  {comparison.iloc[0]['after_rate']:.2%}")
print(f"Conversion change:     {comparison.iloc[0]['rate_change']:.2%}")

print(f"\nPayment failure rate before: {comparison.iloc[0]['before_failure_rate']:.2%}")
print(f"Payment failure rate after:  {comparison.iloc[0]['after_failure_rate']:.2%}")
print(f"Payment failure change:      {comparison.iloc[0]['failure_rate_change']:.2%}")

print("\nInterpretation:")
print("The segment shows a large conversion decline alongside a large increase in payment failures.")
print("This is evidence of an association, not proof of causation.")