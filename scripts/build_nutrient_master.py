"""
build_nutrient_master.py — 全353タグの日英ラベル・単位マスター生成

Excelのヘッダーから日本語名を抽出し、INFOODS規約に基づいて
英語名と単位を付与する。

出力: data/output/nutrient_master.json
"""

import openpyxl
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = BASE_DIR / "data" / "output"

# ========================================
# アミノ酸の基本定義
# ========================================

AMINO_ACIDS = {
    "ILE": ("イソロイシン", "Isoleucine"),
    "LEU": ("ロイシン", "Leucine"),
    "LYS": ("リシン（リジン）", "Lysine"),
    "MET": ("メチオニン", "Methionine"),
    "CYS": ("シスチン", "Cystine"),
    "PHE": ("フェニルアラニン", "Phenylalanine"),
    "TYR": ("チロシン", "Tyrosine"),
    "THR": ("トレオニン（スレオニン）", "Threonine"),
    "TRP": ("トリプトファン", "Tryptophan"),
    "VAL": ("バリン", "Valine"),
    "HIS": ("ヒスチジン", "Histidine"),
    "ARG": ("アルギニン", "Arginine"),
    "ALA": ("アラニン", "Alanine"),
    "ASP": ("アスパラギン酸", "Aspartic acid"),
    "GLU": ("グルタミン酸", "Glutamic acid"),
    "GLY": ("グリシン", "Glycine"),
    "PRO": ("プロリン", "Proline"),
    "SER": ("セリン", "Serine"),
    "HYP": ("ヒドロキシプロリン", "Hydroxyproline"),
    "AMMON": ("アンモニア", "Ammonia"),
    "AMMON-E": ("アンモニア（当量）", "Ammonia (equivalent)"),
    "AAT": ("アミノ酸合計", "Total amino acids"),
    "AAA": ("芳香族アミノ酸", "Aromatic amino acids"),
    "AAS": ("含硫アミノ酸", "Sulfur-containing amino acids"),
}

# アミノ酸テーブル接尾辞
AMINO_SUFFIXES = {
    "": ("mg/可食部100g", "mg/100g edible portion", "amino1"),
    "N": ("mg/g基準窒素", "mg/g reference nitrogen", "amino2"),
    "PA": ("mg/gたんぱく質(AA)", "mg/g protein (amino acid)", "amino3"),
    "P": ("mg/gたんぱく質(N)", "mg/g protein (nitrogen)", "amino4"),
}

# ========================================
# 脂肪酸の基本定義
# ========================================

