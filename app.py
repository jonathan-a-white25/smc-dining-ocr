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

SMC_NAVY = "#002855"
SMC_RED = "#C8102E"

STATION_NAMES = [
    "Stacked",
    "Simple Servings",
    "Sizzle",
    "Slices",
    "Twists",
    "Bliss",
]

# --------------------------------------------------------
# OPTIONAL CSS
# --------------------------------------------------------
css_path = Path("assets/theme.css")
if css_path.exists():
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# --------------------------------------------------------
# LOGO
# --------------------------------------------------------
logo_path = Path("assets/smc_g_logo.png")


def load_logo_base64(path: Path) -> str:
    with open(path, "rb") as f:
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
OCR will extract all items and quantities, normalize units, merge similar items,
and generate a clean CSV for you to download.
"""
)

# --------------------------------------------------------
# OCR CALL
# --------------------------------------------------------
def extract_text_from_image(uploaded_image):
    """Google Vision OCR using Streamlit Secrets credentials."""
    try:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(dict(info))
        client = vision.ImageAnnotatorClient(credentials=creds)
    except Exception:
        st.error("❌ Could not load Google Vision credentials. Check Streamlit Secrets.")
        st.stop()

    content = uploaded_image.read()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations

    return texts[0].description if texts else ""


# --------------------------------------------------------
# STATION DETECTION
# --------------------------------------------------------
def detect_station_name(text: str) -> str:
    """Look for one of the known station names anywhere in the OCR text."""
    for name in STATION_NAMES:
        if re.search(rf"\b{name}\b", text, re.IGNORECASE):
            return name
    return "Unknown"


# --------------------------------------------------------
# MAIN PARSER (NO MERGE STEP)
# --------------------------------------------------------
def parse_ocr_text(text: str):
    """
    OCR text parser for dining logs.

    - Detects station + date.
    - Normalizes units (#, lb, lbs, pounds → 'lbs').
    - Uses FIFO queue to associate item-only lines with following qty-only lines.
    - Normalizes item names (punctuation, broccoli synonyms, title case).
    - Uses fuzzy + token-based grouping to merge misspellings.
    - Returns: aggregated_df, station, debug_df
    """

    # ---- Station + Date ----
    station = detect_station_name(text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""

    # ---- Normalize units but do NOT modify plain numbers ----
    cleaned = text

    # Fix obvious 'lbs' typos like '1bs', 'lbs.' or 'lb.'
    cleaned = re.sub(r"1[bB][sS]\.?", "lbs", cleaned)
    cleaned = re.sub(r"l[bB][sS]\.?", "lbs", cleaned)

    # Convert '#', 'lb', 'lbs', 'pounds' → 'lbs'
    cleaned = re.sub(r"(\d+)\s*#", r"\1 lbs", cleaned)
    cleaned = re.sub(
        r"(\d+)\s*(?:pounds?|pound|lbs?|lb)\b\.?",
        r"\1 lbs",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned_lines = [ln.rstrip("\n") for ln in cleaned.splitlines()]

    # ----------------------------------------------------
    # PATTERNS FOR CLASSIFICATION
    # ----------------------------------------------------
    inline_re = re.compile(
        r"^([A-Za-z][A-Za-z\s\./,&-]+?)\s+(\d+(?:\.\d+)?)\s*lbs\b",
        re.IGNORECASE,
    )
    qty_re = re.compile(
        r"^(\d+(?:\.\d+)?)\s*lbs\b",
        re.IGNORECASE,
    )
    header_re = re.compile(
        r"^(Station|Time|Item|Date|Quantity)\b",
        re.IGNORECASE,
    )

    rows = []
    debug_rows = []
    pending_items = []  # FIFO queue of items waiting for a quantity
    last_item = None    # Most recent item, used as fallback

    # ----------------------------------------------------
    # CLASSIFICATION + ITEM/QTY MATCHING LOOP
    # ----------------------------------------------------
    for idx, line in enumerate(cleaned_lines):
        cl = line.strip()
        if not cl:
            continue

        cl = re.sub(r"\s+", " ", cl)

        classification = "ignored"
        item_candidate = ""
        qty_candidate = ""
        last_item_after = last_item

        # ---- Headers ----
        if header_re.match(cl):
            classification = "header"

        else:
            # ---- Case 1: inline "Item 10 lbs" ----
            m_inline = inline_re.match(cl)
            if m_inline:
                classification = "inline"
                item_candidate = m_inline.group(1).strip()
                qty_candidate = m_inline.group(2).strip()

                item = item_candidate
                try:
                    qty = float(qty_candidate)
                    rows.append((header_date, item, qty))
                    last_item = item
                    last_item_after = item
                except ValueError:
                    pass

            else:
                # ---- Case 2: quantity-only "10 lbs" ----
                m_qty = qty_re.match(cl)
                if m_qty:
                    classification = "qty_only"
                    qty_candidate = m_qty.group(1).strip()

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
                            last_item_after = item

                else:
                    # ---- Case 3: item-only line (letters, no digits) ----
                    has_letters = bool(re.search(r"[A-Za-z]", cl))
                    has_digits = bool(re.search(r"\d", cl))

                    if has_letters and not has_digits:
                        classification = "item_only"
                        item_candidate = cl
                        pending_items.append(cl)
                        last_item = cl
                        last_item_after = cl

        debug_rows.append(
            {
                "idx": idx,
                "cleaned_line": cl,
                "classification": classification,
                "item_candidate": item_candidate,
                "qty_candidate": qty_candidate,
                "pending_items_after_line": list(pending_items),
                "last_item_after_line": last_item_after,
            }
        )

    # ----------------------------------------------------
    # HANDLE CASE: NO ROWS FOUND
    # ----------------------------------------------------
    if not rows:
        empty_df = pd.DataFrame(
            columns=["Station", "Date", "Item", "Total Quantity (lbs)"]
        )
        debug_df = pd.DataFrame(debug_rows)
        return empty_df, station, debug_df

    # ----------------------------------------------------
    # BUILD WORKING DATAFRAME
    # ----------------------------------------------------
    df = pd.DataFrame(rows, columns=["Date", "Item", "Quantity"])
    df["Quantity"] = df["Quantity"].astype(float)

    # ---- Item name normalization ----
    # 1) strip trailing punctuation
    df["Item"] = df["Item"].str.replace(r"[^\w\s]", "", regex=True)

    # 2) broccoli-related synonyms + other manual mappings
    def normalize_item(name: str) -> str:
        n = name.lower().strip()

        # Broccoli-related variants
        if n in {"raasted broccoli", "roasted broccoli", "broccoli", "roasted"}:
            return "Roasted Broccoli"

        return name

    df["Item"] = df["Item"].apply(normalize_item)

    # 3) collapse extra spaces and use Title Case
    df["Item"] = (
        df["Item"]
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.title()
    )

    # ----------------------------------------------------
    # FUZZY + TOKEN MERGING
    # ----------------------------------------------------
    unique_items = list(dict.fromkeys(df["Item"].tolist()))  # preserve first-seen order
    canonicals = []
    mapping = {}
    cutoff = 0.87

    for item in unique_items:
        if not canonicals:
            canonicals.append(item)
            mapping[item] = item
            continue

        # 1) Strong character-level similarity
        match = difflib.get_close_matches(item, canonicals, n=1, cutoff=cutoff)
        if match:
            mapping[item] = match[0]
            continue

        # 2) Word-level overlap, e.g., "Broccoli" vs "Roasted Broccoli"
        tokens = set(item.split())
        best_canon = None
        best_overlap = 0

        for c in canonicals:
            overlap = len(tokens & set(c.split()))
            if overlap > best_overlap:
                best_overlap = overlap
                best_canon = c

        if best_canon and best_overlap > 0:
            mapping[item] = best_canon
        else:
            canonicals.append(item)
            mapping[item] = item

    df["Canonical Item"] = df["Item"].map(mapping)

    aggregated = (
        df.groupby(["Date", "Canonical Item"], as_index=False)["Quantity"]
        .sum()
        .rename(
            columns={
                "Canonical Item": "Item",
                "Quantity": "Total Quantity (lbs)",
            }
        )
    )

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

    # Debug view
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
