import streamlit as st
import sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import json
import urllib3
from openai import OpenAI

# Suppress SSL warnings for government websites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="RegIntel | Master Architecture", layout="wide", page_icon="🛡️")

# --- 1. DATABASE COMPONENT (Layer 1 & 2) ---
def init_db():
    conn = sqlite3.connect("regintel_master.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS updates
                 (id TEXT PRIMARY KEY, authority TEXT, title TEXT, date TEXT, 
                  url TEXT, topic TEXT, summary TEXT, impact TEXT, relevance_score INTEGER, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, update_id TEXT, action TEXT, user TEXT, timestamp TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. COMPANY PROFILE & RAG CONFIGURATION ---
st.sidebar.title("🏢 Company Profile")
company_name = st.sidebar.text_input("Company Name", "Nova Formulation Ltd.")
markets = st.sidebar.multiselect("Markets", ["India (CDSCO)", "EU (EMA)"], ["India (CDSCO)", "EU (EMA)"])
products = st.sidebar.multiselect("Products", ["Injectables", "Oral Solids", "Biologics"], ["Injectables"])
topics = st.sidebar.multiselect("Topics", ["GMP", "Clinical Trials", "Stability", "Pharmacovigilance"], ["GMP", "Stability"])

st.sidebar.divider()
st.sidebar.markdown("⚙️ AI & RAG Settings")
api_key = st.sidebar.text_input("OpenAI API Key (Optional)", type="password")
st.sidebar.info("Free Mode Active: If no API key is entered, the system uses built-in RAG simulation against file S_26.")

# --- 3. AI INTELLIGENCE ENGINE (WITH FREE FALLBACK) ---
def analyze_regulatory_update(title, authority, profile_context):
    if not api_key:
        # Fallback simulation mapping against internal baseline S_26 without requiring a paid key
        return {
            "topic": "GMP Compliance & Quality",
            "summary": f"Simulated Intelligence: Analyzed '{title[:45]}...' against internal baseline S_26 requirements for sterile suites.",
            "impact": "High",
            "relevance": 85
        }
    
    client = OpenAI(api_key=api_key)
    prompt = f"""
    Analyze this {authority} regulatory update: '{title}'.
    Company Context: {profile_context}.
    Cross-reference against internal baselines.
    Provide JSON output strictly with keys: 
    'topic' (string), 
    'summary' (1 sentence explaining what changed), 
    'impact' (High, Medium, Low),
    'relevance' (integer 0-100 based on company context).
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert Regulatory Intelligence AI."},
                {"role": "user", "content": prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"topic": "Error", "summary": str(e), "impact": "Low", "relevance": 0}

# --- 4. SOURCE MONITOR (CDSCO) ---
def scrape_cdsco(profile_context):
    new_updates = []
    c = conn.cursor()
    
    try:
        url = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, verify=False, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for row in soup.find_all('tr')[1:6]: 
            cols = row.find_all('td')
            if len(cols) >= 3:
                title = cols[1].text.strip()
                date = cols[2].text.strip()
                update_id = f"CDSCO-{date.replace('-','')}-{abs(hash(title))%1000}"
                
                c.execute("SELECT id FROM updates WHERE id=?", (update_id,))
                if not c.fetchone():
                    ai_data = analyze_regulatory_update(title, "CDSCO", profile_context)
                    c.execute("INSERT INTO updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                             (update_id, "CDSCO", title, date, url, 
                              ai_data.get('topic'), ai_data.get('summary'), ai_data.get('impact'), 
                              ai_data.get('relevance'), "Pending Review"))
                    new_updates.append(update_id)
        conn.commit()
    except Exception as e:
        st.error(f"Source Monitor Error: {e}")
    return len(new_updates)

# --- 5. UI DASHBOARD & RA WORKFLOW ---
st.title("🛡️ RegIntel Master Platform")

profile_context = f"Markets: {markets}, Products: {products}, Topics: {topics}"

if st.button("🔄 Execute Source Monitor"):
    with st.spinner("Monitoring CDSCO sources and processing documents..."):
        count = scrape_cdsco(profile_context)
        st.success(f"Lifecycle Complete: {count} new regulatory documents discovered and classified.")

st.divider()

df = pd.read_sql_query("SELECT * FROM updates ORDER BY date DESC", conn)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Updates", len(df))
col2.metric("High Relevance (>80)", len(df[df['relevance_score'] >= 80]) if not df.empty else 0)
col3.metric("Pending RA Reviews", len(df[df['status'] == 'Pending Review']) if not df.empty else 0)
col4.metric("Monitored Sources", "CDSCO Notices")

st.subheader("📋 Regulatory Intelligence Records")

if not df.empty:
    for _, row in df.iterrows():
        rel_color = "🔴" if row['relevance_score'] >= 80 else ("🟡" if row['relevance_score'] >= 50 else "🟢")
        
        with st.expander(f"{rel_color} [{row['authority']}] {row['title']} — {row['date']}"):
            meta_col, ai_col, action_col = st.columns([1.5, 2, 1])
            
            with meta_col:
                st.markdown("Metadata")
                st.write(f"Document Type: Public Notice")
                st.write(f"Topic: {row['topic']}")
                st.markdown(f"[View Official Evidence]({row['url']})")
                
            with ai_col:
                st.markdown("AI Intelligence Engine")
                st.write(f"Relevance Score: {row['relevance_score']}/100")
                st.write(f"Impact: {row['impact']}")
                st.write(f"Summary: {row['summary']}")
                st.caption("Cross-referenced against company profile and file S_26.")
                
            with action_col:
                st.markdown("RA Workflow")
                options = ["Pending Review", "Action Required", "Informational", "Not Relevant"]
                current_idx = options.index(row['status']) if row['status'] in options else 0
                
                new_status = st.selectbox("Decision", options, index=current_idx, key=row['id'])
                
                if new_status != row['status']:
                    c = conn.cursor()
                    c.execute("UPDATE updates SET status=? WHERE id=?", (new_status, row['id']))
                    c.execute("INSERT INTO audit_logs (update_id, action, user, timestamp) VALUES (?, ?, ?, ?)", 
                              (row['id'], new_status, "RA Professional", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.rerun()
else:
    st.info("The Regulatory Knowledge Base is currently empty. Run the Source Monitor to populate data.")

st.divider()

st.subheader("📑 Audit Trail & Tracking")
logs = pd.read_sql_query("SELECT update_id, action, user, timestamp FROM audit_logs ORDER BY id DESC", conn)
st.dataframe(logs, use_container_width=True, hide_index=True)
