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
# OCR CALL — return full text + per-word bounding boxes
# --------------------------------------------------------
def extract_text_and_boxes(uploaded_image):
    """Use Google Vision to get full text and bounding boxes for each word."""
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
    annotations = response.text_annotations

    if not annotations:
        return "", []

    full_text = annotations[0].description

    # Build list of word boxes with centers
    word_boxes = []
    for ann in annotations[1:]:
        if not ann.description.strip():
            continue
        vertices = ann.bounding_poly.vertices
        xs = [v.x for v in vertices]
        ys = [v.y for v in vertices]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        word_boxes.append(
            {
                "text": ann.description,
                "cx": cx,
                "cy": cy,
            }
        )

    return full_text, word_boxes


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
# HELPER: CLUSTER WORDS INTO ROWS BY Y-COORDINATE
# --------------------------------------------------------
def cluster_rows(word_boxes, row_threshold=25):
    """
    Group words into rows based on their vertical (cy) position.

    row_threshold: max vertical distance (pixels) between words
                   to be considered in the same row.
    """
    if not word_boxes:
        return []

    sorted_words = sorted(word_boxes, key=lambda w: w["cy"])
    rows = []
    current_row = []
    current_y = None

    for w in sorted_words:
        if current_y is None:
            current_row = [w]
            current_y = w["cy"]
            continue

        if abs(w["cy"] - current_y) <= row_threshold:
            current_row.append(w)
            # keep running average (not critical, just stability)
            current_y = (current_y + w["cy"]) / 2.0
        else:
            rows.append(current_row)
            current_row = [w]
            current_y = w["cy"]

    if current_row:
        rows.append(current_row)

    return rows


# --------------------------------------------------------
# HELPER: PARSE A SINGLE ROW INTO (ITEM, QUANTITY)
# --------------------------------------------------------
def parse_row_tokens(tokens):
    """
    Given a list of tokens for a single row (ordered left → right),
    return (item_text, quantity_value) or (None, None) if no quantity found.
    """

    # Detect the first quantity-ish token
    qty_index = None
    qty_value = None

    for idx, tok in enumerate(tokens):
        raw = tok.strip()
        if not raw:
            continue

        # normalize: keep letters, digits, and #
        t = re.sub(r"[^\w#]", "", raw.lower())

        if not t:
            continue

        # pattern: digits + optional unit/# suffix
        m = re.match(r"^(\d+)(#|lbs?|lb|pounds?)?$", t)
        if m:
            try:
                qty_value = float(m.group(1))
                qty_index = idx
                break
            except ValueError:
                continue

    if qty_index is None or qty_value is None:
        return None, None

    # Everything to the left of the first quantity token is the item
    item_tokens = tokens[:qty_index]
    item_text = " ".join(item_tokens).strip()

    if not item_text:
        return None, None

    return item_text, qty_value


# --------------------------------------------------------
# MAIN PARSER — BOUNDING BOX–BASED
# --------------------------------------------------------
def parse_ocr_text(full_text: str, word_boxes):
    """
    Full OCR parsing with bounding boxes:

    - Detects station and date from full text.
    - Clusters words into rows using Y-coordinates.
    - For each row, finds first numeric quantity on the right.
    - Treats everything to the left as item name.
    - Normalizes item names (punctuation, broccoli synonyms, Title Case).
    - Fuzzy merges similar items and aggregates quantities.
    - Returns: aggregated_df, station, debug_df
    """

    station = detect_station_name(full_text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""

    # Normalize units inside tokens for easier parsing
    # (we only use this inside parse_row_tokens, so we keep boxes as-is)
    # The per-token logic there handles #, lb, lbs, pounds etc.

    # Cluster words into row groups
    rows = cluster_rows(word_boxes, row_threshold=25)

    all_rows = []
    debug_rows = []

    for row_idx, row_words in enumerate(rows):
        # Sort each row left→right
        row_words_sorted = sorted(row_words, key=lambda w: w["cx"])
        tokens = [w["text"] for w in row_words_sorted]
        row_text = " ".join(tokens)

        # Classify row
        classification = "data"
        item_candidate = ""
        qty_candidate = ""

        # Skip header-like rows
        header_keywords = ["station", "time", "item", "quantity", "date"]
        if any(re.search(rf"\b{hk}\b", row_text, re.IGNORECASE) for hk in header_keywords):
            classification = "header"
        else:
            item, qty = parse_row_tokens(tokens)
            if item is None or qty is None:
                classification = "no_qty"
            else:
                classification = "parsed"
                item_candidate = item
                qty_candidate = qty
                all_rows.append((header_date, item, qty))

        debug_rows.append(
            {
                "row_index": row_idx,
                "row_text": row_text,
                "classification": classification,
                "item_candidate": item_candidate,
                "qty_candidate": qty_candidate,
            }
        )

    # If no rows with quantities, return empty
    if not all_rows:
        empty_df = pd.DataFrame(
            columns=["Station", "Date", "Item", "Total Quantity (lbs)"]
        )
        debug_df = pd.DataFrame(debug_rows)
        return empty_df, station, debug_df

    # Build DataFrame from parsed rows
    df = pd.DataFrame(all_rows, columns=["Date", "Item", "Quantity"])
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
    upload_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with st.spinner("Reading image... please wait"):
        full_text, word_boxes = extract_text_and_boxes(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", full_text, height=200)

    st.subheader("Parsed & Aggregated Table")
    df, detected_station, debug_df = parse_ocr_text(full_text, word_boxes)

    # Show detected station
    if detected_station and detected_station != "Unknown":
        st.info(f"Detected Station: {detected_station}")
    else:
        st.warning(
            "Station not clearly detected. Please confirm the station on the original log."
        )

    st.dataframe(df, use_container_width=True)

    # Debug view
    with st.expander("Debug: row reconstruction and parsing"):
        st.write("Each reconstructed row and how the parser classified it:")
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
