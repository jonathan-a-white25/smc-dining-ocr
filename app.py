# --------------------------------------------------------
# SMC Dining OCR — DEMO VERSION (No OCR, Hardcoded Data)
# Author: Jonathan White
# Date: December 2025
# --------------------------------------------------------

import streamlit as st
import pandas as pd
import smtplib
import ssl
from email.message import EmailMessage

# --------------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------------
st.set_page_config(page_title="SMC Dining OCR", layout="wide")

SMC_NAVY = "#002855"
SMC_RED = "#C8102E"

# Logo path
logo_path = "assets/smc_g_logo.png"

# --------------------------------------------------------
# TOP BANNER
# --------------------------------------------------------
st.markdown(
    f"""
    <div style="background-color:{SMC_NAVY};padding:15px 25px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h1 style="color:white;margin-bottom:4px;">📋 SMC Dining OCR (Demo)</h1>
            <p style="color:white;margin-top:0;font-size:16px;">Built by Jonathan White · Demo Version (Hardcoded Data)</p>
        </div>
        <img src="{logo_path}" width="80" style="border-radius:6px;margin-left:10px;">
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

st.write("""
This demo displays **pre-loaded food production data** and sends a CSV summary by email.
No OCR is used.  
""")

# --------------------------------------------------------
# HARDCODED DATA FOR DEMO
# --------------------------------------------------------
def get_demo_df():
    data = [
        {"Item": "Teriyaki Chicken", "Total Quantity (lbs)": 55},
        {"Item": "Rice", "Total Quantity (lbs)": 35},
        {"Item": "Soy Glazed Carrots", "Total Quantity (lbs)": 33},
        {"Item": "Roasted Broccoli", "Total Quantity (lbs)": 30},
    ]
    return pd.DataFrame(data)

df = get_demo_df()

# --------------------------------------------------------
# DISPLAY DEMO DATA
# --------------------------------------------------------
st.markdown(f"""
<div style='background-color:{SMC_RED};padding:10px;border-radius:6px;'>
<h3 style='color:white;text-align:center;margin:0;'>Demo Data Preview</h3>
</div>
""", unsafe_allow_html=True)

st.dataframe(df, use_container_width=True)

csv_bytes = df.to_csv(index=False).encode("utf-8")

# --------------------------------------------------------
# EMAIL SENDING FUNCTION
# --------------------------------------------------------
def send_email_with_attachment(recipient, note_text, csv_bytes):
    sender = st.secrets["gmail"]["email"]
    app_pw = st.secrets["gmail"]["app_password"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "SMC Dining OCR Demo Report"

    body = note_text if note_text else "Attached is the SMC Dining OCR demo report."
    msg.set_content(body)

    msg.add_attachment(
        csv_bytes,
        maintype="text",
        subtype="csv",
        filename="smc_dining_demo_report.csv"
    )

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender, app_pw)
        server.send_message(msg)

# --------------------------------------------------------
# EMAIL UI
# --------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div style='background-color:{SMC_NAVY};padding:10px;border-radius:6px;'>
        <h3 style='color:white;text-align:center;margin:0;'>Send Demo CSV</h3>
    </div>
    """,
    unsafe_allow_html=True
)

recipient_email = st.text_input("Recipient Email:", value="jon.whitea@gmail.com")
note_text = st.text_area("Optional Note:", placeholder="Example: Lunch prep totals for today.")

if st.button("📤 Send CSV Now", use_container_width=True):
    try:
        send_email_with_attachment(recipient_email, note_text, csv_bytes)
        st.success(f"Email sent to {recipient_email} successfully!")
    except Exception as e:
        st.error(f"Email failed: {e}")

# FOOTER
st.markdown("<br><hr>", unsafe_allow_html=True)
st.caption("Saint Mary’s College Dining Data Project · Team 1")
