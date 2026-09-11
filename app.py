import streamlit as st
import pandas as pd
import requests, sqlite3, hashlib, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from io import BytesIO
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

st.set_page_config(page_title="RegIntel", page_icon="🇮🇳", layout="wide")

# -----------------------------
# STYLE: simple RA workbench
# -----------------------------
st.markdown("""
<style>
.main .block-container {max-width: 1250px; padding-top: 1.2rem;}
h1 {margin-bottom: .1rem;}
.small {font-size:.82rem; color:#6b7280;}
.card {border:1px solid #e5e7eb; border-radius:10px; padding:14px 16px; margin:8px 0; background:#fff;}
.badge {display:inline-block; padding:3px 8px; border-radius:999px; font-size:.75rem; font-weight:600; margin-right:5px;}
.high {background:#fee2e2; color:#991b1b;}
.medium {background:#fef3c7; color:#92400e;}
.low {background:#e5e7eb; color:#374151;}
.review {background:#dbeafe; color:#1e40af;}
.action {background:#dcfce7; color:#166534;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# OFFICIAL CDSCO SOURCES
# -----------------------------
SOURCES = {
    "Gazette Notifications": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Gazette-Notifications/",
    "Circulars": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
    "Public Notices": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
}

PRODUCTS = {
    "Oral Solids": ["tablet", "tablets", "capsule", "capsules", "oral solid", "oral dosage", "oral"],
    "Oral Liquids": ["syrup", "suspension", "solution", "oral liquid", "oral"],
    "Sterile Injectables": ["injection", "injectable", "parenteral", "sterile", "infusion"],
    "Biologics / Vaccines": ["biologic", "biosimilar", "vaccine", "serum", "recombinant", "monoclonal"],
    "APIs": ["api", "active pharmaceutical ingredient", "bulk drug", "active ingredient"],
    "Topical / Semisolid": ["cream", "ointment", "gel", "lotion", "topical", "dermal"],
}
TOPICS = {
    "GMP / Manufacturing": ["schedule m", "gmp", "manufacturing", "good manufacturing", "quality system"],
    "Clinical / New Drugs": ["clinical trial", "new drug", "ndct", "phase i", "phase ii", "phase iii", "phase iv"],
    "Pharmacovigilance / Safety": ["pharmacovigilance", "adverse drug", "safety", "post marketing", "pvpi"],
    "Import / Registration": ["import", "registration", "sugam", "marketing authorization", "permission"],
    "Quality / FDC": ["fdc", "quality", "pharmacopoeia", "standard", "specification"],
}

TRIGGERS = {
    "Critical": ["ban", "prohibited", "suspension", "recall", "cancellation", "spurious", "unapproved"],
    "High": ["mandatory", "shall", "amendment", "schedule m", "schedule h1", "new requirement",
             "notification", "license", "compliance", "withdrawal"],
}

DB = "regintel_v3.db"

def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS documents(
        id TEXT PRIMARY KEY, source TEXT, title TEXT, published_date TEXT,
        url TEXT, doc_type TEXT, raw_text TEXT, priority TEXT,
        relevance INTEGER, matched_products TEXT, matched_topics TEXT,
        status TEXT DEFAULT 'Needs Review', created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS actions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, action TEXT,
        owner TEXT, due_date TEXT, status TEXT DEFAULT 'Open', created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, event TEXT, details TEXT
    )""")
    c.commit()
    return c

conn = db()

def clean(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()

def date_from_text(x):
    m = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", x)
    if m:
        return m.group(1).replace("/", "-").replace(".", "-")
    return ""

def classify(title, text, source):
    s = (title + " " + text).lower()
    matched_products = [p for p, kws in PRODUCTS.items() if any(k in s for k in kws)]
    matched_topics = [t for t, kws in TOPICS.items() if any(k in s for k in kws)]

    priority = "Low"
    for level in ["Critical", "High"]:
        if any(k in s for k in TRIGGERS[level]):
            priority = level
            break
    if priority == "Low" and matched_topics:
        priority = "Medium"

    return priority, matched_products, matched_topics

def relevance(title, text, source, selected_products, selected_topics):
    s = (title + " " + text).lower()
    score = 0
    reasons = []

    if selected_products:
        product_hits = []
        for p in selected_products:
            hits = sum(1 for k in PRODUCTS[p] if k in s)
            if hits:
                product_hits.append(p)
        if product_hits:
            score += min(55, 20 + 10 * len(product_hits))
            reasons.append("Product match: " + ", ".join(product_hits))
    else:
        score += 10

    if selected_topics:
        topic_hits = []
        for t in selected_topics:
            hits = sum(1 for k in TOPICS[t] if k in s)
            if hits:
                topic_hits.append(t)
        if topic_hits:
            score += min(35, 15 + 7 * len(topic_hits))
            reasons.append("Topic match: " + ", ".join(topic_hits))
    else:
        score += 5

    if source in ["Gazette Notifications", "Circulars"]:
        score += 10
    elif source == "Public Notices":
        score += 5

    return min(score, 100), reasons


def extract_document_text(url):
    """Read a linked official PDF when available; otherwise return empty text.
    The official source page remains the authority."""
    if not url or not url.lower().split("?")[0].endswith(".pdf") or PdfReader is None:
        return ""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 RegIntel/3.1"},
                         timeout=30)
        r.raise_for_status()
        reader = PdfReader(BytesIO(r.content))
        pages = []
        for page in reader.pages[:20]:
            try:
                pages.append(clean(page.extract_text() or ""))
            except Exception:
                pass
        return clean(" ".join(pages))[:50000]
    except Exception:
        return ""

