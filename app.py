import streamlit as st
import sqlite3
import requests
import pandas as pd
import hashlib
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from io import BytesIO

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

st.set_page_config(
    page_title="RegIntel — Regulatory Intelligence",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "analysis_started" not in st.session_state:
    st.session_state.analysis_started = False
if "latest_updates" not in st.session_state:
    st.session_state.latest_updates = []
if "sync_result" not in st.session_state:
    st.session_state.sync_result = None

# ============================================================
# CONFIGURATION
# ============================================================

DB_FILE = "regintel.db"

CDSCO_SOURCES = {
    "Gazette Notifications": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Gazette-Notifications/",
    "Circulars": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
    "Public Notices": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
    "New Drugs / NDCTR": "https://www.cdsco.gov.in/opencms/opencms/en/Drugs/New-Drugs/"
}

PRODUCT_HIERARCHY = {
    "Tablets": {
        "Antibiotics": ["antibiotic", "antimicrobial", "antibacterial"],
        "Antidiabetics": ["antidiabetic", "diabetes", "metformin", "glucose lowering"],
        "Antihypertensives": ["antihypertensive", "hypertension", "blood pressure"],
        "Gastro-retentive": ["gastro-retentive", "gastroretentive", "gastric retention", "floating tablet"],
        "Modified / Controlled Release": ["modified release", "controlled release", "extended release", "sustained release"],
        "Immediate Release": ["immediate release"],
        "Other": [],
    },
    "Capsules": {
        "Antibiotics": ["antibiotic", "antimicrobial", "antibacterial"],
        "Antidiabetics": ["antidiabetic", "diabetes", "metformin"],
        "Gastro-retentive": ["gastro-retentive", "gastroretentive", "gastric retention"],
        "Modified / Controlled Release": ["modified release", "controlled release", "extended release", "sustained release"],
        "Immediate Release": ["immediate release"],
        "Other": [],
    },
    "Oral Liquids": {
        "Syrups": ["syrup", "oral syrup"],
        "Suspensions": ["suspension"],
        "Solutions": ["oral solution", "oral liquid", "solution"],
        "Pediatric": ["pediatric", "paediatric"],
        "Antibiotics": ["antibiotic", "antimicrobial"],
        "Other": [],
    },
    "Injectables": {
        "Antibiotics": ["antibiotic", "antimicrobial"],
        "Biologics": ["biologic", "biosimilar"],
        "Vaccines": ["vaccine", "vaccination"],
        "General Parenterals": ["parenteral", "injectable", "injection"],
        "Other": [],
    },
    "Topicals / Semisolids": {
        "Creams": ["cream"],
        "Ointments": ["ointment"],
        "Gels": ["gel"],
        "Lotions": ["lotion"],
        "Antifungal": ["antifungal", "fungal"],
        "Antibacterial": ["antibacterial", "antimicrobial"],
        "Other": [],
    },
    "APIs / Bulk Drugs": {
        "Antibiotic APIs": ["antibiotic api", "antibiotic active", "antimicrobial api"],
        "Antidiabetic APIs": ["antidiabetic api", "metformin api"],
        "General APIs": ["active pharmaceutical ingredient", "bulk drug", "api"],
        "Other": [],
    },
    "Biologics / Vaccines": {
        "Vaccines": ["vaccine", "vaccination"],
        "Monoclonal Antibodies": ["monoclonal", "mab"],
        "Recombinant Products": ["recombinant"],
        "Biosimilars": ["biosimilar"],
        "Other": [],
    },
}

REGULATORY_DOMAINS = {
    "GMP / Manufacturing": [
        "gmp", "good manufacturing", "schedule m", "manufacturing",
        "quality system", "validation", "inspection", "manufacturing practice"
    ],
    "Clinical / New Drugs": [
        "clinical trial", "new drug", "ndct", "phase i", "phase ii",
        "phase iii", "phase iv", "clinical research"
    ],
    "Pharmacovigilance / Safety": [
        "pharmacovigilance", "adverse drug", "drug safety",
        "post marketing", "pvpi", "safety signal"
    ],
    "Import / Registration": [
        "import", "registration", "marketing authorization",
        "permission", "licence", "license", "sugam"
    ],
    "Quality / FDC": [
        "fdc", "quality", "pharmacopoeia", "standard",
        "specification", "fixed dose combination"
    ],
}

CRITICAL_WORDS = [
    "ban", "banned", "prohibited", "suspension", "suspended",
    "recall", "cancellation", "cancelled", "spurious", "unapproved",
]
HIGH_WORDS = [
    "mandatory", "shall", "amendment", "schedule m", "schedule h",
    "new requirement", "license", "licence", "compliance",
    "withdrawal", "notification", "requirement",
]

# ============================================================
# DATABASE
# ============================================================

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

conn = get_conn()

conn.executescript("""
CREATE TABLE IF NOT EXISTS company_profile (
    id INTEGER PRIMARY KEY CHECK(id=1),
    company_name TEXT,
    country TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS profile_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_field TEXT NOT NULL,
    secondary_field TEXT NOT NULL,
    notes TEXT DEFAULT '',
    UNIQUE(primary_field, secondary_field)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    published_date TEXT,
    url TEXT NOT NULL,
    doc_type TEXT,
    raw_text TEXT DEFAULT '',
    priority TEXT,
    relevance INTEGER DEFAULT 0,
    matched_products TEXT DEFAULT '',
    matched_domains TEXT DEFAULT '',
    match_reasons TEXT DEFAULT '',
    status TEXT DEFAULT 'Informational',
    first_seen TEXT,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    action TEXT NOT NULL,
    owner TEXT DEFAULT '',
    due_date TEXT DEFAULT '',
    status TEXT DEFAULT 'Open',
    created_at TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    event TEXT,
    details TEXT
);
""")
conn.commit()

# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def normalize_date(value):
    value = clean(value)
    if not value:
        return ""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", value)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
        except Exception:
            pass
    return ""

def parse_source_page(source, url):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 RegIntel/1.0"},
        timeout=30
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    records = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        href = a.get("href", "").strip()

        if not title or len(title) < 8:
            continue
        if title.lower() in {"home", "next", "previous", "download", "read more"}:
            continue

        absolute = requests.compat.urljoin(url, href)
        low = (title + " " + absolute).lower()

        signals = [
            ".pdf", "notification", "circular", "public notice", "gazette",
            "notice", "amendment", "schedule", "drug", "clinical", "gmp",
            "quality", "recall", "license", "licence"
        ]
        if not any(x in low for x in signals):
            continue

        key = (title.lower(), absolute.lower())
        if key in seen:
            continue
        seen.add(key)

        parent_text = clean(a.parent.get_text(" ", strip=True)) if a.parent else ""
        date_match = re.search(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            parent_text,
            re.I
        )
        date = normalize_date(date_match.group(0)) if date_match else ""
        doc_type = "PDF" if ".pdf" in absolute.lower() else "Web notice"

        records.append({
            "source": source,
            "title": title,
            "published_date": date,
            "url": absolute,
            "doc_type": doc_type,
        })

    return records

def extract_pdf(url):
    if PdfReader is None or not url.lower().split("?")[0].endswith(".pdf"):
        return ""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 RegIntel/1.0"},
            timeout=40
        )
        r.raise_for_status()
        reader = PdfReader(BytesIO(r.content))
        chunks = []
        for page in reader.pages[:30]:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                pass
        return clean(" ".join(chunks))[:100000]
    except Exception:
        return ""

