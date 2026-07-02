"""
xlsx_to_jsonl.py - v1.2.0
Author: takaki & Copilot
目的: ヘッダーなしExcelを header_full.json に基づいて構文合成し、
表記揺れと単位付き構造 {"value": x, "unit": "..."} に整形して JSONL出力
"""

import pandas as pd
import json

# 📘 ヘッダー辞書読み込み
with open("header_full.json", encoding="utf-8") as f:
    column_map = json.load(f)

# 🔍 有効な成分列（unit付き／component_idがnullでないもの）抽出
excluded_ids = ["group", "food_number", "index", "edible_base", "remarks", None]
nutrient_columns = {
    col: {
        "id": v["component_id"],
        "unit": v["unit"]
    }
    for col, v in column_map.items()
    if v["component_id"] not in excluded_ids and v["component_id"] is not None
}

# 📘 主要列記号
group_cols = {
    "group": "A",
    "food_number": "B",
    "index": "C",
    "edible_base": "D",
    "remarks": "BJ"
}

# 📊 Excel読み込み（ヘッダーなし／13行目以降）
df = pd.read_excel("成分表.xlsx", sheet_name="1穀類", header=None, skiprows=12)

# ✂️ 列記号 → インデックス変換関数
def col_letter_to_index(letter):
    result = 0
    for char in letter:
        result = result * 26 + (ord(char.upper()) - ord('A') + 1)
    return result - 1

# 🎯 表記揺れフィルタ関数
def clean_value(val):
    if pd.isna(val):
        return None
    val_str = str(val).strip()
    if val_str in ["-", "", "NaN"]:
        return None
    if val_str in ["Tr", "(Tr)", "tr", "(tr)"]:
        return 0.0
    if val_str.startswith("(") and val_str.endswith(")"):
        val_str = val_str[1:-1].strip()
    try:
        return float(val_str)
    except ValueError:
        return val_str

# 📦 JSONL出力処理
with open("1kokurui.jsonl", "w", encoding="utf-8") as f_out:
    for _, row in df.iterrows():
        record = {
            "group": row[col_letter_to_index(group_cols["group"])],
            "food_number": str(row[col_letter_to_index(group_cols["food_number"])]),
            "index": str(row[col_letter_to_index(group_cols["index"])]),
            "edible_base": str(row[col_letter_to_index(group_cols["edible_base"])]),
            "nutrients": {},
            "remarks": clean_value(row[col_letter_to_index(group_cols["remarks"])])
        }

        for col_letter, spec in nutrient_columns.items():
            val = clean_value(row[col_letter_to_index(col_letter)])
            if val is not None:
                record["nutrients"][spec["id"]] = {
                    "value": val,
                    "unit": spec["unit"]
                }

        f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

print("✅ '1kokurui.jsonl' を単位付き構造で正常に出力しました（v1.2.0）")
