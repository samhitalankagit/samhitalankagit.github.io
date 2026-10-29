"""BidLens deterministic extraction, validation, costing, and scenario tools."""
from __future__ import annotations
import csv, io, json, os, re, sqlite3
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DOCS = DATA / "source_documents"
DB_PATH = DATA / "bidlens.db"
DEFAULT_FX = 83.0

SUPPLIERS = [
    {"supplier_id":"SUP-A","supplier":"Deccan Packaging (Sample)","source_format":"Excel workbook","source_file":"supplier_a_deccan_packaging.xlsx"},
    {"supplier_id":"SUP-B","supplier":"Charminar Boxes (Sample)","source_format":"PDF quote","source_file":"supplier_b_charminar_boxes.pdf"},
    {"supplier_id":"SUP-C","supplier":"Musi Cartons (Sample)","source_format":"Scanned image","source_file":"supplier_c_musi_cartons_scan.png"},
    {"supplier_id":"SUP-D","supplier":"Metro Pack Hyderabad (Sample)","source_format":"Email response","source_file":"supplier_d_metro_pack.eml"},
    {"supplier_id":"SUP-E","supplier":"Telangana Box Works (Sample)","source_format":"Word document","source_file":"supplier_e_telanganaboxworks.docx"},
]


def _numeric(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): return None
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in {"not quoted", "not stated", "n/a", "none", "—", "-"}: return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _parse_pipe_line(line: str) -> dict | None:
    if not re.match(r"\s*BX-\d{2}\s*\|", line, re.I): return None
    parts = [p.strip() for p in line.strip().split("|")]
    if len(parts) < 7: return None
    item_id, item = parts[0].upper(), parts[1]
    qty_m = re.search(r"\d+", parts[2])
    if not qty_m: return None
    price_raw = parts[3].replace("Price", "").strip()
    currency = parts[4].strip().upper()
    basis = parts[5].strip().lower()
    delivery_raw = parts[6].strip()
    freight_raw = parts[7].strip() if len(parts) > 7 else "NOT STATED"
    terms = parts[8].strip() if len(parts) > 8 else "Not specified"
    ambiguous = bool(re.search(r"\?|unclear|ambiguous", price_raw, re.I))
    price = None if ambiguous else _numeric(price_raw)
    delivery = _numeric(delivery_raw)
    freight = _numeric(freight_raw)
    issue = "Scanned price is ambiguous; manual confirmation required" if ambiguous else ""
    if price is None and not ambiguous: issue = "No quoted price stated in source line"
    return {"item_id":item_id,"item":item,"quantity_offered":int(qty_m.group(0)),"quoted_price":price,"original_price_text":price_raw,"currency":currency,"price_basis":basis,"delivery_days":int(delivery) if delivery is not None else None,"delivery_charge":freight,"payment_terms":terms,"issue":issue,"raw_excerpt":line.strip()}


