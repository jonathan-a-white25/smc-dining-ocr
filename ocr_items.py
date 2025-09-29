from typing import Dict, List, Tuple, Optional
import re
import pytesseract
from pytesseract import Output
from PIL import Image
import numpy as np
import pandas as pd

import preprocessing

ITEM_TOKEN_MIN_LEN = 2
ALPHA_RE = re.compile(r"[A-Za-z]")

def _group_lines(data: Dict, y_tol: int = 12) -> List[List[Tuple[int,int,str,int]]]:
    pts = []
    for i, t in enumerate(data["text"]):
        txt = (t or "").strip()
        if not txt:
            continue
        try:
            conf = int(float(data["conf"][i]))
        except:
            conf = -1
        y = data["top"][i]
        x = data["left"][i]
        pts.append((y, x, txt, conf))
    pts.sort(key=lambda r: (r[0], r[1]))
    lines, cur, prev_y = [], [], None
    for y, x, txt, conf in pts:
        if prev_y is None or abs(y - prev_y) <= y_tol:
            cur.append((y, x, txt, conf))
        else:
            if cur: lines.append(cur)
            cur = [(y, x, txt, conf)]
        prev_y = y
    if cur: lines.append(cur)
    return lines

def _extract_line_item_and_qty(tokens: List[Tuple[int,int,str,int]], conf_threshold: int) -> Tuple[Optional[str], Optional[int]]:
    qty, qty_conf = None, -1
    words = []
    for _, _, txt, conf in tokens:
        if txt.isdigit():
            if conf >= conf_threshold and conf > qty_conf:
                qty, qty_conf = int(txt), conf
            continue
        if ALPHA_RE.search(txt):
            t = re.sub(r"[^A-Za-z0-9'/-]+", " ", txt).strip()
            if len(t) >= ITEM_TOKEN_MIN_LEN:
                words.append(t)
    item = " ".join(words).strip() or None
    return item, qty

def extract_items_quantities(
    img_file,
    conf_threshold: int = 80,
    normalize: bool = False,
    normalization_map: Optional[Dict[str, List[str]]] = None
) -> pd.DataFrame:
    img = Image.open(img_file).convert("RGB")
    np_img = np.array(img)
    proc = preprocessing.preprocess_for_digits(np_img)

    cfg = r'--oem 3 --psm 6'
    data = pytesseract.image_to_data(proc, config=cfg, output_type=Output.DICT)
    lines = _group_lines(data)

    rows = []
    for line in lines:
        item, qty = _extract_line_item_and_qty(line, conf_threshold=conf_threshold)
        if item is None and qty is None:
            continue
        rows.append({"item": item, "quantity": qty})

    cleaned = []
    for r in rows:
        if (r["item"] and ALPHA_RE.search(r["item"])) or (r["quantity"] is not None):
            cleaned.append(r)
    df = pd.DataFrame(cleaned) if cleaned else pd.DataFrame(columns=["item","quantity"])
    return df
