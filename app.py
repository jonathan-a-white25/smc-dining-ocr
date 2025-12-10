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
    "Stacked", "Simple Servings", "Sizzle", "Slices", "Twists", "Bliss"
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
def load_logo_base64(path):
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
        <img src="data:image/png;base64,{logo_data}" width="80">
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

st.write(
    """
Upload a photo of your handwritten prep log.  
OCR will extract all items, quantities, normalize units, merge similar items,
and generate a clean CSV.
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
        st.error("Could not load Google Vision credentials.")
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
    for name in STATION_NAMES:
        if re.search(rf"\b{name}\b", text, re.IGNORECASE):
            return name
    return "Unknown"


# --------------------------------------------------------
# MAIN PARSER
# --------------------------------------------------------
def parse_ocr_text(text: str):
    """
    Full OCR parsing with:
    - OCR fragment merging
    - Item/quantity extraction using FIFO queue
    - Synonym normalization
    - Fuzzy + token aggregation
    - Debug info
    """

    # ---- Station + Date ----
    station = detect_station_name(text)
    date_match = re.search(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", text)
    header_date = date_match.group(1) if date_match else ""

    # ---- Normalize units but do NOT modify raw numbers ----
    cleaned = text
    cleaned = re.sub(r"1[bB][sS]\.?", "lbs", cleaned)
    cleaned = re.sub(r"l[bB][sS]\.?", "lbs", cleaned)
    cleaned = re.sub(r"(\d+)\s*#", r"\1 lbs", cleaned)
    cleaned = re.sub(r"(\d+)\s*(?:pounds?|pound|lbs?|lb)\b\.?",
                     r"\1 lbs", cleaned, flags=re.IGNORECASE)

    raw_lines = [ln.rstrip("\n") for ln in text.splitlines()]
    cleaned_lines = [ln.rstrip("\n") for ln in cleaned.splitlines()]

    # ----------------------------------------------------
    # FIX: MERGE BROKEN OCR FRAGMENTS (Roasted + Broccoli)
    # ----------------------------------------------------
    merged = []
    skip = False

    for i in range(len(cleaned_lines)):
        if skip:
            skip = False
            continue

        curr = cleaned_lines[i].strip()

        if i < len(cleaned_lines) - 1:
            nxt = cleaned_lines[i+1].strip()

            # If both lines contain letters, no digits → merge them
            if (
                re.search(r"[A-Za-z]", curr) and not re.search(r"\d", curr) and
                re.search(r"[A-Za-z]", nxt) and not re.search(r"\d", nxt)
            ):
                merged.append(curr + " " + nxt)
                skip = True
                continue

        merged.append(curr)

    cleaned_lines = merged

    # ----------------------------------------------------
    # PATTERNS
    # ----------------------------------------------------
    inline_re = re.compile(
        r"^([A-Za-z][A-Za-z\s\./,&-]+?)\s+(\d+(?:\.\d+)?)\s*lbs\b"
    )
    qty_re = re.compile(r"^(\d+(?:\.\d+)?)\s*lbs\b")
    header_re = re.compile(r"^(Station|Time|Item|Date|Quantity)\b", re.IGNORECASE)

    rows = []
    debug_rows = []

    pending_items = []
    last_item = None

    # ----------------------------------------------------
    # CLASSIFICATION LOOP
    # ----------------------------------------------------
    for idx, line in enumerate(cleaned_lines):
        cl = line.strip()
        cl = re.sub(r"\s+", " ", cl)

        classification = "ignored"
        item_candidate = ""
        qty_candidate = ""
        last_after = last_item

        # ---- headers ----
        if header_re.match(cl):
            classification = "header"

        else:
            # ---- Case 1: inline "item 10 lbs" ----
            m_inline = inline_re.match(cl)
            if m_inline:
                classification = "inline"
                item = m_inline.group(1).strip()
                qty = float(m_inline.group(2))
                rows.append((header_date, item, qty))
                last_item = item
                last_after = item

            else:
                # ---- Case 2: quantity-only ----
                m_qty = qty_re.match(cl)
                if m_qty:
                    classification = "qty_only"
                    qty = float(m_qty.group(1))

                    if pending_items:
                        item = pending_items.pop(0)
                    else:
                        item = last_item

                    if item is not None:
                        rows.append((header_date, item, qty))
                        last_item = item
                        last_after = item

                else:
                    # ---- Case 3: item-only ----
                    if re.search(r"[A-Za-z]", cl) and not re.search(r"\d", cl):
                        classification = "item_only"
                        item = cl
                        pending_items.append(item)
                        last_item = item
                        last_after = item

        debug_rows.append({
            "idx": idx,
            "cleaned_line": cl,
            "classification": classification,
            "pending_items_after_line": list(pending_items),
            "last_item_after_line": last_after,
        })

    # ----------------------------------------------------
    # NO VALID ROWS?
    # ----------------------------------------------------
    if not rows:
        return (
            pd.DataFrame(columns=["Station","Date","Item","Total Quantity (lbs)"]),
            station,
            pd.DataFrame(debug_rows)
        )

    # ----------------------------------------------------
    # BUILD WORKING DF
    # ----------------------------------------------------
    df = pd.DataFrame(rows, columns=["Date","Item","Quantity"])

    df["Item"] = (
        df["Item"]
        .str.replace(r"\d+\s*lbs", "", regex=True)
        .str.replace("lbs", "", regex=True)
        .str.strip()
        .str.title()
    )

    df["Quantity"] = df["Quantity"].astype(float)

    # ----------------------------------------------------
    # SYNONYM NORMALIZATION (fix "Roasted" issues)
    # ----------------------------------------------------
    def normalize_item(name):
        n = name.lower().strip()
        if n in {"raasted broccoli", "roasted broccoli", "broccoli", "roasted"}:
            return "Roasted Broccoli"
        return name

    df["Item"] = df["Item"].apply(normalize_item)

    # ----------------------------------------------------
    # FUZZY + TOKEN MERGING
    # ----------------------------------------------------
    unique_items = list(dict.fromkeys(df["Item"].tolist()))
    canonicals = []
    mapping = {}
    cutoff = 0.87

    for item in unique_items:
        if not canonicals:
            canonicals.append(item)
            mapping[item] = item
            continue

        # strong fuzzy match
        match = difflib.get_close_matches(item, canonicals, n=1, cutoff=cutoff)
        if match:
            mapping[item] = match[0]
            continue

        # token overlap match
        tokens = set(item.split())
        best = None
        best_overlap = 0

        for c in canonicals:
            overlap = len(tokens & set(c.split()))
            if overlap > best_overlap:
                best_overlap = overlap
                best = c

        if best and best_overlap > 0:
            mapping[item] = best
        else:
            canonicals.append(item)
            mapping[item] = item

    df["Canonical Item"] = df["Item"].map(mapping)

    aggregated = (
        df.groupby(["Date","Canonical Item"], as_index=False)["Quantity"]
        .sum()
        .rename(columns={"Canonical Item": "Item", "Quantity": "Total Quantity (lbs)"})
    )

    aggregated["Station"] = station
    cols = ["Station","Date","Item","Total Quantity (lbs)"]
    aggregated = aggregated[cols]

    return aggregated, station, pd.DataFrame(debug_rows)


# --------------------------------------------------------
# UPLOAD UI
# --------------------------------------------------------
st.markdown(
    f"""
<div style='background-color:{SMC_RED};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 1 — Upload Your Log</h3>
</div>
""",
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader("Upload image (JPG, JPEG, PNG)", type=["jpg","jpeg","png"])

if uploaded_file:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with st.spinner("Reading image..."):
        extracted = extract_text_from_image(uploaded_file)

    st.subheader("OCR Text Preview")
    st.text_area("Detected Text", extracted, height=200)

    st.subheader("Parsed & Aggregated Table")
    df, station, debug_df = parse_ocr_text(extracted)

    st.info(f"Detected Station: {station}")

    st.dataframe(df, use_container_width=True)

    with st.expander("Debug: OCR line parsing (temporary)"):
        st.dataframe(debug_df, use_container_width=True)

    if not df.empty:
        filename = f"{station}_{timestamp}_dining_log.csv".replace(" ", "_")
        st.download_button(
            "⬇️ Download Aggregated CSV",
            df.to_csv(index=False).encode("utf-8"),
            filename,
            "text/csv",
            use_container_width=True,
        )

else:
    st.info("Please upload an image to begin.")

# --------------------------------------------------------
# STEP 2 — DOWNLOAD LATER
# --------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
<div style='background-color:{SMC_NAVY};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Step 2 — Download Or Email Later</h3>
</div>
""",
    unsafe_allow_html=True,
)

if "df" in locals() and not df.empty:
    st.success("CSV ready.")
    st.download_button(
        label="⬇️ Download Aggregated CSV File",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="dining_log.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("No CSV available — upload and process an image first.")

st.caption("Saint Mary's College Dining Data Project · Developed by Group 1")