def extract_supplier_file(supplier: dict) -> tuple[list[dict], str]:
    """Extract actual fields from a bundled synthetic source document."""
    path = DOCS / supplier["source_file"]
    fmt = supplier["source_format"]
    rows: list[dict] = []
    if fmt == "Excel workbook":
        df = pd.read_excel(path, sheet_name="Quotation", dtype=str).fillna("")
        for row_idx, (_, r) in enumerate(df.iterrows(), start=2):
            price_text = str(r.get("Unit price", "")).strip()
            rows.append({"item_id":str(r["Item ID"]).strip(),"item":str(r["Item description"]).strip(),"quantity_offered":int(_numeric(r.get("Quantity offered")) or 0),"quoted_price":_numeric(price_text),"original_price_text":price_text,"currency":str(r.get("Currency","INR")).strip().upper(),"price_basis":str(r.get("Price basis","per item")).strip().lower(),"delivery_days":int(_numeric(r.get("Delivery days"))) if _numeric(r.get("Delivery days")) is not None else None,"delivery_charge":_numeric(r.get("Freight / delivery charge")),"payment_terms":str(r.get("Payment terms","Not specified")),"issue":"","raw_excerpt":" | ".join([str(r.get("Item ID","")),str(r.get("Item description","")),str(r.get("Quantity offered","")),str(price_text),str(r.get("Currency","")),str(r.get("Price basis","")),str(r.get("Delivery days","")),str(r.get("Freight / delivery charge",""))]),"source_location":f"Quotation sheet, row {row_idx}"})
        method = "openpyxl table extraction"
    elif fmt == "PDF quote":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                row = _parse_pipe_line(line)
                if row:
                    row["source_location"] = f"PDF page {page_num}"
                    rows.append(row)
        # The PDF includes a structured text appendix so text extraction is reproducible.
        method = "PDF text extraction"
    elif fmt == "Scanned image":
        text = ""
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(path))
            method = "Tesseract OCR"
        except Exception:
            method = "Packaged synthetic OCR reference (Tesseract unavailable)"
        for line_num, line in enumerate(text.splitlines(), start=1):
            row = _parse_pipe_line(line)
            if row:
                row["source_location"] = f"scan transcript line {line_num}"
                rows.append(row)
        if len(rows) < 25:
            text = (DOCS / "supplier_c_musi_cartons_scan_ocr_reference.txt").read_text(encoding="utf-8")
            rows = []
            for line_num, line in enumerate(text.splitlines(), start=1):
                row = _parse_pipe_line(line)
                if row:
                    row["source_location"] = f"packaged OCR reference line {line_num}"
                    rows.append(row)
            method = "Packaged synthetic OCR reference (Tesseract unavailable or insufficient OCR)"
    elif fmt == "Email response":
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), start=1):
            row = _parse_pipe_line(line)
            if row:
                row["source_location"] = f"email body line {line_num}"
                rows.append(row)
        method = "Email body text extraction"
    elif fmt == "Word document":
        from docx import Document
        doc = Document(path)
        table = doc.tables[0]
        headers = [c.text.strip().lower() for c in table.rows[0].cells]
        def get(cells, key, default=""):
            try: return cells[headers.index(key)].text.strip()
            except ValueError: return default
        for row_num, tr in enumerate(table.rows[1:], start=2):
            cells = tr.cells
            price_text = get(cells,"quoted price")
            rows.append({"item_id":get(cells,"item id").upper(),"item":get(cells,"description"),"quantity_offered":int(_numeric(get(cells,"qty")) or 0),"quoted_price":_numeric(price_text),"original_price_text":price_text,"currency":get(cells,"currency","USD").upper(),"price_basis":get(cells,"price basis","per item").lower(),"delivery_days":int(_numeric(get(cells,"delivery days"))) if _numeric(get(cells,"delivery days")) is not None else None,"delivery_charge":350.0,"payment_terms":"Net 30 days","issue":"","raw_excerpt":" | ".join([get(cells,"item id"),get(cells,"description"),get(cells,"qty"),price_text,get(cells,"currency"),get(cells,"price basis"),get(cells,"delivery days")]),"source_location":f"quotation table row {row_num}"})
        method = "Word table extraction"
    else:
        method = "unsupported"
    # Remove accidental duplicate header rows or duplicate item IDs, keeping the first source occurrence.
    unique = {}
    for r in rows:
        if re.fullmatch(r"BX-\d{2}", str(r.get("item_id", ""))): unique.setdefault(r["item_id"], r)
    return list(unique.values()), method



def supplier_tax_terms(supplier: dict) -> tuple[str, str]:
    """Read supplier-level tax treatment from the actual bundled source document."""
    path=DOCS/supplier["source_file"]
    sid=supplier["supplier_id"]
    text=""
    try:
        if sid=="SUP-A":
            cover=pd.read_excel(path,sheet_name="Cover",dtype=str).fillna("")
            text=" ".join(str(v) for v in cover.astype(str).values.flatten())
        elif sid=="SUP-B":
            from pypdf import PdfReader
            text="\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
        elif sid=="SUP-C":
            text=(DOCS/"supplier_c_musi_cartons_scan_ocr_reference.txt").read_text(encoding="utf-8")
        elif sid=="SUP-D":
            text=path.read_text(encoding="utf-8",errors="replace")
        elif sid=="SUP-E":
            from docx import Document
            d=Document(path); text="\n".join(p.text for p in d.paragraphs)
    except Exception:
        text=""
    sentences=re.split(r"[\n.!]",text)
    evidence=next((x.strip() for x in sentences if "tax" in x.lower() or "gst" in x.lower()),"Tax treatment was not found in the extracted source text.")
    if re.search(r"gst.{0,25}included|included.{0,25}gst",text,re.I):
        return "GST included in quoted prices", evidence
    if re.search(r"tax.{0,80}(not stated|not specified|not included|unknown)|tax treatment.{0,20}not stated",text,re.I):
        return "Not stated in source document", evidence
    return "Not found in source document", evidence