def classify(title, text, source):
    s = clean(title + " " + text).lower()
    if any(x in s for x in CRITICAL_WORDS):
        priority = "Critical"
    elif any(x in s for x in HIGH_WORDS):
        priority = "High"
    else:
        priority = "Medium" if any(
            any(k in s for k in kws) for kws in REGULATORY_DOMAINS.values()
        ) else "Low"

    matched_domains = [
        d for d, kws in REGULATORY_DOMAINS.items()
        if any(k in s for k in kws)
    ]
    return priority, matched_domains

def calculate_relevance(title, text, selected_products, selected_domains):
    s = clean(title + " " + text).lower()
    score = 0
    reasons = []
    matched_products = []

    for primary, secondary in selected_products:
        primary_terms = []
        secondary_terms = PRODUCT_HIERARCHY.get(primary, {}).get(secondary, [])
        primary_map = {
            "Tablets": ["tablet", "tablets", "solid oral"],
            "Capsules": ["capsule", "capsules"],
            "Oral Liquids": ["oral liquid", "syrup", "suspension", "oral solution"],
            "Injectables": ["injectable", "injection", "parenteral", "sterile"],
            "Topicals / Semisolids": ["cream", "ointment", "gel", "lotion", "topical", "semisolid"],
            "APIs / Bulk Drugs": ["api", "active pharmaceutical ingredient", "bulk drug"],
            "Biologics / Vaccines": ["biologic", "biosimilar", "vaccine", "recombinant", "monoclonal"],
        }
        primary_terms = primary_map.get(primary, [])

        primary_hit = any(k in s for k in primary_terms)
        secondary_hit = any(k in s for k in secondary_terms) if secondary_terms else False

        if secondary_hit:
            score += 45
            matched_products.append(f"{primary} → {secondary}")
            reasons.append(f"Specific product match: {primary} → {secondary}")
        elif primary_hit:
            score += 25
            matched_products.append(primary)
            reasons.append(f"Primary manufacturing match: {primary}")

    domain_hits = []
    for domain in selected_domains:
        kws = REGULATORY_DOMAINS.get(domain, [])
        if any(k in s for k in kws):
            score += 25
            domain_hits.append(domain)
            reasons.append(f"Regulatory domain match: {domain}")

    if any(x in s for x in CRITICAL_WORDS):
        score += 20
        reasons.append("Critical regulatory language detected")
    elif any(x in s for x in HIGH_WORDS):
        score += 10
        reasons.append("High-impact regulatory language detected")

    return min(score, 100), matched_products, domain_hits, reasons