FATTY_ACIDS = {
    "F4D0":     ("酪酸 (4:0)", "Butyric acid (4:0)"),
    "F6D0":     ("カプロン酸 (6:0)", "Caproic acid (6:0)"),
    "F7D0":     ("ヘプタン酸 (7:0)", "Heptanoic acid (7:0)"),
    "F8D0":     ("カプリル酸 (8:0)", "Caprylic acid (8:0)"),
    "F10D0":    ("カプリン酸 (10:0)", "Capric acid (10:0)"),
    "F10D1":    ("デセン酸 (10:1)", "Decenoic acid (10:1)"),
    "F12D0":    ("ラウリン酸 (12:0)", "Lauric acid (12:0)"),
    "F13D0":    ("トリデカン酸 (13:0)", "Tridecanoic acid (13:0)"),
    "F14D0":    ("ミリスチン酸 (14:0)", "Myristic acid (14:0)"),
    "F14D1":    ("ミリストレイン酸 (14:1)", "Myristoleic acid (14:1)"),
    "F15D0":    ("ペンタデカン酸 (15:0)", "Pentadecanoic acid (15:0)"),
    "F15D0AI":  ("ペンタデカン酸(ante-iso) (ai15:0)", "Pentadecanoic acid (ante-iso)"),
    "F15D1":    ("ペンタデセン酸 (15:1)", "Pentadecenoic acid (15:1)"),
    "F16D0":    ("パルミチン酸 (16:0)", "Palmitic acid (16:0)"),
    "F16D0I":   ("パルミチン酸(iso) (i16:0)", "Palmitic acid (iso)"),
    "F16D1":    ("パルミトレイン酸 (16:1)", "Palmitoleic acid (16:1)"),
    "F16D2":    ("ヘキサデカジエン酸 (16:2)", "Hexadecadienoic acid (16:2)"),
    "F16D3":    ("ヘキサデカトリエン酸 (16:3)", "Hexadecatrienoic acid (16:3)"),
    "F16D4":    ("ヘキサデカテトラエン酸 (16:4)", "Hexadecatetraenoic acid (16:4)"),
    "F17D0":    ("ヘプタデカン酸 (17:0)", "Heptadecanoic acid (17:0)"),
    "F17D0AI":  ("ヘプタデカン酸(ante-iso) (ai17:0)", "Heptadecanoic acid (ante-iso)"),
    "F17D1":    ("ヘプタデセン酸 (17:1)", "Heptadecenoic acid (17:1)"),
    "F18D0":    ("ステアリン酸 (18:0)", "Stearic acid (18:0)"),
    "F18D1":    ("オレイン酸 (18:1)", "Oleic acid (18:1)"),
    "F18D1CN9": ("オレイン酸(n-9) (18:1 n-9)", "Oleic acid (18:1 n-9)"),
    "F18D1CN7": ("バクセン酸(n-7) (18:1 n-7)", "Vaccenic acid (18:1 n-7)"),
    "F18D2N6":  ("リノール酸 (18:2 n-6)", "Linoleic acid (18:2 n-6)"),
    "F18D3N3":  ("α-リノレン酸 (18:3 n-3)", "alpha-Linolenic acid (18:3 n-3)"),
    "F18D3N6":  ("γ-リノレン酸 (18:3 n-6)", "gamma-Linolenic acid (18:3 n-6)"),
    "F18D4N3":  ("オクタデカテトラエン酸 (18:4 n-3)", "Octadecatetraenoic acid (18:4 n-3)"),
    "F20D0":    ("アラキジン酸 (20:0)", "Arachidic acid (20:0)"),
    "F20D1":    ("イコセン酸 (20:1)", "Eicosenoic acid (20:1)"),
    "F20D2N6":  ("イコサジエン酸 (20:2 n-6)", "Eicosadienoic acid (20:2 n-6)"),
    "F20D3N3":  ("イコサトリエン酸 (20:3 n-3)", "Eicosatrienoic acid (20:3 n-3)"),
    "F20D3N6":  ("イコサトリエン酸 (20:3 n-6)", "Dihomo-gamma-linolenic acid (20:3 n-6)"),
    "F20D4N3":  ("イコサテトラエン酸 (20:4 n-3)", "Eicosatetraenoic acid (20:4 n-3)"),
    "F20D4N6":  ("アラキドン酸 (20:4 n-6)", "Arachidonic acid (20:4 n-6)"),
    "F20D5N3":  ("EPA (20:5 n-3)", "Eicosapentaenoic acid (20:5 n-3)"),
    "F21D5N3":  ("ヘンイコサペンタエン酸 (21:5 n-3)", "Heneicosapentaenoic acid (21:5 n-3)"),
    "F22D0":    ("ベヘン酸 (22:0)", "Behenic acid (22:0)"),
    "F22D1":    ("エルカ酸 (22:1)", "Erucic acid (22:1)"),
    "F22D2":    ("ドコサジエン酸 (22:2)", "Docosadienoic acid (22:2)"),
    "F22D4N6":  ("ドコサテトラエン酸 (22:4 n-6)", "Docosatetraenoic acid (22:4 n-6)"),
    "F22D5N3":  ("DPA (22:5 n-3)", "Docosapentaenoic acid (22:5 n-3)"),
    "F22D5N6":  ("ドコサペンタエン酸 (22:5 n-6)", "Docosapentaenoic acid (22:5 n-6)"),
    "F22D6N3":  ("DHA (22:6 n-3)", "Docosahexaenoic acid (22:6 n-3)"),
    "F24D0":    ("リグノセリン酸 (24:0)", "Lignoceric acid (24:0)"),
    "F24D1":    ("ネルボン酸 (24:1)", "Nervonic acid (24:1)"),
    "FACID":    ("脂肪酸総量", "Total fatty acids"),
    "FASAT":    ("飽和脂肪酸", "Saturated fatty acids"),
    "FAMS":     ("一価不飽和脂肪酸", "Monounsaturated fatty acids"),
    "FAPU":     ("多価不飽和脂肪酸", "Polyunsaturated fatty acids"),
    "FAPUN3":   ("n-3系多価不飽和脂肪酸", "n-3 polyunsaturated fatty acids"),
    "FAPUN6":   ("n-6系多価不飽和脂肪酸", "n-6 polyunsaturated fatty acids"),
    "FAUN":     ("未同定脂肪酸", "Unidentified fatty acids"),
}

