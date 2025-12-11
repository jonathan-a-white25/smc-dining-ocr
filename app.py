import streamlit as st
import pandas as pd
from datetime import datetime
from emailer import send_email_with_attachment


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
st.title("SMC Dining OCR – Presentation Build")


# =========================================================
#  Station Names
# =========================================================
STATIONS = [
    "Sizzle",
    "Stacked",
    "Simple Servings",
    "Slices",
    "Twists",
    "Bliss"
]


# =========================================================
#  Simulated Hard-Coded Totals For Tomorrow's Demo
# =========================================================
def get_demo_totals():
    rows = [
        ["Teriyaki Chicken", 55, "lbs"],
        ["Rice", 35, "lbs"],
        ["Soy Glazed Carrots", 33, "lbs"],
        ["Roasted Broccoli", 30, "lbs"]
    ]
    df = pd.DataFrame(rows, columns=["Item", "Total Quantity", "Unit"])
    return df


# =========================================================
#  Main UI – Step 1
# =========================================================
st.markdown("## Step 1 — Upload Your Tracking Log")

station_name = st.selectbox("Select Meal Station:", STATIONS, index=0)

uploaded_image = st.file_uploader(
    "Upload image (JPG, JPEG, PNG)",
    type=["png", "jpg", "jpeg"]
)

run_demo = st.button("Process Log")


# =========================================================
#  Run Demo
# =========================================================
if run_demo:

    if uploaded_image is None:
        st.warning("Proceeding with the demo sheet totals for tomorrow's presentation.")

    st.markdown("## Step 2 — Review Parsed & Grouped Totals")

    totals_df = get_demo_totals()
    st.dataframe(totals_df, use_container_width=True)

    # Create CSV
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
    #  Step 3 — Email CSV (FORM FIX APPLIED HERE)
    # =========================================================
    st.markdown("## Step 3 — Email CSV File")

    st.info("Use your verified SendGrid sender email: jaw41@stmarys-ca.edu")

    with st.form("email_form"):
        sender = st.text_input("Sender Email", value="jaw41@stmarys-ca.edu")
        recipient = st.text_input("Recipient Email")
        submit_email = st.form_submit_button("Send CSV via Email")

    if submit_email:
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
