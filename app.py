import streamlit as st
import pandas as pd
from datetime import datetime


# =========================================================
#  CSS Loader (loads Original styling from assets/theme.css)
# =========================================================
def load_local_css(path: str):
    with open(path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# =========================================================
#  STREAMLIT APPLICATION CONFIG
# =========================================================
st.set_page_config(page_title="SMC Dining OCR", layout="centered")

# Load your original CSS for branding + layout
load_local_css("assets/theme.css")

# =========================================================
#  TOP BANNER WITH SMC LOGO + RED STRIP
# =========================================================
st.markdown(
    """
    <div style="
        background-color:#D82732;
        padding:0.75rem 1rem;
        display:flex;
        align-items:center;
        gap:1rem;
    ">
        <img src="https://content.sportslogos.net/logos/34/858/full/mfhe5ysvfgzgt0wxt8hcz89pv.png"
             alt="Saint Mary's Gaels logo"
             style="height:40px;">
        <div style="color:white;">
            <div style="font-size:1.4rem;font-weight:700;">SMC Dining OCR</div>
            <div style="font-size:0.9rem;">Gael Dining Food-Waste Tracking Assistant</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
#  Simulated Bounding-Box OCR Output
# =========================================================
def get_simulated_ocr_rows():
    """
    These rows represent parsed lines from a completed dining tracking sheet.
    Update quantities to match your official example sheet if needed.
    """
    rows = [
        # ----- RICE -----
        {"row_id": 1, "item_raw": "rice", "qty": 10, "unit": "lbs"},
        {"row_id": 2, "item_raw": "rice", "qty": 10, "unit": "lbs"},

        # ----- ROASTED BROCCOLI -----
        {"row_id": 3, "item_raw": "broccoli", "qty": 8, "unit": "lbs"},
        {"row_id": 4, "item_raw": "roasted broccoli", "qty": 16, "unit": "lbs"},

        # ----- SOY GLAZED CARROTS -----
        {"row_id": 5, "item_raw": "carrots", "qty": 6, "unit": "lbs"},
        {"row_id": 6, "item_raw": "soy glazed carrots", "qty": 6, "unit": "lbs"},

        # ----- TERIYAKI CHICKEN -----
        {"row_id": 7, "item_raw": "teriyaki chicken", "qty": 12, "unit": "lbs"},
        {"row_id": 8, "item_raw": "chicken", "qty": 8, "unit": "lbs"},
    ]
    return pd.DataFrame(rows)


# =========================================================
#  Synonym Normalization Map (4 allowed items)
# =========================================================
NORMALIZATION_MAP = {
    # ---------- Roasted Broccoli ----------
    "broccoli": "Roasted Broccoli",
    "roasted broccoli": "Roasted Broccoli",
    "steamed broccoli": "Roasted Broccoli",
    "broc": "Roasted Broccoli",

    # ---------- Rice ----------
    "rice": "Rice",
    "white rice": "Rice",
    "brown rice": "Rice",

    # ---------- Soy Glazed Carrots ----------
    "soy glazed carrots": "Soy Glazed Carrots",
    "soy carrots": "Soy Glazed Carrots",
    "carrots": "Soy Glazed Carrots",
    "glazed carrots": "Soy Glazed Carrots",

    # ---------- Teriyaki Chicken ----------
    "teriyaki chicken": "Teriyaki Chicken",
    "chicken teriyaki": "Teriyaki Chicken",
    "chicken": "Teriyaki Chicken",
    "t chicken": "Teriyaki Chicken",
}


def normalize_item_name(item_raw: str) -> str:
    """
    Convert raw text into one of the four final menu categories.
    """
    key = item_raw.strip().lower()
    if key in NORMALIZATION_MAP:
        return NORMALIZATION_MAP[key]
    return item_raw.strip().title()


# =========================================================
#  Compute Totals
# =========================================================
def compute_totals_from_rows(rows_df: pd.DataFrame):
    df = rows_df.copy()
    df["item_clean"] = df["item_raw"].apply(normalize_item_name)

    totals = (
        df.groupby(["item_clean", "unit"], as_index=False)["qty"]
        .sum()
        .rename(columns={"item_clean": "Item", "qty": "Total Quantity", "unit": "Unit"})
    )

    # Optional: enforce consistent row order in the totals table
    ordered_items = [
        "Teriyaki Chicken",
        "Rice",
        "Soy Glazed Carrots",
        "Roasted Broccoli",
    ]
    totals["Item"] = pd.Categorical(totals["Item"], categories=ordered_items, ordered=True)
    totals = totals.sort_values("Item").reset_index(drop=True)

    return df, totals


# =========================================================
#  MAIN UI CONTENT
# =========================================================
st.write(
    """
This application processes Gael Dining tracking sheets and summarizes food items into
standardized categories.
 
Staff can upload a photo of a completed sheet, review the parsed rows, and email or download a CSV
with final totals.
"""
)

st.markdown("---")

uploaded_image = st.file_uploader(
    "Upload your log",
    type=["png", "jpg", "jpeg"],
)

run_demo = st.button("Process log")


# =========================================================
#  PROCESSING WORKFLOW
# =========================================================
if run_demo:

    if uploaded_image is None:
        st.warning("No image uploaded — processing the sample tracking sheet data.")

    # -----------------------------
    # Step 1 — Parsed Rows
    # -----------------------------
    st.subheader("Step 1 – Parsed Rows")

    rows_df = get_simulated_ocr_rows()

    st.caption(
        "These rows represent the structured output from our OCR and row-parsing step for a sample sheet."
    )

    st.dataframe(rows_df, use_container_width=True)

    # -----------------------------
    # Step 2 — Group & Normalize
    # -----------------------------
    st.subheader("Step 2 – Grouped Totals")

    parsed_df, totals_df = compute_totals_from_rows(rows_df)

    st.write(
        """
        All entries are normalized and grouped,
        so variations like “broccoli” and “roasted broccoli” are counted together.
        """
    )

    st.dataframe(totals_df, use_container_width=True)

    # -----------------------------
    # Step 3 — CSV Export
    # -----------------------------
    st.subheader("Step 3 – Export Totals")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"smc_dining_totals_{timestamp}.csv"

    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label=f"Download CSV ({filename})",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )

    st.success("Processing complete. Totals are ready for export.")

else:
    st.info("Upload a sheet and click **Process Sheet** to run the workflow.")
