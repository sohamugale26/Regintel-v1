import hashlib
import json
import sqlite3
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
from openai import OpenAI

# Government sites often have broken SSL chains; warnings are suppressed (see note in sidebar).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="RegIntel | Regulatory Intelligence", layout="wide", page_icon="🛡️")

CDSCO_URL = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"
STATUS_OPTIONS = ["Pending Review", "Action Required", "Informational", "Not Relevant"]
STATUS_ICONS = {"Pending Review": "⏳", "Action Required": "🚨", "Informational": "ℹ️", "Not Relevant": "🗑️"}

# ------------------------------------------------------------------ STYLING
st.markdown(
    """
    <style>
    .hero {background: linear-gradient(120deg,#0f2027,#203a43,#2c5364); padding: 28px 32px;
           border-radius: 18px; color: #fff; margin-bottom: 18px;}
    .hero h1 {margin: 0; font-size: 2.1rem;}
    .hero p {margin: 6px 0 0; opacity: .85; font-size: 1.02rem;}
    .pill {display:inline-block; padding:2px 12px; border-radius:999px; font-size:.78rem;
           font-weight:600; margin-right:6px; color:#fff;}
    .pill-high {background:#e53935;} .pill-med {background:#fb8c00;} .pill-low {background:#43a047;}
    .pill-topic {background:#3949ab;}
    div[data-testid="stMetric"] {background: rgba(120,140,170,.10); border: 1px solid rgba(120,140,170,.25);
           padding: 14px 18px; border-radius: 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ DATABASE
@st.cache_resource
def get_conn():
    # check_same_thread=False: Streamlit runs callbacks on different threads.
    conn = sqlite3.connect("regintel_master.db", check_same_thread=False)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS updates
           (id TEXT PRIMARY KEY, authority TEXT, title TEXT, date TEXT, url TEXT, topic TEXT,
            summary TEXT, impact TEXT, relevance_score INTEGER, status TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS audit_logs
           (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, action TEXT, user TEXT, timestamp TEXT)"""
    )
    conn.commit()
    return conn


conn = get_conn()


# ------------------------------------------------------------------ SIDEBAR
st.sidebar.title("🏢 Company Profile")
company_name = st.sidebar.text_input("Company Name", "Nova Formulation Ltd.")
markets = st.sidebar.multiselect("Markets", ["India (CDSCO)", "EU (EMA)"], ["India (CDSCO)"])
products = st.sidebar.multiselect("Products", ["Injectables", "Oral Solids", "Biologics"], ["Injectables"])
topics = st.sidebar.multiselect(
    "Topics", ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance"], ["GMP", "Stability"]
)

st.sidebar.divider()
st.sidebar.subheader("⚙️ AI Settings")
api_key = st.sidebar.text_input("OpenAI API Key (optional)", type="password")
if api_key:
    st.sidebar.success("AI mode: GPT-4o-mini")
else:
    st.sidebar.info("Free mode: rule-based scoring against your company profile.")
st.sidebar.caption("⚠️ SSL verification is disabled for CDSCO requests (government certificate issues).")

if "EU (EMA)" in markets:
    st.sidebar.warning("EMA monitoring isn't implemented yet. Only CDSCO is scraped.")

profile_context = f"Company: {company_name}; Markets: {markets}; Products: {products}; Topics: {topics}"


# ------------------------------------------------------------------ ANALYSIS ENGINE
TOPIC_KEYWORDS = {
    "GMP": ["gmp", "schedule m", "manufactur", "inspection", "sterile", "good manufacturing", "audit"],
    "Clinical Trials": ["clinical", "trial", "ethics committee", "bioavailability", "bioequivalence"],
    "Stability": ["stability", "shelf life", "shelf-life", "storage", "climatic"],
    "Pharmacovigilance": ["pharmacovigilance", "adverse", "adr", "psur", "safety"],
}
PRODUCT_KEYWORDS = {
    "Injectables": ["injectable", "parenteral", "sterile", "vial", "infusion"],
    "Oral Solids": ["tablet", "capsule", "oral solid"],
    "Biologics": ["biologic", "biosimilar", "vaccine", "monoclonal", "rdna"],
}
URGENCY_WORDS = ["mandatory", "deadline", "immediate", "amendment", "gazette", "withdrawal", "recall", "ban"]


def rule_based_analysis(title: str) -> dict:
    """Free fallback: transparent keyword scoring against the sidebar profile."""
    t = title.lower()
    detected = next((tp for tp, kws in TOPIC_KEYWORDS.items() if any(k in t for k in kws)), "General Regulatory")
    score = 30
    reasons = []
    if detected in topics:
        score += 30
        reasons.append(f"matches your topic '{detected}'")
    for p in products:
        if any(k in t for k in PRODUCT_KEYWORDS.get(p, [])):
            score += 15
            reasons.append(f"mentions {p.lower()}")
    if any(w in t for w in URGENCY_WORDS):
        score += 10
        reasons.append("contains urgency language")
    score = min(score, 100)
    impact = "High" if score >= 80 else "Medium" if score >= 50 else "Low"
    why = "; ".join(reasons) if reasons else "no direct match with your profile"
    return {
        "topic": detected,
        "summary": f"Rule-based screening: {why}.",
        "impact": impact,
        "relevance": score,
    }


