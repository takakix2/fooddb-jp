"""
migrate_food_names.py — 食品名の構造化パースとDBカラム追加マイグレーション

文科省の食品標準成分表の食品名を構造化パースし、
既存の foods テーブルに category, subcategory, base_name, detail カラムを追加する。

Usage:
    python scripts/migrate_food_names.py [--dry-run]
"""

import sqlite3
import re
import argparse
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fooddb.sqlite"


def parse_food_name(name: str) -> dict:
    """
    文科省の食品標準成分表の食品名を構造化パースする。

    命名パターン:
      [＜category＞]　base_name　[［subcategory］]　[detail...]

    区切りは全角スペース（\\u3000）または半角スペース。
    food_name 原文はそのまま維持し、分解結果を別カラムに格納する。

    Returns:
        dict with keys: category, subcategory, base_name, detail
    """
    remaining = name.strip()
    category = None
    subcategory = None
    base_name = None
    detail = None

    # 1. ＜category＞ を抽出
    m = re.match(r'^＜([^＞]+)＞[\s\u3000]*(.*)', remaining)
    if m:
        category = m.group(1)
        remaining = m.group(2)

    # 2. ［subcategory］ を抽出（位置に関わらず）
    m_sub = re.search(r'［([^\]]+)］', remaining)
    if m_sub:
        subcategory = m_sub.group(1)
        before = remaining[:m_sub.start()].strip().rstrip('\u3000').rstrip()
        after = remaining[m_sub.end():].strip().lstrip('\u3000').lstrip()
        base_name = before if before else None
        detail = after if after else None
    else:
        # ［］がない場合: 最初のトークンがbase_name、残りがdetail
        tokens = re.split(r'[\s\u3000]+', remaining, maxsplit=1)
        if tokens:
            base_name = tokens[0] if tokens[0] else None
            if len(tokens) > 1 and tokens[1]:
                detail = tokens[1]

    return {
        "category": category,
        "subcategory": subcategory,
        "base_name": base_name,
        "detail": detail,
    }


def migrate(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # --- Step 1: カラム追加 (存在チェック付き) ---
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(foods)")}
    new_columns = {
        "category": "TEXT",
        "subcategory": "TEXT",
        "base_name": "TEXT",
        "detail": "TEXT",
    }

    for col_name, col_type in new_columns.items():
        if col_name not in existing_cols:
            print(f"  ALTER TABLE: +{col_name} ({col_type})")
            if not dry_run:
                cur.execute(f"ALTER TABLE foods ADD COLUMN {col_name} {col_type}")

    # --- Step 2: 全レコードをパースして UPDATE ---
    cur.execute("SELECT food_number, food_name FROM foods ORDER BY food_number")
    rows = cur.fetchall()

    updated = 0
    errors = []

    for food_number, food_name in rows:
        parsed = parse_food_name(food_name)

        if not parsed["base_name"]:
            errors.append((food_number, food_name, "base_name is empty"))
            continue

        if not dry_run:
            cur.execute(
                """UPDATE foods
                   SET category = ?, subcategory = ?, base_name = ?, detail = ?
                   WHERE food_number = ?""",
                (
                    parsed["category"],
                    parsed["subcategory"],
                    parsed["base_name"],
                    parsed["detail"],
                    food_number,
                ),
            )
        updated += 1

    # --- Step 3: インデックス追加 ---
    if not dry_run:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_foods_category ON foods(category)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_foods_subcategory ON foods(subcategory)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_foods_base_name ON foods(base_name)"
        )
        conn.commit()

    conn.close()

    # --- 結果レポート ---
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}マイグレーション完了:")
    print(f"  対象: {len(rows)} 件")
    print(f"  更新: {updated} 件")
    print(f"  エラー: {len(errors)} 件")

    if errors:
        print("\nエラー詳細:")
        for fn, fname, reason in errors:
            print(f"  [{fn}] {fname} — {reason}")

    if not dry_run:
        # 検証: サンプル出力
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        print("\n--- 検証サンプル (10件) ---")
        cur.execute(
            """SELECT food_number, food_name, category, subcategory, base_name, detail
               FROM foods
               ORDER BY RANDOM()
               LIMIT 10"""
        )
        for row in cur.fetchall():
            fn, fname, cat, sub, base, det = row
            print(f"  [{fn}] {fname}")
            print(f"    → cat={cat}, sub={sub}, base={base}, detail={det}")
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="食品名構造化マイグレーション")
    parser.add_argument("--dry-run", action="store_true", help="実行せずに結果を表示")
    args = parser.parse_args()

    print(f"DB: {DB_PATH}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print()

    migrate(DB_PATH, dry_run=args.dry_run)
