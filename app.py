import streamlit as st
import pandas as pd
from datetime import datetime
from emailer import send_email_with_attachment
import os


# =========================================================
#  CSS Loader
# =========================================================
def load_local_css(path: str):
    try:
        with open(path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except:
        st.warning(f"CSS file not found at: {path}")


# =========================================================
#  Page Setup
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")
load_local_css("assets/theme.css")

st.image("assets/smc_g_logo2.png", width=120)
st.title("SMC Dining OCR")


# =========================================================
#  Stations
# =========================================================
STATIONS = ["Sizzle", "Stacked", "Simple Servings", "Slices", "Twists", "Bliss"]


# =========================================================
#  Hard-coded demo totals
# =========================================================
def get_demo_totals():
    rows = [
        ["Teriyaki Chicken", 55, "lbs"],
        ["Rice", 35, "lbs"],
        ["Soy Glazed Carrots", 33, "lbs"],
        ["Roasted Broccoli", 30, "lbs"]
    ]
    return pd.DataFrame(rows, columns=["Item", "Total Quantity", "Unit"])


# =========================================================
#  STEP 1 — Upload Form (STABLE)
# =========================================================
st.markdown("## Step 1 — Upload Your Tracking Log")

with st.form("upload_form"):
    station_name = st.selectbox("Select Meal Station:", STATIONS, index=0)

    uploaded_image = st.file_uploader(
        "Upload image (JPG, JPEG, PNG)",
        type=["png", "jpg", "jpeg"]
    )

    run_demo = st.form_submit_button("Process Log")

# =========================================================
#  If user submits upload form
# =========================================================
if run_demo:

    if uploaded_image is None:
        st.warning("No image uploaded — using demo sheet totals for tomorrow's presentation.")

    st.markdown("## Step 2 — Review Parsed & Grouped Totals")
    totals_df = get_demo_totals()
    st.dataframe(totals_df, use_container_width=True)

    # CSV creation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{station_name.lower()}_{timestamp}.csv"
    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label=f"Download CSV ({filename})",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )

    # =========================================================
    #  STEP 3 — Email CSV (ALREADY FIXED WITH FORM)
    # =========================================================
    st.markdown("## Step 3 — Email CSV File")
    st.info("Use your verified SendGrid sender email: jaw41@stmarys-ca.edu")

    # DEBUG — Check if SendGrid key loads
    key = os.getenv("SENDGRID_API_KEY")
    st.caption(f"SENDGRID key loaded: {bool(key)} (length={len(key) if key else 0})")

    with st.form("email_form"):
        sender = st.text_input("Sender Email", value="jaw41@stmarys-ca.edu")
        recipient = st.text_input("Recipient Email")
        send_email_button = st.form_submit_button("Send CSV via Email")

    if send_email_button:
        if not sender or not recipient:
            st.error("Both sender and recipient emails are required.")
        else:
            ok, msg = send_email_with_attachment(
                sender=sender,
                recipient=recipient,
                subject=f"{station_name} Station – Meal Log CSV",
                body_text=f"Attached is the meal log export for the {station_name} station.",
                attachment_bytes=csv_bytes,
                attachment_name=filename
            )

            if ok:
                st.success(f"Email sent successfully for {station_name} station!")
            else:
                st.error(f"Email failed: {msg}")

else:
    st.info("Upload a sheet and click **Process Log** to begin.")