# 脂肪酸テーブル接尾辞
FATTY_SUFFIXES = {
    "":  ("mg/可食部100g", "mg/100g edible portion", "fatty1"),
    "F": ("g/脂肪酸100g", "g/100g fatty acids", "fatty2"),
    "L": ("mg/脂質1g", "mg/g lipid", "fatty3"),
}

# ========================================
# 炭水化物の定義
# ========================================

CARB_MAIN = {
    "STARCH":  ("でん粉", "Starch", "g", "carb_main"),
    "GLUS":    ("ぶどう糖", "Glucose", "g", "carb_main"),
    "FRUS":    ("果糖", "Fructose", "g", "carb_main"),
    "GALS":    ("ガラクトース", "Galactose", "g", "carb_main"),
    "SUCS":    ("しょ糖", "Sucrose", "g", "carb_main"),
    "MALS":    ("麦芽糖", "Maltose", "g", "carb_main"),
    "LACS":    ("乳糖", "Lactose", "g", "carb_main"),
    "TRES":    ("トレハロース", "Trehalose", "g", "carb_main"),
    "SORTL":   ("ソルビトール", "Sorbitol", "g", "carb_main"),
    "MANTL":   ("マンニトール", "Mannitol", "g", "carb_main"),
}

CARB_FIBER = {
    "FIBTG":   ("食物繊維総量（プロスキー法）", "Total dietary fibre (Prosky)", "g", "carb_fiber"),
    "FIBSOL":  ("水溶性食物繊維", "Soluble dietary fibre", "g", "carb_fiber"),
    "FIBINS":  ("不溶性食物繊維", "Insoluble dietary fibre", "g", "carb_fiber"),
    "FIB-TDF": ("食物繊維総量（AOAC 2011.25法）", "Total dietary fibre (AOAC 2011.25)", "g", "carb_fiber"),
    "FIB-SDFS":("低分子量水溶性食物繊維", "Low MW soluble dietary fibre", "g", "carb_fiber"),
    "FIB-SDFP":("高分子量水溶性食物繊維", "High MW soluble dietary fibre", "g", "carb_fiber"),
    "FIB-IDF": ("不溶性食物繊維（AOAC 2011.25法）", "Insoluble dietary fibre (AOAC 2011.25)", "g", "carb_fiber"),
    "STARES":  ("でん粉（難消化性）", "Resistant starch", "g", "carb_fiber"),
}

CARB_ORGANIC = {
    "FORAC":   ("ギ酸", "Formic acid", "mg", "carb_organic"),
    "ACEAC":   ("酢酸", "Acetic acid", "mg", "carb_organic"),
    "GLUAKAC": ("グリコール酸", "Glycolic acid", "mg", "carb_organic"),
    "LACAC":   ("乳酸", "Lactic acid", "mg", "carb_organic"),
    "GLUCAC":  ("グルコン酸", "Gluconic acid", "mg", "carb_organic"),
    "OXALAC":  ("シュウ酸", "Oxalic acid", "mg", "carb_organic"),
    "MALAC":   ("マロン酸", "Malonic acid", "mg", "carb_organic"),
    "SUCAC":   ("コハク酸", "Succinic acid", "mg", "carb_organic"),
    "FUMAC":   ("フマル酸", "Fumaric acid", "mg", "carb_organic"),
    "MOLAC":   ("リンゴ酸", "Malic acid", "mg", "carb_organic"),
    "TARAC":   ("酒石酸", "Tartaric acid", "mg", "carb_organic"),
    "GLYCLAC": ("グリセリン酸", "Glyceric acid", "mg", "carb_organic"),
    "CITAC":   ("クエン酸", "Citric acid", "mg", "carb_organic"),
    "SALAC":   ("サリチル酸", "Salicylic acid", "mg", "carb_organic"),
    "PCHOUAC": ("p-クマル酸", "p-Coumaric acid", "mg", "carb_organic"),
    "CAFFAC":  ("コーヒー酸", "Caffeic acid", "mg", "carb_organic"),
    "FERAC":   ("フェルラ酸", "Ferulic acid", "mg", "carb_organic"),
    "CHLRAC":  ("クロロゲン酸", "Chlorogenic acid", "mg", "carb_organic"),
    "QUINAC":  ("キナ酸", "Quinic acid", "mg", "carb_organic"),
    "OROTAC":  ("オロト酸", "Orotic acid", "mg", "carb_organic"),
    "PYROGAC": ("ピログルタミン酸", "Pyroglutamic acid", "mg", "carb_organic"),
    "PROPAC":  ("プロピオン酸", "Propionic acid", "mg", "carb_organic"),
}