def get_window_cutoff(window):
    today = datetime.now(timezone.utc).date()
    if window == "Past 30 days":
        return today - timedelta(days=30)
    return datetime(today.year, 1, 1).date()

def in_window(date_text, cutoff):
    try:
        return datetime.fromisoformat(date_text).date() >= cutoff
    except Exception:
        return False

def get_profile():
    company = conn.execute("SELECT * FROM company_profile WHERE id=1").fetchone()
    products = conn.execute(
        "SELECT primary_field, secondary_field, notes FROM profile_products ORDER BY primary_field, secondary_field"
    ).fetchall()
    return company, products

def save_profile(company_name, selected_products, notes_map):
    conn.execute("""
        INSERT INTO company_profile(id, company_name, country, updated_at)
        VALUES(1, ?, 'India', ?)
        ON CONFLICT(id) DO UPDATE SET
        company_name=excluded.company_name,
        country=excluded.country,
        updated_at=excluded.updated_at
    """, (company_name.strip(), now_iso()))

    conn.execute("DELETE FROM profile_products")
    for primary, secondary in selected_products:
        conn.execute(
            "INSERT OR IGNORE INTO profile_products(primary_field,secondary_field,notes) VALUES(?,?,?)",
            (primary, secondary, notes_map.get((primary, secondary), ""))
        )

    conn.execute(
        "INSERT INTO audit(timestamp,event,details) VALUES(?,?,?)",
        (now_iso(), "PROFILE_UPDATED",
         f"Company profile updated with {len(selected_products)} product specializations.")
    )
    conn.commit()

def fetch_latest_official_updates():
    all_records = []
    for source, url in CDSCO_SOURCES.items():
        try:
            all_records.extend(parse_source_page(source, url))
        except Exception:
            pass
            
    dated = [r for r in all_records if r.get("published_date")]
    dated.sort(key=lambda x: datetime.fromisoformat(x["published_date"]).date(), reverse=True)
    
    seen = set()
    latest_10 = []
    for r in dated:
        if r["url"] not in seen:
            seen.add(r["url"])
            latest_10.append(r)
            if len(latest_10) == 10:
                break
                
    return latest_10

def sync_cdsco(selected_products, selected_domains, cutoff):
    all_records = []
    errors = []

    for source, url in CDSCO_SOURCES.items():
        try:
            all_records.extend(parse_source_page(source, url))
        except Exception as e:
            errors.append(f"{source}: {str(e)[:120]}")

    checked = 0
    new_count = 0
    relevant_count = 0

    for item in all_records:
        if not item["published_date"] or not in_window(item["published_date"], cutoff):
            continue

        checked += 1
        doc_text = extract_pdf(item["url"])
        full_text = clean(item["title"] + " " + doc_text)

        priority, _ = classify(item["title"], doc_text, item["source"])
        score, mp, md, reasons = calculate_relevance(
            item["title"], doc_text, selected_products, selected_domains
        )

        doc_id = hashlib.sha256(
            (item["source"] + "|" + item["title"] + "|" +
             item["published_date"] + "|" + item["url"]).encode()
        ).hexdigest()[:32]

        exists = conn.execute(
            "SELECT id FROM documents WHERE id=?", (doc_id,)
        ).fetchone()

        status = "Needs RA Review" if score >= 40 else "Informational"

        conn.execute("""
            INSERT INTO documents(
                id,source,title,published_date,url,doc_type,raw_text,priority,
                relevance,matched_products,matched_domains,match_reasons,status,
                first_seen,last_checked
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                raw_text=excluded.raw_text,
                priority=excluded.priority,
                relevance=excluded.relevance,
                matched_products=excluded.matched_products,
                matched_domains=excluded.matched_domains,
                match_reasons=excluded.match_reasons,
                last_checked=excluded.last_checked
        """, (
            doc_id, item["source"], item["title"], item["published_date"],
            item["url"], item["doc_type"], doc_text, priority, score,
            " | ".join(mp), " | ".join(md), " | ".join(reasons), status,
            now_iso(), now_iso()
        ))

        if not exists:
            new_count += 1
        if score >= 40:
            relevant_count += 1

    conn.execute(
        "INSERT INTO audit(timestamp,event,details) VALUES(?,?,?)",
        (now_iso(), "CDSCO_SYNC",
         f"Recent dated CDSCO records checked: {checked}; relevant to profile: {relevant_count}; new: {new_count}.")
    )
    conn.commit()
    return checked, relevant_count, new_count, errors


