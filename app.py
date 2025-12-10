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
# PARSE FUNCTION (robust OCR cleanup + fuzzy aggregation)
# --------------------------------------------------------
def parse_ocr_text(text: str):
    """
    OCR text parser for dining logs using a simple pairing strategy.

    - Detects station name and date.
    - Normalizes '#', 'lb', 'lbs', 'pounds' to 'lbs'.
    - Treats lines with only letters as items.
    - Treats lines with digits + 'lbs' as quantities.
    - Also supports inline 'Item 10 lbs' lines.
    - Pairs items and quantities in order, then aggregates with fuzzy matching.
    """

    # -------- Station + Date detection --------
    station = detect_station_name(text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""

    # -------- Normalize units, but DO NOT touch plain numbers --------
    cleaned_text = text

    # Fix obvious misreads like '1bs', 'lbs.', 'lb.'
    cleaned_text = re.sub(r"1[bB][sS]\.?", "lbs", cleaned_text)
    cleaned_text = re.sub(r"l[bB][sS]\.?", "lbs", cleaned_text)

    # Convert '#', 'pounds', etc. to 'lbs'
    cleaned_text = re.sub(r"(\d+)\s*#", r"\1 lbs", cleaned_text)
    cleaned_text = re.sub(
        r"(\d+)\s*(?:pounds?|pound|lbs?|lb)\b\.?",
        r"\1 lbs",
        cleaned_text,
        flags=re.IGNORECASE,
    )

    # Split into non-empty lines
    lines = [ln.strip() for ln in cleaned_text.splitlines() if ln.strip()]

    inline_rows = []      # (date, item, qty) where item+qty are on same line
    item_lines = []       # item-only lines (letters, no digits)
    qty_values = []       # numeric quantities from pure '10 lbs' lines

    # -------- First pass: classify lines --------
    for raw_line in lines:
        line = raw_line.strip()

        # Skip headers
        if re.match(r"^(Station|Time|Item|Date|Quantity)\b", line, re.IGNORECASE):
            continue

        # Collapse internal spaces
        line = re.sub(r"\s+", " ", line)

        has_letters = bool(re.search(r"[A-Za-z]", line))
        has_digits = bool(re.search(r"\d", line))
        has_lbs = bool(re.search(r"\blbs\b", line, re.IGNORECASE))

        # Case 1: inline "Item 10 lbs"
        if has_letters and has_digits and has_lbs:
            m = re.search(
                r"([A-Za-z][A-Za-z\s\.]+?)\s+(\d+(?:\.\d+)?)\s*lbs",
                line,
                re.IGNORECASE,
            )
            if m:
                item_text = m.group(1)
                qty_str = m.group(2)
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue

                item = item_text.replace(".", " ").strip()
                item = re.sub(r"\s+", " ", item)
                inline_rows.append((header_date, item, qty))
            continue

        # Case 2: item-only line (letters, no digits)
        if has_letters and not has_digits:
            item = line.replace(".", " ").strip()
            item = re.sub(r"\s+", " ", item)
            item_lines.append(item)
            continue

        # Case 3: pure quantity line (digits + 'lbs', no letters)
        if has_digits and has_lbs and not has_letters:
            m = re.search(r"(\d+(?:\.\d+)?)\s*lbs", line, re.IGNORECASE)
            if m:
                qty_str = m.group(1)
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue
                qty_values.append(qty)
            continue

        # Anything else (plain numbers like '8165', junk) -> ignore

    # -------- Pair separate item and quantity lists in order --------
    rows = list(inline_rows)  # start with inline rows

    pair_count = min(len(item_lines), len(qty_values))
    for idx in range(pair_count):
        rows.append((header_date, item_lines[idx], qty_values[idx]))

    # -------- Build DataFrame --------
    if not rows:
        empty_df = pd.DataFrame(
            columns=["Station", "Date", "Item", "Total Quantity (lbs)"]
        )
        return empty_df, station

    df = pd.DataFrame(rows, columns=["Date", "Item", "Quantity"])

    # Clean item names
    df["Item"] = (
        df["Item"]
        .str.replace(r"\d+\s*lbs", "", regex=True)
        .str.replace(r"lbs", "", regex=True)
        .str.strip()
        .str.title()
    )

    df["Quantity"] = df["Quantity"].astype(float)

    # -------- Fuzzy grouping (merge misspellings) --------
    unique_items = sorted(df["Item"].unique())
    canonicals = []
    mapping = {}
    cutoff = 0.87

    for item in unique_items:
        if not canonicals:
            canonicals.append(item)
            mapping[item] = item
        else:
            match = difflib.get_close_matches(item, canonicals, n=1, cutoff=cutoff)
            if match:
                mapping[item] = match[0]
            else:
                canonicals.append(item)
                mapping[item] = item

    df["Canonical Item"] = df["Item"].map(mapping)

    aggregated = (
        df.groupby(["Date", "Canonical Item"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Canonical Item": "Item", "Quantity": "Total Quantity (lbs)"})
    )

    aggregated["Total Quantity (lbs)"] = aggregated["Total Quantity (lbs)"].round(1)
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