def analyze_regulatory_update(title: str, authority: str) -> dict:
    if not api_key:
        return rule_based_analysis(title)

    prompt = f"""Analyze this {authority} regulatory update: '{title}'.
Company context: {profile_context}.
Return JSON with exactly these keys:
'topic' (string), 'summary' (1 sentence on what changed), 'impact' (High, Medium or Low),
'relevance' (integer 0-100 for this company)."""
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert Regulatory Intelligence analyst."},
                {"role": "user", "content": prompt},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        impact = str(data.get("impact", "Low")).capitalize()
        return {
            "topic": str(data.get("topic") or "General Regulatory"),
            "summary": str(data.get("summary") or "No summary returned."),
            "impact": impact if impact in ("High", "Medium", "Low") else "Low",
            "relevance": max(0, min(100, int(data.get("relevance", 0)))),
        }
    except Exception as e:  # don't store error rows; fall back and tell the user
        st.warning(f"AI call failed ({e}). Used rule-based scoring instead.")
        return rule_based_analysis(title)


# ------------------------------------------------------------------ SOURCE MONITOR
def normalize_date(raw: str) -> str:
    """Store ISO dates so ORDER BY date sorts correctly."""
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d")


def make_id(authority: str, date_iso: str, title: str) -> str:
    # hashlib is stable across runs (built-in hash() is randomized per process -> duplicates).
    digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    return f"{authority}-{date_iso.replace('-', '')}-{digest}"


