import pandas as pd
import json
import re

# 🎯 ターゲットExcelファイルとシート
EXCEL_FILE = "成分表.xlsx"
TARGET_SHEET = "1穀類"

# 📥 ヘッダー行（3〜12行目）を読み込む
header_rows = pd.read_excel(EXCEL_FILE, sheet_name=TARGET_SHEET, header=None, skiprows=2, nrows=10)

# 📦 列記号ジェネレータ（A〜ZZ対応）
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

# 🔍 単位抽出パターン
UNIT_REGEX = re.compile(r"(μg|mg|g|kJ|kcal|%)")

# 🧠 コンポーネントID生成ルール（シンプル版）
def generate_component_id(label):
    label = label.strip().replace("（別表記）", "").replace("（", "").replace("）", "")
    return label.upper().replace("-", "_").replace(" ", "_")

# 🛠 ヘッダー統合と整形
column_map = {}
column_letters = generate_column_letters(header_rows.shape[1])

for col_idx, col_letter in enumerate(column_letters):
    parts = [str(cell).strip() for cell in header_rows.iloc[:, col_idx] if pd.notna(cell)]
    full_label = " ".join(parts)
    match = UNIT_REGEX.search(full_label)
    unit = match.group(1) if match else None
    label_jp = full_label.replace(unit or "", "").strip()

    # component_id は簡易整形ルールで仮生成（後で調整OK）
    component_id = generate_component_id(label_jp) if label_jp else None

    column_map[col_letter] = {
        "component_id": component_id,
        "label_jp": label_jp or None,
        "unit": unit,
        "group": None,
        "subgroup": None
    }

# 💾 保存
with open("header_full.json", "w", encoding="utf-8") as f:
    json.dump(column_map, f, ensure_ascii=False, indent=2)

print("✅ 'header_full.json' をヘッダー構文に基づいて生成しました！")
