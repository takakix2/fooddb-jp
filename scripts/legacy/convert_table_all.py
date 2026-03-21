import pandas as pd
import json
import re

EXCEL_FILE = "成分表.xlsx"
SHEET_NAME = "表全体"
HEADER_ROWS = 10  # ヘッダー：3〜12行
DATA_START_ROW = 12

# ✂️ A列〜BJ列に対応した列記号
def generate_column_letters(n):
    result = []
    for i in range(n):
        col = ""
        index = i
        while index >= 0:
            col = chr(index % 26 + 65) + col
            index = index // 26 - 1
        result.append(col)
    return result

# ---------------------------------------------------
# 🧩 ブロック① ヘッダー統合 → header_full.json を生成
# ---------------------------------------------------
def extract_headers():
    header_rows = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, header=None, skiprows=2, nrows=HEADER_ROWS)
    column_letters = generate_column_letters(header_rows.shape[1])
    UNIT_REGEX = re.compile(r"(μg|mg|g|kJ|kcal|%)")

    column_map = {}

    for col_idx, col_letter in enumerate(column_letters):
        parts = [str(cell).strip() for cell in header_rows.iloc[:, col_idx] if pd.notna(cell)]
        full_label = " ".join(parts)
        match = UNIT_REGEX.search(full_label)
        unit = match.group(1) if match else None
        label_jp = full_label.replace(unit or "", "").strip()
        component_id = label_jp.upper().replace("-", "_").replace(" ", "_") if label_jp else None

        column_map[col_letter] = {
            "component_id": component_id,
            "label_jp": label_jp or None,
            "unit": unit,
            "group": None,
            "subgroup": None
        }

    with open("header_full.json", "w", encoding="utf-8") as f:
        json.dump(column_map, f, ensure_ascii=False, indent=2)
    print("✅ header_full.json を生成しました")
    return column_map

# ---------------------------------------------------
# 🍱 ブロック② 食品メタデータ抽出 → food_metadata.json 生成
# ---------------------------------------------------
def extract_food_metadata():
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, header=None, skiprows=DATA_START_ROW)
    metadata = []

    for _, row in df.iterrows():
        food_number = str(row[1]).strip() if pd.notna(row[1]) else None  # B列
        index = str(row[2]).strip() if pd.notna(row[2]) else None        # C列
        name_raw = str(row[3]).strip() if pd.notna(row[3]) else None     # D列

        class_ = str(row[0]).strip() if pd.notna(row[0]) else None       # A列

        # 五段階分類抽出（ルールベース）
        subgroup = group = category = item = None

        match_group = re.search(r"［(.*?)］", name_raw or "")
        if match_group:
            group = match_group.group(1)
        
        tail = (name_raw or "").split("］")[-1].strip() if "］" in (name_raw or "") else name_raw
        parts = tail.split("　")
        if len(parts) >= 1:
            category = parts[0]
        if len(parts) >= 2:
            item = parts[1]

        metadata.append({
            "food_number": food_number,
            "index": index,
            "name": name_raw,
            "class": class_,
            "group": group,
            "category": category,
            "item": item
        })

    with open("food_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print("✅ food_metadata.json を生成しました")
    return {m["food_number"]: m for m in metadata if m["food_number"]}

# ---------------------------------------------------
# 📊 ブロック③ 成分データ整形 → nutrition_all.jsonl 出力
# ---------------------------------------------------
def convert_to_jsonl(column_map, food_meta_map):
    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, header=None, skiprows=DATA_START_ROW)

    # 有効成分列抽出
    excluded_ids = ["group", "food_number", "index", "edible_base", "remarks", None]
    nutrient_columns = {
        col: {
            "id": v["component_id"],
            "unit": v["unit"]
        }
        for col, v in column_map.items()
        if v["component_id"] not in excluded_ids and v["component_id"] is not None
    }

    def col_letter_to_index(letter):
        result = 0
        for char in letter:
            result = result * 26 + (ord(char.upper()) - ord('A') + 1)
        return result - 1

    def clean_value(val):
        if pd.isna(val): return None
        val_str = str(val).strip()
        if val_str in ["-", "", "NaN"]: return None
        if val_str in ["Tr", "(Tr)", "tr", "(tr)"]: return 0.0
        if val_str.startswith("(") and val_str.endswith(")"):
            val_str = val_str[1:-1].strip()
        try:
            return float(val_str)
        except ValueError:
            return val_str

    with open("nutrition_all.jsonl", "w", encoding="utf-8") as f_out:
        for _, row in df.iterrows():
            food_number = str(row[col_letter_to_index("B")])
            index = str(row[col_letter_to_index("C")])
            record = {
                "group": row[col_letter_to_index("A")],
                "food_number": food_number,
                "index": index,
                "edible_base": str(row[col_letter_to_index("D")]),
                "nutrients": {},
                "remarks": clean_value(row[col_letter_to_index("BJ")]),
                "metadata": food_meta_map.get(food_number, {})
            }

            for col_letter, spec in nutrient_columns.items():
                val = clean_value(row[col_letter_to_index(col_letter)])
                if val is not None:
                    record["nutrients"][spec["id"]] = {
                        "value": val,
                        "unit": spec["unit"]
                    }

            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("✅ nutrition_all.jsonl を出力しました")

# 🧪 実行ブロック
if __name__ == "__main__":
    header_map = extract_headers()
    food_map = extract_food_metadata()
    convert_to_jsonl(header_map, food_map)
