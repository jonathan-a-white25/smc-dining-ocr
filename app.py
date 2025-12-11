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
st.set_page_config(page_title="SMC Dining OCR Demo", layout="centered")

# Load your original CSS for branding + layout
load_local_css("assets/theme.css")


# =========================================================
#  Simulated Bounding-Box OCR Output
# =========================================================
def get_simulated_ocr_rows():
    """
    These rows simulate OCR output from the actual dining sheet.
    Update quantities to match your official example sheet.
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
#  Synonym Normalization Map
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
    Convert raw OCR text into one of the four final categories.
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

    return df, totals


# =========================================================
#  USER INTERFACE
# =========================================================
st.title("SMC Dining OCR – Demo Build")

st.write(
    """
This demo shows the **end-to-end workflow** of the SMC Dining OCR system using a 
controlled, stable example.  

The workflow accurately represents the final product:
1. Staff upload a tracking sheet  
2. Rows are parsed (simulated OCR bounding boxes)  
3. Items are normalized to the four allowed menu items  
4. Totals are produced and exported for DRIVE  
"""
)

st.markdown("---")

uploaded_image = st.file_uploader(
    "Upload a tracking sheet photo (any image works for demo)",
    type=["png", "jpg", "jpeg"],
)

run_demo = st.button("Process Sheet")


# =========================================================
#  PROCESSING WORKFLOW
# =========================================================
if run_demo:

    if uploaded_image is None:
        st.warning("No image uploaded — continuing with the simulated OCR example.")

    # -----------------------------
    # Step 1 — Parsed Rows
    # -----------------------------
    st.subheader("Step 1 – Parsed Rows (Simulated OCR Output)")

    rows_df = get_simulated_ocr_rows()

    st.caption(
        "This simulates the output we would receive from Google Vision's bounding-box parser."
    )

    st.dataframe(rows_df, use_container_width=True)

    # -----------------------------
    # Step 2 — Group & Normalize
    # -----------------------------
    st.subheader("Step 2 – Grouped Totals (Synonym-Aware)")

    parsed_df, totals_df = compute_totals_from_rows(rows_df)

    st.write(
        """
        Items are matched against one of **four approved food items**:  
        **Teriyaki Chicken, Rice, Soy Glazed Carrots, Roasted Broccoli**  
        
        All synonyms (e.g., *broccoli*, *roasted broccoli*, *broc*) are grouped automatically.
        """
    )

    st.dataframe(totals_df, use_container_width=True)

    # -----------------------------
    # Step 3 — CSV Export
    # -----------------------------
    st.subheader("Step 3 – Export as CSV")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"smc_dining_totals_{timestamp}.csv"

    csv_bytes = totals_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label=f"Download CSV ({filename})",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )

    st.success("Demo completed successfully! This build is stable and presentation-ready.")

else:
    st.info("Upload a sheet and click **Process Sheet** to simulate the OCR workflow.")
