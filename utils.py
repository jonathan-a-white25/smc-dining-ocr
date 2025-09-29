import logging
import pandas as pd

def setup_logger():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return logging.getLogger("smc-dining-ocr")

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    cols = ["item","quantity"]
    out = df[cols] if all(c in df.columns for c in cols) else df
    return out.to_csv(index=False).encode("utf-8")

def summarize_by_item(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "item" not in df.columns or "quantity" not in df.columns:
        return pd.DataFrame(columns=["item","total_quantity"])
    agg = (df.dropna(subset=["item"])
             .assign(quantity=lambda d: pd.to_numeric(d["quantity"], errors="coerce"))
             .groupby("item", dropna=True, as_index=False)["quantity"]
             .sum()
             .rename(columns={"quantity":"total_quantity"})
             .sort_values("total_quantity", ascending=False))
    return agg

def sanitize_quantity_range(q, min_q, max_q):
    if q is None:
        return None
    try:
        iv = int(q)
    except Exception:
        return None
    if iv < min_q or iv > max_q:
        return None
    return iv