# 本表は convert.py の NUTRIENT_MASTER をそのまま使用
from convert import NUTRIENT_MASTER as MAIN_MASTER


def build_master() -> list[dict]:
    """全353タグのマスターを構築する。"""
    master = []

    # 1. 本表（54タグ）
    for tag, info in MAIN_MASTER.items():
        master.append({
            "tag": tag,
            "label_jp": info["label_jp"],
            "label_en": info["label_en"],
            "unit": info["unit"],
            "table_id": "main",
        })

    # 2. アミノ酸（4表 × ~24タグ）
    for suffix, (unit_jp, unit_en, table_id) in AMINO_SUFFIXES.items():
        for base_tag, (jp, en) in AMINO_ACIDS.items():
            tag = base_tag + suffix
            # 特殊タグの処理
            if suffix == "N" and base_tag in ("AMMON-E",):
                continue  # AMMON-Eはtable1のみ
            if suffix != "" and base_tag == "AMMON-E":
                continue
            # amino2 の追加タグ
            master.append({
                "tag": tag,
                "label_jp": jp,
                "label_en": en,
                "unit": unit_jp,
                "table_id": table_id,
            })
        # amino2 の窒素換算係数
        if suffix == "N":
            master.append({"tag": "XN", "label_jp": "窒素-たんぱく質換算係数", "label_en": "Nitrogen-protein conversion factor", "unit": "", "table_id": "amino2"})
            master.append({"tag": "XNA", "label_jp": "窒素-たんぱく質換算係数(AA)", "label_en": "Nitrogen-protein conversion factor (amino acid)", "unit": "", "table_id": "amino2"})

    # 3. 脂肪酸（3表 × ~55タグ）
    for suffix, (unit_jp, unit_en, table_id) in FATTY_SUFFIXES.items():
        for base_tag, (jp, en) in FATTY_ACIDS.items():
            tag = base_tag + suffix
            master.append({
                "tag": tag,
                "label_jp": jp,
                "label_en": en,
                "unit": unit_jp,
                "table_id": table_id,
            })

    # 4. 炭水化物 本表
    for tag, (jp, en, unit, tid) in CARB_MAIN.items():
        master.append({"tag": tag, "label_jp": jp, "label_en": en, "unit": unit, "table_id": tid})

    # 5. 炭水化物 別表1（食物繊維）
    for tag, (jp, en, unit, tid) in CARB_FIBER.items():
        master.append({"tag": tag, "label_jp": jp, "label_en": en, "unit": unit, "table_id": tid})

    # 6. 炭水化物 別表2（有機酸）
    for tag, (jp, en, unit, tid) in CARB_ORGANIC.items():
        master.append({"tag": tag, "label_jp": jp, "label_en": en, "unit": unit, "table_id": tid})

    # 本表の WATER, PROTCAA, PROT- は他のテーブルにも出現するが、
    # nutrient_defs としては一意のタグとして1つだけ持てば十分

    return master


def main():
    master = build_master()

    # 重複除去（タグが一意になるよう最初の出現を優先）
    seen = set()
    unique = []
    for m in master:
        if m["tag"] not in seen:
            seen.add(m["tag"])
            unique.append(m)

    output_path = OUTPUT_DIR / "nutrient_master.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"✅ {output_path}: {len(unique)} タグ定義")

    # DB の nutrient_defs を未カバーのタグがないか確認
    import sqlite3
    conn = sqlite3.connect(str(BASE_DIR / "fooddb.sqlite"))
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT tag FROM nutrient_defs")
    db_tags = {row[0] for row in cur.fetchall()}
    master_tags = {m["tag"] for m in unique}

    missing = db_tags - master_tags
    extra = master_tags - db_tags

    if missing:
        print(f"\n⚠️  DB にあるがマスター未定義のタグ: {len(missing)}")
        for t in sorted(missing):
            print(f"   {t}")
    else:
        print(f"\n✅ 全DBタグをカバー済み")

    if extra:
        print(f"\n📝 マスターにあるがDBに無いタグ: {len(extra)}")
        for t in sorted(extra):
            print(f"   {t}")

    conn.close()


if __name__ == "__main__":
    main()
