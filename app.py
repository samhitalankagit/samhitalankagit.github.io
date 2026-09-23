
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Trace AI",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 Trace AI")
st.subheader("Evidence-Backed Data Investigation")

st.markdown(
    "Trace helps teams move from a business signal to evidence, "
    "a testable hypothesis, and the next investigation."
)

st.divider()

st.markdown("### Investigation")

uploaded_file = st.file_uploader(
    "Upload a CSV dataset",
    type=["csv"]
)

if uploaded_file is not None:

    # -----------------------------
    # LOAD DATA
    # -----------------------------

    df = pd.read_csv(uploaded_file)

    st.success(f"Dataset loaded: {len(df):,} rows")

    st.markdown("#### Data preview")
    st.dataframe(
        df.head(10),
        use_container_width=True
    )

    # -----------------------------
    # PREPARE DATA
    # -----------------------------

    df["date"] = pd.to_datetime(df["date"])

    before = df[df["date"] < "2026-09-15"]
    after = df[df["date"] >= "2026-09-15"]

    # -----------------------------
    # SIGNAL
    # -----------------------------

    before_rate = (
        before["conversions"].sum()
        / before["sessions"].sum()
    )

    after_rate = (
        after["conversions"].sum()
        / after["sessions"].sum()
    )

    rate_change = after_rate - before_rate

    st.divider()

    st.markdown("### 📉 Signal")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Before",
        f"{before_rate:.2%}"
    )

    col2.metric(
        "After",
        f"{after_rate:.2%}"
    )

    col3.metric(
        "Change",
        f"{rate_change:.2%}"
    )

    # -----------------------------
    # EVIDENCE
    # -----------------------------

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

    comparison["rate_change"] = (
        comparison["after_rate"]
        - comparison["before_rate"]
    )

    comparison["failure_rate_change"] = (
        comparison["after_failure_rate"]
        - comparison["before_failure_rate"]
    )

    comparison = comparison.sort_values(
        "rate_change"
    )

    top = comparison.iloc[0]
    top_segment = comparison.index[0]

    st.divider()

    st.markdown("### 🔎 Evidence")

    st.markdown(
        f"**Largest affected segment:** "
        f"{top_segment[0]} + "
        f"{top_segment[1]} + "
        f"{top_segment[2]}"
    )

    col1, col2 = st.columns(2)

    col1.metric(
        "Conversion change",
        f"{top['rate_change']:.2%}"
    )

    col2.metric(
        "Payment failure change",
        f"{top['failure_rate_change']:.2%}"
    )

    st.caption(
        "Evidence shows an association between the conversion decline "
        "and increased payment failures. This does not establish causation."
    )

    # -----------------------------
    # HYPOTHESIS
    # -----------------------------

    st.divider()

    st.markdown("### 💡 Hypothesis")

    st.info(
        f"Payment failures may be contributing to the conversion decline "
        f"within the {top_segment[0]} + {top_segment[1]} + "
        f"{top_segment[2]} segment."
    )

    st.markdown("**What we know**")

    st.write(
        f"Conversion changed by {top['rate_change']:.2%}, "
        f"while payment failure rate changed by "
        f"{top['failure_rate_change']:.2%}."
    )

    st.markdown("**What we do not know**")

    st.write(
        "The evidence does not establish that payment failures "
        "caused the conversion decline."
    )

    # -----------------------------
    # NEXT INVESTIGATION
    # -----------------------------

    st.divider()

    st.markdown("### ➡️ Next Investigation")

    st.warning(
        f"Investigate payment failures for "
        f"{top_segment[0]} + {top_segment[1]} + "
        f"{top_segment[2]} after September 15."
    )

    st.markdown(
        "The next step is to determine whether the increase in "
        "payment failures is associated with a specific payment "
        "failure pattern, country, or date."
    )

st.divider()

st.markdown(
    "#### Signal → Evidence → Hypothesis → Next Investigation"
)