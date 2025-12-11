# --------------------------------------------------------
# SMC Dining OCR — Streamlit + Google Vision (Cloud Ready)
# Author: Jonathan White (Revised by Gemini)
# Date: December 2025
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
# PAGE CONFIGURATION & CONSTANTS
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
# OPTIONAL CSS & LOGO SETUP
# --------------------------------------------------------
css_path = Path("assets/theme.css")
if css_path.exists():
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

logo_path = Path("assets/smc_g_logo.png")


def load_logo_base64(path: Path) -> str:
    """Loads logo and encodes to base64 for embedding in Streamlit markdown."""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        st.error(f"Logo file not found at {path}. Using placeholder.")
        return ""


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
OCR will extract all items and quantities using fixed column boundaries for accuracy,
normalize units, merge similar items, and generate a clean CSV for you to download.
"""
)

# --------------------------------------------------------
# OCR CALL — Using DOCUMENT_TEXT_DETECTION for layout analysis
# --------------------------------------------------------
def extract_text_and_boxes(uploaded_image):
    """Use Google Vision DOCUMENT_TEXT_DETECTION to get precise word boxes."""
    try:
        info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(dict(info))
        client = vision.ImageAnnotatorClient(credentials=creds)
    except Exception:
        st.error("❌ Could not load Google Vision credentials. Check Streamlit Secrets.")
        st.stop()

    content = uploaded_image.read()
    image = vision.Image(content=content)
    # Using DOCUMENT_TEXT_DETECTION for better table/layout understanding
    response = client.document_text_detection(image=image)
    
    if not response.text_annotations:
        return "", []

    full_text = response.text_annotations[0].description

    # Build list of word boxes with centers (from the pages/blocks/paragraphs/words structure)
    word_boxes = []
    
    # Iterate through pages, blocks, paragraphs, and words to get granular boxes
    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    # Reconstruct the word text from symbols
                    word_text = "".join([symbol.text for symbol in word.symbols])
                    
                    if not word_text.strip():
                        continue
                        
                    vertices = word.bounding_box.vertices
                    xs = [v.x for v in vertices]
                    ys = [v.y for v in vertices]
                    # Calculate center coordinates
                    cx = sum(xs) / len(xs)
                    cy = sum(ys) / len(ys)
                    
                    word_boxes.append(
                        {
                            "text": word_text,
                            "cx": cx,
                            "cy": cy,
                            "box": vertices # Keep full vertices for debugging/future use
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
def cluster_rows(word_boxes, row_threshold=35):
    """
    Group words into rows based on their vertical (cy) position.
    A higher threshold (35) is used to tolerate large handwriting.
    """
    if not word_boxes:
        return []

    # Sort by vertical position
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
            # Update running average Y for stability
            current_y = (current_y * (len(current_row) - 1) + w["cy"]) / len(current_row)
        else:
            rows.append(current_row)
            current_row = [w]
            current_y = w["cy"]

    if current_row:
        rows.append(current_row)

    return rows


# --------------------------------------------------------
# HELPER: PARSE QUANTITY TOKENS (NOW SIMPLIFIED)
# --------------------------------------------------------
def parse_quantity_tokens(qty_tokens):
    """
    Given only the tokens from the Quantity column, find the number/unit.
    """
    if not qty_tokens:
        return None
        
    # Join tokens to handle '8' and 'lbs' being separate, or '10' and '#'
    qty_string = " ".join(qty_tokens)

    # RegEx: Look for a number (int or decimal) followed by an optional unit.
    # Unit variations: #, lb, lbs, pounds
    UNIT_REGEX = r"(\d+\.?\d*)\s*([l\#]b?s?|pounds?)"
    
    m = re.search(UNIT_REGEX, qty_string, re.IGNORECASE)
    
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    
    # Fallback: if no unit, look for a standalone number
    try:
        # Find the first number in the string
        m_num = re.search(r"(\d+\.?\d*)", qty_string)
        if m_num:
            return float(m_num.group(1))
    except (ValueError, TypeError):
        return None
        
    return None


# --------------------------------------------------------
# ITEM NORMALIZATION FUNCTION
# --------------------------------------------------------
def normalize_item(name: str) -> str:
    """Standardizes item names, handles common misspellings/variants."""
    n = name.lower().strip()
    
    # Tofu variants (e.g., 'tofo')
    if "tofu" in n or "tofo" in n:
        return "Fried Tofu"

    # Broccoli variants (e.g., 'raasted', 'broccoli' used alone)
    if "broccoli" in n or "brocoli" in n or "raasted" in n or n == "roasted":
        return "Roasted Broccoli"
    
    # Soy Glazed Carrots variants
    if "soy" in n and "carrot" in n:
        return "Soy Glazed Carrots"
    
    # Teriyaki Chicken variants 
    if "teriyaki" in n or "teriyacki" in n:
        return "Teriyaki Chicken"
    
    # Rice variants (assuming generic 'Rice' means 'White Rice')
    if n == "rice":
        return "White Rice"
        
    return name


# --------------------------------------------------------
# MAIN PARSER — COLUMN BOUNDARY–BASED (NEW CORE LOGIC)
# --------------------------------------------------------
def parse_ocr_text(full_text: str, word_boxes):
    """
    1. Assigns words to columns based on X-coordinate.
    2. Clusters assigned words into rows (Y-coordinate).
    3. Extracts and aggregates item/quantity pairs.
    """

    station = detect_station_name(full_text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""
    
    # --- CRITICAL: Define Column Boundaries using X-coordinates ---
    # These values are estimated from the provided template image (IMG_6318.jpg).
    # If the image format changes, these coordinates may need adjustment.
    # Coordinates are in pixels from the left edge (X=0).
    
    # Everything before this is Time/Station
    X_ITEM_START = 280 
    
    # Everything after this is Quantity
    X_QTY_START = 720 
    
    # 1. ASSIGN WORDS TO COLUMNS
    column_assigned_words = []
    
    for w in word_boxes:
        column = None
        if w['cx'] >= X_ITEM_START and w['cx'] < X_QTY_START:
            column = 'Item'
        elif w['cx'] >= X_QTY_START:
            column = 'Quantity'
        else: 
            # Skip words in the 'Time' column or margins
            continue 
            
        w['column'] = column
        column_assigned_words.append(w)

    # 2. CLUSTER WORDS BY ROW
    # Group words into rows based on Y-coordinate
    rows = cluster_rows(column_assigned_words, row_threshold=35) 
    
    # 3. EXTRACT ITEM AND QUANTITY
    all_rows = []
    debug_rows = []

    for row_idx, row_words in enumerate(rows):
        # Sort words in the row by X-coordinate (left to right) for correct joining
        row_words_sorted = sorted(row_words, key=lambda w: w["cx"])
        
        # Separate tokens based on their assigned column
        item_tokens = [w['text'] for w in row_words_sorted if w['column'] == 'Item']
        qty_tokens = [w['text'] for w in row_words_sorted if w['column'] == 'Quantity']
        
        item_text = " ".join(item_tokens).strip()
        qty_value = parse_quantity_tokens(qty_tokens) 

        # Classify row and record results
        classification = "data"
        item_candidate = ""
        qty_candidate = ""
        
        # Skip header-like rows (re-check now that words are split by column)
        header_keywords = ["item", "quantity", "lbs", "time", "date"]
        row_text = item_text + " " + " ".join(qty_tokens)

        if any(re.search(rf"\b{hk}\b", row_text, re.IGNORECASE) for hk in header_keywords):
            classification = "header/skip"
        elif item_text and qty_value is not None:
            classification = "parsed"
            item_candidate = item_text
            qty_candidate = qty_value
            all_rows.append((header_date, item_text, qty_value))
        else:
            classification = "no_qty/incomplete"

        debug_rows.append(
            {
                "row_index": row_idx,
                "row_text": row_text.strip(),
                "classification": classification,
                "item_candidate": item_candidate,
                "qty_candidate": qty_candidate,
            }
        )

    if not all_rows:
        empty_df = pd.DataFrame(columns=["Station", "Date", "Item", "Total Quantity (lbs)"])
        debug_df = pd.DataFrame(debug_rows)
        return empty_df, station, debug_df

    # 4. NORMALIZATION AND AGGREGATION
    df = pd.DataFrame(all_rows, columns=["Date", "Item", "Quantity"])
    df["Quantity"] = df["Quantity"].astype(float)

    # Item name cleaning and normalization
    df["Item"] = df["Item"].str.replace(r"[^\w\s-]", "", regex=True) # strip punctuation
    df["Item"] = df["Item"].str.replace(r"\s+", " ", regex=True).str.strip() # collapse spaces
    df["Item"] = df["Item"].apply(normalize_item) # Apply manual fixes
    df["Item"] = df["Item"].str.title() # Use Title Case
    
    # Fuzzy Merging Logic (Keep existing logic to group similar items)
    unique_items = list(dict.fromkeys(df["Item"].tolist()))
    canonical_items = {} 
    
    for item in unique_items:
        best_match = None
        best_ratio = 0
        
        for canon in canonical_items.keys():
            # Check character-level similarity
            ratio = difflib.SequenceMatcher(None, item, canon).ratio()
            if ratio > 0.87:
                 best_match = canon
                 break
            
            # Check word-level overlap
            item_tokens = set(item.split())
            canon_tokens = set(canon.split())
            if len(item_tokens & canon_tokens) > 0 and len(item_tokens | canon_tokens) <= 5: 
                best_match = canon
                break 

        if best_match:
            df.loc[df['Item'] == item, 'Canonical Item'] = best_match
        else:
            canonical_items[item] = True
            df.loc[df['Item'] == item, 'Canonical Item'] = item

    # Aggregation
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
# FILE UPLOAD SECTION (UI unchanged)
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

# Initialize variables for the second section's use
df = pd.DataFrame()
detected_station = "Unknown"
upload_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

if uploaded_file is not None:
    upload_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with st.spinner("Reading image... please wait"):
        full_text, word_boxes = extract_text_and_boxes(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", full_text, height=200)

    st.subheader("Parsed & Aggregated Table")
    # Call the new parsing function
    df, detected_station, debug_df = parse_ocr_text(full_text, word_boxes)

    # Show detected station
    if detected_station and detected_station != "Unknown":
        st.info(f"Detected Station: **{detected_station}**")
    else:
        st.warning(
            "Station not clearly detected. Please confirm the station on the original log."
        )

    st.dataframe(df, use_container_width=True)

    # Debug view
    with st.expander("Debug: Column Assignment and Row Parsing"):
        st.write("This debug shows how words were assigned to columns and rows:")
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
# STEP 2 — DOWNLOAD OR EMAIL LATER (UI unchanged)
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

if not df.empty:
    st.success("✅ Aggregated CSV is ready.")
    st.markdown("You can download the file below and email it manually if needed.")
    csv_data = df.to_csv(index=False).encode("utf-8")

    safe_station = (detected_station or "UnknownStation").replace(" ", "_")
    ts = upload_timestamp

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