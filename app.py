import sqlite3
import urllib.parse
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
import urllib3
from bs4 import BeautifulSoup
import time

# Suppress SSL warnings for government websites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PAGE CONFIG ---
st.set_page_config(page_title="CDSCO - RegIntel", layout="wide", page_icon="🛡️")

# --- CUSTOM CSS ---
st.markdown("""
<style>
.header-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #f0f2f6;
    padding-bottom: 10px;
    margin-bottom: 20px;
}
.main-title {
    margin: 0;
    font-size: 32px;
    font-weight: 700;
}
.live-date {
    font-size: 18px;
    font-weight: 600;
    color: #444;
}
.marquee-container {
    background-color: #ffeaea;
    border: 1px solid #ffc0c0;
    padding: 8px;
    border-radius: 5px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    overflow: hidden;
}
.marquee-badge {
    background-color: #d93025;
    color: white;
    font-weight: bold;
    padding: 4px 10px;
    border-radius: 4px;
    margin-right: 15px;
    white-space: nowrap;
    z-index: 10;
}
.marquee-text {
    color: #d93025;
    font-weight: 600;
    white-space: nowrap;
    animation: scroll-left 25s linear infinite;
}
@keyframes scroll-left {
    0% { transform: translateX(100%); }
    100% { transform: translateX(-100%); }
}
.blink-indicator {
    color: #d93025;
    font-weight: bold;
    font-size: 16px;
    animation: blinker 0.8s linear infinite;
    padding: 10px 0;
}
@keyframes blinker {
    50% { opacity: 0; }
}
</style>
""", unsafe_allow_html=True)

# --- SESSION STATES ---
if 'marquee_message' not in st.session_state:
    st.session_state.marquee_message = ""

# --- BROWSER HEADERS ---
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive'
}

CDSCO_REGISTERS = {
    "Public Notices": "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/",
    "Circulars": "https://cdsco.gov.in/opencms/opencms/en/Notifications/Circulars/",
    "Safety Alerts": "https://cdsco.gov.in/opencms/opencms/en/Alerts/"
}

