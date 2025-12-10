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
    OCR text parser for dining logs with debug output and an item queue.

    - Detects station name and date.
    - Normalizes '#', 'lb', 'lbs', 'pounds' to 'lbs' (but does NOT touch plain numbers like 8165).
    - Supports:
        * Inline:  "Roasted Broccoli 8 lbs"
        * Multi-item block: several item lines, then several qty lines.
        * Two-line: "Rice" / "5 lbs"
    - Keeps a FIFO queue of pending items so quantities pair in order.
    - Returns: aggregated_df, station, debug_df
    """

    # -------- Station + Date detection --------
    station = detect_station_name(text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""

    # -------- Normalize units (but DO NOT touch plain numbers) --------
    cleaned_text = text

    # Fix obvious 'lbs' variants like '1bs', 'lbs.' or 'lb.'
    cleaned_text = re.sub(r"1[bB][sS]\.?", "lbs", cleaned_text)
    cleaned_text = re.sub(r"l[bB][sS]\.?", "lbs", cleaned_text)

    # Convert '#', 'lb', 'lbs', 'pounds' → 'lbs'
    cleaned_text = re.sub(r"(\d+)\s*#", r"\1 lbs", cleaned_text)
    cleaned_text = re.sub(
        r"(\d+)\s*(?:pounds?|pound|lbs?|lb)\b\.?",
        r"\1 lbs",
        cleaned_text,
        flags=re.IGNORECASE,
    )

    # Raw & cleaned line lists for debugging
    raw_lines = [ln.rstrip("\n") for ln in text.splitlines()]
    cleaned_lines = [ln.rstrip("\n") for ln in cleaned_text.splitlines()]

    # We'll classify only non-empty cleaned lines
    nonempty_indices = [i for i, ln in enumerate(cleaned_lines) if ln.strip()]

    # Pre-compiled patterns
    inline_pattern = re.compile(
        r"^([A-Za-z][A-Za-z\s\./,&-]+?)\s+(\d+(?:\.\d+)?)\s*lbs\b",
        re.IGNORECASE,
    )
    qty_pattern = re.compile(
        r"^(\d+(?:\.\d+)?)\s*lbs\b",
        re.IGNORECASE,
    )
    header_pattern = re.compile(
        r"^(Station|Time|Item|Date|Quantity)\b",
        re.IGNORECASE,
    )

    debug_rows = []
    rows = []

    pending_items = []   # FIFO queue of items waiting for a quantity
    last_item = None     # most recent item we saw (for fallback)

    for idx in nonempty_indices:
        raw_line = raw_lines[idx]
        cline = cleaned_lines[idx].strip()
        cline = re.sub(r"\s+", " ", cline)

        classification = "ignored"
        item_candidate = ""
        qty_candidate = ""
        last_item_after = last_item

        # Header?
        if header_pattern.match(cline):
            classification = "header"

        else:
            # 1) Inline "Item 10 lbs"
            m_inline = inline_pattern.match(cline)
            if m_inline:
                classification = "inline"
                item_candidate = m_inline.group(1)
                qty_candidate = m_inline.group(2)

                item = item_candidate.replace(".", " ").strip()
                item = re.sub(r"\s+", " ", item)
                try:
                    qty = float(qty_candidate)
                    rows.append((header_date, item, qty))
                    last_item = item
                    last_item_after = last_item
                except ValueError:
                    pass

            else:
                # 2) Pure quantity "10 lbs"
                m_qty = qty_pattern.match(cline)
                if m_qty:
                    classification = "qty_only"
                    qty_candidate = m_qty.group(1)

                    try:
                        qty = float(qty_candidate)
                    except ValueError:
                        qty = None

                    if qty is not None:
                        if pending_items:
                            # Use the oldest pending item (FIFO)
                            item = pending_items.pop(0)
                        else:
                            # Fallback: use the last seen item
                            item = last_item

                        if item is not None:
                            rows.append((header_date, item, qty))
                            last_item = item
                            last_item_after = last_item

                else:
                    # 3) Item-only line (letters, no digits)
                    has_letters = bool(re.search(r"[A-Za-z]", cline))
                    has_digits = bool(re.search(r"\d", cline))
                    if has_letters and not has_digits:
                        classification = "item_only"
                        item_candidate = cline
                        item = cline.replace(".", " ").strip()
                        item = re.sub(r"\s+", " ", item)
                        pending_items.append(item)
                        last_item = item
                        last_item_after = last_item

        debug_rows.append(
            {
                "idx": idx,
                "raw_line": raw_line,
                "cleaned_line": cline,
                "classification": classification,
                "item_candidate": item_candidate,
                "qty_candidate": qty_candidate,
                "pending_items_after_line": list(pending_items),
                "last_item_after_line": last_item_after,
            }
        )

    # -------- Build DataFrame --------
    if not rows:
        debug_df = pd.DataFrame(debug_rows)
        empty_df = pd.DataFrame(
            columns=["Station", "Date", "Item", "Total Quantity (lbs)"]
        )
        return empty_df, station, debug_df

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

    debug_df = pd.DataFrame(debug_rows)
    return aggregated, station, debug_df

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
    df, detected_station, debug_df = parse_ocr_text(text_output)


    # Show detected station
    if detected_station and detected_station != "Unknown":
        st.info(f"Detected Station: {detected_station}")
    else:
        st.warning(
            "Station not clearly detected. Please confirm the station on the original log."
        )

    st.dataframe(df, use_container_width=True)

     # --- Temporary debug view ---
    with st.expander("Debug: OCR line parsing (temporary)"):
        st.write("Each OCR line and how the parser classified it:")
        st.dataframe(debug_df, use_container_width=True)

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
