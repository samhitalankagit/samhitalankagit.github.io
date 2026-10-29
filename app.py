from __future__ import annotations
import json, os, re, sqlite3
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import streamlit as st
from bidlens_engine import (
    DB_PATH, DATA, DOCS, SUPPLIERS, DEFAULT_FX, init_db, read_state, write_state,
    get_data, save_review, normalize_price, normalize_charge, calculate_supplier_summary,
    optimize_allocation, simulate_split_allocation, deterministic_answer, refine_requirement_with_llm, interpret_question, interpret_quote_excerpt_with_llm, llm_enabled,
)

st.set_page_config(page_title="BidLens | Sourcing decision workspace", page_icon="📦", layout="wide")
init_db()
items, quotes, source_meta = get_data()
request = read_state("request_json", {})

st.markdown("""
<style>
.block-container {max-width: 1500px; padding-top: 1.15rem; padding-bottom: 2.2rem;}
[data-testid="stMetric"] {border: 1px solid #e6eaf0; padding: .8rem 1rem; border-radius: 12px; background: #fff;}
.bid-muted {color: #667085; font-size: .88rem;}
.bid-pill {display:inline-block;padding:.22rem .55rem;border-radius:999px;background:#f2f4f7;font-size:.76rem;color:#344054;}
div[data-testid="stDataFrame"] {border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

st.markdown("<span class='bid-pill'>SOURCING WORKSPACE · SYNTHETIC DEMO</span>", unsafe_allow_html=True)
st.title("📦 BidLens")
st.caption("From an imperfect requirement to a defensible sourcing decision.")
st.info("All suppliers, prices and documents are fictional. The app reads the bundled source documents and stores review edits/scenarios locally in SQLite. No supplier emails are sent.")

pages = ["1 · Prepare request", "2 · Supplier responses", "3 · Decision workbench"]
page = st.sidebar.radio("Workflow", pages, label_visibility="visible")
st.sidebar.markdown("---")
st.sidebar.caption("One shared sourcing event · Evidence-backed records · Explicit assumptions")
if llm_enabled():
    st.sidebar.success("Optional LLM enabled")
else:
    st.sidebar.info("Local mode · Add OPENAI_API_KEY to enable optional LLM interpretation")
st.sidebar.caption("When enabled, requirement/chat text may be sent to the configured LLM provider. Use only data you're authorized to share.")


def requirement_gaps(text: str, location: str, due: str, item_count: int) -> list[str]:
    low=text.lower(); gaps=[]
    if item_count <= 0: gaps.append("Add item-level quantities before requesting quotes.")
    if not any(x in low for x in ["day", "date", "deliver by", "delivery", "lead time"]): gaps.append("Specify a delivery date or acceptable lead time.")
    if not any(x in low for x in ["freight", "tax", "charges", "additional charge"]): gaps.append("Ask suppliers to state freight, taxes and other charges.")
    if not any(x in low for x in ["currency", "inr", "usd", "per item", "per unit", "per 100", "price basis"]): gaps.append("Require suppliers to state currency and price basis.")
    if not location.strip(): gaps.append("Set a delivery location.")
    if not due: gaps.append("Set a required delivery date.")
    return gaps


def quote_gap_summary(q: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for sid,g in q.groupby("supplier_id", sort=True):
        missing=int(g.quoted_price.isna().sum())
        ambiguous=int((g.issue.fillna("").str.contains("ambiguous",case=False) & ~g.reviewed.fillna(False)).sum())
        freight=int(g.delivery_charge.isna().sum())
        delivery=int(g.delivery_days.isna().sum())
        unconfirmed=int(g.issue.fillna("").str.contains("unconfirmed|not specified|requires",case=False).sum())
        ready=(missing==0 and ambiguous==0 and delivery==0 and freight==0)
        tax_status = "; ".join(dict.fromkeys(str(x) for x in g.get("tax_status", pd.Series(dtype=str)).dropna() if str(x).strip())) or "Not stated"
        rows.append({"Supplier":g.supplier.iloc[0],"Response": "Received" if g.source_file.iloc[0] else "Not received","Quoted items":int(g.quoted_price.notna().sum()),"Missing prices":missing,"Ambiguous values":ambiguous,"Delivery gaps":delivery,"Freight gaps":freight,"Tax treatment":tax_status,"Status":"Ready for review" if ready else "Needs review"})
    return pd.DataFrame(rows)


def supplier_source_download(supplier_id: str):
    meta=next(s for s in SUPPLIERS if s["supplier_id"]==supplier_id)
    path=DOCS/meta["source_file"]
    return meta, path.read_bytes()

if page == "1 · Prepare request":
    st.header("Prepare the sourcing request")
    st.caption("Start in your own words. BidLens checks whether the request is complete enough to generate comparable supplier responses.")
    with st.form("request_form"):
        c1,c2=st.columns([1.2,1])
        with c1:
            name=st.text_input("Request name", request.get("name","Shipping boxes for customer orders"))
            description=st.text_area("What are you looking for?", request.get("description","We need small, medium and large shipping boxes for customer orders. Please quote the requested quantities and disclose all charges."),height=115)
            requirements=st.text_area("Must-have requirements and context", request.get("requirements","Deliver to Hyderabad within 7 days. Disclose freight, taxes and other charges. Identify exceptions and confirm the price basis."),height=100)
        with c2:
            location=st.text_input("Delivery location",request.get("location","Hyderabad, Telangana"))
            default_due=date.fromisoformat(request.get("due","2026-12-15"))
            due=st.date_input("Required delivery date",value=default_due,format="DD/MM/YYYY")
            st.metric("Requested line items",f"{len(items)} items",help="Quantities are defined per item in the shared RFx item list below.")
            budget=st.number_input("Budget in INR (optional; 0 means not set)",min_value=0,value=int(request.get("budget") or 0),step=10000)
        st.markdown("**Evaluation criteria**")
        criteria_options=["Comparable total cost","Delivery commitment","All charges disclosed","Payment terms","Exceptions to requirements","Quote coverage"]
        criteria=st.multiselect("Choose the factors that matter",criteria_options,default=[x for x in request.get("criteria",criteria_options[:5]) if x in criteria_options])
        questions_default="\n".join(request.get("questions",[
            "Can you supply the requested quantity for every item?","Can you meet the required delivery date?","Have freight, taxes and all other charges been disclosed?","Do you accept the requested payment terms?","What exceptions, substitutions or assumptions apply?"
        ]))
        questions=st.text_area("Standard supplier questionnaire",questions_default,height=130)
        submitted=st.form_submit_button("Save request draft",type="primary",use_container_width=True)
    if submitted:
        quantity=int(items.quantity.sum())
        request={"name":name,"description":description,"requirements":requirements,"location":location,"due":str(due),"quantity":quantity,"budget":budget or None,"criteria":criteria,"questions":[x.strip(" -\t") for x in questions.splitlines() if x.strip()],"approved":False}
        write_state("request_json",request)
        st.success("Request draft saved locally. Review the readiness check below before approving.")
        st.rerun()

    st.divider()
    st.subheader("Sourcing readiness check")
    gaps=requirement_gaps(request.get("description","")+" "+request.get("requirements",""),request.get("location",""),request.get("due",""),len(items))
    if gaps:
        st.warning(f"{len(gaps)} potential gap(s) to review")
        for gap in gaps: st.write(f"- {gap}")
    else:
        st.success("No common completeness gaps detected. This is a checklist, not a guarantee that every technical specification is complete.")

    with st.expander("Ask BidLens to review the requirement",expanded=False):
        st.caption("The review flags ambiguity and missing decisions; it does not silently invent specifications.")
        if st.button("Analyze requirement",type="secondary"):
            try:
                analysis=refine_requirement_with_llm(request.get("description","")+"\nContext: "+request.get("requirements","")+"\nLocation: "+request.get("location","")+"\nDue date: "+request.get("due",""))
                st.session_state["requirement_analysis"]=analysis
            except Exception as e:
                st.error(f"Requirement analysis failed: {e}. The saved request was not changed.")
        if st.session_state.get("requirement_analysis"):
            a=st.session_state["requirement_analysis"]
            st.caption(a.get("mode","Review"))
            st.write(a.get("summary","Requirement review"))
            for gap in a.get("gaps",[]): st.write(f"- {gap}")
            for question in a.get("questions",[]): st.write(f"- Question: {question}")
            st.caption("Review these suggestions and edit the request yourself before approval.")

    with st.expander(f"Review the {len(items)} requested line items · {int(items.quantity.sum()):,} units total"):
        st.dataframe(items[["item_id","item","family","description","quantity"]].rename(columns={"item_id":"Item ID","item":"Item","family":"Family","description":"Description","quantity":"Requested quantity"}),use_container_width=True,hide_index=True,height=300)
        st.caption("These line-item quantities are the source of truth for the demo scenario calculations.")

    st.subheader("What suppliers will be asked to return")
    template=pd.DataFrame([
        ["Item ID and description","Required","Must match requested item"],["Quantity offered","Required","Numeric quantity"],["Quoted price","Required per quoted item","Original amount preserved"],["Currency","Required","INR, USD, etc."],["Price basis","Required","Per item, per 100, or explicitly stated basis"],["Delivery commitment","Required","Date or lead time"],["Freight and additional charges","Required","Amount or explicitly included/excluded"],["Payment terms and quote validity","Required","Supplier-stated terms"],["Exceptions / assumptions","Required if applicable","No silent assumptions"]],columns=["Field","Requirement","Validation rule"])
    st.dataframe(template,use_container_width=True,hide_index=True)
    with st.expander("Preview questionnaire"):
        for i,q in enumerate(request.get("questions",[]),1): st.write(f"{i}. {q}")
    a,b=st.columns([1,1])
    with a:
        if st.button("Approve sourcing pack",type="primary",use_container_width=True):
            if not request.get("description","").strip() or not request.get("questions"):
                st.error("Add a requirement and at least one questionnaire question before approval.")
            else:
                request["approved"]=True; request["approved_at"]=datetime.now().isoformat(timespec="seconds"); write_state("request_json",request)
                st.success("Sourcing pack approved for this demo. No email was sent.")
    with b:
        st.download_button("Download sourcing pack (JSON)",json.dumps(request,indent=2).encode(),file_name="bidlens_sourcing_pack.json",mime="application/json",use_container_width=True)

elif page == "2 · Supplier responses":
    st.header("Supplier response intelligence")
    st.caption("A consolidated view of what was received, what can be trusted, and what needs clarification.")
    last=read_state("inbox_last_refresh","Demo data loaded")
    a,b=st.columns([5,1])
    with a: st.caption(f"Synthetic supplier responses · Last refresh: {last}")
    with b:
        if st.button("↻ Refresh",type="primary",use_container_width=True):
            write_state("inbox_last_refresh",datetime.now().strftime("%d %b %Y, %I:%M %p")); st.toast("Synthetic response register refreshed; no mailbox was accessed."); st.rerun()

    summary=quote_gap_summary(quotes)
    total_missing=int(quotes.quoted_price.isna().sum())
    needs=int((summary.Status!="Ready for review").sum())
    ready=int((summary.Status=="Ready for review").sum())
    m1,m2,m3,m4=st.columns(4)
    m1.metric("Responses received","5 / 5",help="All five fictional source documents are bundled with the demo.")
    m2.metric("Suppliers ready for review",ready,help="All requested prices, delivery fields and freight fields are present; analyst approval is still required.")
    m3.metric("Suppliers needing review",needs)
    m4.metric("Missing / unquoted item prices",total_missing)

    st.subheader("Response register")
    display=summary[["Supplier","Quoted items","Missing prices","Ambiguous values","Delivery gaps","Freight gaps","Tax treatment","Status"]]
    st.dataframe(display,use_container_width=True,hide_index=True,height=245)
    st.caption("A received response is not necessarily a complete quote. Missing item prices remain unknown, never zero.")

    left,right=st.columns([1.05,1],gap="large")
    with left:
        st.subheader("Priority data gaps")
        unresolved_ambiguous=quotes.issue.fillna("").str.contains("ambiguous",case=False) & ~quotes.reviewed.fillna(False)
        other_issues=quotes.issue.fillna("").str.contains("unconfirmed|not specified|requires",case=False)
        gap_rows=quotes[quotes.quoted_price.isna() | unresolved_ambiguous | other_issues].copy()
        if gap_rows.empty:
            st.success("No open data gaps in the current synthetic records.")
        else:
            grouped=gap_rows.groupby(["supplier","supplier_id"],as_index=False).agg(Items_affected=("item_id","nunique"),Examples=("item_id",lambda s:", ".join(list(s)[:5])),Issues=("issue",lambda s:"; ".join(dict.fromkeys([str(x) for x in s if x]))[:220]))
            grouped=grouped.rename(columns={"supplier":"Supplier","Items_affected":"Items affected","Examples":"Example items","Issues":"Why it needs attention"})
            tax_gap_rows=[]
            for _, sg in quotes.groupby(["supplier_id","supplier"],sort=True):
                status=str(sg.tax_status.iloc[0])
                if status!="GST included in quoted prices":
                    tax_gap_rows.append({"supplier":sg.supplier.iloc[0],"supplier_id":sg.supplier_id.iloc[0],"Items_affected":"Supplier-level","Examples":"All quoted items","Issues":"Tax treatment not stated or not found: "+status})
            if tax_gap_rows:
                tax_df=pd.DataFrame(tax_gap_rows).rename(columns={"supplier":"Supplier","Items_affected":"Items affected","Examples":"Example items","Issues":"Why it needs attention"})
                grouped=pd.concat([grouped,tax_df],ignore_index=True)
            st.dataframe(grouped,use_container_width=True,hide_index=True,height=260)
        st.markdown("**Review or clarify a specific value**")
        supplier_options={s["supplier"]:s["supplier_id"] for s in SUPPLIERS}
        chosen_name=st.selectbox("Supplier",list(supplier_options),key="review_supplier")
        chosen_sid=supplier_options[chosen_name]
        supplier_rows=quotes[quotes.supplier_id==chosen_sid].copy()
        supplier_ambiguous=supplier_rows.issue.fillna("").str.contains("ambiguous",case=False) & ~supplier_rows.reviewed.fillna(False)
        supplier_other=supplier_rows.issue.fillna("").str.contains("unconfirmed|not specified|requires",case=False)
        issue_rows=supplier_rows[supplier_rows.quoted_price.isna() | supplier_ambiguous | supplier_other]
        if issue_rows.empty: issue_rows=supplier_rows.head(1)
        item_options=issue_rows.item_id.tolist()
        chosen_item=st.selectbox("Item or issue",item_options,key="review_item")
        rec=quotes[(quotes.supplier_id==chosen_sid)&(quotes.item_id==chosen_item)].iloc[0]
        st.caption(f"Source: {rec.source_locator}")
        st.code(rec.source_excerpt,language=None)
        st.caption(f"Extraction method: {rec.extraction_method}. Values from scanned documents may require manual confirmation.")
        with st.expander("Ask AI to interpret this excerpt",expanded=False):
            st.caption("The AI can suggest fields from the excerpt. Suggestions are not saved, normalized or approved automatically.")
            if st.button("Interpret source excerpt",key="interpret_excerpt"):
                try:
                    st.session_state["quote_interpretation"]=interpret_quote_excerpt_with_llm(str(rec.source_excerpt),str(chosen_item))
                except Exception as e:
                    st.error(f"Excerpt interpretation failed: {e}")
            if st.session_state.get("quote_interpretation"):
                suggestion=st.session_state["quote_interpretation"]
                st.caption(suggestion.get("mode","Suggestion"))
                st.json(suggestion)
        with st.form("review_value_form"):
            current_price=rec.quoted_price
            corrected_price=st.number_input("Confirmed price (leave 0 if still unknown)",min_value=0.0,value=float(current_price) if pd.notna(current_price) else 0.0,step=0.1,format="%.2f")
            cur_opts=["INR","USD","EUR","GBP"]
            current_cur=rec.currency if rec.currency in cur_opts else "INR"
            corrected_currency=st.selectbox("Confirmed currency",cur_opts,index=cur_opts.index(current_cur))
            basis_opts=["per item","per 100 items"]
            current_basis=rec.price_basis if rec.price_basis in basis_opts else "per item"
            corrected_basis=st.selectbox("Confirmed price basis",basis_opts,index=basis_opts.index(current_basis))
            confirm=st.checkbox("I reviewed the source and confirm these values")
            save=st.form_submit_button("Save reviewed value")
        if save:
            if not confirm: st.error("Tick the confirmation box only after reviewing the source.")
            elif corrected_price<=0: st.error("A positive price is required to save a confirmed quote. Leave it unresolved if the source is still unclear.")
            else:
                save_review(chosen_sid,chosen_item,corrected_price,corrected_currency,corrected_basis)
                st.success("Reviewed value saved in local SQLite. The original source excerpt remains preserved.")
                st.rerun()
        with st.expander("Prepare a clarification email draft"):
            issues_for_supplier=gap_rows[gap_rows.supplier_id==chosen_sid]
            lines=[]
            if issues_for_supplier.empty: lines=["Please confirm your quoted values and commercial terms."]
            else:
                for _,g in issues_for_supplier.head(12).iterrows(): lines.append(f"{g.item_id}: {g.issue or 'Required information missing'}")
            draft=(f"Subject: Clarification required — {request.get('name','Sourcing request')}\n\nHello {chosen_name},\n\nThank you for your quotation. Before we complete our comparison, please clarify the following:\n\n"+"\n".join(f"- {x}" for x in lines)+"\n\nPlease confirm the original price, currency, price basis, delivery commitment, and any freight, tax or additional charges that apply.\n\nRegards,\nProcurement Team")
            st.text_area("Draft — review before use",draft,height=180)
            st.download_button("Download clarification draft",draft.encode(),file_name=f"clarification_{chosen_sid.lower()}.txt",mime="text/plain")

    with right:
        st.subheader("Source evidence")
        ev_supplier_name=st.selectbox("Inspect source document",list(supplier_options),key="evidence_supplier")
        ev_sid=supplier_options[ev_supplier_name]
        ev_meta,ev_bytes=supplier_source_download(ev_sid)
        st.write(f"**{ev_meta['source_format']}** · `{ev_meta['source_file']}`")
        st.download_button("Download source document",ev_bytes,file_name=ev_meta["source_file"],mime="application/octet-stream",use_container_width=True)
        ev_item=st.selectbox("Show evidence for item",items.item_id.tolist(),key="evidence_item")
        ev_row=quotes[(quotes.supplier_id==ev_sid)&(quotes.item_id==ev_item)].iloc[0]
        with st.container(border=True):
            st.caption(ev_row.source_locator)
            st.code(ev_row.source_excerpt,language=None)
            st.caption(f"Method: {ev_row.extraction_method}")
            st.markdown("**Supplier-level tax treatment**")
            st.write(ev_row.tax_status)
            st.caption(ev_row.tax_source_locator)
            st.code(ev_row.tax_evidence,language=None)
            if ev_row.issue: st.warning(ev_row.issue)
            elif not ev_row.quoted: st.warning("No quote was found for this item in the source document.")
            else: st.success("A quoted value was extracted. Verify against the source before relying on it.")
        st.markdown("**Source documents included**")
        for s in SUPPLIERS: st.write(f"- {s['supplier']} — {s['source_format']}")
        st.caption("The scan uses Tesseract OCR when sufficient text is recognized; otherwise a packaged synthetic OCR reference transcript is used and disclosed.")

elif page == "3 · Decision workbench":
    st.header("Sourcing decision workbench")
    st.caption("Compare supplier responses, simulate feasible allocations, and inspect the evidence behind each result.")
    fx=st.number_input("Illustrative USD → INR rate",min_value=1.0,value=DEFAULT_FX,step=0.5,help="Demo assumption only. This is not a live exchange rate.")
    c1,c2,c3,c4=st.columns(4)
    with c1: delivery_limit=st.number_input("Required delivery (days)",min_value=1,max_value=365,value=7)
    with c2: max_suppliers=st.selectbox("Maximum suppliers in allocation",[1,2,3,4,5],index=1)
    with c3: priority=st.selectbox("Optimization priority",["Lowest known cost","Fastest feasible delivery"],index=0)
    with c4: exclude_unknown=st.checkbox("Exclude suppliers with unknown freight",value=True)
    priority_key="delivery" if priority=="Fastest feasible delivery" else "cost"

    st.subheader("Supplier scorecard")
    score=calculate_supplier_summary(quotes,fx,int(delivery_limit))
    score=score.rename(columns={"Median comparable INR/item":"Median comparable INR / item"})
    st.dataframe(score[["Supplier","Quote coverage %","Median comparable INR / item","Delivery days",f"Meets {int(delivery_limit)}-day target","Freight disclosed","Tax treatment","Open price gaps","Needs review"]],use_container_width=True,hide_index=True)
    st.caption("This scorecard uses observed quote coverage and declared lead times. It does not claim historical supplier reliability or score unprovided criteria.")

    st.subheader("What-if allocation simulator")
    scenario_mode=st.selectbox("Scenario type",["Find lowest-cost whole-line allocation","Simulate a quantity split between two suppliers"],key="scenario_mode")
    split_a_pct=50; split_a_name=SUPPLIERS[0]["supplier"]; split_b_name=SUPPLIERS[1]["supplier"]
    if scenario_mode=="Find lowest-cost whole-line allocation":
        st.write("Find a lowest-known-cost assignment of each requested item to one eligible supplier, respecting delivery, freight-data and maximum-supplier constraints.")
        st.caption("The solver assigns whole line items. It does not model supplier capacity or minimum order quantities, which are not included in the synthetic quotes.")
    else:
        st.write("Test a user-defined quantity split across two suppliers. For each item, the selected percentage is allocated to Supplier A and the remainder to Supplier B where both have a valid quote.")
        supplier_labels={s["supplier"]:s["supplier_id"] for s in SUPPLIERS}
        sc1,sc2,sc3=st.columns([1,1,1.2])
        with sc1: split_a_name=st.selectbox("Supplier A",list(supplier_labels),index=0,key="split_supplier_a")
        with sc2:
            other_names=[n for n in supplier_labels if n!=split_a_name]
            split_b_name=st.selectbox("Supplier B",other_names,index=0,key="split_supplier_b")
        with sc3: split_a_pct=st.slider("Share assigned to Supplier A",min_value=0,max_value=100,value=50,step=5,key="split_share_a")
        st.caption("If only one selected supplier has a valid quote for an item, it receives the full line quantity and the exception is shown. This is a simulation, not an optimizer.")
    run=st.button("Run scenario",type="primary",use_container_width=True)
    if run:
        if scenario_mode=="Find lowest-cost whole-line allocation":
            result=optimize_allocation(quotes,items,fx,int(delivery_limit),int(max_suppliers),exclude_unknown,priority_key)
        else:
            result=simulate_split_allocation(quotes,items,supplier_labels[split_a_name],supplier_labels[split_b_name],int(split_a_pct),fx,int(delivery_limit),exclude_unknown)
        baseline=optimize_allocation(quotes,items,fx,int(delivery_limit),1,exclude_unknown,priority_key)
        scenario_name=f"{scenario_mode} · {int(delivery_limit)} days"
        inputs={"mode":scenario_mode,"fx":fx,"delivery_limit":delivery_limit,"max_suppliers":max_suppliers,"exclude_unknown_freight":exclude_unknown,"priority":priority,"supplier_a":split_a_name,"supplier_b":split_b_name,"supplier_a_share_pct":split_a_pct}
        with sqlite3.connect(DB_PATH) as con:
            con.execute("INSERT INTO scenarios(name,inputs_json,result_json) VALUES(?,?,?)",(scenario_name,json.dumps(inputs),json.dumps(result,default=str)))
        st.session_state["latest_scenario"]=result
        st.session_state["latest_baseline"]=baseline
    result=st.session_state.get("latest_scenario")
    if result:
        if not result.get("feasible"):
            st.warning(result.get("reason","No feasible allocation found."))
            if result.get("open_items"): st.write("Items without a feasible quote: "+", ".join(result["open_items"]))
        else:
            a,b,c=st.columns(3)
            a.metric("Estimated known cost",f"₹{result['total_known_cost']:,.2f}",help="Includes normalized line subtotals and known supplier-level freight. Excludes unspecified taxes and other unstated charges.")
            b.metric("Suppliers used",result["supplier_count"])
            c.metric("Slowest assigned delivery",f"{result['max_delivery_days']} days")
            st.success("Suggested allocation for analyst review: "+", ".join(result["suppliers"]))
            baseline=st.session_state.get("latest_baseline")
            if baseline and baseline.get("feasible") and max_suppliers>1:
                delta=round(baseline["total_known_cost"]-result["total_known_cost"],2)
                st.write(f"Compared with the best feasible single-supplier scenario: **{'₹'+format(delta,',.2f')+' lower' if delta>0 else ('₹'+format(abs(delta),',.2f')+' higher' if delta<0 else 'same known cost')}**. This is a synthetic model result, not a purchasing commitment.")
            st.dataframe(pd.DataFrame(result["assignments"]),use_container_width=True,hide_index=True,height=360)
            st.download_button("Download allocation scenario (CSV)",pd.DataFrame(result["assignments"]).to_csv(index=False).encode(),file_name="bidlens_allocation_scenario.csv",mime="text/csv")
            with st.expander("Assumptions and limitations",expanded=True):
                for limitation in result.get("limitations",[]): st.write(f"- {limitation}")
                st.write(f"Illustrative FX rate: 1 USD = {result['fx_rate']} INR.")
                st.write("The 10% discount in Supplier B's PDF is not applied because its applicability is unconfirmed.")
                st.write("The allocation is a model suggestion for analyst review; it is not a purchase award.")

    st.divider()
    st.subheader("Ask BidLens")
    st.caption("Questions are answered from the same extracted records and deterministic cost functions. When an LLM is enabled, it may interpret the question, but it does not calculate the cost itself.")
    if "chat_history" not in st.session_state: st.session_state.chat_history=[]
    prompt=st.chat_input("Ask: What if we use two suppliers? Which items are missing? Compare BX-13.")
    if prompt:
        intent=interpret_question(prompt,int(delivery_limit),int(max_suppliers))
        if intent.get("intent")=="scenario":
            dl=int(intent.get("delivery_days",delivery_limit))
            maxs=int(intent.get("max_suppliers",max_suppliers))
            pr=intent.get("priority","cost")
            sim=optimize_allocation(quotes,items,fx,dl,maxs,exclude_unknown,pr)
            if sim.get("feasible"):
                ans={"answer":f"Feasible scenario calculated for a {dl}-day delivery limit and up to {maxs} supplier(s). Estimated known cost: ₹{sim['total_known_cost']:,.2f}. Suppliers used: {', '.join(sim['suppliers'])}. This is not a full landed-cost total.","table":sim["assignments"][:30],"evidence":[{"Source":x["Evidence"],"Excerpt":x["Source excerpt"],"Item":x["Item ID"],"Supplier":x["Supplier"]} for x in sim["assignments"][:12]],"limitations":sim["limitations"]}
            else: ans={"answer":sim.get("reason","No feasible allocation."),"table":[],"evidence":[],"limitations":sim.get("limitations",[])}
        else:
            ans=deterministic_answer(prompt,quotes,items,fx,int(intent.get("delivery_days",delivery_limit)))
            ans["mode"]=intent.get("mode","Rule-based intent routing")
        st.session_state.chat_history.append({"q":prompt,"a":ans})
    for msg in st.session_state.chat_history[-8:]:
        with st.chat_message("user"): st.write(msg["q"])
        with st.chat_message("assistant"):
            st.write(msg["a"].get("answer",""))
            if msg["a"].get("mode"): st.caption("Question routing: "+msg["a"]["mode"])
            if msg["a"].get("table"): st.dataframe(pd.DataFrame(msg["a"]["table"]),use_container_width=True,hide_index=True)
            if msg["a"].get("evidence"):
                with st.expander("Supporting source records"):
                    st.dataframe(pd.DataFrame(msg["a"]["evidence"]),use_container_width=True,hide_index=True)
            for limitation in msg["a"].get("limitations",[]): st.caption("Limitation: "+limitation)
    if st.button("Clear chat",key="clear_workbench_chat"):
        st.session_state.chat_history=[]; st.rerun()

st.divider()
st.caption("BidLens · Synthetic sourcing demo · No supplier emails sent · No purchasing decision is made automatically.")
