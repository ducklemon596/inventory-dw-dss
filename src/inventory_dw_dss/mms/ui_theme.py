"""Scoped visual theme using native Streamlit components for accessibility."""
import streamlit as st


def apply_theme():
    st.html('''<style>
    :root {--mms-ink:#163239;--mms-teal:#087f82;--mms-muted:#637980;}
    .stApp {background:#f4f7f8; color:var(--mms-ink);}
    .block-container {max-width:1500px;padding-top:2.4rem;padding-bottom:3rem;}
    h1,h2,h3 {color:var(--mms-ink);letter-spacing:-.035em;}
    h1 {font-size:2.5rem!important;font-weight:750!important;}
    h2 {font-size:1.5rem!important;}
    [data-testid="stSidebar"] {background:#123b43;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {color:#edf6f5;}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#bbd2d6;}
    [data-testid="stSidebar"] p {color:#d6e6e8!important;}
    [data-testid="stSidebarCollapseButton"] button {color:#edf6f5;}
    [data-testid="stSidebar"] hr {border-color:#41636a;}
    [data-testid="stSidebar"] [data-testid="stExpander"] {background:#19464e;border-color:#41636a;}
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {background:#19464e;color:#edf6f5;}
    [data-testid="stMetric"] {background:white;border:1px solid #dfE8eb;
        border-radius:15px;padding:1.15rem 1.3rem;box-shadow:0 3px 12px #173b4305;}
    [data-testid="stMetricValue"] {font-weight:700;color:#0c646b;}
    [data-testid="stMetricLabel"] {color:var(--mms-muted);font-size:.85rem;}
    [data-testid="stButton"] button[kind="primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"] {background:#087f82;border-color:#087f82;}
    [data-testid="stTabs"] [role="tablist"] {gap:1rem;border-bottom:1px solid #dbe5e8;}
    [data-testid="stTabs"] [role="tab"] {padding:.85rem .35rem;font-weight:600;}
    [data-testid="stTabs"] [aria-selected="true"] {color:#087f82;}
    [data-testid="stExpander"], [data-testid="stForm"] {background:white;border-color:#dfe8eb;border-radius:12px;}
    [data-testid="stDataFrame"] {border-radius:12px;overflow:hidden;}
    .mms-eyebrow {font-size:.72rem;letter-spacing:.19em;font-weight:750;color:#087f82;margin-bottom:.4rem;}
    .mms-brand {font-size:1.3rem;font-weight:750;letter-spacing:-.03em;color:#fff;}
    .mms-empty {background:#fff;border:1px dashed #bacfd4;border-radius:18px;padding:2rem;text-align:center;}
    .mms-empty p {color:#637980;max-width:550px;margin:.5rem auto;}
    @media(max-width:700px) {
      .block-container {padding:1.4rem 1rem;}
      h1 {font-size:1.9rem!important;}
      [data-testid="stMetric"] {padding:.8rem;}
      [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem;}
      [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {min-width:0!important;width:auto!important;}
      [data-testid="stMetricValue"] {font-size:1.6rem;}
      [data-testid="stTabs"] [role="tablist"] {gap:.6rem;}
    }
    </style>''')