# ============================================================
# SIDEBAR — PROFILE SETUP
# ============================================================

company_saved, saved_product_rows = get_profile()

with st.sidebar:
    st.title("⚕️ RegIntel")
    st.caption("Company-specific Regulatory Intelligence")

    st.divider()
    st.subheader("1. Company")
    default_company = company_saved["company_name"] if company_saved else ""
    company_name = st.text_input(
        "Company name",
        value=default_company,
        placeholder="e.g., ABC Pharmaceuticals Ltd."
    )

    st.divider()
    st.subheader("2. What does your company manufacture?")
    primary_options = list(PRODUCT_HIERARCHY.keys())
    saved_primary = sorted(set(r["primary_field"] for r in saved_product_rows))
    selected_primary = st.multiselect(
        "Primary manufacturing field",
        primary_options,
        default=saved_primary,
        help="Choose the broad manufacturing/product category first."
    )

    secondary_options = []
    for primary in selected_primary:
        for secondary in PRODUCT_HIERARCHY.get(primary, {}):
            secondary_options.append(f"{primary}  →  {secondary}")

    saved_secondary_labels = {
        f"{r['primary_field']}  →  {r['secondary_field']}"
        for r in saved_product_rows
    }

    selected_secondary_labels = st.multiselect(
        "Specific product / specialization",
        secondary_options,
        default=[x for x in secondary_options if x in saved_secondary_labels],
        help="Choose the more specific product or therapeutic specialization."
    )

    selected_products = []
    for label in selected_secondary_labels:
        primary, secondary = [x.strip() for x in label.split("→", 1)]
        selected_products.append((primary, secondary))

    st.divider()
    st.subheader("3. Regulatory areas")
    saved_domains = st.session_state.get("domains", ["GMP / Manufacturing"])
    selected_domains = st.multiselect(
        "What should RA monitor?",
        list(REGULATORY_DOMAINS.keys()),
        default=saved_domains
    )
    st.session_state["domains"] = selected_domains

    st.divider()
    st.subheader("4. Time window")
    window = st.radio(
        "Show official updates from",
        ["Past 30 days", "This year"],
        index=0
    )
    cutoff = get_window_cutoff(window)

    st.divider()

    if st.button("🔎 START ANALYSIS", type="primary", use_container_width=True):
        if not company_name.strip():
            st.error("Enter the company name first.")
        elif not selected_products:
            st.error("Select at least one specific product/manufacturing specialization.")
        else:
            with st.spinner("Analyzing regulatory landscape..."):
                save_profile(company_name, selected_products, {})
                st.session_state.latest_updates = fetch_latest_official_updates()
                checked, relevant, new, errors = sync_cdsco(
                    selected_products, selected_domains, cutoff
                )
                st.session_state.sync_result = (checked, relevant, new, errors)
                st.session_state.analysis_started = True
            st.rerun()

# ============================================================
# MAIN DASHBOARD
# ============================================================

st.title("CDSCO Regulatory Intelligence")

if not st.session_state.analysis_started:
    st.info("Configure your company profile on the left, then click **🔎 START ANALYSIS** to begin.")
    st.stop()

st.subheader(f"Company: {company_name}")
profile_text = ", ".join([f"{p} → {s}" for p, s in selected_products]) if selected_products else "None"
st.caption(f"Profile: {profile_text} | Monitoring: {window}")
st.divider()

# ------------------------------------------------------------
# LAYER 1: REGULATORY AWARENESS
# ------------------------------------------------------------
st.markdown("### 1. LATEST 10 OFFICIAL CDSCO UPDATES")
st.caption("General Regulatory Awareness (Independent of Company Profile)")

