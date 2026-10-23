import streamlit as st
import requests
import json
import time

BACKEND_URL = "http://localhost:8000/api/v1"
BASE_HEALTH_URL = "http://localhost:8000"

# Page Configuration
st.set_page_config(
    page_title="IndicDoc-AI | Enterprise Multi-Document Intelligence",
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
        margin-bottom: 12px;
    }
    .doc-item-row {
        background: #131d31;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 8px 12px;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
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
        padding: 4px 12px;
        border-radius: 12px;
        background-color: rgba(16, 185, 129, 0.15);
        color: #10b981;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid #10b981;
    }
    .status-badge-offline {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        background-color: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid #ef4444;
    }
    .citation-card {
        background: #111827;
        border-left: 3px solid #06b6d4;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 0.85rem;
        color: #cbd5e1;
        margin-top: 8px;
    }
    .scope-banner {
        background: #1e1b4b;
        border: 1px solid #4338ca;
        border-radius: 8px;
        padding: 8px 14px;
        margin-bottom: 15px;
        color: #c7d2fe;
        font-size: 0.9rem;
    }
    </style>
""", unsafe_allow_html=True)

# Helper functions to communicate with Backend
def check_backend_status():
    try:
        r = requests.get(BASE_HEALTH_URL, timeout=2.0)
        if r.status_code == 200:
            return True, r.json()
    except Exception:
        pass
    return False, {}

def get_library_documents():
    try:
        r = requests.get(f"{BACKEND_URL}/documents", timeout=3.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"documents": [], "total_documents": 0, "total_pages": 0, "total_words": 0}

backend_online, backend_meta = check_backend_status()
library_data = get_library_documents() if backend_online else {"documents": [], "total_documents": 0, "total_pages": 0, "total_words": 0}

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "summary" not in st.session_state:
    st.session_state.summary = None
if "custom_api_key" not in st.session_state:
    st.session_state.custom_api_key = ""

# Sidebar
with st.sidebar:
    st.markdown("### 📑 IndicDoc-AI")
    
    if backend_online:
        active_model = backend_meta.get("active_model", "Gemini 3.5 Flash")
        st.markdown(f'<span class="status-badge-online">🟢 Connected ({active_model})</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge-offline">🔴 Backend Offline</span>', unsafe_allow_html=True)
        st.caption("Start the backend with: `python run.py`")

    st.divider()
    
    # 1. Multi-Document Upload Section
    st.header("📂 Document Hub (Unlimited)")
    uploaded_files = st.file_uploader(
        "Upload PDF, TXT or MD Document(s)",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        help="You can upload unlimited documents at once or add more files anytime."
    )

    if uploaded_files:
        if st.button("🚀 Process & Index All Documents"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_files = len(uploaded_files)
            files_payload = []
            
            for idx, uf in enumerate(uploaded_files):
                status_text.text(f"Preparing {uf.name} ({idx+1}/{total_files})...")
                files_payload.append(("files", (uf.name, uf.getvalue(), uf.type or "application/pdf")))
                progress_bar.progress(int(((idx + 1) / total_files) * 50))
            
            status_text.text("Sending to backend RAG engine & chunking...")
            try:
                res = requests.post(f"{BACKEND_URL}/upload", files=files_payload, timeout=180)
                progress_bar.progress(100)
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"✨ {data.get('message', 'Documents indexed successfully!')}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Upload failed: {res.json().get('detail', res.text)}")
            except Exception as e:
                st.error(f"Connection error: {e}")

    # Display Document Library Statistics
    doc_count = library_data.get("total_documents", 0)
    total_pages = library_data.get("total_pages", 0)
    total_words = library_data.get("total_words", 0)

    st.markdown(f"""
    <div class="doc-stat-card">
        <strong>📚 Indexed Library:</strong> {doc_count} Document{'s' if doc_count != 1 else ''}<br>
        <strong>📑 Total Pages:</strong> {total_pages:,}<br>
        <strong>📝 Total Words:</strong> {total_words:,}
    </div>
    """, unsafe_allow_html=True)

    # Managed Documents List with individual delete option
    docs_list = library_data.get("documents", [])
    if docs_list:
        with st.expander(f"📁 View Indexed Files ({len(docs_list)})", expanded=False):
            for doc in docs_list:
                c_info, c_del = st.columns([4, 1])
                with c_info:
                    st.markdown(f"**{doc['filename']}**  \n<small style='color: #94a3b8;'>{doc['total_pages']} pgs • {doc['word_count']:,} words</small>", unsafe_allow_html=True)
                with c_del:
                    if st.button("🗑️", key=f"del_{doc['filename']}", help=f"Remove {doc['filename']}"):
                        try:
                            d_res = requests.delete(f"{BACKEND_URL}/documents/{doc['filename']}")
                            if d_res.status_code == 200:
                                st.toast(f"Removed {doc['filename']}")
                                time.sleep(0.5)
                                st.rerun()
                        except Exception as ex:
                            st.error(f"Failed to delete: {ex}")

    st.divider()

    # 2. Scope & Localization
    st.header("🎯 Scope & Language")
    
    doc_options = ["🌐 All Documents (Global Search)"] + [d["filename"] for d in docs_list]
    selected_scope_raw = st.selectbox(
        "Question Scope",
        options=doc_options,
        index=0,
        help="Select 'All Documents' to query across your entire uploaded library, or choose a specific document."
    )
    doc_filter = "all" if "All Documents" in selected_scope_raw else selected_scope_raw

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

    # 3. Quick Actions
    st.header("⚡ Quick Actions")
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        if st.button("📊 Summarize"):
            with st.spinner("Generating executive summary..."):
                try:
                    payload = {
                        "target_language": target_language,
                        "doc_filter": doc_filter,
                        "api_key": st.session_state.custom_api_key or None
                    }
                    response = requests.post(f"{BACKEND_URL}/summarize", json=payload, timeout=90)
                    if response.status_code == 200:
                        st.session_state.summary = response.json().get("summary")
                        st.rerun()
                    else:
                        st.error("Please upload at least one document first.")
                except Exception as e:
                    st.error(f"Backend call failed: {e}")

    with col_a2:
        if st.button("🧹 Clear Chat"):
            st.session_state.messages = []
            st.rerun()

    if st.button("🗑️ Reset Entire Library"):
        try:
            requests.post(f"{BACKEND_URL}/reset")
            st.session_state.summary = None
            st.session_state.messages = []
            st.success("Document library reset successfully.")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Reset failed: {e}")

    # 4. Unlimited API Configuration (Optional custom API Key)
    with st.expander("🔑 Unlimited API Key Settings (Optional)"):
        st.caption("IndicDoc-AI includes automatic multi-model failover & caching. You can also paste your personal Gemini API key here for 100% dedicated unlimited throughput.")
        custom_key_input = st.text_input(
            "Custom Google Gemini API Key",
            value=st.session_state.custom_api_key,
            type="password",
            placeholder="AIzaSy..."
        )
        if custom_key_input != st.session_state.custom_api_key:
            st.session_state.custom_api_key = custom_key_input
            st.toast("Custom API key saved!")

    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #64748b; font-size: 0.8rem;'>IndicDoc-AI v2.5 • Multi-PDF Semantic RAG</p>", unsafe_allow_html=True)

# Main Application Area
st.markdown('<p class="main-header">📑 IndicDoc-AI</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Unlimited Document Intelligence • Multi-PDF RAG • Page Citations & Multilingual Chat.</p>', unsafe_allow_html=True)

# Active Search Scope Banner
if doc_filter == "all":
    scope_text = f"🌐 Searching across **All Documents** ({doc_count} files, {total_pages:,} pages loaded)"
else:
    scope_text = f"🎯 Focused query on: **{doc_filter}**"

st.markdown(f'<div class="scope-banner">{scope_text}</div>', unsafe_allow_html=True)

# Show Executive Summary Card if generated
if st.session_state.summary:
    with st.expander("📋 Executive Summary (Click to collapse)", expanded=True):
        st.markdown(st.session_state.summary)

# Quick Suggestion Chips
st.caption("💡 Quick Suggestions:")
chip_cols = st.columns(4)
sample_prompt = None
with chip_cols[0]:
    if st.button("📌 Key Takeaways", key="chip1"):
        sample_prompt = "Provide a comprehensive summary of the core points and takeaways across the documents."
with chip_cols[1]:
    if st.button("⚖️ Risks & Liabilities", key="chip2"):
        sample_prompt = "What are the key penalty clauses, liabilities, obligations, or risks mentioned? Cite document names and page numbers."
with chip_cols[2]:
    if st.button("📅 Dates & Deadlines", key="chip3"):
        sample_prompt = "Extract all significant dates, milestones, or deadlines mentioned across the documents."
with chip_cols[3]:
    if st.button("🔍 Cross-Doc Comparison", key="chip4"):
        sample_prompt = "Compare the main themes, differences, or connections between the uploaded documents."

# Chat History Display
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Chat Input
user_input = st.chat_input("Ask any question across your documents (e.g. What is the fee structure? Compare the clauses?)...")
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
                "target_language": target_language,
                "doc_filter": doc_filter,
                "api_key": st.session_state.custom_api_key or None
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
                    try:
                        err_detail = res.json().get("detail", err_msg)
                        message_placeholder.error(f"Error: {err_detail}")
                    except Exception:
                        message_placeholder.error(err_msg)
        except Exception as e:
            message_placeholder.error(f"Connection failed: {str(e)}")

# Export Chat History Button (if messages exist)
if st.session_state.messages:
    st.markdown("---")
    chat_export_text = "# IndicDoc-AI Chat Transcript\n\n"
    for m in st.session_state.messages:
        role = "### User" if m["role"] == "user" else "### Assistant"
        chat_export_text += f"{role}\n{m['content']}\n\n"
    st.download_button(
        label="💾 Export Chat Transcript (.md)",
        data=chat_export_text,
        file_name="indicdoc_chat_transcript.md",
        mime="text/markdown"
    )
