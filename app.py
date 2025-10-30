# --------------------------------------------------------
# SMC Dining OCR — Streamlit + Google Vision (Cloud Ready)
# Author: Jonathan White
# Date: October 2025
# --------------------------------------------------------

import streamlit as st
import pandas as pd
import re
import io
import smtplib
import tempfile
import json
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google.cloud import vision
from google.oauth2 import service_account

# --------------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------------
st.set_page_config(page_title="SMC Dining OCR", layout="wide")

# SMC Brand Colors
SMC_NAVY = "#002855"
SMC_RED = "#C8102E"

# Optional CSS theme
css_path = Path("assets/theme.css")
if css_path.exists():
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Logo path (optional asset)
import base64
from pathlib import Path

logo_path = Path("assets/smc_g_logo.png")

def load_logo_base64(logo_path):
    with open(logo_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_data = load_logo_base64(logo_path)

# --------------------------------------------------------
# TOP BANNER
# --------------------------------------------------------
st.markdown(
    f"""
    <div style="background-color:{SMC_NAVY};padding:15px 25px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h1 style="color:white;margin-bottom:4px;"> SMC Dining OCR</h1>
            <p style="color:white;margin-top:0;font-size:16px;">Built by Group 1 · Powered by Google Cloud Vision API</p>
        </div>
            <img src="data:image/png;base64,{logo_data}" width="80" style="border-radius:6px;margin-left:10px;">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

st.write("""
Upload a photo of your handwritten prep log.  
The system reads entries using **Google Cloud Vision API**, cleans and groups “like” items, and allows you to **download or email** the aggregated CSV report.
""")

# --------------------------------------------------------
# OCR FUNCTION — fixed for Streamlit Cloud
# --------------------------------------------------------

def extract_text_from_image(uploaded_image):
    """Extract text from uploaded image using credentials stored in Streamlit Secrets."""
    try:
        # ✅ Always load from Streamlit Secrets in cloud
        credentials_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(dict(credentials_info))
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception as e:
        st.error("❌ Failed to load Google Cloud Vision credentials. Check Streamlit Secrets.")
        st.stop()

    content = uploaded_image.read()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        return "No text detected."
    return texts[0].description

# --------------------------------------------------------
# PARSE FUNCTION (aggregate like-data)
# --------------------------------------------------------
def parse_ocr_text(text):
    """Cleans OCR text and aggregates quantities of similar menu items."""
    cleaned = re.sub(r'\s+', ' ', text.strip())
    cleaned = re.sub(r'(\d+)\s?1?65\.?', r'\1 lbs', cleaned)
    cleaned = re.sub(r'(\d+)\s?lb[sS]?', r'\1 lbs', cleaned)

    pattern = r"(\d{1,2}/\d{1,2})\s+([\d:]{4,5})\s+([A-Za-z\s]+?)\s+(\d+)\s*lbs\.?"
    rows = re.findall(pattern, cleaned, re.IGNORECASE)

    if not rows:
        return pd.DataFrame(columns=["Date", "Item", "Total Quantity (lbs)"])

    df = pd.DataFrame(rows, columns=["Date", "Time", "Item", "Quantity"])
    df["Item"] = df["Item"].str.strip().str.title()
    df["Quantity"] = df["Quantity"].astype(float)

    # Detect merged items like "Teriyaki Chicken Rice"
    menu_items = ["Roasted Broccoli", "Teriyaki Chicken", "Rice"]
    fixed_rows = []

    for _, row in df.iterrows():
        item = row["Item"]
        qty = row["Quantity"]
        found = [m for m in menu_items if m in item]
        if len(found) > 1:
            split_qty = qty / len(found)
            for f in found:
                fixed_rows.append([row["Date"], f, split_qty])
        else:
            fixed_rows.append([row["Date"], item, qty])

    fixed_df = pd.DataFrame(fixed_rows, columns=["Date", "Item", "Quantity"])

    # Aggregate by Date + Item
    aggregated = (
        fixed_df.groupby(["Date", "Item"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Quantity": "Total Quantity (lbs)"})
    )

    aggregated["Total Quantity (lbs)"] = aggregated["Total Quantity (lbs)"].round(1)
    return aggregated

# --------------------------------------------------------
# FILE UPLOAD SECTION
# --------------------------------------------------------
st.markdown(f"""
<div style='background-color:{SMC_RED};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 1 — Upload Your Log</h3>
</div>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload image (JPG, JPEG, PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    with st.spinner("Reading image... please wait"):
        text_output = extract_text_from_image(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", text_output, height=200)

    st.subheader(" Parsed & Aggregated Table")
    df = parse_ocr_text(text_output)
    st.dataframe(df, use_container_width=True)

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Aggregated CSV",
            csv,
            "aggregated_dining_log.csv",
            "text/csv",
            use_container_width=True
        )
    else:
        st.warning("No valid table data found. Try a clearer photo or adjust handwriting spacing.")
else:
    st.info("Please upload an image to begin.")

# --------------------------------------------------------
# STEP 2 — DOWNLOAD OR EMAIL LATER
# --------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(f"""
<div style='background-color:{SMC_NAVY};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 2 — Download or Email Later</h3>
</div>
""", unsafe_allow_html=True)

if 'df' in locals() and not df.empty:
    st.success("✅ Aggregated CSV is ready.")
    st.markdown("You can download the file below and email it manually if needed.")
    csv_data = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="⬇️ Download Aggregated CSV File",
        data=csv_data,
        file_name="aggregated_dining_log.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.info("No CSV available yet — please upload and process an image first.")

st.markdown("<br><hr>", unsafe_allow_html=True)
st.caption("Saint Mary’s College Dining Data Project · Developed by Group 1")
