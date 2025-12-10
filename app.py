# --------------------------------------------------------
# SMC Dining OCR — Streamlit + Google Vision (Cloud Ready)
# Author: Jonathan White
# Date: October 2025
# --------------------------------------------------------

import streamlit as st
import pandas as pd
import re
import base64
import difflib
from pathlib import Path
from datetime import datetime
from google.cloud import vision
from google.oauth2 import service_account

# --------------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------------
st.set_page_config(page_title="SMC Dining OCR", layout="wide")

# SMC Brand Colors
SMC_NAVY = "#002855"
SMC_RED = "#C8102E"

# Known station names to detect in OCR text
STATION_NAMES = [
    "Stacked",
    "Simple Servings",
    "Sizzle",
    "Slices",
    "Twists",
    "Bliss",
]

# --------------------------------------------------------
# OPTIONAL CSS THEME
# --------------------------------------------------------
css_path = Path("assets/theme.css")
if css_path.exists():
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# --------------------------------------------------------
# LOGO LOADING
# --------------------------------------------------------
logo_path = Path("assets/smc_g_logo.png")


def load_logo_base64(logo_path: Path) -> str:
    with open(logo_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


logo_data = load_logo_base64(logo_path)

# --------------------------------------------------------
# TOP BANNER
# --------------------------------------------------------
st.markdown(
    f"""
    <div style="background-color:{SMC_NAVY};padding:15px 25px;border-radius:8px;
                display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h1 style="color:white;margin-bottom:4px;">SMC Dining OCR</h1>
            <p style="color:white;margin-top:0;font-size:16px;">
                Built by Group 1 · Powered by Google Cloud Vision API
            </p>
        </div>
        <img src="data:image/png;base64,{logo_data}" width="80"
             style="border-radius:6px;margin-left:10px;">
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

st.write(
    """
Upload a photo of your handwritten prep log.  
The system reads entries using **Google Cloud Vision API**, cleans and groups similar
items, and lets you **download** the aggregated CSV report.
"""
)

# --------------------------------------------------------
# OCR FUNCTION — uses credentials from Streamlit Secrets
# --------------------------------------------------------


def extract_text_from_image(uploaded_image):
    """Extract text from uploaded image using credentials stored in Streamlit Secrets."""
    try:
        credentials_info = st.secrets["gcp_service_account"]
        credentials = service_account.Credentials.from_service_account_info(
            dict(credentials_info)
        )
        client = vision.ImageAnnotatorClient(credentials=credentials)
    except Exception:
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
# STATION DETECTION
# --------------------------------------------------------
def detect_station_name(text: str) -> str:
    """
    Look for one of the known station names anywhere in the OCR text.
    Returns 'Unknown' if none found.
    """
    for name in STATION_NAMES:
        if re.search(rf"\b{name}\b", text, re.IGNORECASE):
            return name
    return "Unknown"


# --------------------------------------------------------
# PARSE FUNCTION (aggregate like-data, fuzzy grouping)
# --------------------------------------------------------
def parse_ocr_text(text: str):
    """
    Cleans OCR text and aggregates quantities of similar menu items.

    - Detects the station name from the full OCR text.
    - Normalizes weight formats (10#, 10 lbs, 10 pounds → 10 lbs).
    - Extracts rows with Date, Time, Item, Quantity.
    - Uses fuzzy grouping so similar item names aggregate together.
    - Returns: (aggregated_df, station)
    """
    # Detect station from the raw OCR text
    station = detect_station_name(text)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", text.strip())

    # Normalize all weight notations to 'lbs'
    # Handles: '10#', '10 #', '10 lb', '10lbs', '10 LB', '10 pounds', '10 pound'
    cleaned = re.sub(r"(\d+)\s*#", r"\1 lbs", cleaned)  # kitchen shorthand '#'
    cleaned = re.sub(
        r"(\d+)\s*(?:pounds?|pound|lbs?|lb)\b\.?",
        r"\1 lbs",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Keep original custom normalizations if they help with noisy OCR
    cleaned = re.sub(r"(\d+)\s?1?65\.?", r"\1 lbs", cleaned)
    cleaned = re.sub(r"(\d+)\s?lb[sS]?", r"\1 lbs", cleaned)

    # Pattern: Date, Time, Item, Quantity (numeric) before 'lbs'
    pattern = (
        r"(\d{1,2}/\d{1,2})\s+"        # Date (e.g., 10/15)
        r"([\d:]{4,5})\s+"             # Time (e.g., 7:30, 12:00)
        r"([A-Za-z\s]+?)\s+"           # Item (lazy match)
        r"(\d+(?:\.\d+)?)\s*lbs\.?"    # Quantity number followed by 'lbs'
    )
    rows = re.findall(pattern, cleaned, re.IGNORECASE)

    if not rows:
        empty_df = pd.DataFrame(
            columns=["Station", "Date", "Item", "Total Quantity (lbs)"]
        )
        return empty_df, station

    df = pd.DataFrame(rows, columns=["Date", "Time", "Item", "Quantity"])

    # Basic cleaning
    df["Item"] = df["Item"].str.strip().str.title()
    df["Quantity"] = df["Quantity"].astype(float)

    # --------------------------------------------------------
    # Fuzzy grouping of similar item names
    # --------------------------------------------------------
    unique_items = sorted(df["Item"].unique())
    canonicals = []
    mapping = {}
    cutoff = 0.87  # similarity threshold for grouping similar items

    for item in unique_items:
        if not canonicals:
            # First item becomes its own canonical form
            canonicals.append(item)
            mapping[item] = item
        else:
            # Find the closest existing canonical name
            match = difflib.get_close_matches(item, canonicals, n=1, cutoff=cutoff)
            if match:
                # Map this item to the existing canonical name
                mapping[item] = match[0]
            else:
                # Start a new canonical group
                canonicals.append(item)
                mapping[item] = item

    # Apply the canonical mapping
    df["Canonical Item"] = df["Item"].map(mapping)

    # Aggregate by Date + Canonical Item
    aggregated = (
        df.groupby(["Date", "Canonical Item"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Canonical Item": "Item", "Quantity": "Total Quantity (lbs)"})
    )

    aggregated["Total Quantity (lbs)"] = aggregated["Total Quantity (lbs)"].round(1)

    # Attach Station column and reorder
    aggregated["Station"] = station
    aggregated = aggregated[["Station", "Date", "Item", "Total Quantity (lbs)"]]

    return aggregated, station


# --------------------------------------------------------
# FILE UPLOAD SECTION
# --------------------------------------------------------
st.markdown(
    f"""
<div style='background-color:{SMC_RED};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 1 — Upload Your Log</h3>
</div>
""",
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader(
    "Upload image (JPG, JPEG, PNG)", type=["jpg", "jpeg", "png"]
)

if uploaded_file is not None:
    # Capture upload timestamp for filename
    upload_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with st.spinner("Reading image... please wait"):
        text_output = extract_text_from_image(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", text_output, height=200)

    # Parse + aggregate + detect station
    st.subheader("Parsed & Aggregated Table")
    df, detected_station = parse_ocr_text(text_output)

    # Show detected station
    if detected_station and detected_station != "Unknown":
        st.info(f"Detected Station: {detected_station}")
    else:
        st.warning(
            "Station not clearly detected. Please confirm the station on the original log."
        )

    st.dataframe(df, use_container_width=True)

    if not df.empty:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        safe_station = (detected_station or "UnknownStation").replace(" ", "_")
        file_name = f"{safe_station}_{upload_timestamp}_dining_log.csv"

        st.download_button(
            "⬇️ Download Aggregated CSV",
            csv_bytes,
            file_name,
            "text/csv",
            use_container_width=True,
        )
    else:
        st.warning(
            "No valid table data found. Try a clearer photo or adjust handwriting spacing."
        )
else:
    st.info("Please upload an image to begin.")

# --------------------------------------------------------
# STEP 2 — DOWNLOAD OR EMAIL LATER
# --------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
<div style='background-color:{SMC_NAVY};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 2 — Download or Email Later</h3>
</div>
""",
    unsafe_allow_html=True,
)

if "df" in locals() and not df.empty:
    st.success("✅ Aggregated CSV is ready.")
    st.markdown("You can download the file below and email it manually if needed.")
    csv_data = df.to_csv(index=False).encode("utf-8")

    # Try to reuse station + timestamp; fall back safely if not defined
    try:
        safe_station = (detected_station or "UnknownStation").replace(" ", "_")
    except NameError:
        safe_station = "UnknownStation"

    try:
        ts = upload_timestamp
    except NameError:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    file_name_later = f"{safe_station}_{ts}_dining_log.csv"

    st.download_button(
        label="⬇️ Download Aggregated CSV File",
        data=csv_data,
        file_name=file_name_later,
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("No CSV available yet — please upload and process an image first.")

st.markdown("<br><hr>", unsafe_allow_html=True)
st.caption("Saint Mary’s College Dining Data Project · Developed by Group 1")
