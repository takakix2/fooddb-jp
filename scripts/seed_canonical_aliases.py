#!/usr/bin/env python3
"""主要食品の英語名 → 正規 food_number を alias_canonical テーブルへ投入する（非破壊・冪等）。

背景:
    food_aliases には build_aliases.py が MEXT 英語名から英語別名を約1,000行生成済みだが、
    1つの英語語が多数の食品に張られる（例 "beef" が139部位すべて）。検索の並び順を
    food_number 昇順にすると、基本形でない食品が先頭に来てしまう（"tofu" → たまご豆腐 等）。

設計:
    food_aliases は触らず、別テーブル alias_canonical(alias, food_number) に「この英語語の
    代表はこの食品」という正規マッピングだけを持たせる。検索 (api.py search_foods) は
    canonical 完全一致を最優先で並べる。これで既存の広いカバレッジ（"beef"で139件出る等）を
    保ったまま、トップだけ基本形に固定できる。

冪等:
    alias_canonical を毎回作り直す（DROP/CREATE + INSERT）。food_aliases には無影響。

使い方:
    python3 scripts/seed_canonical_aliases.py [path/to/fooddb.sqlite]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 正規 food_number -> [English aliases]（小文字。検索の LIKE/比較は大小無視）
# food_number はすべて MEXT 成分表の「生／主品目／基本形」を採用。
CANONICAL: dict[str, list[str]] = {
    # --- 卵・乳製品 ---
    "12004": ["egg", "eggs", "chicken egg"],
    "13003": ["milk", "cow milk"],
    "13040": ["cheese", "processed cheese"],
    "13025": ["yogurt", "yoghurt"],
    "14017": ["butter"],
    # --- 主食・穀類・麺 ---
    "1088": ["rice", "cooked rice", "steamed rice", "white rice"],
    "1083": ["raw rice", "uncooked rice", "polished rice"],
    "1080": ["brown rice"],
    "1026": ["bread", "white bread"],
    "1015": ["flour", "wheat flour"],
    "1039": ["udon", "udon noodles"],
    "1128": ["soba", "buckwheat noodles"],
    # --- 肉・加工肉 ---
    "11221": ["chicken", "chicken thigh"],
    "11004": ["beef"],
    "11115": ["pork"],
    "11176": ["ham"],
    "11186": ["sausage"],
    "11183": ["bacon"],
    # --- 魚介 ---
    "10134": ["salmon"],
    "10253": ["tuna"],
    "10047": ["sardine"],
    "10154": ["mackerel"],
    "10415": ["shrimp", "prawn"],
    "10345": ["squid", "calamari"],
    "10361": ["octopus", "tako"],
    "10311": ["scallop"],
    "10281": ["clam"],
    "9004": ["nori", "seaweed"],
    # --- 大豆製品 ---
    "4032": ["tofu", "bean curd"],
    "4046": ["natto", "fermented soybeans"],
    "4023": ["soybean", "soybeans", "soy beans", "soy"],
    "4052": ["soy milk", "soymilk"],
    "6015": ["edamame"],
    # --- いも・野菜 ---
    "2017": ["potato", "potatoes"],
    "2006": ["sweet potato", "sweet potatoes"],
    "6214": ["carrot", "carrots"],
    "6153": ["onion", "onions"],
    "6182": ["tomato", "tomatoes"],
    "6061": ["cabbage"],
    "6312": ["lettuce"],
    "6065": ["cucumber"],
    "6267": ["spinach"],
    "6263": ["broccoli"],
    "8039": ["shiitake", "mushroom", "shiitake mushroom"],
    "6175": ["corn", "sweet corn", "sweetcorn"],
    "6223": ["garlic"],
    "6103": ["ginger"],
    "6191": ["eggplant", "aubergine"],
    "6048": ["pumpkin", "kabocha", "squash"],
    "6134": ["daikon", "radish", "daikon radish"],
    "6226": ["green onion", "spring onion", "scallion", "negi"],
    "6245": ["bell pepper", "green pepper", "capsicum"],
    "6291": ["bean sprout", "bean sprouts"],
    "6317": ["lotus root"],
    # --- 果物 ---
    "7148": ["apple", "apples"],
    "7107": ["banana", "bananas"],
    "7027": ["mandarin orange", "mandarin", "tangerine", "satsuma", "orange"],
    "7012": ["strawberry", "strawberries"],
    "7116": ["grape", "grapes"],
    "7155": ["lemon", "lemons"],
    "7006": ["avocado"],
    "7136": ["peach", "peaches"],
    "7077": ["watermelon"],
    "7097": ["pineapple"],
    "7134": ["melon"],
    "7088": ["pear"],
    "7054": ["kiwi", "kiwifruit"],
    "7124": ["blueberry"],
    "7070": ["cherry", "cherries"],
    "7049": ["persimmon"],
    # --- 調味料・飲料・その他 ---
    "17007": ["soy sauce", "soysauce", "shoyu"],
    "17045": ["miso"],
    "3003": ["sugar"],
    "17012": ["salt"],
    "17015": ["vinegar"],
    "17042": ["mayonnaise", "mayo"],
    "17036": ["ketchup"],
    "17063": ["black pepper"],
    "16037": ["green tea", "sencha", "tea"],
    "16035": ["matcha"],
    "16045": ["coffee"],
    "16001": ["sake", "rice wine"],
    "16006": ["beer"],
    "15116": ["chocolate"],
    "3022": ["honey"],
}


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fooddb.sqlite")
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout = 5000")

    # food_number 実在チェック（タイポ検知）
    valid = {r[0] for r in conn.execute("SELECT food_number FROM foods")}
    bad = [fn for fn in CANONICAL if fn not in valid]
    if bad:
        print(f"ERROR: unknown food_number(s): {bad}", file=sys.stderr)
        conn.close()
        return 1

    pairs = [(alias, fn) for fn, names in CANONICAL.items() for alias in names]
    # alias の重複（2つの food_number に同じ英語を当てた）を検知
    seen: dict[str, str] = {}
    dup = []
    for alias, fn in pairs:
        if alias in seen and seen[alias] != fn:
            dup.append((alias, seen[alias], fn))
        seen[alias] = fn
    if dup:
        print(f"ERROR: duplicate alias mapped to multiple foods: {dup}", file=sys.stderr)
        conn.close()
        return 1

    # 非破壊: 専用テーブルを作り直すだけ。food_aliases には一切触れない。
    conn.executescript(
        """
        DROP TABLE IF EXISTS alias_canonical;
        CREATE TABLE alias_canonical (
            alias       TEXT NOT NULL,
            food_number TEXT NOT NULL,
            FOREIGN KEY (food_number) REFERENCES foods(food_number)
        );
        CREATE INDEX idx_alias_canonical_alias ON alias_canonical(alias);
        """
    )
    conn.executemany(
        "INSERT INTO alias_canonical (alias, food_number) VALUES (?, ?)", pairs
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM alias_canonical").fetchone()[0]
    conn.close()

    print(f"alias_canonical seeded: {n} aliases for {len(CANONICAL)} foods (non-destructive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
