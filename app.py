import streamlit as st
import pandas as pd
import base64
from google.cloud import vision
from datetime import datetime
from zoneinfo import ZoneInfo  # For Pacific Time

# =========================================================
#  Helper: Convert logo to Base64
# =========================================================
def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

logo_base64 = get_base64_image("assets/smc_g_logo2.png")

# =========================================================
#  Page Setup
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")

# =========================================================
#  Banner Styling (with embedded base64 logo)
# =========================================================
RED_BANNER = f"""
<div style="
    background-color: #D7263D;
    padding: 18px;
    border-radius: 8px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
">
    <img src="data:image/png;base64,{logo_base64}" style="height:60px; margin-right:20px;">
    <h1 style="color:white; margin:0; font-size:32px;">SMC Dining OCR</h1>
</div>
"""

BLUE_BANNER_TEMPLATE = """
<div style="
    background-color: #143257;
    padding: 14px;
    border-radius: 8px;
    margin-top: 25px;
    margin-bottom: 12px;
">
    <h2 style="color:white; margin:0; font-size:22px;">{text}</h2>
</div>
"""

RED_BANNER_TEMPLATE = """
<div style="
    background-color: #D7263D;
    padding: 14px;
    border-radius: 8px;
    margin-top: 25px;
    margin-bottom: 12px;
">
    <h2 style="color:white; margin:0; font-size:22px;">{text}</h2>
</div>
"""

# Render header banner
st.markdown(RED_BANNER, unsafe_allow_html=True)

st.write(
    "Upload a photo of the tracking sheet. The app will run OCR, show the raw text, "
    "and display a parsed summary."
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
#  Always Hardcoded Parsed Output
# =========================================================
def get_fixed_output(station_name):
    summary = {
        "Teriyaki Chicken": 55,
        "Rice": 45,
        "Soy Glazed Carrots": 33,
        "Roasted Broccoli": 25,
    }

    df = pd.DataFrame(
        [
            {"station": station_name, "item": item, "quantity": qty}
            for item, qty in summary.items()
        ]
    )
    return df

# =========================================================
#  STREAMLIT UI
# =========================================================
client = load_vision_client()

# -------------------------
#  STEP 1 SECTION
# -------------------------
st.markdown(BLUE_BANNER_TEMPLATE.format(text="Step 1: Upload & OCR Extraction"), unsafe_allow_html=True)

# Station dropdown
station_name = st.selectbox(
    "Select Station",
    ["Stacked", "Simple Servings", "Sizzle", "Slices", "Twists", "Bliss"],
    index=0
)

# Date picker
selected_date = st.date_input("Select Date")

uploaded_file = st.file_uploader("Upload a photo", type=["png", "jpg", "jpeg"])

if uploaded_file is not None and client is not None:

    image_bytes = uploaded_file.read()
    raw_text = extract_text_from_image(image_bytes, client)

    if raw_text:
        st.text_area("Raw OCR Output", raw_text, height=220)

        # STEP 2
        st.markdown(RED_BANNER_TEMPLATE.format(text="Step 2: Parsed Items"), unsafe_allow_html=True)

        st.write(f"Summarized output for **{station_name}** on **{selected_date}**:")

        df = get_fixed_output(station_name)
        st.dataframe(df, use_container_width=True)

        # STEP 3
        st.markdown(BLUE_BANNER_TEMPLATE.format(text="Step 3: Download CSV"), unsafe_allow_html=True)

        # Generate Pacific Time timestamp for filename
        pacific_now = datetime.now(ZoneInfo("America/Los_Angeles"))
        timestamp_str = pacific_now.strftime("%H-%M-%S_%Z")  # e.g. "14-32-05_PST"

        # Build filename
        filename = (
            f"{station_name.replace(' ', '_').lower()}"
            f"_{selected_date}"
            f"_{timestamp_str}.csv"
        )

        csv_data = df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
        )

else:
    st.info("Upload an image above to begin.")
