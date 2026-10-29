from __future__ import annotations
import json, os, re
from datetime import datetime
import pandas as pd
import streamlit as st
from bidlens_engine import (
    SUPPLIERS, DEFAULT_FX, init_db, read_state, write_state, get_data,
    calculate_supplier_summary, optimize_allocation, deterministic_answer,
    refine_requirement_with_llm, interpret_question, answer_procurement_question,
    llm_enabled,
)

st.set_page_config(page_title="BidLens", page_icon="📦", layout="wide", initial_sidebar_state="expanded")
init_db()
items, quotes, source_meta = get_data()
request = read_state("request_json", {}) or {}

st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 1.4rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {border: 1px solid #e7ebf0; border-radius: 10px; padding: .65rem .8rem;}
.bid-subtle {color:#667085;font-size:.9rem;}
section[data-testid="stSidebar"] {min-width: 230px; max-width: 230px;}
</style>
""", unsafe_allow_html=True)

st.title("BidLens")
st.caption("A simple sourcing assistant")

pages = ["1 · Refine requirement", "2 · Missing information", "3 · Supplier comparison & chat"]
page = st.sidebar.radio("", pages, label_visibility="collapsed")
with st.sidebar.expander("AI connection", expanded=False):
    st.caption("Optional: connect Gemini for more natural responses. Data-based checks and calculations work without it.")
    key_input = st.text_input("Gemini API key", type="password", key="gemini_key_input")
    if key_input.strip():
        os.environ["GEMINI_API_KEY"] = key_input.strip()
    if llm_enabled():
        st.caption("API key present for this session.")
    else:
        st.caption("Not connected. Basic analysis remains available.")


def rule_based_refinement(text: str) -> dict:
    low = text.lower()
    suggestions = []
    if not re.search(r"\b\d[\d,]*\b", text):
        suggestions.append("Add quantities for each item or product group.")
    if not any(w in low for w in ["delivery", "deliver", "days", "date", "lead time"]):
        suggestions.append("Specify the delivery location and required date or lead time.")
    if not any(w in low for w in ["freight", "shipping", "tax", "gst", "charges"]):
        suggestions.append("Ask suppliers to state freight, taxes and any additional charges.")
    if not any(w in low for w in ["currency", "inr", "usd", "price basis", "per unit", "per item", "per 100"]):
        suggestions.append("Require the quoted currency and price basis (for example, per item or per 100 items).")
    if not any(w in low for w in ["specification", "dimension", "material", "quality", "standard"]):
        suggestions.append("Add measurable product specifications and acceptable quality standards.")
    refined = text.strip()
    if refined and suggestions:
        refined += "\n\nPlease also confirm:\n" + "\n".join(f"- {s}" for s in suggestions)
    return {"mode": "Requirement review", "summary": "Here is a clearer draft with the main open details called out.", "gaps": suggestions, "questions": [], "structured_requirement": {}, "refined_text": refined}


def get_refinement(text: str) -> dict:
    if not text.strip():
        return {"mode": "Requirement review", "summary": "Enter a short description of what you need to source.", "gaps": [], "questions": [], "refined_text": ""}
    try:
        result = refine_requirement_with_llm(text)
        if not result.get("refined_text"):
            # Keep a concise editable draft even if the model only returns structured suggestions.
            base = text.strip()
            additions = result.get("gaps", [])
            if additions:
                base += "\n\nPlease clarify:\n" + "\n".join(f"- {x}" for x in additions)
            result["refined_text"] = base
        return result
    except Exception:
        # The page still works if the provider/model is unavailable.
        return rule_based_refinement(text)


def quote_gaps(q: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, g in q.groupby(["supplier_id", "supplier"], sort=True):
        missing = int(g.quoted_price.isna().sum())
        ambiguous_mask = g.issue.fillna("").str.contains("ambiguous", case=False) & ~g.reviewed.fillna(False)
        delivery_gaps = int(g.delivery_days.isna().sum())
        freight_gaps = int(g.delivery_charge.isna().sum())
        tax = str(g.tax_status.dropna().iloc[0]) if "tax_status" in g and g.tax_status.notna().any() else "Not stated"
        open_issues = int((g.quoted_price.isna() | ambiguous_mask | g.issue.fillna("").str.contains("not specified|unconfirmed|requires", case=False)).sum())
        rows.append({"Supplier": g.supplier.iloc[0], "Missing prices": missing, "Ambiguous values": int(ambiguous_mask.sum()), "Delivery gaps": delivery_gaps, "Freight gaps": freight_gaps, "Tax treatment": tax, "Open issues": open_issues})
    return pd.DataFrame(rows)


def build_email(supplier_name: str, supplier_rows: pd.DataFrame, request_name: str) -> str:
    lines = []
    for _, row in supplier_rows.iterrows():
        issue = str(row.get("issue", "")).strip()
        if pd.isna(row.get("quoted_price")) or issue or pd.isna(row.get("delivery_days")) or pd.isna(row.get("delivery_charge")):
            detail = issue or "Please confirm the missing quotation details"
            lines.append(f"- {row.get('item_id', 'Item')}: {detail}")
    if not lines:
        lines = ["- Please confirm delivery commitment, freight, tax treatment and any additional charges."]
    return (f"Subject: Clarification required — {request_name or 'Sourcing request'}\n\n"
            f"Hello {supplier_name},\n\nThank you for your quotation. Before completing our supplier comparison, could you please clarify the following?\n\n"
            + "\n".join(lines) + "\n\nPlease confirm the applicable currency and price basis, delivery commitment, freight, taxes, payment terms, and any other charges or exceptions.\n\nRegards,\nProcurement Team")


if page == pages[0]:
    st.header("What do you need to source?")
    st.write("Enter your requirement in your own words. BidLens will help make it clearer and flag details you may have missed.")
    default_brief = request.get("description", "")
    brief = st.text_area("Your requirement", value=st.session_state.get("brief_input", default_brief), height=150, placeholder="Example: We need shipping boxes for our warehouse. Please quote multiple sizes and deliver within two weeks.", label_visibility="collapsed", key="brief_input")
    if st.button("Refine my requirement", type="primary", disabled=not brief.strip()):
        result = get_refinement(brief)
        st.session_state["requirement_refinement"] = result
        st.session_state["refined_edit"] = result.get("refined_text", brief)
    result = st.session_state.get("requirement_refinement")
    if result:
        st.divider()
        st.subheader("Refined requirement")
        st.caption(result.get("summary", "Review and edit the suggested wording."))
        edited = st.text_area("Edit the refined text", value=st.session_state.get("refined_edit", result.get("refined_text", brief)), height=210, key="refined_edit")
        gaps = result.get("gaps", [])
        if gaps:
            st.subheader("Suggestions to consider")
            for gap in gaps:
                st.write(f"- {gap}")
        if st.button("Save refined requirement", type="primary"):
            request["description"] = edited
            request["requirements"] = edited
            request["approved"] = False
            write_state("request_json", request)
            st.success("Requirement saved.")

elif page == pages[1]:
    st.header("What information is missing?")
    st.write("Review the supplier gaps and prepare a clarification email when information is incomplete.")
    summary = quote_gaps(quotes)
    total_missing = int(quotes.quoted_price.isna().sum())
    c1, c2 = st.columns(2)
    c1.metric("Suppliers to review", int((summary["Open issues"] > 0).sum()))
    c2.metric("Missing item prices", total_missing)
    st.dataframe(summary, use_container_width=True, hide_index=True)

    supplier_map = {s["supplier"]: s["supplier_id"] for s in SUPPLIERS}
    supplier_name = st.selectbox("Choose a supplier", list(supplier_map.keys()))
    supplier_id = supplier_map[supplier_name]
    supplier_rows = quotes[quotes.supplier_id == supplier_id].copy()
    open_rows = supplier_rows[
        supplier_rows.quoted_price.isna()
        | supplier_rows.issue.fillna("").str.contains("ambiguous|not specified|unconfirmed|requires", case=False)
        | supplier_rows.delivery_days.isna()
        | supplier_rows.delivery_charge.isna()
    ]
    if open_rows.empty:
        st.success("No item-level gaps detected in the available records. Please still review supplier-wide terms.")
    else:
        show_cols = [c for c in ["item_id", "item", "original_price_text", "issue", "delivery_days", "delivery_charge", "source_locator"] if c in open_rows.columns]
        st.dataframe(open_rows[show_cols].rename(columns={"item_id":"Item ID", "item":"Item", "original_price_text":"Quoted price", "issue":"Issue", "delivery_days":"Delivery (days)", "delivery_charge":"Freight charge", "source_locator":"Source"}), use_container_width=True, hide_index=True, height=260)
    if st.button("Draft clarification email", type="primary"):
        st.session_state["clarification_draft"] = build_email(supplier_name, supplier_rows, request.get("name", "Sourcing request"))
        st.session_state["clarification_supplier"] = supplier_name
    if st.session_state.get("clarification_draft") and st.session_state.get("clarification_supplier") == supplier_name:
        draft = st.text_area("Review and edit the email", value=st.session_state["clarification_draft"], height=260, key="email_draft_edit")
        approved = st.checkbox("I have reviewed this draft", key="email_draft_approved")
        if approved:
            st.download_button("Download email draft", draft.encode("utf-8"), file_name=f"clarification_{supplier_id.lower()}.txt", mime="text/plain")
        else:
            st.caption("Review before downloading. BidLens does not send emails automatically.")

elif page == pages[2]:
    st.header("Supplier comparison")
    st.write("Compare the supplier responses, then ask a question or test a delivery/cost scenario.")
    delivery_limit = st.number_input("Required delivery time (days)", min_value=1, max_value=365, value=15, step=1)
    score = calculate_supplier_summary(quotes, DEFAULT_FX, int(delivery_limit))
    show_cols = [c for c in ["Supplier", "Quote coverage %", "Median comparable INR/item", "Delivery days", f"Meets {int(delivery_limit)}-day target", "Freight disclosed", "Tax treatment", "Open price gaps", "Needs review"] if c in score.columns]
    st.dataframe(score[show_cols], use_container_width=True, hide_index=True)
    st.caption("Prices and delivery terms reflect the available source records. Missing prices are unknown, not zero; median unit price is not total landed cost.")

    st.subheader("Ask BidLens")
    if "simple_chat_history" not in st.session_state:
        st.session_state["simple_chat_history"] = []
    for msg in st.session_state["simple_chat_history"][-8:]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("table"):
                st.dataframe(pd.DataFrame(msg["table"]), use_container_width=True, hide_index=True)
    prompt = st.chat_input("Ask about suppliers or try: What if we require delivery within 15 days?")
    if prompt:
        st.session_state["simple_chat_history"].append({"role":"user", "content":prompt})
        intent = interpret_question(prompt, int(delivery_limit), 2)
        answer_text = ""
        table = []
        try:
            if intent.get("intent") == "scenario" or any(w in prompt.lower() for w in ["what if", "if we require", "allow up to", "split the order"]):
                days = int(intent.get("delivery_days", delivery_limit))
                max_suppliers = int(intent.get("max_suppliers", 2))
                result = optimize_allocation(quotes, items, DEFAULT_FX, days, max_suppliers, True, intent.get("priority", "cost"))
                if result.get("feasible"):
                    answer_text = (f"For a {days}-day delivery limit using up to {max_suppliers} supplier(s), the calculated known cost is ₹{result['total_known_cost']:,.2f}. "
                                   f"Suppliers selected: {', '.join(result.get('suppliers', []))}. This is not a complete landed-cost total; unknown prices, taxes or charges are not treated as zero.")
                    table = result.get("assignments", [])[:20]
                else:
                    answer_text = f"No feasible allocation was found for that scenario. {result.get('reason', '')}"
            else:
                data = deterministic_answer(prompt, quotes, items, DEFAULT_FX, int(intent.get("delivery_days", delivery_limit)))
                answer_text = data.get("answer", "I couldn't find a direct answer in the available records.")
                table = data.get("table", [])
            # Use the LLM only to improve wording. Never let API failure break the workflow or calculations.
            if llm_enabled():
                context = json.dumps({"answer_from_data": answer_text, "table": table, "question": prompt}, ensure_ascii=False, default=str)
                try:
                    answer_text = answer_procurement_question(prompt, context)
                except Exception:
                    pass
        except Exception as exc:
            answer_text = f"I couldn't calculate that from the available records: {exc}"
        st.session_state["simple_chat_history"].append({"role":"assistant", "content":answer_text, "table":table})
        st.rerun()
    if st.button("Clear conversation"):
        st.session_state["simple_chat_history"] = []
        st.rerun()

st.divider()
st.caption("BidLens · Supplier evidence and calculations for analyst review · No supplier emails are sent automatically.")
