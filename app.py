import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
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
st.title("SMC Dining OCR")


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
#  Simulated Hard-Coded Totals (Presentation Demo)
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
#  STEP 1 — Upload Section
# =========================================================
st.markdown("## Step 1 — Upload Your Tracking Log")

station_name = st.selectbox("Select Meal Station:", STATIONS, index=0)

uploaded_image = st.file_uploader(
    "Upload image (JPG, JPEG, PNG)",
    type=["png", "jpg", "jpeg"]
)

run_demo = st.button("Process Log")


# =========================================================
#  PROCESS
# =========================================================
if run_demo:

    if uploaded_image is None:
        st.warning("Proceeding with demo totals for presentation.")

    st.markdown("## Step 2 — Review Grouped Totals")

    totals_df = get_demo_totals()
    st.dataframe(totals_df, use_container_width=True)

    # =====================================================
    #  Generate filename using Pacific Time (Option B)
    # =====================================================
    pt_now = datetime.now(ZoneInfo("America/Los_Angeles"))

    date_str = pt_now.strftime("%Y-%m-%d")
    time_str = pt_now.strftime("%H-%M-%S")

    # Replace spaces with hyphens for cleaner filenames
    station_clean = station_name.replace(" ", "-")

    filename = f"{station_clean}_{date_str}_{time_str}.csv"
    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    # =====================================================
    #  CSV Download Button
    # =====================================================
    st.download_button(
        label=f"Download CSV ({filename})",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )


# =====================================================
#  STEP 3 — Email Form
# =====================================================
banner("Step 3 — Email the CSV File", "#1E7F3B")  # green

st.info("Use your verified SendGrid sender email: jon.whitea@gmail.com")

api_key_exists = bool(st.secrets.get("SENDGRID_API_KEY"))
st.caption(f"SENDGRID key loaded: {api_key_exists}")

with st.form("email_form"):
    sender = st.text_input("Sender Email", value="jon.whitea@gmail.com")
    recipient = st.text_input("Recipient Email")
    notes = st.text_area("Optional Notes", value="Thank you! Please review today's log.")

    submit_email = st.form_submit_button("Send CSV via Email")

    if submit_email:
        if not sender or not recipient:
            st.error("Both sender and recipient are required.")

        else:
            st.write("Attempting to send email...")  # DEBUG

            subject = f"{station_name} Log – {date_str} ({time_str} PT)"

            body = (
                f"Hello,\n\n"
                f"Attached is the meal log for the {station_name} station.\n"
                f"- Date: {date_str}\n"
                f"- Time: {time_str} PT\n\n"
                f"{notes}\n\n"
                f"Sent automatically by the SMC Dining OCR system."
            )

            ok, msg = send_email_with_attachment(
                sender=sender,
                recipient=recipient,
                subject=subject,
                body_text=body,
                attachment_bytes=csv_bytes,
                attachment_name=filename
            )

            st.write("Email send function response:", msg)

            if ok:
                st.success(f"Email sent successfully to {recipient}!")
            else:
                st.error(f"EMAIL FAILED: {msg}")

else:
    st.info("Upload a sheet and click **Process Log** to begin.")
