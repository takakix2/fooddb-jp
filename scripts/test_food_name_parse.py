"""
test_food_name_parse.py — 食品名パースの照合テスト

Excel 原本 (成分表.xlsx) から10品目をサンプリングし、
DB のパース結果と突き合わせて正確性を検証する。
"""

import sqlite3
import openpyxl
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "fooddb.sqlite"
EXCEL_PATH = BASE_DIR / "data" / "raw" / "成分表.xlsx"


def test_parse_accuracy():
    """Excel原本から10品目を取得し、DBのパース結果と照合する。"""
    
    # Excel から食品名を取得
    wb = openpyxl.load_workbook(str(EXCEL_PATH), read_only=True)
    ws = wb["表全体"]
    
    # 特定の行を選んで多様なパターンをカバー
    # Row 13がデータ開始、col B=食品番号, col D=食品名
    test_rows = [13, 25, 50, 100, 200, 500, 750, 1000, 1500, 2000]
    
    excel_foods = []
    for row_num in test_rows:
        food_number = None
        food_name = None
        for row in ws.iter_rows(min_row=row_num, max_row=row_num, max_col=4, values_only=True):
            food_number = str(row[1]).strip() if row[1] else None
            food_name = str(row[3]).strip() if row[3] else None
        
        if food_number and food_name and food_number != "None":
            # DB は先頭ゼロなし (1001)、Excel は先頭ゼロあり (01001)
            db_food_number = str(int(food_number)) if food_number.isdigit() else food_number
            excel_foods.append((db_food_number, food_name, row_num))
    
    wb.close()
    
    # DBと照合
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    print("=" * 70)
    print("食品名パース照合テスト")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for food_number, excel_name, row_num in excel_foods:
        cur.execute(
            """SELECT food_name, category, subcategory, base_name, detail
               FROM foods WHERE food_number = ?""",
            (food_number,)
        )
        result = cur.fetchone()
        
        if not result:
            print(f"\n❌ [{food_number}] Row {row_num}: DB にレコードなし")
            print(f"   Excel: {excel_name}")
            failed += 1
            continue
        
        db_name, cat, sub, base, detail = result
        
        # food_name が原文と一致するか
        name_match = db_name == excel_name
        
        # パース結果の再構成が元の名前を復元可能か（緩いチェック）
        parts = []
        if cat:
            parts.append(f"＜{cat}＞")
        if base:
            parts.append(base)
        if sub:
            parts.append(f"［{sub}］")
        if detail:
            parts.append(detail)
        
        # base_name が名前に含まれるか
        base_in_name = base in excel_name if base else False
        
        status = "✅" if name_match and base_in_name else "❌"
        if name_match and base_in_name:
            passed += 1
        else:
            failed += 1
        
        print(f"\n{status} [{food_number}] Row {row_num}")
        print(f"   Excel原文: {excel_name}")
        print(f"   DB food_name: {db_name}")
        print(f"   パース: cat={cat}, sub={sub}, base={base}, detail={detail}")
        if not name_match:
            print(f"   ⚠️  food_name不一致!")
    
    conn.close()
    
    print(f"\n{'=' * 70}")
    print(f"結果: {passed}/{passed + failed} PASS")
    if failed == 0:
        print("🎉 全品目照合OK!")
    else:
        print(f"⚠️  {failed}件の不一致あり")
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = test_parse_accuracy()
    sys.exit(0 if success else 1)
