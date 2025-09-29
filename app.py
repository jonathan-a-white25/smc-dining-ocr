import os
import yaml
import pandas as pd
import streamlit as st
from datetime import datetime

from ocr_items import extract_items_quantities
from utils import to_csv_bytes, setup_logger, summarize_by_item, sanitize_quantity_range
from emailer import send_email_with_attachment

LOG = setup_logger()

st.set_page_config(
    page_title="SMC Dining • Production OCR → CSV",
    page_icon="🍽️",
    layout="wide"
)

# Inject custom CSS
with open(os.path.join("assets", "theme.css"), "r", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

SMC_NAVY = "#143257"
SMC_RED = "#D82732"

# Defaults (free-text items, no normalization)
DEFAULT_CONF = {
    "confidence_threshold": 80,
    "min_qty": 0,
    "max_qty": 10000,
    "email": {"from": "", "to": "", "subject": "Daily Production CSV", "body": "Attached is today's CSV."},
    "normalize_items": False,
    "normalization_map": {}
}
if os.path.exists("config.yml"):
    with open("config.yml", "r") as f:
        loaded = yaml.safe_load(f) or {}
        for k, v in loaded.items():
            DEFAULT_CONF[k] = v

# Header with logo
logo_path = os.path.join("assets", "smc_g_logo.png")
col1, col2 = st.columns([1, 6], vertical_alignment="center")
with col1:
    if os.path.exists(logo_path):
        st.image(logo_path, width=72)
with col2:
    st.markdown(
        f"""
        <div class="smc-header">
          <div class="smc-title">Saint Mary's College • Dining Production OCR</div>
          <div class="smc-sub">Brand: Lasallian Navy ({SMC_NAVY}) &amp; SMC Red ({SMC_RED})</div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.caption(
    "Upload photos of production logs. The app extracts **Item** (free text) and **Quantity** (digits). "
    "Low-confidence quantities become **NULL**. Review, edit, export, and email a CSV."
)

# Sidebar controls
with st.sidebar:
    st.header("Settings")
    conf_cutoff = st.slider("Confidence threshold (quantity)", 0, 100, int(DEFAULT_CONF["confidence_threshold"]), 5,
                            help="Quantities with OCR confidence below this threshold become NULL.")
    min_qty = st.number_input("Min quantity", value=int(DEFAULT_CONF["min_qty"]))
    max_qty = st.number_input("Max quantity", value=int(DEFAULT_CONF["max_qty"]))
    st.caption("Quantities outside this range become NULL.")
    st.divider()

    st.header("Email")
    sender_email = st.text_input("Sender email", value=DEFAULT_CONF["email"]["from"])
    recipient_email = st.text_input("Recipient email", value=DEFAULT_CONF["email"]["to"])
    subject = st.text_input("Subject", value=DEFAULT_CONF["email"]["subject"])
    body = st.text_area("Body", value=DEFAULT_CONF["email"]["body"], height=100)
    st.caption("Configure credentials via secrets/env vars (.env, Streamlit Secrets, or platform env).")

# Upload
uploaded = st.file_uploader(
    "Upload one or more photos (JPG/PNG). On mobile, you can take photos directly.",
    type=["jpg","jpeg","png"], accept_multiple_files=True
)

all_rows = []
if uploaded:
    for f in uploaded:
        st.subheader(f"Image: {f.name}")
        st.image(f, use_column_width=True)

        try:
            df = extract_items_quantities(
                f,
                conf_threshold=conf_cutoff,
                normalize=False,                # keep item text as-is
                normalization_map={}
            )
        except Exception as e:
            st.error(f"OCR failed for {f.name}: {e}")
            LOG.exception("OCR failure")
            continue

        # range sanitize quantities
        df["quantity"] = df["quantity"].apply(lambda q: sanitize_quantity_range(q, min_qty, max_qty))

        st.caption("Review & edit. Leave blank if quantity should be NULL.")
        df_edit = st.data_editor(df, use_container_width=True, num_rows="dynamic")
        all_rows.append(df_edit)
        st.divider()

    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=["item","quantity"])

    st.subheader("All Entries (Combined)")
    st.dataframe(combined, use_container_width=True)

    st.subheader("Aggregate Summary (Totals by Item)")
    summary = summarize_by_item(combined)
    st.dataframe(summary, use_container_width=True)

    csv_bytes = to_csv_bytes(combined)
    default_name = f"smc_dining_production_{datetime.now().strftime('%Y-%m-%d')}.csv"
    st.download_button("⬇️ Download CSV", data=csv_bytes, file_name=default_name, mime="text/csv")

    if st.button("📧 Email CSV"):
        try:
            ok, msg = send_email_with_attachment(
                sender=sender_email,
                recipient=recipient_email,
                subject=subject,
                body_text=body,
                attachment_bytes=csv_bytes,
                attachment_name=default_name
            )
            st.success("Email sent ✅" if ok else f"Email failed: {msg}")
        except Exception as e:
            LOG.exception("Email send error")
            st.error(f"Email error: {e}")
else:
    st.info("Upload at least one photo to begin.")
