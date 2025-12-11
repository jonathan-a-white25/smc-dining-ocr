import streamlit as st
import pandas as pd
from datetime import datetime


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
        <img src="assets/smc_g_logo.png">
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
        {"Item": "Rice", "Total Quantity": 35, "Unit": "lbs"},
        {"Item": "Soy Glazed Carrots", "Total Quantity": 33, "Unit": "lbs"},
        {"Item": "Roasted Broccoli", "Total Quantity": 30, "Unit": "lbs"},
    ])


# =========================================================
#  USER WORKFLOW
# =========================================================

# ---------- STEP 1 ----------
st.markdown("## Step 1 — Upload Your Log")

uploaded_image = st.file_uploader("Upload Image (JPG, PNG)", type=["jpg", "jpeg", "png"])
run_demo = st.button("Process Log")

if run_demo:

    # Totals are hardcoded for the presentation
    totals_df = compute_totals(None)

    # ---------- STEP 2 ----------
    st.markdown("---")
    st.markdown("## Step 2 — Review Totals")
    st.dataframe(totals_df, use_container_width=True)

    # ---------- STEP 3 ----------
    st.markdown("---")
    st.markdown("## Step 3 — Download CSV")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"smc_dining_totals_{timestamp}.csv"

    st.download_button(
        label=f"Download CSV ({filename})",
        data=totals_df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv"
    )

    st.success("Totals generated successfully.")

else:
    st.info("Upload a log image to begin.")
