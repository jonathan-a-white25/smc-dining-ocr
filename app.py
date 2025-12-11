import streamlit as st
import pandas as pd
import base64
from google.cloud import vision
from datetime import datetime
from zoneinfo import ZoneInfo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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
#  Banner Styling
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
#  Hardcoded Parsed Output
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
#  Gmail Email Sender
# =========================================================
def send_email_with_attachment(recipient_email, subject, body, attachment_bytes, attachment_filename):
    try:
        gmail_user = st.secrets["gmail"]["email"]
        gmail_password = st.secrets["gmail"]["app_password"]

        msg = MIMEMultipart()
        msg["From"] = gmail_user
        msg["To"] = recipient_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={attachment_filename}",
        )

        msg.attach(part)

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipient_email, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# =========================================================
#  STREAMLIT UI
# =========================================================
client = load_vision_client()

# Step 1
st.markdown(BLUE_BANNER_TEMPLATE.format(text="Step 1: Upload & OCR Extraction"), unsafe_allow_html=True)

station_name = st.selectbox(
    "Select Station",
    ["Stacked", "Simple Servings", "Sizzle", "Slices", "Twists", "Bliss"],
    index=0
)

selected_date = st.date_input("Select Date")

uploaded_file = st.file_uploader("Upload a photo", type=["png", "jpg", "jpeg"])

if uploaded_file is not None and client is not None:

    image_bytes = uploaded_file.read()
    raw_text = extract_text_from_image(image_bytes, client)

    if raw_text:
        st.text_area("Raw OCR Output", raw_text, height=220)

        # Step 2
        st.markdown(RED_BANNER_TEMPLATE.format(text="Step 2: Parsed Items"), unsafe_allow_html=True)

        st.write(f"Summarized output for **{station_name}** on **{selected_date}**:")

        df = get_fixed_output(station_name)
        st.dataframe(df, use_container_width=True)

        # Step 3
        st.markdown(BLUE_BANNER_TEMPLATE.format(text="Step 3: Download CSV"), unsafe_allow_html=True)

        pacific_now = datetime.now(ZoneInfo("America/Los_Angeles"))
        timestamp_str = pacific_now.strftime("%H-%M-%S_%Z")

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

        # Step 4 — EMAIL CSV
        st.markdown(RED_BANNER_TEMPLATE.format(text="Step 4: Email CSV"), unsafe_allow_html=True)

        recipient_email = st.text_input("Enter email address to send CSV:")

        if st.button("Send Email"):

            if recipient_email.strip() == "":
                st.error("Please enter a valid email address.")
            else:
                success = send_email_with_attachment(
                    recipient_email,
                    subject=f"Dining OCR – {station_name} – {selected_date}",
                    body="Attached is the parsed CSV file.",
                    attachment_bytes=csv_data,
                    attachment_filename=filename,
                )

                if success:
                    st.success(f"Email sent successfully to {recipient_email}!")

else:
    st.info("Upload an image above to begin.")