# --- 1. DATABASE COMPONENT (Raw Data Only) ---
def init_db():
    conn = sqlite3.connect("regintel_raw_v3.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates
                 (id TEXT PRIMARY KEY, category TEXT, title TEXT, date TEXT, url TEXT, status TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. DATE NORMALIZER ---
def parse_db_date(date_str):
    if not date_str:
        return datetime(1900, 1, 1)
    clean_date = date_str.replace('/', '-').strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%B %d, %Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(clean_date, fmt)
        except ValueError:
            pass
    return datetime(1900, 1, 1)

# --- 3. CORE SCRAPER (Dynamic Timeframe Matcher) ---
def scrape_cdsco_category(category_name, timeframe):
    url = CDSCO_REGISTERS.get(category_name)
    if not url:
        return []
    
    new_records = []
    c = conn.cursor()
    current_date = datetime.now()
    
    # Determine the time delta for the notice box
    if timeframe == "Past Week":
        time_limit = current_date - timedelta(days=7)
    elif timeframe == "Past Month":
        time_limit = current_date - timedelta(days=30)
    else: # Past Year
        time_limit = current_date - timedelta(days=365)
    
    try:
        res = requests.get(url, headers=BROWSER_HEADERS, verify=False, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            tables = soup.find_all('table')
            if tables:
                for row in tables[0].find_all('tr')[1:]:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 3:
                        # Capture EVERYTHING raw
                        title = cols[1].get_text(separator=" ", strip=True)
                        if not title or title == ".":
                            title = "[Blank or Unnamed Document Submitted]"
                            
                        date_val = cols[2].get_text(strip=True)
                        parsed_date = parse_db_date(date_val)
                        
                        link_tag = cols[1].find('a') or cols[-1].find('a') or row.find('a')
                        doc_url = urllib.parse.urljoin("https://cdsco.gov.in", link_tag['href']) if (link_tag and link_tag.has_attr('href')) else url
                        
                        clean_date = date_val.replace('-', '').replace('/', '')
                        update_id = f"CDSCO-{category_name[:3].upper()}-{clean_date}-{abs(hash(title)) % 100000}"
                        
                        # Store in database
                        c.execute("SELECT id FROM updates WHERE id=?", (update_id,))
                        if not c.fetchone():
                            c.execute("INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?)",
                                      (update_id, category_name, title, date_val, doc_url, "Unread"))
                            
                        # If it falls within the selected execution timeframe, add to marquee array
                        if parsed_date >= time_limit and parsed_date <= current_date:
                            new_records.append(f"[{category_name}] {title} ({date_val})")
                conn.commit()
    except Exception as e:
        pass
    
    return new_records

# --- 4. HEADER & LIVE DATE ---
current_live_date = datetime.now().strftime("%A, %B %d, %Y")

st.markdown(f"""
<div class="header-container">
    <h1 class="main-title">🛡️ CDSCO - RegIntel</h1>
    <div class="live-date">🗓️ Live Date: {current_live_date}</div>
</div>
""", unsafe_allow_html=True)

# --- 5. RED MARQUEE TICKER (Shows only when executed) ---
if st.session_state.marquee_message:
    st.markdown(f"""
    <div class="marquee-container">
        <div class="marquee-badge">LIVE PUBLICATION NOTICE</div>
        <div class="marquee-text">{st.session_state.marquee_message}</div>
    </div>
    """, unsafe_allow_html=True)

# --- 6. SCRAPER CONTROLS (Dropdown + Timeframe) ---
st.subheader("📡 Fetch Latest Data")
fetch_col1, fetch_col2, fetch_col3 = st.columns([2, 2, 4])

with fetch_col1:
    target_category = st.selectbox("Select Target Registry:", ["Public Notices", "Circulars", "Safety Alerts"])

with fetch_col2:
    execution_timeframe = st.selectbox("Select Timeframe:", ["Past Week", "Past Month", "Past Year"])

with fetch_col3:
    st.write("") 
    st.write("") 
    execute_btn = st.button("▶ Execute Live Scrape")

# Placeholder for blinking light
live_light_placeholder = st.empty()

if execute_btn:
    # Turn on blinking red light
    live_light_placeholder.markdown('<div class="blink-indicator">🔴 SCRAPING LIVE... Connecting to CDSCO server...</div>', unsafe_allow_html=True)
    
    # Scrape data based on timeframe
    fetched_new_items = scrape_cdsco_category(target_category, execution_timeframe)
    
    # Update marquee message professionally
    if fetched_new_items:
        st.session_state.marquee_message = " &nbsp;&nbsp;&nbsp; | &nbsp;&nbsp;&nbsp; ".join(fetched_new_items)
    else:
        st.session_state.marquee_message = "No new regulatory updates published recently in the selected timeframe."
        
    # Turn off light and reload UI
    live_light_placeholder.empty()
    st.rerun()

st.divider()

# --- 7. HISTORICAL ARCHIVE SEARCH (Restored Year) ---
with st.expander("🔍 Search Database Archive", expanded=False):
    s_col1, s_col2, s_col3, s_col4 = st.columns([3, 1.5, 1, 1])
    with s_col1:
        q = st.text_input("Enter regulatory keyword", placeholder="e.g. Schedule M, Ethics...")
    with s_col2:
        search_cat = st.selectbox("Search Category:", ["All Categories", "Public Notices", "Circulars", "Safety Alerts"])
    with s_col3:
        search_year = st.selectbox("Select Year:", ["All", "2026", "2025", "2024", "2023"])
    with s_col4:
        st.write("")
        st.write("")
        s_btn = st.button("Search Archive")
        
    if s_btn and q:
        query = "SELECT * FROM updates WHERE title LIKE ?"
        params = [f"%{q}%"]
        
        if search_cat != "All Categories":
            query += " AND category = ?"
            params.append(search_cat)
            
        c = conn.cursor()
        c.execute(query, params)
        matches = c.fetchall()
        
        # Filter by year locally
        final_matches = []
        for m in matches:
            if search_year == "All" or search_year in m[3]:
                final_matches.append(m)
        
        if final_matches:
            st.success(f"Found {len(final_matches)} matching records.")
            for m in final_matches:
                st.markdown(f"**[{m[1]}]** {m[2]}  \n*Published:* {m[3]} | [View Document]({m[4]})")
                st.divider()
        else:
            st.warning("No records matched your criteria.")

st.divider()

# --- 8. RAW DATA FEED (Strict 1-Month Window) ---
st.subheader("📋 Recent Records Feed (Strict 1-Month Window)")

# Filter strictly to past 30 days regardless of execution dropdown
df = pd.read_sql_query("SELECT * FROM updates ORDER BY date DESC", conn)

if not df.empty:
    df['parsed_date'] = df['date'].apply(parse_db_date)
    current_date = datetime.now()
    df['days_old'] = (current_date - df['parsed_date']).dt.days
    
    # STRICT 30-DAY LOCK
    display_df = df[df['days_old'] <= 30].copy()
    
    if display_df.empty:
        st.info("No documents have been published on the portal within the exact last 1 month (30 days).")
else:
    st.info("Database is empty. Please select a category above and execute the scrape.")