def parse_source(name, url):
    headers = {"User-Agent": "Mozilla/5.0 RegIntel/3.0"}
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []

    # Prefer tables because CDSCO notification pages commonly expose lists as tables.
    for tr in soup.find_all("tr"):
        cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["td","th"])]
        links = [a.get("href") for a in tr.find_all("a", href=True)]
        if len(cells) >= 2:
            title = max(cells, key=len)
            if title.lower() in ["title", "subject", "description"]:
                continue
            href = links[0] if links else url
            if href.startswith("/"):
                href = "https://www.cdsco.gov.in" + href
            elif href.startswith("http") is False:
                href = url.rstrip("/") + "/" + href.lstrip("/")
            date = next((date_from_text(c) for c in cells if date_from_text(c)), "")
            rows.append({"source": name, "title": title, "published_date": date,
                         "url": href, "doc_type": name.rstrip("s")})
    # Fallback: collect meaningful linked headings if table parsing found nothing.
    if not rows:
        for a in soup.find_all("a", href=True):
            txt = clean(a.get_text(" ", strip=True))
            if len(txt) >= 18:
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.cdsco.gov.in" + href
                elif not href.startswith("http"):
                    href = url.rstrip("/") + "/" + href.lstrip("/")
                rows.append({"source": name, "title": txt, "published_date": date_from_text(txt),
                              "url": href, "doc_type": name.rstrip("s")})
    # Deduplicate
    out, seen = [], set()
    for x in rows:
        key = (x["title"].lower(), x["published_date"], x["url"])
        if key not in seen:
            seen.add(key); out.append(x)
    return out[:150]