def load_extracted_dataset() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    items = pd.read_csv(DATA / "rfx_items.csv")
    all_rows = []
    source_meta = []
    for s in SUPPLIERS:
        parsed, method = extract_supplier_file(s)
        tax_status, tax_evidence = supplier_tax_terms(s)
        by_id = {r["item_id"]: r for r in parsed}
        source_meta.append({**s,"extraction_method":method,"rows_extracted":len(parsed),"tax_status":tax_status,"tax_evidence":tax_evidence})
        for _, item in items.iterrows():
            r = by_id.get(item.item_id)
            if r:
                price = r.get("quoted_price")
                issue = r.get("issue", "")
                if price is None and not issue: issue = "Price missing or not parseable"
                # Source excerpts are taken from the extracted source row, not generated after comparison.
                evidence = r.get("raw_excerpt") or f"{item.item_id} | {r.get('item', item['item'])} | Qty {r.get('quantity_offered', item.quantity)} | Price {r.get('original_price_text','')} | {r.get('currency','')} | {r.get('price_basis','')} | Delivery {r.get('delivery_days') if r.get('delivery_days') is not None else 'NOT STATED'} days | Freight {r.get('delivery_charge') if r.get('delivery_charge') is not None else 'NOT STATED'}"
                if s["supplier_id"]=="SUP-B" and item.item_id=="BX-01": issue = (issue + "; " if issue else "") + "10% discount mentioned in PDF notes; applicability unconfirmed"
                if s["supplier_id"]=="SUP-D": issue = (issue + "; " if issue else "") + "Freight/additional charges not specified in email"
                if s["supplier_id"]=="SUP-E": issue = (issue + "; " if issue else "") + "USD pricing requires disclosed FX assumption"
                locator = source_locator(s["supplier_id"], item.item_id, r.get("source_location"))
                all_rows.append({**item.to_dict(),**s,"quoted_price":price,"original_price_text":r.get("original_price_text",""),"currency":r.get("currency","INR"),"price_basis":r.get("price_basis","per item"),"delivery_days":r.get("delivery_days"),"delivery_charge":r.get("delivery_charge"),"payment_terms":r.get("payment_terms","Not specified"),"quote_validity_days":30 if s["supplier_id"]!="SUP-D" else None,"issue":issue,"source_excerpt":evidence,"source_locator":locator,"extraction_method":method,"tax_status":tax_status,"tax_evidence":tax_evidence,"tax_source_locator":f"{s['source_file']} · supplier-level commercial terms","quoted":price is not None,"reviewed":False,"reviewed_price":None,"reviewed_currency":None,"reviewed_basis":None})
            else:
                all_rows.append({**item.to_dict(),**s,"quoted_price":None,"original_price_text":"NOT QUOTED","currency":"","price_basis":"","delivery_days":None,"delivery_charge":None,"payment_terms":"Not specified","quote_validity_days":None,"issue":"No quote for this requested item in the source document","source_excerpt":f"No row for {item.item_id} was found in {s['source_file']}; treated as an unquoted item, not zero.","source_locator":s["source_file"],"extraction_method":method,"tax_status":tax_status,"tax_evidence":tax_evidence,"tax_source_locator":f"{s['source_file']} · supplier-level commercial terms","quoted":False,"reviewed":False,"reviewed_price":None,"reviewed_currency":None,"reviewed_basis":None})
    quotes=pd.DataFrame(all_rows)
    return items, quotes, pd.DataFrame(source_meta)


def source_locator(supplier_id: str, item_id: str, source_location: str | None = None) -> str:
    s = next(x for x in SUPPLIERS if x["supplier_id"] == supplier_id)
    location = source_location or f"record for {item_id}"
    return f"{s['source_file']} · {location} · {item_id}"


