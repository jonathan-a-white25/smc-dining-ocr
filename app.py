import streamlit as st
import pandas as pd
from datetime import datetime
from emailer import send_email_with_attachment
import os


# =========================================================
# CSS Loader
# =========================================================
def load_local_css(path: str):
    try:
        with open(path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        st.warning(f"CSS file not found: {path}")


# =========================================================
# Page Setup
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")
load_local_css("assets/theme.css")

st.image("assets/smc_g_logo2.png", width=120)
st.title("SMC Dining OCR")


# =========================================================
# Hard-coded totals for demo
# =========================================================
def get_demo_totals():
    rows = [
        ["Teriyaki Chicken", 55, "lbs"],
        ["Rice", 35, "lbs"],
        ["Soy Glazed Carrots", 33, "lbs"],
        ["Roasted Broccoli", 30, "lbs"],
    ]
    return pd.DataFrame(rows, columns=["Item", "Total Quantity", "Unit"])


STATIONS = [
    "Sizzle",
    "Stacked",
    "Simple Servings",
    "Slices",
    "Twists",
    "Bliss",
]


# =========================================================
# Initialize session state
# =========================================================
if "demo_started" not in st.session_state:
    st.session_state.demo_started = False
if "station_name" not in st.session_state:
    st.session_state.station_name = None
if "uploaded_image" not in st.session_state:
    st.session_state.uploaded_image = None
if "csv_bytes" not in st.session_state:
    st.session_state.csv_bytes = None
if "filename" not in st.session_state:
    st.session_state.filename = None


# =========================================================
# STEP 1 — Upload Form (stable, no rerun issues)
# =========================================================
st.markdown("## Step 1 — Upload Your Tracking Log")

with st.form("upload_form"):
    station_name = st.selectbox("Select Meal Station:", STATIONS)
    uploaded_image = st.file_uploader(
        "Upload image (JPG, JPEG, PNG)", type=["png", "jpg", "jpeg"]
    )
    submit_upload = st.form_submit_button("Process Log")

if submit_upload:
    st.session_state.demo_started = True
    st.session_state.station_name = station_name
    st.session_state.uploaded_image = uploaded_image

    # Hard-coded totals for demo
    totals_df = get_demo_totals()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{station_name.lower()}_{timestamp}.csv"
    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    st.session_state.csv_bytes = csv_bytes
    st.session_state.filename = filename


# =========================================================
# STEP 2 — Show Totals
# =========================================================
if st.session_state.demo_started:

    st.markdown("## Step 2 — Review Parsed & Grouped Totals")

    totals_df = get_demo_totals()
    st.dataframe(totals_df, use_container_width=True)

    # Download button uses stored CSV
    st.download_button(
        label=f"Download CSV ({st.session_state.filename})",
        data=st.session_state.csv_bytes,
        file_name=st.session_state.filename,
        mime="text/csv",
    )

    # =========================================================
    # STEP 3 — Email CSV (fully stable, no rerun wipe)
    # =========================================================
    st.markdown("## Step 3 — Email CSV File")
    st.info("Use your verified SendGrid sender email: jaw41@stmarys-ca.edu")

    # DEBUG — show if SENDGRID key is loaded
    sg_key = os.getenv("SENDGRID_API_KEY")
    st.caption(
        f"SENDGRID key loaded: {bool(sg_key)} "
        f"(length={len(sg_key) if sg_key else 0})"
    )

    with st.form("email_form"):
        sender = st.text_input("Sender Email", value="jaw41@stmarys-ca.edu")
        recipient = st.text_input("Recipient Email")
        send_btn = st.form_submit_button("Send CSV via Email")

    if send_btn:
        if not sender or not recipient:
            st.error("Both sender and recipient emails are required.")
        else:
            ok, msg = send_email_with_attachment(
                sender=sender,
                recipient=recipient,
                subject=f"{st.session_state.station_name} Station – Meal Log CSV",
                body_text=f"Attached is the meal log export for the "
                          f"{st.session_state.station_name} station.",
                attachment_bytes=st.session_state.csv_bytes,
                attachment_name=st.session_state.filename,
            )

            if ok:
                st.success("Email sent successfully!")
            else:
                st.error(f"Email failed: {msg}")

else:
    st.info("Upload a sheet and click **Process Log** to begin.")