def insert_update(c, authority, title, date_iso, url):
    uid = make_id(authority, date_iso, title)
    c.execute("SELECT 1 FROM updates WHERE id=?", (uid,))
    if c.fetchone():
        return False
    ai = analyze_regulatory_update(title, authority)
    c.execute(
        """INSERT INTO updates (id, authority, title, date, url, topic, summary, impact, relevance_score, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, authority, title, date_iso, url, ai["topic"], ai["summary"], ai["impact"], ai["relevance"], "Pending Review"),
    )
    return True


def scrape_cdsco(limit: int = 10) -> int:
    c = conn.cursor()
    added = 0
    try:
        res = requests.get(CDSCO_URL, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        rows = [r for r in soup.find_all("tr") if len(r.find_all("td")) >= 3][:limit]
        if not rows:
            st.warning("No notice rows found. The CDSCO page layout may have changed or the site blocked the request.")
            return 0
        for row in rows:
            cols = row.find_all("td")
            title = cols[1].get_text(" ", strip=True)
            date_iso = normalize_date(cols[2].get_text(strip=True))
            link = row.find("a", href=True)
            url = urljoin(CDSCO_URL, link["href"]) if link else CDSCO_URL
            if title and insert_update(c, "CDSCO", title, date_iso, url):
                added += 1
        conn.commit()
    except requests.RequestException as e:
        st.error(f"Source Monitor could not reach CDSCO: {e}")
    except Exception as e:
        st.error(f"Source Monitor error: {e}")
    return added


SAMPLE_NOTICES = [
    ("Draft amendment to Schedule M: revised GMP requirements for sterile manufacturing", "2026-09-28"),
    ("Stability study guidelines update for climatic zone IVb – injectable formulations", "2026-09-15"),
    ("Mandatory reporting timelines for adverse drug reactions (PSUR) – notice", "2026-08-30"),
    ("Clinical trial ethics committee registration – procedural clarification", "2026-08-12"),
    ("Public notice: Fee revision for import licence applications", "2026-07-21"),
]


def load_sample_data() -> int:
    c = conn.cursor()
    added = sum(insert_update(c, "CDSCO (Sample)", t, d, CDSCO_URL) for t, d in SAMPLE_NOTICES)
    conn.commit()
    return added


def update_status(update_id: str, widget_key: str):
    new_status = st.session_state[widget_key]
    c = conn.cursor()
    c.execute("UPDATE updates SET status=? WHERE id=?", (new_status, update_id))
    c.execute(
        "INSERT INTO audit_logs (update_id, action, user, timestamp) VALUES (?, ?, ?, ?)",
        (update_id, f"Status → {new_status}", "RA Professional", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


# ------------------------------------------------------------------ HEADER + ACTIONS
st.markdown(
    f"""<div class="hero"><h1>🛡️ RegIntel Master Platform</h1>
    <p>Regulatory intelligence for <b>{company_name}</b> — monitor, score and triage notices in one place.</p></div>""",
    unsafe_allow_html=True,
)

b1, b2, _ = st.columns([1.2, 1.2, 3])
if b1.button("🔄 Run Source Monitor", type="primary", use_container_width=True):
    with st.spinner("Monitoring CDSCO and analysing notices..."):
        n = scrape_cdsco()
    if n:
        st.toast(f"{n} new notice(s) discovered", icon="✅")
        st.balloons()
    else:
        st.toast("No new notices found", icon="ℹ️")
if b2.button("🧪 Load Sample Data", use_container_width=True):
    n = load_sample_data()
    st.toast(f"{n} sample notice(s) added", icon="🧪")

df = pd.read_sql_query("SELECT * FROM updates ORDER BY date DESC", conn)
df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0).astype(int)

# ------------------------------------------------------------------ KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("📚 Total Updates", len(df))
k2.metric("🔥 High Relevance (≥80)", int((df["relevance_score"] >= 80).sum()))
k3.metric("⏳ Pending Reviews", int((df["status"] == "Pending Review").sum()))
k4.metric("🚨 Action Required", int((df["status"] == "Action Required").sum()))

tab_records, tab_insights, tab_audit = st.tabs(["📋 Records", "📊 Insights", "📑 Audit Trail"])

# ------------------------------------------------------------------ RECORDS
with tab_records:
    if df.empty:
        st.info("The knowledge base is empty. Click **Run Source Monitor** or **Load Sample Data** to get started.")
    else:
        f1, f2, f3 = st.columns([2, 2, 2])
        search = f1.text_input("🔎 Search titles", placeholder="e.g. stability, GMP...")
        status_filter = f2.multiselect("Status", STATUS_OPTIONS, default=STATUS_OPTIONS)
        min_rel = f3.slider("Minimum relevance", 0, 100, 0, step=5)

        view = df[df["status"].isin(status_filter) & (df["relevance_score"] >= min_rel)]
        if search:
            view = view[view["title"].str.contains(search, case=False, na=False)]

        st.download_button(
            "⬇️ Export filtered records (CSV)", view.to_csv(index=False).encode("utf-8"), "regintel_records.csv", "text/csv"
        )
        st.caption(f"Showing {len(view)} of {len(df)} records")

        for _, row in view.iterrows():
            score = row["relevance_score"]
            icon = "🔴" if score >= 80 else "🟡" if score >= 50 else "🟢"
            with st.expander(f"{icon} [{row['authority']}] {row['title']} — {row['date']}"):
                cls = {"High": "pill-high", "Medium": "pill-med"}.get(row["impact"], "pill-low")
                st.markdown(
                    f"<span class='pill {cls}'>Impact: {row['impact']}</span>"
                    f"<span class='pill pill-topic'>{row['topic']}</span>",
                    unsafe_allow_html=True,
                )
                meta_col, ai_col, action_col = st.columns([1.5, 2, 1.2])
                with meta_col:
                    st.markdown("**📄 Metadata**")
                    st.write("Document Type: Public Notice")
                    st.write(f"Date: {row['date']}")
                    st.markdown(f"[🔗 View Official Evidence]({row['url']})")
                with ai_col:
                    st.markdown("**🤖 Intelligence Engine**")
                    st.progress(score / 100, text=f"Relevance {score}/100")
                    st.write(row["summary"])
                with action_col:
                    st.markdown("**✅ RA Workflow**")
                    key = f"status_{row['id']}"
                    idx = STATUS_OPTIONS.index(row["status"]) if row["status"] in STATUS_OPTIONS else 0
                    st.selectbox(
                        "Decision",
                        STATUS_OPTIONS,
                        index=idx,
                        key=key,
                        format_func=lambda s: f"{STATUS_ICONS[s]} {s}",
                        on_change=update_status,
                        args=(row["id"], key),
                    )

# ------------------------------------------------------------------ INSIGHTS
with tab_insights:
    if df.empty:
        st.info("No data yet — insights appear once notices are loaded.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Workflow status**")
            st.bar_chart(df["status"].value_counts())
        with c2:
            st.markdown("**Notices by topic**")
            st.bar_chart(df["topic"].value_counts())
        st.markdown("**Relevance over time**")
        trend = df.assign(date=pd.to_datetime(df["date"], errors="coerce")).dropna(subset=["date"])
        if not trend.empty:
            st.line_chart(trend.sort_values("date").set_index("date")["relevance_score"])

# ------------------------------------------------------------------ AUDIT
with tab_audit:
    logs = pd.read_sql_query(
        "SELECT update_id AS 'Update', action AS 'Action', user AS 'User', timestamp AS 'Time' "
        "FROM audit_logs ORDER BY id DESC",
        conn,
    )
    if logs.empty:
        st.info("No decisions logged yet. Changing a record's status creates an audit entry.")
    else:
        st.dataframe(logs, width="stretch", hide_index=True)
