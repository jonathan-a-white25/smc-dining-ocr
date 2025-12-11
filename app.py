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
# OPTIONAL CSS (Assuming the user has the theme.css file)
# --------------------------------------------------------
css_path = Path("assets/theme.css")
if css_path.exists():
    with open(css_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# --------------------------------------------------------
# LOGO (Assuming the user has the logo file)
# --------------------------------------------------------
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
OCR will extract all items and quantities, normalize units, merge similar items,
and generate a clean CSV for you to download.
"""
)

# --------------------------------------------------------
# OCR CALL — return full text + per-word bounding boxes
# (No changes needed here - this is Google Vision boilerplate)
# --------------------------------------------------------
def extract_text_and_boxes(uploaded_image):
    """Use Google Vision to get full text and bounding boxes for each word."""
    try:
        # NOTE: Assumes 'gcp_service_account' is configured in st.secrets
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
    
    # We will process the annotations structure from DOCUMENT_TEXT_DETECTION
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
                    word_text = "".join([symbol.text for symbol in word.symbols])
                    
                    if not word_text.strip():
                        continue
                        
                    vertices = word.bounding_box.vertices
                    xs = [v.x for v in vertices]
                    ys = [v.y for v in vertices]
                    cx = sum(xs) / len(xs)
                    cy = sum(ys) / len(ys)
                    
                    word_boxes.append(
                        {
                            "text": word_text,
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
# (Uses original logic, which is a sound starting point)
# --------------------------------------------------------
def cluster_rows(word_boxes, row_threshold=25):
    """
    Group words into rows based on their vertical (cy) position.
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

        # Check proximity to the running average Y-coordinate of the row
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
# HELPER: PARSE A SINGLE ROW INTO (ITEM, QUANTITY)
# 
# CRITICAL REVISION: Searches from the right and uses a robust RegEx 
# to capture quantity with flexible units.
# --------------------------------------------------------
def parse_row_tokens(tokens):
    """
    Given a list of tokens for a single row (ordered left → right),
    return (item_text, quantity_value) or (None, None) if no quantity found.
    """

    # RegEx for quantity: (Number with optional decimal) + (optional space/junk) + (Unit)
    # Allows lbs, lb, #, pounds. The \s* handles the space flexibility.
    # The \b ensures the unit is a word boundary.
    UNIT_REGEX = r"(\d+\.?\d*)\s*([l\#]b?s?|pounds?)\b"

    # CRITICAL: Iterate from the right-most token to ensure we capture 
    # the quantity in the Quantity column, not a false positive in the Item column.
    for idx, tok in reversed(list(enumerate(tokens))):
        raw = tok.strip()
        if not raw:
            continue
        
        # 1. Look for a number AND a unit (e.g., '8 lbs', '10#', '4.5 lb')
        m = re.search(UNIT_REGEX, raw, re.IGNORECASE)
        if m:
            try:
                # Group 1 is the number
                qty_value = float(m.group(1))
            except ValueError:
                # Should not happen if RegEx is good, but good practice
                continue 
            
            qty_index = idx
            
            # The item text is everything *before* this token.
            item_tokens = tokens[:qty_index]
            item_text = " ".join(item_tokens).strip()
            
            # If the quantity and unit were detected *within* a token, 
            # we must separate the item part from the qty part within that token.
            if m.start() > 0:
                item_part_of_token = raw[:m.start()].strip()
                item_text = item_text + " " + item_part_of_token
                item_text = item_text.strip() # Clean up leading/trailing spaces

            if item_text:
                return item_text, qty_value
            else:
                # Quantity found, but no item text to the left/in the same token. Ignore.
                return None, None
            
        # 2. If no unit, look for a standalone number (must be the last token in the row 
        # for maximum safety, or rely on its position)
        try:
            qty_value = float(raw)
            
            # If a number is found as a token, it MUST be the last token (or close to it)
            # We assume if we are searching right-to-left, the last number is the quantity.
            
            item_tokens = tokens[:idx]
            item_text = " ".join(item_tokens).strip()
            
            if item_text:
                return item_text, qty_value
            
        except ValueError:
            pass # Not a number, continue to next token
    
    return None, None


# --------------------------------------------------------
# ITEM NORMALIZATION FUNCTION
# Includes manual fixes for common OCR/Handwriting errors
# --------------------------------------------------------
def normalize_item(name: str) -> str:
    """Standardizes item names, handles common misspellings/variants."""
    n = name.lower().strip()
    
    # 1. Manual/Fuzzy Fixes for Common OCR Errors (e.g., f instead of t, 'raasted')
    
    # Tofu variants (e.g., 'tofo')
    if "tofu" in n or "tofo" in n:
        return "Fried Tofu"

    # Broccoli variants (e.g., 'raasted', 'broccoli' used alone)
    if "broccoli" in n or "brocoli" in n or "raasted" in n:
        return "Roasted Broccoli"
    
    # Soy Glazed Carrots variants (e.g., 'soy' or 'carrots')
    if "soy" in n and "carrot" in n:
        return "Soy Glazed Carrots"
    
    # Teriyaki Chicken variants (e.g., 'teriyacki')
    if "teriyaki" in n or "teriyacki" in n or "teriyaki chicken" in n:
        return "Teriyaki Chicken"
    
    # Rice variants (e.g., "Rice" detected alone, assume 'White Rice' if no other type specified)
    if n == "rice":
        return "White Rice"
        
    return name


# --------------------------------------------------------
# MAIN PARSER — BOUNDING BOX–BASED
# --------------------------------------------------------
def parse_ocr_text(full_text: str, word_boxes):
    """
    Parses OCR text: Detects header info, clusters rows, extracts items/quantities, 
    normalizes, fuzzy merges, and aggregates.
    """

    station = detect_station_name(full_text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.IGNORECASE)
    header_date = date_match.group(1) if date_match else ""

    # Cluster words into row groups
    rows = cluster_rows(word_boxes, row_threshold=25)

    all_rows = []
    debug_rows = []

    for row_idx, row_words in enumerate(rows):
        # Sort each row left→right by X-coordinate
        row_words_sorted = sorted(row_words, key=lambda w: w["cx"])
        tokens = [w["text"] for w in row_words_sorted]
        row_text = " ".join(tokens)

        # Skip header-like rows
        header_keywords = ["station", "time", "item", "quantity", "date", "lbs"]
        if any(re.search(rf"\b{hk}\b", row_text, re.IGNORECASE) for hk in header_keywords):
            classification = "header/skip"
            item_candidate = ""
            qty_candidate = ""
        else:
            item, qty = parse_row_tokens(tokens)
            if item is None or qty is None:
                classification = "no_qty"
                item_candidate = ""
                qty_candidate = ""
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

    if not all_rows:
        empty_df = pd.DataFrame(columns=["Station", "Date", "Item", "Total Quantity (lbs)"])
        debug_df = pd.DataFrame(debug_rows)
        return empty_df, station, debug_df

    # Build DataFrame from parsed rows
    df = pd.DataFrame(all_rows, columns=["Date", "Item", "Quantity"])
    df["Quantity"] = df["Quantity"].astype(float)

    # ---- Item name normalization ----

    # 1) Strip punctuation (keeping hyphens/slashes) and collapse spaces
    df["Item"] = df["Item"].str.replace(r"[^\w\s-]", "", regex=True)
    df["Item"] = df["Item"].str.replace(r"\s+", " ", regex=True).str.strip()

    # 2) Apply manual/fuzzy normalization
    df["Item"] = df["Item"].apply(normalize_item)

    # 3) Use Title Case for final presentation
    df["Item"] = df["Item"].str.title()
    
    # ----------------------------------------------------
    # FUZZY + TOKEN MERGING (REVISED)
    # The longest, most descriptive name should become the canonical.
    # ----------------------------------------------------
    unique_items = list(dict.fromkeys(df["Item"].tolist()))
    
    # Sort unique items by length, descending, to prioritize longer names as canonicals
    sorted_unique_items = sorted(unique_items, key=len, reverse=True) 
    
    canonical_items = {} # {canonical_name: [list of variants mapped to it]}
    
    for item in sorted_unique_items:
        best_match = None
        best_ratio = 0
        
        # Check against existing canonicals
        for canon in canonical_items.keys():
            # Use SequenceMatcher for character-level similarity
            ratio = difflib.SequenceMatcher(None, item, canon).ratio()
            
            # Use get_close_matches for a standard fuzzy check
            fuzzy_match = difflib.get_close_matches(item, [canon], n=1, cutoff=0.87)

            if fuzzy_match and ratio > best_ratio:
                 best_ratio = ratio
                 best_match = canon
            
            # Logic for word-level overlap: handles "Rice" matching "White Rice"
            item_tokens = set(item.split())
            canon_tokens = set(canon.split())
            if len(item_tokens & canon_tokens) >= 1 and len(item_tokens | canon_tokens) <= 3: 
                # If they share at least one word and aren't too different in word count
                best_match = canon
                break # A strong token match is often better than character ratio

        if best_match:
            # Map the current item to the existing canonical
            df.loc[df['Item'] == item, 'Canonical Item'] = best_match
        else:
            # This item becomes a new canonical
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
# FILE UPLOAD SECTION
# (Streamlit UI remains the same)
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
        # The Vision API call is now DOCUMENT_TEXT_DETECTION for better accuracy
        full_text, word_boxes = extract_text_and_boxes(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", full_text, height=200)

    st.subheader("Parsed & Aggregated Table")
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

# Use the variables set in the 'if uploaded_file is not None' block
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