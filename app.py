import streamlit as st
import pandas as pd
import re
from google.cloud import vision

# =========================================================
#  Page Setup
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")

st.image("assets/smc_g_logo2.png", width=120)
st.title("SMC Dining OCR – Prototype")

st.write(
    "Upload a photo of the tracking sheet. The app will run OCR, show the raw text, "
    "and display a parsed summary (prototype output)."
)

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

        return response.full_text_annotation.text
    except Exception as e:
        st.error(f"OCR failed: {e}")
        return ""


# =========================================================
#  ALWAYS-SHOWN HARDCODED SUMMARY
# =========================================================
def get_fixed_output():
    """
    These are the totals from the Sizzle station sheet for 12/10/2025.
    This output is always shown in Step 2 to demonstrate the prototype's intent.
    """

    summary = {
        "Teriyaki Chicken": 55,
        "Rice": 45,
        "Soy Glazed Carrots": 33,
        "Roasted Broccoli": 25,
    }

    df = pd.DataFrame(
        [{"item": item, "quantity": qty} for item, qty in summary.items()]
    )

    return df


# =========================================================
#  STREAMLIT UI
# =========================================================
client = load_vision_client()
uploaded_file = st.file_uploader("Upload a photo", type=["png", "jpg", "jpeg"])

if uploaded_file is not None and client is not None:

    st.subheader("Step 1: OCR Extraction")

    image_bytes = uploaded_file.read()
    raw_text = extract_text_from_image(image_bytes, client)

    if raw_text:
        st.text_area("Raw OCR Output", raw_text, height=200)

        st.subheader("Step 2: Parsed Items (Prototype Output)")
        st.write("Below is the summarized output the system is designed to produce:")

        df = get_fixed_output()
        st.dataframe(df, use_container_width=True)

        st.subheader("Step 3: Download CSV")

        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="parsed_items.csv",
            mime="text/csv",
        )
