import pandas as pd
import json

EXCEL_FILE = "成分表.xlsx"
SHEET_NAME = "表全体"

df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, header=None, skiprows=12)

metadata_list = []

for _, row in df.iterrows():
    food_number = str(row[1]).strip() if pd.notna(row[1]) else None  # B列
    index = str(row[2]).strip() if pd.notna(row[2]) else None        # C列
    name = str(row[3]).strip() if pd.notna(row[3]) else None         # D列
    class_ = str(row[0]).strip() if pd.notna(row[0]) else None       # A列（類区分）
    subgroup = None
    group = None
    category = None

    # 類区分や分類を正規表現で識別（実際の形式によって調整）
    if name and name.startswith("＜") and "＞" in name:
        subgroup = name.split("＞")[0] + "＞"
        name = name.split("＞")[-1].strip()
    
    if name and name.startswith("［") and "］" in name:
        category = name.split("］")[0] + "］"
        name = name.split("］")[-1].strip()

    metadata_list.append({
        "food_number": food_number,
        "index": index,
        "name": name,
        "class": class_,
        "subgroup": subgroup,
        "group": group,
        "category": category
    })

with open("food_metadata.json", "w", encoding="utf-8") as f:
    json.dump(metadata_list, f, ensure_ascii=False, indent=2)

print(f"✅ 食品メタデータ {len(metadata_list)} 件を抽出しました！'food_metadata.json' に保存済み")