if st.session_state.latest_updates:
    for i, update in enumerate(st.session_state.latest_updates, 1):
        st.markdown(f"**{i}. {update['title']}**")
        st.caption(f"{update['source']} | {update['published_date']}")
        st.link_button("Official Source ↗", update['url'], key=f"latest_{i}")
        st.write("---")
else:
    st.info("No updates found in the official sources.")

# ------------------------------------------------------------
# LAYER 2: COMPANY-SPECIFIC INTELLIGENCE
# ------------------------------------------------------------
st.markdown("### 2. COMPANY-SPECIFIC REGULATORY INTELLIGENCE")
st.caption("Filtered and scored for direct and strategic relevance to your company")

df = pd.read_sql_query(
    "SELECT * FROM documents ORDER BY published_date DESC, last_checked DESC",
    conn
)

if not df.empty:
    df["published_dt"] = pd.to_datetime(df["published_date"], errors="coerce")
    df = df[df["published_dt"].notna()]
    df = df[df["published_dt"].dt.date >= cutoff]

    if not df.empty:
        calculations = df.apply(
            lambda r: calculate_relevance(
                r["title"], r["raw_text"], selected_products, selected_domains
            ), axis=1
        )
        df["current_relevance"] = [x[0] for x in calculations]
        df["current_matches"] = [", ".join(x[1]) for x in calculations]
        df["current_domains"] = [", ".join(x[2]) for x in calculations]
        df["current_reasons"] = [" • ".join(x[3]) for x in calculations]
        df["current_priority"] = [
            classify(r["title"], r["raw_text"], r["source"])[0] for _, r in df.iterrows()
        ]
        feed = df[df["current_relevance"] >= 40].copy()
    else:
        feed = pd.DataFrame()
else:
    feed = pd.DataFrame()

if feed.empty:
    st.info("No specific updates matched your exact company profile in this time window.")
else:
    feed = feed.sort_values(by=["current_priority", "published_dt"], ascending=[True, False])
    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    feed["_sort"] = feed["current_priority"].map(priority_order).fillna(9)
    feed = feed.sort_values(["_sort", "published_dt"], ascending=[True, False])

    for _, row in feed.iterrows():
        priority = row["current_priority"]
        badge = {"Critical": "🔴 CRITICAL", "High": "🟠 HIGH", "Medium": "🟡 MEDIUM", "Low": "⚪ LOW"}.get(priority, priority)

        with st.container(border=True):
            st.markdown(f"**[{badge}] {row['title']}**")
            st.caption(f"{row['source']} • {row['published_date']}")
            
            domain_text = row['current_domains'] or "general regulatory requirements"
            product_text = row['current_matches'] or "indirect operations"
            
            st.markdown("**Why this matters:**")
            st.write(f"This update relates to **{domain_text}** and may impact your company's **{product_text}**. ({row['current_reasons']})")
            
            if row["raw_text"]:
                excerpt = clean(row["raw_text"])[:400]
                st.markdown("**Official evidence:**")
                st.info(f"\"...{excerpt}...\"")
            
            a1, a2 = st.columns([1, 5])
            with a1:
                if st.button("Needs Action", key=f"action_{row['id']}"):
                    conn.execute("UPDATE documents SET status='Action Required' WHERE id=?", (row["id"],))
                    conn.execute("INSERT INTO actions(document_id,action,created_at) VALUES(?,?,?)", 
                                 (row["id"], "RA to assess applicability", now_iso()))
                    conn.commit()
                    st.rerun()
            with a2:
                st.link_button("View CDSCO document ↗", row["url"])

st.divider()

# ------------------------------------------------------------
# LAYER 3: RA REVIEW / ACTIONS
# ------------------------------------------------------------
st.markdown("### 3. RA REVIEW / ACTIONS")

actions = pd.read_sql_query("""
    SELECT a.id, a.action, d.title, d.source, d.published_date 
    FROM actions a JOIN documents d ON d.id = a.document_id 
    WHERE a.status='Open' ORDER BY d.published_date DESC
""", conn)

if actions.empty:
    st.caption("No open RA actions.")
else:
    for _, a in actions.iterrows():
        with st.container(border=True):
            st.markdown(f"**{a['title']}**")
            st.caption(f"Source: {a['source']} | Published: {a['published_date']}")
            st.write(f"**Action required:** {a['action']}")
            if st.button("Close Action", key=f"close_{a['id']}"):
                conn.execute("UPDATE actions SET status='Closed' WHERE id=?", (int(a["id"]),))
                conn.commit()
                st.rerun()
