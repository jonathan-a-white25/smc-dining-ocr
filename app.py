import streamlit as st
import pandas as pd
import json
from google.cloud import vision

# =========================================================
#  Page Setup
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")

st.image("assets/smc_g_logo2.png", width=120)
st.title("SMC Dining OCR – Rebuilt Version")

st.write("Upload a photo of the tracking sheet. The app will extract text, parse quantities, consolidate items, and let you download a clean CSV.")

# =========================================================
#  Google Vision Client Loader
# =========================================================
@st.cache_resource
def load_vision_client():
    try:
        key_data = st.secrets["google_cloud"]["vision_key"]
        client = vision.ImageAnnotatorClient.from_service_account_info(key_data)
        return client
    except Exception as e:
        st.error(f"Failed to load Google Vision credentials: {e}")
        return None


# =========================================================
#  OCR Function
# =========================================================
def extract_text_from_image(image_bytes, client):
    try:
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        if response.error.message:
            st.error(f"OCR Error: {response.error.message}")
            return ""

        # raw detected text
        return response.full_text_annotation.text
    except Exception as e:
        st.error(f"OCR failed: {e}")
        return ""


# =========================================================
#  Parsing Logic – Clean, Deterministic, No Bounding Boxes
# =========================================================
def parse_ocr_text(raw_text):
    """
    Approach:
    1. Split lines.
    2. Normalize text.
    3. Extract item + quantity if line ends with a number.
    4. Consolidate repeated items.
    """

    lines = raw_text.split("\n")
    parsed_items = {}

    for line in lines:
        clean = line.strip().lower()

        if not clean:
            continue

        # Try to split out an ending number (quantity)
        parts = clean.rsplit(" ", 1)

        if len(parts) == 2 and parts[1].replace(".", "", 1).isdigit():
            item = parts[0].strip()
            qty = float(parts[1])

            # Basic synonym handling
            if "broccoli" in item:
                item = "broccoli (all types)"
            if "rice" in item:
                item = "rice"
            if "chicken" in item:
                item = "chicken"

            parsed_items[item] = parsed_items.get(item, 0) + qty

    return parsed_items


# =========================================================
#  Streamlit Interface
# =========================================================
client = load_vision_client()

uploaded_file = st.file_uploader("Upload a photo", type=["png", "jpg", "jpeg"])

if uploaded_file is not None and client is not None:
    st.subheader("Step 1: OCR Extraction")

    image_bytes = uploaded_file.read()
    raw_text = extract_text_from_image(image_bytes, client)

    if raw_text:
        st.text_area("Raw OCR Output", raw_text, height=200)

        st.subheader("Step 2: Parsed Items")
        parsed_dict = parse_ocr_text(raw_text)

        df = pd.DataFrame(
            [{"item": k.title(), "quantity": v} for k, v in parsed_dict.items()]
        )

        st.dataframe(df, use_container_width=True)

        st.subheader("Step 3: Download CSV")

        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="parsed_items.csv",
            mime="text/csv",
        )
