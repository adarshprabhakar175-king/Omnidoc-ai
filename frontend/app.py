import streamlit as st
import requests
import json
import time

BACKEND_URL = "http://localhost:8000/api/v1"
BASE_HEALTH_URL = "http://localhost:8000"

# Page Configuration
st.set_page_config(
    page_title="IndicDoc-AI | Enterprise Document Intelligence",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
    <style>
    .main {
        background-color: #0b0f19;
        color: #f3f4f6;
    }
    .main-header {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #6366f1, #06b6d4, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #94a3b8;
        margin-bottom: 20px;
    }
    .doc-stat-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 12px 16px;
        margin-top: 10px;
        margin-bottom: 15px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        color: white;
        border: none;
        padding: 0.55rem 1rem;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        opacity: 0.92;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }
    .status-badge-online {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid #10b981;
    }
    .status-badge-offline {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid #ef4444;
    }
    .summary-card {
        background: #131d31;
        border-left: 4px solid #6366f1;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# Helper function to check backend health
def check_backend_status():
    try:
        r = requests.get(BASE_HEALTH_URL, timeout=1.5)
        if r.status_code == 200:
            return True, r.json()
    except Exception:
        pass
    return False, {}

backend_online, backend_meta = check_backend_status()

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_doc_info" not in st.session_state:
    st.session_state.current_doc_info = None
if "summary" not in st.session_state:
    st.session_state.summary = None

# Sidebar
with st.sidebar:
    st.markdown("### 📑 IndicDoc-AI")
    
    if backend_online:
        active_model = backend_meta.get("active_model", "Gemini")
        st.markdown(f'<span class="status-badge-online">🟢 Backend Connected ({active_model})</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge-offline">🔴 Backend Offline</span>', unsafe_allow_html=True)
        st.caption("Start the backend with: `python -m uvicorn main:app --reload`")
    
    st.divider()
    st.header("📂 Document Hub")
    uploaded_file = st.file_uploader("Upload PDF or TXT Document", type=["pdf", "txt", "md"])

    if uploaded_file is not None:
        if st.button("🚀 Process & Index Document"):
            with st.spinner("Extracting multi-page content & indexing..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/pdf")}
                try:
                    response = requests.post(f"{BACKEND_URL}/upload", files=files, timeout=60)
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.current_doc_info = data
                        st.session_state.summary = None
                        st.session_state.messages = []
                        st.success(f"✨ Document '{data.get('filename')}' indexed ({data.get('total_pages')} pages)!")
                    else:
                        st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Failed to connect to backend: {e}")

    # Display active document stats
    if st.session_state.current_doc_info:
        info = st.session_state.current_doc_info
        st.markdown(f"""
        <div class="doc-stat-card">
            <strong>📄 Active Document:</strong> {info.get('filename')}<br>
            <strong>📑 Total Pages:</strong> {info.get('total_pages')}<br>
            <strong>📝 Words:</strong> {info.get('word_count'):,}
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    st.header("🌐 Localization")
    target_language = st.selectbox(
        "Response Language",
        [
            "English",
            "Hindi (हिन्दी)",
            "Tamil (தமிழ்)",
            "Telugu (తెలుగు)",
            "Marathi (मराठी)",
            "Bengali (বাংলা)",
            "Gujarati (ગુજરાતી)",
            "Hinglish (Hindi + English)"
        ],
        index=0
    )

    st.divider()
    st.header("⚡ Quick Actions")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("📊 Executive Summary"):
            with st.spinner("Generating executive summary..."):
                try:
                    payload = {"target_language": target_language}
                    response = requests.post(f"{BACKEND_URL}/summarize", json=payload, timeout=90)
                    if response.status_code == 200:
                        st.session_state.summary = response.json().get("summary")
                        st.rerun()
                    else:
                        st.error("Please upload a document first.")
                except Exception as e:
                    st.error(f"Backend call failed: {e}")

    with col_s2:
        if st.button("🗑️ Reset Doc"):
            try:
                requests.post(f"{BACKEND_URL}/reset")
                st.session_state.current_doc_info = None
                st.session_state.summary = None
                st.session_state.messages = []
                st.rerun()
            except Exception as e:
                st.error(f"Reset failed: {e}")

    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.8rem;'>IndicDoc-AI v2.0 • Native Gemini Engine</p>", unsafe_allow_html=True)

# Main Application Area
st.markdown('<p class="main-header">📑 IndicDoc-AI</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">High-performance Document Intelligence, Multi-Page Citation RAG & Multilingual Chat.</p>', unsafe_allow_html=True)

# Show Executive Summary Card if generated
if st.session_state.summary:
    with st.expander("📋 Executive Summary (Click to collapse)", expanded=True):
        st.markdown(st.session_state.summary)

# Quick Suggestion Chips
st.caption("💡 Quick Question Suggestions:")
chip_cols = st.columns(3)
sample_prompt = None
with chip_cols[0]:
    if st.button("📌 Summarize Key Points", key="chip1"):
        sample_prompt = "Provide a concise summary of the key points in this document."
with chip_cols[1]:
    if st.button("⚖️ What are the Penalty / Risk Clauses?", key="chip2"):
        sample_prompt = "What are the key penalty clauses, liabilities, or risks mentioned in this document? Cite page numbers."
with chip_cols[2]:
    if st.button("📅 Extract Dates & Deadlines", key="chip3"):
        sample_prompt = "Extract all significant dates, milestones, or deadlines mentioned in this document."

# Chat History Display
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Chat Input
user_input = st.chat_input("Ask any question about your document (e.g. What is the fee structure?)...")
active_query = sample_prompt if sample_prompt else user_input

if active_query:
    st.session_state.messages.append({"role": "user", "content": active_query})
    with st.chat_message("user"):
        st.markdown(active_query)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""

        try:
            payload = {
                "question": active_query,
                "target_language": target_language
            }
            with requests.post(f"{BACKEND_URL}/stream-query", json=payload, stream=True, timeout=90) as res:
                if res.status_code == 200:
                    for chunk in res.iter_content(chunk_size=None, decode_unicode=True):
                        if chunk:
                            full_response += chunk
                            message_placeholder.markdown(full_response + "▌")
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                else:
                    err_msg = f"⚠️ Server returned error: {res.status_code}"
                    message_placeholder.error(err_msg)
        except Exception as e:
            message_placeholder.error(f"Connection failed: {str(e)}")