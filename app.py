import streamlit as st
import pandas as pd
from datetime import datetime

# Import your email module
from emailer import send_email_with_attachment


# =========================================================
#  CSS Loader
# =========================================================
def load_local_css(path: str):
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# =========================================================
#  APP CONFIG
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="wide")
load_local_css("assets/theme.css")


# =========================================================
#  TOP FULL-WIDTH RED BANNER WITH LOCAL LOGO
# =========================================================
st.markdown(
    """
    <style>
        .full-width-banner {
            width: 100% !important;
            margin: 0 !important;
            padding: 1.25rem 1rem;
            background-color: #D82732;
            display:flex;
            align-items:center;
            gap:1rem;
        }
        .full-width-banner img {
            height: 45px;
        }
        .full-width-banner-title {
            color: white;
            font-size: 1.5rem;
            font-weight: 700;
        }
        .stApp {
            padding-top: 0 !important;
        }
    </style>

    <div class="full-width-banner">
        <img src="assets/smc_g_logo2.png">
        <div class="full-width-banner-title">SMC Dining OCR</div>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
#  HARD-CODED TOTALS FOR PRESENTATION
# =========================================================
def compute_totals(_df_ignored):
    return pd.DataFrame([
        {"Item": "Teriyaki Chicken", "Total Quantity": 55, "Unit": "lbs"},
        {"Item": "Rice",            "Total Quantity": 35, "Unit": "lbs"},
        {"Item": "Soy Glazed Carrots", "Total Quantity": 33, "Unit": "lbs"},
        {"Item": "Roasted Broccoli", "Total Quantity": 30, "Unit": "lbs"},
    ])


# =========================================================
#  USER WORKFLOW
# =========================================================

# ---------- STEP 1 ----------
st.markdown("## Step 1 — Upload Your Log")

# Station Selector
station = st.selectbox(
    "Select Meal Station",
    ["Stacked", "Simple Servings", "Sizzle", "Slices", "Twists", "Bliss"],
    index=2  # default to Sizzle for your demo
)

uploaded_image = st.file_uploader("Upload Image (JPG, PNG)", type=["jpg", "jpeg", "png"])
run_demo = st.button("Process Log")


if run_demo:

    # Totals are preset for the presentation
    totals_df = compute_totals(None)

    # ---------- STEP 2 ----------
    st.markdown("---")
    st.markdown(f"## Step 2 — Review Totals ({station} Station)")
    st.dataframe(totals_df, use_container_width=True)

    # ---------- STEP 3 ----------
    st.markdown("---")
    st.markdown("## Step 3 — Export or Email CSV")

    # Create timestamped filename with station name
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    station_clean = station.replace(" ", "_").lower()  # e.g., "Simple Servings" → "simple_servings"
    filename = f"{station_clean}_{timestamp}.csv"

    # Convert to CSV bytes (for download + email)
    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    # DOWNLOAD BUTTON (optional)
    st.download_button(
        label=f"Download CSV ({filename})",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv"
    )

    # EMAIL SECTION
    st.markdown("### Email CSV File")

    sender_email = st.text_input("Sender Email", value="gaeldining@stmarys.edu")
    recipient_email = st.text_input("Recipient Email")
    email_subject = f"{station} Station – Gael Dining Log Summary"
    email_body = f"Attached is the food log summary for the {station} station."

    send_email_button = st.button("Send CSV via Email")

    if send_email_button:
        if not recipient_email:
            st.error("Please enter a recipient email address.")
        else:
            success, message = send_email_with_attachment(
                sender=sender_email,
                recipient=recipient_email,
                subject=email_subject,
                body_text=email_body,
                attachment_bytes=csv_bytes,
                attachment_name=filename
            )

            if success:
                st.success(f"Email sent successfully for {station} station!")
            else:
                st.error(f"Email failed: {message}")

else:
    st.info("Upload a log image to begin.")