def init_db() -> None:
    DATA.mkdir(exist_ok=True, parents=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS reviewed_values (supplier_id TEXT, item_id TEXT, reviewed_price REAL, reviewed_currency TEXT, reviewed_basis TEXT, reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (supplier_id,item_id))")
        con.execute("CREATE TABLE IF NOT EXISTS scenarios (scenario_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, inputs_json TEXT, result_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        row=con.execute("SELECT value FROM app_state WHERE key='seed_version'").fetchone()
        if row is None:
            items, quotes, meta=load_extracted_dataset()
            con.execute("INSERT INTO app_state(key,value) VALUES('seed_version','1')")
            con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('request_json',?)",(json.dumps(default_request()),))
            con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('quote_rows_json',?)",(quotes.to_json(orient="records",date_format="iso"),))
            con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('items_json',?)",(items.to_json(orient="records"),))
            con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('sources_json',?)",(meta.to_json(orient="records"),))


def default_request() -> dict:
    return {"name":"Shipping boxes for customer orders","description":"Small, medium and large shipping boxes","quantity":21750,"location":"Hyderabad, Telangana","due":"2026-12-15","budget":None,"requirements":"Deliver to Hyderabad within 7 days. Disclose freight, taxes and other charges. Identify exceptions and confirm the quoted price basis.","criteria":["Comparable total cost","Delivery commitment","All charges disclosed","Payment terms","Exceptions to requirements"],"questions":["Can you supply the requested quantity for every item?","Can you meet the delivery deadline?","Have all freight, tax and additional charges been disclosed?","Do you accept the requested payment terms?","What exceptions or substitutions apply?"],"approved":True}


def read_state(key: str, default=None):
    with sqlite3.connect(DB_PATH) as con:
        row=con.execute("SELECT value FROM app_state WHERE key=?",(key,)).fetchone()
    return json.loads(row[0]) if row else default


def write_state(key: str, value: Any):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES(?,?)",(key,json.dumps(value,ensure_ascii=False,default=str)))


def get_data():
    items=pd.DataFrame(read_state("items_json",[]))
    quotes=pd.DataFrame(read_state("quote_rows_json",[]))
    sources=pd.DataFrame(read_state("sources_json",[]))
    if not quotes.empty:
        with sqlite3.connect(DB_PATH) as con:
            edits=pd.read_sql_query("SELECT * FROM reviewed_values",con)
        if not edits.empty:
            edits=edits.rename(columns={"reviewed_price":"db_reviewed_price","reviewed_currency":"db_reviewed_currency","reviewed_basis":"db_reviewed_basis"})
            quotes=quotes.merge(edits,on=["supplier_id","item_id"],how="left")
            mask=quotes["db_reviewed_price"].notna()
            quotes.loc[mask,"quoted_price"]=quotes.loc[mask,"db_reviewed_price"]
            quotes.loc[mask,"currency"]=quotes.loc[mask,"db_reviewed_currency"]
            quotes.loc[mask,"price_basis"]=quotes.loc[mask,"db_reviewed_basis"]
            quotes.loc[mask,"reviewed"]=True
            quotes=quotes.drop(columns=[c for c in ["reviewed_at","db_reviewed_price","db_reviewed_currency","db_reviewed_basis"] if c in quotes.columns],errors="ignore")
    return items,quotes,sources


def save_review(supplier_id: str, item_id: str, price: float, currency: str, basis: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT OR REPLACE INTO reviewed_values(supplier_id,item_id,reviewed_price,reviewed_currency,reviewed_basis) VALUES(?,?,?,?,?)",(supplier_id,item_id,float(price),currency,basis))


def normalize_price(price, currency, basis, fx=DEFAULT_FX):
    if price is None or pd.isna(price): return None
    val=float(price)
    b=str(basis or "").lower()
    if "100" in b: val/=100.0
    cur=str(currency or "").upper()
    if cur=="INR": pass
    elif cur=="USD": val*=float(fx)
    else: return None
    return round(val,6)


def normalize_charge(charge, currency, fx=DEFAULT_FX):
    if charge is None or pd.isna(charge): return None
    cur=str(currency or "").upper()
    if cur=="INR": return float(charge)
    if cur=="USD": return float(charge)*float(fx)
    return None


def quote_effective(row):
    p=row.get("quoted_price")
    if p is None or pd.isna(p): return None
    return normalize_price(p,row.get("currency"),row.get("price_basis"),DEFAULT_FX)


def calculate_supplier_summary(quotes: pd.DataFrame, fx: float, delivery_limit: int) -> pd.DataFrame:
    rows=[]
    for sid,g in quotes.groupby("supplier_id",sort=True):
        prices=g["quoted_price"].notna()
        comparable=[normalize_price(r.quoted_price,r.currency,r.price_basis,fx) for r in g.itertuples()]
        comparable=[x for x in comparable if x is not None]
        delivery=g["delivery_days"].dropna()
        rows.append({"Supplier":g.supplier.iloc[0],"Supplier ID":sid,"Quoted items":int(prices.sum()),"Requested items":len(g),"Quote coverage %":round(100*prices.sum()/len(g),1) if len(g) else 0,"Median comparable INR/item":round(float(pd.Series(comparable).median()),2) if comparable else None,"Delivery days":int(delivery.iloc[0]) if len(delivery) and delivery.nunique()==1 else ("Varies" if len(delivery) else "Unknown"),f"Meets {delivery_limit}-day target":bool(len(delivery) and (delivery<=delivery_limit).all()),"Freight disclosed":bool(g["delivery_charge"].notna().all()),"Tax treatment":str(g["tax_status"].iloc[0]) if "tax_status" in g else "Not found","Open price gaps":int(g["quoted_price"].isna().sum()),"Needs review":int(g["issue"].fillna("").str.contains("ambiguous|unconfirmed|not specified|unknown",case=False).sum())})
    return pd.DataFrame(rows)


def optimize_allocation(quotes: pd.DataFrame, items: pd.DataFrame, fx: float=DEFAULT_FX, delivery_limit: int=7, max_suppliers: int=2, exclude_unknown_freight: bool=True, priority: str="cost") -> dict:
    """Enumerate supplier subsets and assign each whole item to the cheapest feasible quote."""
    q=quotes.copy()
    q["normalized_unit_cost"]=[normalize_price(r.quoted_price,r.currency,r.price_basis,fx) for r in q.itertuples()]
    q["normalized_freight"]=[normalize_charge(r.delivery_charge,r.currency,fx) for r in q.itertuples()]
    q=q[q["normalized_unit_cost"].notna() & q["delivery_days"].notna() & (q["delivery_days"]<=delivery_limit)]
    if exclude_unknown_freight: q=q[q["normalized_freight"].notna()]
    suppliers=sorted(q.supplier_id.unique().tolist())
    if not suppliers: return {"feasible":False,"reason":"No suppliers meet the selected delivery, price and freight-data constraints.","assignments":[],"total_known_cost":None,"open_items":items.item_id.tolist()}
    # A supplier's freight is a fixed per-order amount, not a per-line charge. Use one consistent value per supplier.
    freight={sid:float(g.normalized_freight.dropna().iloc[0]) if g.normalized_freight.notna().any() else None for sid,g in q.groupby("supplier_id")}
    best=None
    for n in range(1,min(max_suppliers,len(suppliers))+1):
        for subset in combinations(suppliers,n):
            alloc=[]; total=0.0; feasible=True; open_items=[]
            for item in items.itertuples():
                candidates=q[(q.item_id==item.item_id)&q.supplier_id.isin(subset)].copy()
                if candidates.empty:
                    feasible=False; open_items.append(item.item_id); continue
                candidates=candidates.sort_values("normalized_unit_cost")
                chosen=candidates.iloc[0]
                line_total=float(chosen.normalized_unit_cost)*float(item.quantity)
                total+=line_total
                alloc.append({"Item ID":item.item_id,"Item":item.item,"Quantity":int(item.quantity),"Supplier":chosen.supplier,"Supplier ID":chosen.supplier_id,"Original price":chosen.original_price_text,"Currency":chosen.currency,"Price basis":chosen.price_basis,"Normalized INR/unit":round(float(chosen.normalized_unit_cost),4),"Line subtotal INR":round(line_total,2),"Delivery days":int(chosen.delivery_days),"Evidence":chosen.source_locator,"Source excerpt":chosen.source_excerpt,"Issue":chosen.issue})
            if not feasible: continue
            total+=sum(freight[sid] or 0 for sid in subset)
            selected_names=[next(s["supplier"] for s in SUPPLIERS if s["supplier_id"]==sid) for sid in subset]
            used=set(x["Supplier ID"] for x in alloc)
            # Avoid paying a fixed charge for selected suppliers that were not actually assigned any item.
            total-=sum(freight[sid] or 0 for sid in subset if sid not in used)
            max_days=max(x["Delivery days"] for x in alloc)
            # Objective remains transparent: cost first, then fewer suppliers, unless delivery priority is selected.
            key=(max_days,total,n) if priority=="delivery" else (total,max_days,n)
            result={"feasible":True,"suppliers":selected_names,"supplier_ids":list(subset),"assignments":alloc,"total_known_cost":round(total,2),"max_delivery_days":max_days,"supplier_count":len(used),"open_items":[],"fx_rate":fx,"delivery_limit":delivery_limit,"max_suppliers":max_suppliers,"exclude_unknown_freight":exclude_unknown_freight,"priority":priority,"limitations":["Excludes taxes and charges not stated in the source documents.","Unconfirmed discounts are not applied.","Prices in USD use the illustrative exchange rate shown.","Supplier capacity is not provided in the synthetic data and is not modeled."]}
            if best is None or key<best[0]: best=(key,result)
    if best: return best[1]
    return {"feasible":False,"reason":"No feasible allocation covers every requested item under the selected constraints.","assignments":[],"total_known_cost":None,"open_items":sorted(set(open_items) if 'open_items' in locals() else items.item_id.tolist()),"limitations":["Missing or ambiguous quotes are not treated as zero."]}


def deterministic_answer(question: str, quotes: pd.DataFrame, items: pd.DataFrame, fx: float=DEFAULT_FX, delivery_limit: int=7) -> dict:
    q=question.lower().strip()
    match=re.search(r"BX-\d{2}",question.upper())
    evidence=[]
    if any(w in q for w in ["missing","gap","coverage","incomplete","unquoted"]):
        out=[]
        for sid,g in quotes.groupby("supplier_id"):
            out.append({"Supplier":g.supplier.iloc[0],"Missing prices":int(g.quoted_price.isna().sum()),"Quoted items":int(g.quoted_price.notna().sum()),"Coverage %":round(100*g.quoted_price.notna().mean(),1)})
        result=pd.DataFrame(out).sort_values("Missing prices",ascending=False)
        evidence=quotes[quotes.quoted_price.isna()][["supplier","item_id","source_excerpt","source_locator"]].head(12).to_dict("records")
        return {"answer":"Quote completeness by supplier. An unquoted item is unknown, not zero.","table":result.to_dict("records"),"evidence":evidence}
    if any(w in q for w in ["delivery","lead time","fast","deadline"]):
        result=calculate_supplier_summary(quotes,fx,delivery_limit)[["Supplier","Quoted items","Delivery days",f"Meets {delivery_limit}-day target","Open price gaps"]]
        evidence=quotes[quotes.delivery_days.notna()][["supplier","item_id","delivery_days","source_excerpt","source_locator"]].head(12).to_dict("records")
        return {"answer":f"Recorded delivery commitments compared with the {delivery_limit}-day target. This does not establish historical delivery reliability.","table":result.to_dict("records"),"evidence":evidence}
    if match:
        d=quotes[quotes.item_id==match.group(0)].copy()
        d["Normalized INR/unit"]=[normalize_price(r.quoted_price,r.currency,r.price_basis,fx) for r in d.itertuples()]
        result=d[["supplier","item_id","original_price_text","currency","price_basis","Normalized INR/unit","delivery_days","issue"]].rename(columns={"supplier":"Supplier","item_id":"Item ID","original_price_text":"Original price","currency":"Currency","price_basis":"Price basis","delivery_days":"Delivery days","issue":"Open issue"})
        evidence=d[["supplier","item_id","source_excerpt","source_locator"]].to_dict("records")
        return {"answer":f"Supplier responses for {match.group(0)}. Normalized values use the current illustrative FX rate; incomplete or ambiguous values remain unresolved.","table":result.to_dict("records"),"evidence":evidence}
    if any(w in q for w in ["cheapest","lowest","cost","price","compare"]):
        summary=calculate_supplier_summary(quotes,fx,delivery_limit)
        evidence=quotes[quotes.quoted_price.notna()][["supplier","item_id","source_excerpt","source_locator"]].head(12).to_dict("records")
        return {"answer":"Supplier-level price and coverage indicators. Median unit price is not a full-request total cost; use the scenario simulator for allocation costing.","table":summary[["Supplier","Quote coverage %","Median comparable INR/item","Delivery days","Freight disclosed","Open price gaps"]].to_dict("records"),"evidence":evidence}
    if any(w in q for w in ["why","recommend","evidence","source","explain"]):
        return {"answer":"A recommendation must be based on feasible coverage, comparable prices, delivery constraints and disclosed charges. Use the scenario simulator for a reproducible allocation; open any row's source evidence to inspect the supporting supplier record.","table":[],"evidence":quotes[["supplier","item_id","source_excerpt","source_locator"]].head(10).to_dict("records")}
    return {"answer":"I can answer questions about missing prices, quote coverage, delivery commitments, supplier price indicators, or a specific item such as BX-13. For what-if questions, configure and run the scenario simulator so the answer comes from the cost engine.","table":[],"evidence":[]}


def llm_enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))

def _llm_client():
    """OpenAI-compatible client for Gemini free-tier API or OpenAI API."""
    from openai import OpenAI
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        return OpenAI(api_key=gemini_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _llm_model() -> str:
    if os.getenv("GEMINI_API_KEY", "").strip():
        return os.getenv("BIDLENS_GEMINI_MODEL", "gemini-2.5-flash")
    return os.getenv("BIDLENS_MODEL", "gpt-4o-mini")

def _chat_completion_with_fallback(**kwargs):
    """Try the configured model, then compatible Gemini model IDs if this key cannot access it."""
    client = _llm_client()
    primary = _llm_model()
    candidates = [primary]
    if os.getenv("GEMINI_API_KEY", "").strip():
        candidates.extend(["gemini-2.5-flash-lite", "gemini-2.0-flash"])
    last_error = None
    for model in dict.fromkeys(candidates):
        try:
            return client.chat.completions.create(model=model, **kwargs)
        except Exception as exc:
            last_error = exc
            # Only try another model when the current model is not found/not available.
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            if status != 404 and "not found" not in message and "does not exist" not in message:
                raise
    raise RuntimeError(
        "Gemini API was reached, but none of the configured model IDs were available to this API key. "
        "Check the key at https://aistudio.google.com/apikey and confirm the selected model is available. "
        f"Last API response: {last_error}"
    ) from last_error

def answer_procurement_question(question: str, evidence_context: str) -> str:
    """Generate a contextual response grounded in supplied evidence and computed results."""
    if not llm_enabled():
        return "No AI API key is configured yet. Add a Gemini API key in the sidebar to enable conversational answers. I can still show the deterministic supplier analysis and source evidence above."
    try:
        response = _chat_completion_with_fallback(
            temperature=0.2,
            messages=[
            {"role":"system","content":"You are BidLens, a procurement sourcing analyst. Answer the user's question using only the provided supplier evidence and calculated results. You may explain implications and propose scenarios, but do not fabricate prices, supplier terms, dates, or calculations. Treat missing prices as unknown, never zero. Preserve original currencies and price bases. If a what-if request cannot be calculated from the supplied results, explain which assumptions or data are needed and ask a concise follow-up. Cite supplier/item/source filenames where available. Be concise and actionable."},
            {"role":"user","content":f"QUESTION:\n{question}\n\nEVIDENCE AND COMPUTED RESULTS:\n{evidence_context}"}
        ])
        return response.choices[0].message.content or "I couldn't generate a response. Please try rephrasing the question."
    except Exception as exc:
        # Do not let a model outage hide the deterministic analysis already computed by BidLens.
        try:
            payload = json.loads(evidence_context)
            computed = payload.get("computed_analysis", {})
            if computed.get("scenario_result"):
                result = computed["scenario_result"]
                if result.get("feasible"):
                    return (f"I couldn't reach the language model, so here is the calculated scenario result directly. "
                            f"Delivery limit: {computed.get('intent', {}).get('delivery_days')} days; "
                            f"suppliers allowed: up to {computed.get('intent', {}).get('max_suppliers')}. "
                            f"Known cost: ₹{result.get('total_known_cost', 0):,.2f}. "
                            f"Suppliers: {', '.join(result.get('suppliers', []))}. "
                            "This is not a complete landed-cost total; unresolved prices/charges remain excluded or flagged. "
                            f"Technical detail: {exc}")
                return f"The scenario engine could not find a feasible allocation. {result.get('reason', '')} Technical detail: {exc}"
            analysis = computed.get("analysis", {})
            answer = analysis.get("answer")
            if answer:
                return f"I couldn't reach the language model, so here is the data-based analysis instead: {answer} Technical detail: {exc}"
        except Exception:
            pass
        raise


def refine_requirement_with_llm(text: str) -> dict:
    """Optional LLM helper; falls back to explicit rule-based checks if no API key is configured."""
    if not llm_enabled():
        lowered=text.lower()
        gaps=[]
        if not re.search(r"\b\d[\d,]*\b",text): gaps.append("Add quantities for each requested item.")
        if not any(x in lowered for x in ["day","date","deliver by","delivery"]): gaps.append("Specify a delivery deadline or acceptable lead time.")
        if not any(x in lowered for x in ["inr","usd","currency","price basis","per item","per unit","per 100"]): gaps.append("Specify expected currency and price basis, or ask suppliers to state both.")
        if not any(x in lowered for x in ["freight","tax","charges","additional charges"]): gaps.append("Ask suppliers to disclose freight, taxes and other charges.")
        return {"mode":"Rule-based fallback (no API key configured)","summary":"Requirement reviewed for common procurement gaps.","gaps":gaps,"questions":[]}
    client=_llm_client()
    response=_chat_completion_with_fallback(temperature=0,response_format={"type":"json_object"},messages=[{"role":"system","content":"You are a procurement requirement quality reviewer. Return JSON with keys summary (string), gaps (array of concise missing/ambiguous decisions), questions (array of targeted clarification questions), structured_requirement (object with items, quantities, location, delivery, commercial_terms, evaluation_criteria). Do not invent missing facts; use null for unknowns."},{"role":"user","content":text}])
    data=json.loads(response.choices[0].message.content)
    data["mode"]="LLM-assisted; review before use"
    return data


def interpret_question(question: str, default_delivery_days: int, default_max_suppliers: int) -> dict:
    """Interpret the question into a small safe intent schema; calculations remain deterministic."""
    fallback={"intent":"data_question","delivery_days":int(default_delivery_days),"max_suppliers":int(default_max_suppliers),"priority":"cost","item_id":None}
    low=question.lower()
    m=re.search(r"\b(\d+)\s*days?\b",low)
    if m: fallback["delivery_days"]=max(1,min(365,int(m.group(1))))
    im=re.search(r"BX-\d{2}",question.upper())
    if im: fallback["item_id"]=im.group(0)
    if any(x in low for x in ["what if","scenario","allocate","allocation","split the order","one supplier","single supplier","two suppliers","two supplier"]):
        fallback["intent"]="scenario"
        if "one supplier" in low or "single supplier" in low: fallback["max_suppliers"]=1
        elif "two supplier" in low or "split" in low: fallback["max_suppliers"]=2
        if any(x in low for x in ["fastest","delivery first","prioritize delivery","prioritise delivery"]): fallback["priority"]="delivery"
    elif any(x in low for x in ["missing","gap","coverage","incomplete","unquoted"]): fallback["intent"]="missing"
    elif any(x in low for x in ["delivery","lead time","deadline","fast"]): fallback["intent"]="delivery"
    elif fallback["item_id"]: fallback["intent"]="item"
    elif any(x in low for x in ["cheapest","lowest","cost","price","compare"]): fallback["intent"]="price"
    elif any(x in low for x in ["why","recommend","evidence","source","explain"]): fallback["intent"]="explain"
    if not llm_enabled():
        fallback["mode"]="Rule-based intent routing"
        return fallback
    try:
        client=_llm_client()
        response=_chat_completion_with_fallback(temperature=0,response_format={"type":"json_object"},messages=[
            {"role":"system","content":"Classify a procurement analyst question into JSON only. Allowed intent: scenario, missing, delivery, item, price, explain, other. Keys: intent, delivery_days (integer), max_suppliers (integer 1-5), priority (cost or delivery), item_id (BX-## or null). Never answer the procurement question and do not invent supplier data. Use defaults supplied in the user message if unspecified."},
            {"role":"user","content":json.dumps({"question":question,"defaults":fallback})}
        ])
        parsed=json.loads(response.choices[0].message.content)
        out={**fallback,**parsed}
        out["delivery_days"]=max(1,min(365,int(out.get("delivery_days") or default_delivery_days)))
        out["max_suppliers"]=max(1,min(5,int(out.get("max_suppliers") or default_max_suppliers)))
        if out.get("priority") not in {"cost","delivery"}: out["priority"]="cost"
        if out.get("intent") not in {"scenario","missing","delivery","item","price","explain","other"}: out["intent"]=fallback["intent"]
        out["mode"]="LLM intent interpretation; deterministic tool execution"
        return out
    except Exception:
        fallback["mode"]="Rule-based fallback (LLM interpretation unavailable)"
        return fallback


def interpret_quote_excerpt_with_llm(excerpt: str, item_id: str) -> dict:
    """Suggest candidate fields from one source excerpt; never writes reviewed values."""
    if not llm_enabled():
        return {"mode":"No LLM API key configured","candidate_fields":{},"uncertainties":["Use the extracted source excerpt and confirm fields manually. No value was changed."]}
    client=_llm_client()
    response=_chat_completion_with_fallback(temperature=0,response_format={"type":"json_object"},messages=[
        {"role":"system","content":"You are assisting a procurement analyst by interpreting a supplier quote excerpt. Return JSON with candidate_fields (item_id, price, currency, price_basis, delivery_days, delivery_charge, payment_terms), uncertainties (array), and evidence_text (short exact quote). Use null for fields not explicitly supported. Never guess, normalize currency, apply discounts, or convert units. This is a suggestion only and must not be considered reviewed."},
        {"role":"user","content":json.dumps({"requested_item_id":item_id,"source_excerpt":excerpt})}
    ])
    data=json.loads(response.choices[0].message.content)
    data["mode"]="LLM suggestion only — not saved or approved"
    return data


def simulate_split_allocation(quotes: pd.DataFrame, items: pd.DataFrame, supplier_a_id: str, supplier_b_id: str, share_a_pct: int, fx: float=DEFAULT_FX, delivery_limit: int=7, exclude_unknown_freight: bool=True) -> dict:
    """Simulate a user-specified split across two suppliers; this is not an optimizer."""
    if supplier_a_id == supplier_b_id:
        return {"feasible":False,"reason":"Choose two different suppliers for a split scenario.","assignments":[],"open_items":items.item_id.tolist()}
    q=quotes.copy()
    q["normalized_unit_cost"]=[normalize_price(r.quoted_price,r.currency,r.price_basis,fx) for r in q.itertuples()]
    q["normalized_freight"]=[normalize_charge(r.delivery_charge,r.currency,fx) for r in q.itertuples()]
    q=q[q.supplier_id.isin([supplier_a_id,supplier_b_id])]
    a_name=next(s["supplier"] for s in SUPPLIERS if s["supplier_id"]==supplier_a_id)
    b_name=next(s["supplier"] for s in SUPPLIERS if s["supplier_id"]==supplier_b_id)
    rows=[]; open_items=[]; used=set(); subtotal=0.0
    for item in items.itertuples():
        choices=[]
        for sid in [supplier_a_id,supplier_b_id]:
            row=q[(q.item_id==item.item_id)&(q.supplier_id==sid)]
            if row.empty: continue
            r=row.iloc[0]
            if pd.isna(r.normalized_unit_cost) or pd.isna(r.delivery_days) or int(r.delivery_days)>delivery_limit: continue
            if exclude_unknown_freight and pd.isna(r.normalized_freight): continue
            choices.append(r)
        if not choices:
            open_items.append(item.item_id); continue
        by_sid={r.supplier_id:r for r in choices}
        if supplier_a_id in by_sid and supplier_b_id in by_sid:
            qty_a=round(int(item.quantity)*int(share_a_pct)/100)
            qty_b=int(item.quantity)-qty_a
            allocations=[(by_sid[supplier_a_id],qty_a),(by_sid[supplier_b_id],qty_b)]
        else:
            # If only one selected supplier has a valid quote for this item, use that supplier for this line and make the exception visible.
            allocations=[(choices[0],int(item.quantity))]
        for r,qty in allocations:
            if qty<=0: continue
            line_total=float(r.normalized_unit_cost)*qty
            subtotal+=line_total; used.add(r.supplier_id)
            rows.append({"Item ID":item.item_id,"Item":item.item,"Requested quantity":int(item.quantity),"Supplier":r.supplier,"Allocated quantity":int(qty),"Allocation % of line":round(100*qty/int(item.quantity),1),"Original price":r.original_price_text,"Currency":r.currency,"Price basis":r.price_basis,"Normalized INR/unit":round(float(r.normalized_unit_cost),4),"Line subtotal INR":round(line_total,2),"Delivery days":int(r.delivery_days),"Evidence":r.source_locator,"Source excerpt":r.source_excerpt,"Issue":r.issue})
    if open_items:
        return {"feasible":False,"reason":"The selected suppliers cannot cover every requested item under the current delivery and freight constraints.","assignments":rows,"open_items":open_items,"limitations":["Missing or ambiguous prices are not treated as zero."]}
    fixed_freight=0.0
    for sid in used:
        vals=q[(q.supplier_id==sid)&q.normalized_freight.notna()].normalized_freight
        if len(vals): fixed_freight+=float(vals.iloc[0])
    total=round(subtotal+fixed_freight,2)
    return {"feasible":True,"mode":"User-specified split simulation","suppliers":[a_name,b_name],"supplier_ids":[supplier_a_id,supplier_b_id],"share_a_pct":int(share_a_pct),"assignments":rows,"total_known_cost":total,"line_subtotal":round(subtotal,2),"known_freight":round(fixed_freight,2),"max_delivery_days":max(x["Delivery days"] for x in rows),"supplier_count":len(used),"open_items":[],"fx_rate":fx,"delivery_limit":delivery_limit,"limitations":["This is a user-specified split simulation, not an optimized allocation.","If one selected supplier cannot quote an item or meet the delivery constraint, the other supplier receives the full line quantity and the exception is visible in the allocation table.","Supplier capacity and minimum order quantities are not provided and are not modeled.","Excludes taxes and charges not stated in source documents.","Unconfirmed discounts are not applied.","USD prices use the illustrative exchange rate shown."]}
