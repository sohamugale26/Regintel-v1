
import os
import re
import io
import json
import time
import hashlib
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
import streamlit as st

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

# Optional AI support. The app remains functional without an API key.
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# ============================================================
# REGINTEL V2 — CDSCO REGULATORY INTELLIGENCE PLATFORM
# Scope: India / CDSCO V2
# Human-in-the-loop. Official source is the regulatory authority.
# ============================================================

st.set_page_config(
    page_title="RegIntel V2 | CDSCO Regulatory Intelligence",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: "IBM Plex Sans", sans-serif;
}
.block-container { padding-top: 1.2rem; }
.small-muted { opacity: .72; font-size: .84rem; }
.official {
    border-left: 4px solid #2e7d32;
    padding: .7rem 1rem;
    background: rgba(46,125,50,.08);
    border-radius: 6px;
}
.ai-box {
    border-left: 4px solid #1565c0;
    padding: .7rem 1rem;
    background: rgba(21,101,192,.08);
    border-radius: 6px;
}
.warning-box {
    border-left: 4px solid #f57c00;
    padding: .7rem 1rem;
    background: rgba(245,124,0,.08);
    border-radius: 6px;
}
.metric-card {
    border: 1px solid var(--secondary-background-color);
    border-radius: 8px;
    padding: 12px;
    background: var(--background-color);
}
</style>
""", unsafe_allow_html=True)


# -----------------------------
# Configuration
# -----------------------------
APP_VERSION = "2.0.0"
DB_PATH = os.getenv("REGINTEL_DB_PATH", "regintel_master_cdsco_v2.db")
REQUEST_TIMEOUT = int(os.getenv("REGINTEL_REQUEST_TIMEOUT", "30"))
MAX_DOCUMENTS_PER_SOURCE = int(os.getenv("REGINTEL_MAX_DOCS_PER_SOURCE", "30"))

SOURCES = {
    "Gazette Notifications": {
        "url": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Gazette-Notifications/",
        "doc_type": "Gazette Notification",
        "priority": 1,
    },
    "Circulars": {
        "url": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
        "doc_type": "Circular",
        "priority": 1,
    },
    "Public Notices": {
        "url": "https://www.cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
        "doc_type": "Public Notice",
        "priority": 1,
    },
}

PRODUCTS = [
    "APIs & Intermediates",
    "Oral Solids & Liquids",
    "Sterile Injectables & Parenterals",
    "Biologics, Biosimilars & Vaccines",
    "Medical Devices (Class A-D) & IVDs",
    "Cosmetics & Dermaceuticals",
    "AYUSH Formulations",
]

DOMAINS = [
    "GMP, GLP & Manufacturing Compliance",
    "Clinical Trials & New Drugs (NDCT 2019)",
    "Pharmacovigilance & Safety (PvPI)",
    "Import, Export & Registration (SUGAM)",
    "Quality Control & Pharmacopoeia (IPC)",
    "Medical Devices & Diagnostics",
    "Cosmetics",
    "Biologics",
]

DOMAIN_KEYWORDS = {
    "GMP, GLP & Manufacturing Compliance": [
        "gmp", "schedule m", "manufacture", "manufacturing", "quality system",
        "inspection", "good manufacturing", "glp", "sterilization", "spurious",
        "unapproved", "misbranded", "fabricated", "debarment"
    ],
    "Clinical Trials & New Drugs (NDCT 2019)": [
        "ndct", "clinical trial", "new drug", "cro", "phase i", "phase ii",
        "phase iii", "phase iv", "ethics committee", "ct-05", "ct-06", "ct-10",
        "ba-be", "bioequivalence"
    ],
    "Pharmacovigilance & Safety (PvPI)": [
        "pharmacovigilance", "pvpi", "adverse drug reaction", "adr",
        "safety", "psur", "prescribing information", "signal"
    ],
    "Import, Export & Registration (SUGAM)": [
        "sugam", "import", "export", "registration certificate", "marketing authorization",
        "written confirmation", "licence", "license", "post approval change"
    ],
    "Quality Control & Pharmacopoeia (IPC)": [
        "quality control", "testing", "pharmacopoeia", "ipc", "laboratory",
        "government analyst", "test fee", "sampling", "specification"
    ],
    "Medical Devices & Diagnostics": [
        "medical device", "ivd", "in vitro", "mdr 2017", "risk classification",
        "device software", "diagnostic"
    ],
    "Cosmetics": [
        "cosmetic", "cosmetics rules", "dermaceutical", "cosmetics rules 2020"
    ],
    "Biologics": [
        "vaccine", "vaccines", "biosimilar", "biologics", "anti-sera",
        "r-dna", "cell and gene", "blood product"
    ],
}

PRODUCT_KEYWORDS = {
    "APIs & Intermediates": ["api", "active pharmaceutical ingredient", "intermediate", "granules", "pellets"],
    "Oral Solids & Liquids": ["tablet", "capsule", "oral", "syrup", "solution", "suspension", "dosage form", "fdc"],
    "Sterile Injectables & Parenterals": ["sterile", "injectable", "parenteral", "injection", "aseptic"],
    "Biologics, Biosimilars & Vaccines": ["vaccine", "biosimilar", "biologic", "anti-sera", "r-dna", "cell and gene"],
    "Medical Devices (Class A-D) & IVDs": ["medical device", "ivd", "in-vitro", "diagnostic", "mdr-2017"],
    "Cosmetics & Dermaceuticals": ["cosmetic", "dermaceutical", "cosmetics rules"],
    "AYUSH Formulations": ["ayush", "ayurvedic", "siddha", "unani", "homoeopathic"],
}

CRITICAL_TRIGGERS = [
    "ban", "prohibition", "prohibited", "recall", "spurious", "unapproved",
    "immediate effect", "mandatory", "shall", "schedule m", "debarment",
    "cancellation", "suspended", "safety alert", "withdrawal"
]

HIGH_TRIGGERS = [
    "amendment", "notification", "new requirement", "revised", "mandatory",
    "restriction", "licence", "license", "post approval", "psur", "clinical trial"
]


# -----------------------------
# Database
# -----------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        authority TEXT,
        url TEXT,
        doc_type TEXT,
        priority INTEGER,
        active INTEGER DEFAULT 1,
        last_checked TEXT,
        last_success TEXT,
        last_error TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        source_name TEXT,
        authority TEXT,
        doc_type TEXT,
        title TEXT,
        published_date TEXT,
        official_url TEXT,
        pdf_url TEXT,
        official_ref TEXT,
        discovered_at TEXT,
        last_seen_at TEXT,
        content_hash TEXT,
        text_content TEXT,
        extraction_status TEXT,
        classification_status TEXT,
        version_group TEXT,
        previous_document_id TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS intelligence (
        document_id TEXT PRIMARY KEY,
        summary TEXT,
        what_changed TEXT,
        why_it_matters TEXT,
        topic TEXT,
        affected_products TEXT,
        impact_area TEXT,
        relevance_score INTEGER,
        priority TEXT,
        confidence REAL,
        evidence_excerpt TEXT,
        analysis_method TEXT,
        ai_model TEXT,
        generated_at TEXT,
        FOREIGN KEY(document_id) REFERENCES documents(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT,
        reviewer TEXT,
        status TEXT,
        justification TEXT,
        reviewed_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT,
        title TEXT,
        owner TEXT,
        due_date TEXT,
        priority TEXT,
        status TEXT,
        impact_area TEXT,
        notes TEXT,
        created_at TEXT,
        completed_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        user TEXT,
        action TEXT,
        record_id TEXT,
        details TEXT
    )
    """)

    for name, cfg in SOURCES.items():
        cur.execute("""
        INSERT OR IGNORE INTO sources
        (name, authority, url, doc_type, priority)
        VALUES (?, ?, ?, ?, ?)
        """, (name, "CDSCO", cfg["url"], cfg["doc_type"], cfg["priority"]))

    conn.commit()
    return conn