def sync(selected_products, selected_topics):
    found = []
    errors = []
    for name, url in SOURCES.items():
        try:
            found.extend(parse_source(name, url))
        except Exception as e:
            errors.append(f"{name}: {e}")

    new_count = 0
    relevant_count = 0

    for item in found:
        # Read official PDF text where a PDF is directly linked.
        raw_text = extract_document_text(item["url"])
        analysis_text = clean(item["title"] + " " + raw_text)

        rid = hashlib.sha256(
            (item["source"] + "|" + item["title"] + "|" +
             item["published_date"] + "|" + item["url"]).encode()
        ).hexdigest()[:24]

        priority, mp, mt = classify(item["title"], analysis_text, item["source"])
        score, reasons = relevance(
            item["title"], analysis_text, item["source"],
            selected_products, selected_topics
        )

        # Relevant = enough evidence of a company/product/topic relationship.
        status = "Needs Review" if score >= 40 else "Informational"

        cur = conn.execute("SELECT id FROM documents WHERE id=?", (rid,))
        exists = cur.fetchone() is not None

        if not exists:
            conn.execute("""INSERT INTO documents
                (id,source,title,published_date,url,doc_type,raw_text,priority,relevance,
                 matched_products,matched_topics,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, item["source"], item["title"], item["published_date"],
                 item["url"], item["doc_type"], analysis_text, priority, score,
                 "; ".join(mp), "; ".join(mt), status,
                 datetime.now(timezone.utc).isoformat()))
            new_count += 1

        if score >= 40:
            relevant_count += 1

    conn.execute(
        "INSERT INTO audit(timestamp,event,details) VALUES(?,?,?)",
        (datetime.now(timezone.utc).isoformat(), "CDSCO_SYNC",
         f"Checked {len(found)} source records; {relevant_count} matched current profile; {new_count} new records stored.")
    )
    conn.commit()
    return len(found), relevant_count, new_count, errors

# -----------------------------
# SIDEBAR: ONLY REAL PROFILE INPUTS
# -----------------------------
with st.sidebar:
    st.title("RegIntel")
    st.caption("AI-assisted Regulatory Intelligence")
    company = st.text_input("Company", "My Pharmaceutical Company")
    st.divider()
    selected_products = st.multiselect(
        "Products / manufacturing",
        list(PRODUCTS.keys()),
        default=["Oral Solids"]
    )
    selected_topics = st.multiselect(
        "Regulatory interests",
        list(TOPICS.keys()),
        default=["GMP / Manufacturing", "Clinical / New Drugs"]
    )
    st.divider()
    st.caption("V3 scope: India • CDSCO")
    st.caption("Official source = authority. RegIntel = decision support.")

# -----------------------------
# MAIN
# -----------------------------
st.title("🇮🇳 RegIntel")
st.write("**Show me what matters to my company — not everything the regulator publishes.**")
st.caption(f"{company}  •  India / CDSCO  •  Products: {', '.join(selected_products) or 'None'}")

if st.button("🔄 Check CDSCO for new updates", type="primary"):
    with st.spinner("Checking official CDSCO sources..."):
        total, relevant, new, errors = sync(selected_products, selected_topics)
    st.success(f"Checked {total} CDSCO records • {relevant} matched your current profile • {new} new records stored.")
    for e in errors:
        st.warning(e)

df = pd.read_sql_query("SELECT * FROM documents ORDER BY published_date DESC, created_at DESC", conn)

# Re-score current database against current profile on every rerun.
if not df.empty:
    def current_score(row):
        score, _ = relevance(
            row["title"],
            row["raw_text"],
            row["source"],
            selected_products,
            selected_topics
        )
        return score
    df["current_relevance"] = df.apply(current_score, axis=1)

    # Only relevant items enter the intelligence feed.
    feed = df[df["current_relevance"] >= 40].copy()
    feed["current_priority"] = feed.apply(
        lambda r: classify(r["title"], r["raw_text"], r["source"])[0], axis=1
    )
else:
    feed = df.copy()

# KPI row
total_found = len(df)
relevant = len(feed)
high = len(feed[feed["current_priority"].isin(["Critical","High"])]) if not feed.empty else 0
review = len(feed[feed["status"] == "Needs Review"]) if not feed.empty else 0
open_actions = pd.read_sql_query("SELECT * FROM actions WHERE status != 'Completed'", conn)
actions_n = len(open_actions)

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("CDSCO records found", total_found)
c2.metric("Relevant to me", relevant)
c3.metric("Critical / High", high)
c4.metric("Needs RA review", review)
c5.metric("Open actions", actions_n)

st.divider()
st.subheader("Relevant Regulatory Updates")

if feed.empty:
    st.info("No relevant CDSCO updates for the current product and regulatory-interest profile. Change the profile or check CDSCO again.")
else:
    feed = feed.sort_values(["current_priority","current_relevance","published_date"],
                            key=lambda s: s.map({"Critical":0,"High":1,"Medium":2,"Low":3}) if s.name=="current_priority" else s,
                            ascending=[True,False,False])
    for _, row in feed.head(50).iterrows():
        p = row["current_priority"]
        cls = p.lower()
        with st.expander(f"{'🔴' if p=='Critical' else '🟠' if p=='High' else '🟡' if p=='Medium' else '⚪'} {row['title']}"):
            st.markdown(
                f"<span class='badge {cls}'>{p}</span>"
                f"<span class='badge review'>{row['current_relevance']}/100 relevant</span>"
                f"<span class='small'>{row['source']} • {row['published_date']}</span>",
                unsafe_allow_html=True)
            mp = row.get("matched_products","") or "Current profile match"
            mt = row.get("matched_topics","") or "Regulatory relevance"
            st.write(f"**Why it is here:** {mp} • {mt}")
            st.write("**RegIntel interpretation:** This item matches your current company/product/regulatory profile and should be assessed by RA.")
            st.write(f"**Status:** {row['status']}")
            st.link_button("Open official CDSCO source", row["url"])
            col1,col2,col3 = st.columns([1,1,2])
            with col1:
                if st.button("Mark Action Required", key=f"act_{row['id']}"):
                    conn.execute("UPDATE documents SET status='Action Required' WHERE id=?", (row["id"],))
                    conn.execute("INSERT INTO actions(doc_id,action,owner,status,created_at) VALUES(?,?,?,?,?)",
                                 (row["id"],"Assess regulatory impact and determine required action.","RA","Open",
                                  datetime.now(timezone.utc).isoformat()))
                    conn.commit(); st.rerun()
            with col2:
                if st.button("Mark Not Relevant", key=f"nr_{row['id']}"):
                    conn.execute("UPDATE documents SET status='Not Relevant' WHERE id=?", (row["id"],))
                    conn.commit(); st.rerun()

st.divider()
with st.expander("System details"):
    st.write("**Purpose:** discover → filter → interpret → RA review → action.")
    st.write("**Important:** Relevance is a screening aid, not a regulatory conclusion. Final applicability/compliance decisions remain with qualified RA.")
    st.write("**Official sources monitored:** CDSCO Gazette Notifications, Circulars, Public Notices.")