conn = init_db()


def audit(action, record_id="SYSTEM", details="", user="RA Professional"):
    conn.execute(
        "INSERT INTO audit_logs(timestamp,user,action,record_id,details) VALUES(?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), user, action, record_id, details)
    )
    conn.commit()


# -----------------------------
# HTTP / extraction
# -----------------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (compatible; RegIntel-CDSCO-Monitor/2.0; "
        "+https://www.cdsco.gov.in/)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


def fetch(url):
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT, verify=True)
    response.raise_for_status()
    return response


def normalize_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_date(text):
    text = normalize_text(text)
    patterns = [
        r"(\d{4})[-./](\d{2})[-./](\d{2})",
        r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            y, mth, d = map(int, m.groups())
            try:
                return f"{y:04d}-{mth:02d}-{d:02d}"
            except ValueError:
                pass

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    m = re.search(r"(\d{4})[- ]([A-Za-z]{3})[- ](\d{1,2})", text)
    if m:
        y, mon, d = m.groups()
        try:
            return f"{int(y):04d}-{month_map[mon.lower()]:02d}-{int(d):02d}"
        except Exception:
            pass
    return ""


def extract_pdf_text(pdf_bytes):
    if PdfReader is None:
        return "", "pypdf-not-installed"
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for idx, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt.strip():
                pages.append(f"[Page {idx+1}]\n{txt}")
        text = "\n\n".join(pages)
        if not text.strip():
            return "", "no-text-or-scanned-pdf"
        return normalize_text(text), "success"
    except Exception as exc:
        return "", f"error: {exc}"


def find_pdf_link(anchor, page_url):
    href = (anchor.get("href") or "").strip()
    onclick = (anchor.get("onclick") or "").strip()
    candidates = [href, onclick]

    for value in candidates:
        if not value:
            continue
        m = re.search(r"""['"]([^'"]+\.pdf(?:\?[^'"]*)?)['"]""", value, re.I)
        if m:
            return urljoin(page_url, m.group(1))
        if ".pdf" in value.lower():
            part = value[value.lower().find(".pdf")-300:]
            m2 = re.search(r"""(https?://[^'"\s]+\.pdf[^'"\s]*)""", value, re.I)
            if m2:
                return m2.group(1)
    return ""


def parse_source_page(source_name, cfg, html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    # CDSCO pages are table-oriented. We scan table rows and also fall back
    # to anchors containing PDF links.
    for tr in soup.find_all("tr"):
        cells = [normalize_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue

        row_text = " | ".join(cells)
        anchors = tr.find_all("a")
        pdf_url = ""
        official_url = cfg["url"]

        for a in anchors:
            pdf = find_pdf_link(a, cfg["url"])
            if pdf:
                pdf_url = pdf
                break

        title = cells[1] if len(cells) >= 2 else (cells[0] if cells else "")
        if title.lower() in {"title", "download pdf"}:
            continue
        if len(title) < 8:
            continue

        published = ""
        for cell in cells:
            candidate = parse_date(cell)
            if candidate:
                published = candidate
                break

        official_ref = ""
        ref_match = re.search(r"\b(?:G\.S\.R\.|S\.O\.|F\.No\.|File No\.)\s*[^|,]+", row_text, re.I)
        if ref_match:
            official_ref = normalize_text(ref_match.group(0))

        # Keep official page URL even if PDF discovery fails.
        canonical_key = f"{source_name}|{title}|{published}|{pdf_url or official_url}"
        doc_id = "CDSCO-" + hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()[:20]

        rows.append({
            "id": doc_id,
            "source_name": source_name,
            "authority": "CDSCO",
            "doc_type": cfg["doc_type"],
            "title": title,
            "published_date": published,
            "official_url": official_url,
            "pdf_url": pdf_url,
            "official_ref": official_ref,
        })

    # De-duplicate within page.
    seen = set()
    unique = []
    for row in rows:
        key = (row["title"].lower(), row["published_date"], row["pdf_url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    return unique[:MAX_DOCUMENTS_PER_SOURCE]


def classify_text(title, text):
    combined = normalize_text(f"{title} {text}").lower()
    scores = {}
    for domain, words in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for w in words if w.lower() in combined)

    best_domain = max(scores, key=scores.get) if scores else "Unclassified"
    if scores.get(best_domain, 0) == 0:
        best_domain = "General CDSCO Regulatory"

    products = []
    for product, words in PRODUCT_KEYWORDS.items():
        if any(w.lower() in combined for w in words):
            products.append(product)

    return best_domain, products


def score_relevance(title, text, selected_products, selected_domains):
    combined = normalize_text(f"{title} {text}").lower()

    domain_hits = []
    for domain in selected_domains:
        hits = sum(1 for w in DOMAIN_KEYWORDS.get(domain, []) if w.lower() in combined)
        if hits:
            domain_hits.append((domain, hits))

    product_hits = []
    for product in selected_products:
        hits = sum(1 for w in PRODUCT_KEYWORDS.get(product, []) if w.lower() in combined)
        if hits:
            product_hits.append((product, hits))

    critical_hits = sum(1 for x in CRITICAL_TRIGGERS if x in combined)
    high_hits = sum(1 for x in HIGH_TRIGGERS if x in combined)

    score = 20
    score += min(30, sum(h for _, h in domain_hits) * 5)
    score += min(25, sum(h for _, h in product_hits) * 5)
    score += min(20, critical_hits * 7)
    score += min(10, high_hits * 2)

    score = max(0, min(100, score))

    if score >= 85:
        priority = "Critical"
    elif score >= 70:
        priority = "High"
    elif score >= 50:
        priority = "Medium"
    else:
        priority = "Low"

    return score, priority, [x[0] for x in domain_hits], [x[0] for x in product_hits]


def heuristic_summary(title, text):
    text = normalize_text(text)
    if not text:
        return "No document text was extracted. Review the official source manually."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    useful = [s for s in sentences if len(s) > 50][:3]
    return " ".join(useful)[:1200] if useful else text[:1200]


def evidence_excerpt(text):
    if not text:
        return ""
    # Prefer passages containing regulatory trigger words.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        low = s.lower()
        if any(k in low for k in ["shall", "prohibit", "mandatory", "notification", "amend", "requirement"]):
            return s[:1000]
    return sentences[0][:1000] if sentences else text[:1000]


def download_document(pdf_url):
    if not pdf_url:
        return b"", "no-pdf-url"
    try:
        r = fetch(pdf_url)
        content_type = r.headers.get("content-type", "").lower()
        if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
            # Still allow content if it begins with the PDF magic bytes.
            if not r.content.startswith(b"%PDF"):
                return b"", f"not-pdf:{content_type}"
        return r.content, "success"
    except Exception as exc:
        return b"", f"download-error:{exc}"


# -----------------------------
# Optional AI
# -----------------------------
def get_ai_client():
    if OpenAI is None:
        return None
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


def ai_analyze(title, source_text, relevance_context):
    client = get_ai_client()
    if client is None:
        return None

    prompt = f"""
You are assisting a pharmaceutical Regulatory Affairs professional.
Use ONLY the supplied regulatory document text. Do not invent requirements.
Return JSON with:
summary, what_changed, why_it_matters, impact_area, uncertainty.
If the text does not establish a point, say "Not established from source text".
Clearly distinguish source facts from interpretation.

Title: {title}
Company relevance context: {relevance_context}

Document text:
{source_text[:18000]}
"""
    try:
        response = client.chat.completions.create(
            model=os.getenv("REGINTEL_AI_MODEL", "gpt-5-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return None


# -----------------------------
# Synchronization
# -----------------------------
def sync_source(source_name, selected_products, selected_domains, download_pdfs=True, use_ai=False):
    cfg = SOURCES[source_name]
    checked = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE sources SET last_checked=?, last_error=NULL WHERE name=?",
        (checked, source_name)
    )
    conn.commit()

    try:
        response = fetch(cfg["url"])
        records = parse_source_page(source_name, cfg, response.text)
    except Exception as exc:
        conn.execute(
            "UPDATE sources SET last_error=? WHERE name=?",
            (str(exc)[:1000], source_name)
        )
        conn.commit()
        audit("SOURCE_SYNC_FAILED", source_name, str(exc)[:1000])
        return {"source": source_name, "found": 0, "new": 0, "updated": 0, "failed": 1, "error": str(exc)}

    new_count = 0
    updated_count = 0
    failed_docs = 0

    for record in records:
        existing = conn.execute(
            "SELECT id, content_hash, text_content FROM documents WHERE id=?",
            (record["id"],)
        ).fetchone()

        text = ""
        extraction_status = "not-attempted"
        content_hash = ""

        if download_pdfs and record["pdf_url"]:
            pdf_bytes, dl_status = download_document(record["pdf_url"])
            if pdf_bytes:
                text, extraction_status = extract_pdf_text(pdf_bytes)
                content_hash = hashlib.sha256(pdf_bytes).hexdigest()
            else:
                extraction_status = dl_status

        # If the record already exists, retain existing text when a fresh
        # download cannot be performed.
        if existing and not text:
            text = existing[2] or ""
            content_hash = existing[1] or ""

        document_text = text[:500000]

        domain, products = classify_text(record["title"], document_text)
        score, priority, matched_domains, matched_products = score_relevance(
            record["title"], document_text, selected_products, selected_domains
        )

        summary = heuristic_summary(record["title"], document_text)
        evidence = evidence_excerpt(document_text)
        analysis_method = "rule-based"
        ai_model = ""

        if use_ai and document_text:
            ai_result = ai_analyze(
                record["title"],
                document_text,
                f"Products: {selected_products}; Domains: {selected_domains}"
            )
            if ai_result:
                summary = ai_result.get("summary") or summary
                what_changed = ai_result.get("what_changed") or "Not established from source text."
                why_matters = ai_result.get("why_it_matters") or "Not established from source text."
                impact_area = ai_result.get("impact_area") or domain
                analysis_method = "AI + rules"
                ai_model = os.getenv("REGINTEL_AI_MODEL", "gpt-5-mini")
            else:
                what_changed = "Automatic change interpretation not established; RA review required."
                why_matters = "Review official document and evidence before making a regulatory determination."
                impact_area = domain
        else:
            what_changed = "Automatic change interpretation not established; RA review required."
            why_matters = "Review official document and evidence before making a regulatory determination."
            impact_area = domain

        if not existing:
            conn.execute("""
                INSERT INTO documents(
                    id, source_name, authority, doc_type, title, published_date,
                    official_url, pdf_url, official_ref, discovered_at, last_seen_at,
                    content_hash, text_content, extraction_status,
                    classification_status, version_group, previous_document_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                record["id"], record["source_name"], record["authority"],
                record["doc_type"], record["title"], record["published_date"],
                record["official_url"], record["pdf_url"], record["official_ref"],
                checked, checked, content_hash, document_text, extraction_status,
                "classified", hashlib.sha256(record["title"].lower().encode()).hexdigest()[:16],
                None
            ))
            new_count += 1
            audit("DOCUMENT_DISCOVERED", record["id"], f"{source_name}: {record['title']}")
        else:
            old_hash = existing[1] or ""
            if content_hash and old_hash and content_hash != old_hash:
                updated_count += 1
                conn.execute("""
                    UPDATE documents SET last_seen_at=?, content_hash=?, text_content=?,
                    extraction_status=?, pdf_url=? WHERE id=?
                """, (checked, content_hash, document_text, extraction_status,
                      record["pdf_url"], record["id"]))
                audit("DOCUMENT_UPDATED", record["id"], "Document content hash changed.")
            else:
                conn.execute(
                    "UPDATE documents SET last_seen_at=? WHERE id=?",
                    (checked, record["id"])
                )

        conn.execute("""
            INSERT INTO intelligence(
                document_id, summary, what_changed, why_it_matters, topic,
                affected_products, impact_area, relevance_score, priority,
                confidence, evidence_excerpt, analysis_method, ai_model, generated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
                summary=excluded.summary,
                what_changed=excluded.what_changed,
                why_it_matters=excluded.why_it_matters,
                topic=excluded.topic,
                affected_products=excluded.affected_products,
                impact_area=excluded.impact_area,
                relevance_score=excluded.relevance_score,
                priority=excluded.priority,
                confidence=excluded.confidence,
                evidence_excerpt=excluded.evidence_excerpt,
                analysis_method=excluded.analysis_method,
                ai_model=excluded.ai_model,
                generated_at=excluded.generated_at
        """, (
            record["id"], summary, what_changed, why_matters, domain,
            ", ".join(products or matched_products), impact_area, score, priority,
            0.85 if analysis_method == "AI + rules" else 0.65,
            evidence, analysis_method, ai_model, checked
        ))

    conn.execute(
        "UPDATE sources SET last_success=?, last_error=NULL WHERE name=?",
        (checked, source_name)
    )
    conn.commit()
    audit("SOURCE_SYNC_COMPLETED", source_name,
          f"Found={len(records)}, New={new_count}, Updated={updated_count}, FailedDocs={failed_docs}")

    return {
        "source": source_name,
        "found": len(records),
        "new": new_count,
        "updated": updated_count,
        "failed": failed_docs,
        "error": "",
    }


def sync_all(selected_sources, selected_products, selected_domains, download_pdfs=True, use_ai=False):
    results = []
    for source in selected_sources:
        results.append(sync_source(
            source, selected_products, selected_domains,
            download_pdfs=download_pdfs, use_ai=use_ai
        ))
        time.sleep(0.5)
    return results


# -----------------------------
# Data helpers
# -----------------------------
def load_feed():
    query = """
    SELECT
        d.id, d.source_name, d.authority, d.doc_type, d.title,
        d.published_date, d.official_url, d.pdf_url, d.official_ref,
        d.extraction_status, d.last_seen_at,
        i.summary, i.what_changed, i.why_it_matters, i.topic,
        i.affected_products, i.impact_area, i.relevance_score,
        i.priority, i.confidence, i.evidence_excerpt,
        i.analysis_method, i.ai_model
    FROM documents d
    LEFT JOIN intelligence i ON i.document_id = d.id
    ORDER BY COALESCE(d.published_date, '') DESC, d.discovered_at DESC
    """
    return pd.read_sql_query(query, conn)


def load_reviews():
    return pd.read_sql_query(
        "SELECT * FROM reviews ORDER BY reviewed_at DESC", conn
    )


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("## 🏢 Operating Entity")
    company_name = st.text_input(
        "Pharmaceutical Organization",
        value="Meridian Pharmaceuticals Ltd."
    )

    st.markdown("---")
    st.markdown("### 🇮🇳 CDSCO Monitoring")

    selected_products = st.multiselect(
        "Active Manufacturing / Product Lines",
        PRODUCTS,
        default=PRODUCTS[:3],
    )

    selected_domains = st.multiselect(
        "Regulatory Domains",
        DOMAINS,
        default=DOMAINS[:5],
    )

    selected_sources = st.multiselect(
        "Official Sources to Monitor",
        list(SOURCES.keys()),
        default=list(SOURCES.keys()),
    )

    download_pdfs = st.checkbox(
        "Download and extract PDFs",
        value=True,
        help="Downloads discovered official PDFs for evidence and analysis."
    )

    ai_enabled = st.checkbox(
        "Enable AI analysis (optional)",
        value=False,
        help="Requires OPENAI_API_KEY in the deployment environment."
    )

    st.markdown("---")
    st.caption(f"RegIntel V{APP_VERSION}")
    st.caption("Official source = authority. AI/rules = interpretation. RA = final determination.")


# -----------------------------
# Header
# -----------------------------
st.title("🇮🇳 CDSCO Regulatory Intelligence Terminal")
st.caption(
    f"Operating Entity: **{company_name}**  |  "
    f"Scope: **India / CDSCO**  |  "
    f"Version: **{APP_VERSION}**"
)

tabs = st.tabs([
    "📊 Intelligence Dashboard",
    "🔄 Live Source Monitor",
    "🗄️ Regulatory Registry",
    "🧠 Intelligence",
    "⚖️ RA Review & Actions",
    "📋 Audit Trail",
    "⚙️ System Status",
])


# -----------------------------
# Dashboard
# -----------------------------
with tabs[0]:
    df = load_feed()

    if df.empty:
        st.info("No documents are currently stored. Run a live synchronization from the Source Monitor.")
    else:
        high = len(df[df["priority"].isin(["Critical", "High"])])
        review_count = len(df[df["id"].isin(
            load_reviews().query("status == 'Needs Review'")["document_id"].tolist()
        )]) if not load_reviews().empty else 0
        action_count = len(df[df["id"].isin(
            pd.read_sql_query("SELECT document_id FROM actions WHERE status != 'Completed'", conn)["document_id"].tolist()
        )])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Regulatory Documents", len(df))
        c2.metric("Critical / High", high)
        c3.metric("Needs RA Review", review_count)
        c4.metric("Open Actions", action_count)

        st.markdown("### Regulatory Intelligence Feed")

        search = st.text_input(
            "Search",
            placeholder="e.g. Schedule M, PSUR, FDC, SUGAM, medical device..."
        )

        view = df.copy()
        if search:
            mask = view.astype(str).apply(
                lambda col: col.str.contains(search, case=False, na=False)
            ).any(axis=1)
            view = view[mask]

        priority_filter = st.multiselect(
            "Priority",
            ["Critical", "High", "Medium", "Low"],
            default=["Critical", "High", "Medium", "Low"]
        )
        view = view[view["priority"].isin(priority_filter)]

        for _, item in view.head(50).iterrows():
            with st.expander(
                f"{item['priority']} | {item['title']} | {item['published_date'] or 'Date not extracted'}"
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Relevance", f"{int(item['relevance_score'] or 0)}/100")
                c2.metric("Confidence", f"{float(item['confidence'] or 0):.0%}")
                c3.write(f"**Method:** {item['analysis_method'] or 'Not analyzed'}")

                st.markdown(
                    f"**Topic:** {item['topic'] or 'Unclassified'}  \n"
                    f"**Affected products:** {item['affected_products'] or 'Not established'}  \n"
                    f"**Impact area:** {item['impact_area'] or 'Not established'}"
                )

                st.markdown("#### Summary")
                st.write(item["summary"] or "No summary available.")

                st.markdown("#### What Changed?")
                st.write(item["what_changed"] or "Not established from source text.")

                st.markdown("#### Why It Matters")
                st.write(item["why_it_matters"] or "Not established from source text.")

                st.markdown("#### Official Evidence")
                st.markdown(
                    f'<div class="official"><b>Official source:</b> {item["source_name"]}<br>'
                    f'<b>Reference:</b> {item["official_ref"] or "Not extracted"}<br>'
                    f'<b>Evidence:</b> {item["evidence_excerpt"] or "No extractable evidence; open official source."}</div>',
                    unsafe_allow_html=True
                )

                st.markdown(
                    f"[Open official CDSCO source]({item['official_url']})"
                )
                if item["pdf_url"]:
                    st.markdown(f"[Open official PDF]({item['pdf_url']})")


# -----------------------------
# Source Monitor
# -----------------------------
with tabs[1]:
    st.subheader("🔄 Live CDSCO Source Monitor")

    st.markdown("""
    <div class="official">
    <b>Monitoring principle:</b> the application retrieves information from official CDSCO
    publication pages. The official document remains the source of regulatory truth.
    </div>
    """, unsafe_allow_html=True)

    source_df = pd.read_sql_query(
        "SELECT name, authority, doc_type, url, active, last_checked, last_success, last_error FROM sources ORDER BY priority, name",
        conn
    )

    st.dataframe(source_df, use_container_width=True, hide_index=True)

    if st.button("🚀 Sync Selected CDSCO Sources Now", type="primary", use_container_width=True):
        with st.spinner("Checking official CDSCO publication pages and extracting available documents..."):
            results = sync_all(
                selected_sources,
                selected_products,
                selected_domains,
                download_pdfs=download_pdfs,
                use_ai=ai_enabled,
            )

        st.success("Synchronization completed.")
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
        st.rerun()

    st.markdown("### Current official source coverage")
    for name in selected_sources:
        st.markdown(
            f"- **{name}** — [{SOURCES[name]['url']}]({SOURCES[name]['url']})"
        )

    st.info(
        "For a cloud deployment, scheduled/background monitoring should be added separately. "
        "The button above performs an on-demand live synchronization."
    )


# -----------------------------
# Registry
# -----------------------------
with tabs[2]:
    st.subheader("🗄️ Regulatory Master Registry")

    df = load_feed()
    if df.empty:
        st.info("Registry is empty.")
    else:
        cols = [
            "id", "source_name", "doc_type", "official_ref",
            "title", "published_date", "extraction_status",
            "last_seen_at"
        ]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Registry CSV",
            csv,
            "regintel_registry.csv",
            "text/csv"
        )


# -----------------------------
# Intelligence
# -----------------------------
with tabs[3]:
    st.subheader("🧠 Regulatory Intelligence Analysis")

    df = load_feed()
    if df.empty:
        st.info("Run a source synchronization first.")
    else:
        doc_id = st.selectbox(
            "Select regulatory document",
            df["id"].tolist(),
            format_func=lambda x: df.loc[df["id"] == x, "title"].iloc[0]
        )

        item = df[df["id"] == doc_id].iloc[0]

        st.markdown("### Official Information")
        st.write(f"**Title:** {item['title']}")
        st.write(f"**Authority:** {item['authority']}")
        st.write(f"**Document type:** {item['doc_type']}")
        st.write(f"**Published:** {item['published_date']}")
        st.write(f"**Official reference:** {item['official_ref'] or 'Not extracted'}")

        st.markdown("### System Interpretation")
        st.markdown(
            f'<div class="ai-box"><b>Summary:</b><br>{item["summary"] or "Not available"}'
            f'<br><br><b>What changed:</b><br>{item["what_changed"] or "Not established"}'
            f'<br><br><b>Why it matters:</b><br>{item["why_it_matters"] or "Not established"}'
            f'<br><br><b>Relevance:</b> {int(item["relevance_score"] or 0)}/100'
            f'<br><b>Priority:</b> {item["priority"]}'
            f'<br><b>Method:</b> {item["analysis_method"] or "Not analyzed"}</div>',
            unsafe_allow_html=True
        )

        st.markdown("### Evidence")
        st.write(item["evidence_excerpt"] or "No evidence excerpt available.")

        st.warning(
            "System interpretation is decision support only. Final applicability, compliance "
            "and regulatory action must be determined by a qualified RA professional."
        )


# -----------------------------
# RA Review & Actions
# -----------------------------
with tabs[4]:
    st.subheader("⚖️ Human RA Governance")

    df = load_feed()
    if df.empty:
        st.info("No documents available.")
    else:
        doc_id = st.selectbox(
            "Document for RA review",
            df["id"].tolist(),
            format_func=lambda x: df.loc[df["id"] == x, "title"].iloc[0],
            key="review_doc"
        )
        item = df[df["id"] == doc_id].iloc[0]

        existing_review = conn.execute(
            "SELECT status, justification, reviewer FROM reviews WHERE document_id=? ORDER BY id DESC LIMIT 1",
            (doc_id,)
        ).fetchone()

        statuses = [
            "Needs Review",
            "Action Required",
            "Informational",
            "Not Relevant",
        ]

        default_status = existing_review[0] if existing_review else "Needs Review"
        status = st.selectbox(
            "RA Determination",
            statuses,
            index=statuses.index(default_status) if default_status in statuses else 0
        )
        reviewer = st.text_input(
            "Reviewer",
            value=existing_review[2] if existing_review else "RA Professional"
        )
        justification = st.text_area(
            "Technical Justification",
            value=existing_review[1] if existing_review else ""
        )

        if st.button("Commit RA Determination", type="primary"):
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO reviews(document_id,reviewer,status,justification,reviewed_at) VALUES(?,?,?,?,?)",
                (doc_id, reviewer, status, justification, now)
            )
            audit(
                "RA_GOVERNANCE_REVIEW",
                doc_id,
                f"Status={status}; Reviewer={reviewer}"
            )
            conn.commit()
            st.success("RA determination recorded.")

        st.markdown("---")
        st.markdown("### Create Action")

        if status == "Action Required":
            action_title = st.text_input(
                "Action title",
                value=f"Assess applicability of: {item['title']}"
            )
            owner = st.text_input("Action owner", value="Regulatory Affairs")
            due_date = st.date_input("Due date")
            action_priority = st.selectbox(
                "Action priority",
                ["Critical", "High", "Medium", "Low"],
                index=1 if item["priority"] == "High" else 0 if item["priority"] == "Critical" else 2
            )
            impact_area = st.text_input(
                "Impact area",
                value=item["impact_area"] or ""
            )
            notes = st.text_area("Action notes")

            if st.button("Create Action"):
                now = datetime.now(timezone.utc).isoformat()
                conn.execute("""
                    INSERT INTO actions(
                        document_id,title,owner,due_date,priority,status,
                        impact_area,notes,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                """, (
                    doc_id, action_title, owner, str(due_date),
                    action_priority, "New", impact_area, notes, now
                ))
                audit("ACTION_CREATED", doc_id, action_title)
                conn.commit()
                st.success("Action created.")

        st.markdown("### Open Actions")
        actions = pd.read_sql_query(
            "SELECT * FROM actions ORDER BY created_at DESC", conn
        )
        if actions.empty:
            st.info("No actions created.")
        else:
            st.dataframe(actions, use_container_width=True, hide_index=True)


# -----------------------------
# Audit
# -----------------------------
with tabs[5]:
    st.subheader("📋 Audit Trail & Verification")

    logs = pd.read_sql_query(
        "SELECT timestamp,user,action,record_id,details FROM audit_logs ORDER BY id DESC",
        conn
    )
    st.dataframe(logs, use_container_width=True, hide_index=True)

    st.markdown("### Review History")
    reviews = load_reviews()
    if reviews.empty:
        st.info("No RA reviews recorded yet.")
    else:
        st.dataframe(reviews, use_container_width=True, hide_index=True)


# -----------------------------
# System status
# -----------------------------
with tabs[6]:
    st.subheader("⚙️ System Status")

    total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    extracted = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE extraction_status='success'"
    ).fetchone()[0]
    intelligence = conn.execute(
        "SELECT COUNT(*) FROM intelligence"
    ).fetchone()[0]
    actions = conn.execute(
        "SELECT COUNT(*) FROM actions WHERE status != 'Completed'"
    ).fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documents", total_docs)
    c2.metric("Text Extracted", extracted)
    c3.metric("Intelligence Records", intelligence)
    c4.metric("Open Actions", actions)

    st.markdown("### AI configuration")
    if get_ai_client():
        st.success("Optional AI engine is configured.")
    else:
        st.info(
            "AI engine is not configured. The platform currently uses deterministic "
            "rule-based classification/relevance and evidence extraction."
        )

    st.markdown("### Scope")
    st.write("Current implementation: India / CDSCO.")
    st.write("EU/EMA integration is intentionally not enabled in this V2 build.")

    st.markdown("### Important deployment note")
    st.warning(
        "SQLite is suitable for a prototype/demo. For persistent multi-user production "
        "deployment, migrate the database to PostgreSQL and add authentication, backups "
        "and scheduled background jobs."
    )

    st.markdown("### Regulatory governance")
    st.write(
        "This system is decision support. It does not independently determine legal "
        "compliance or replace qualified Regulatory Affairs review."
    )
