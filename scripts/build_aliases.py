"""
build_aliases.py — 食品名の検索エイリアス一括生成

正式名称「＜鳥肉類＞　にわとり　［若どり・主品目］　むね　皮なし　生」から
「鶏むね」「チキン胸」「chicken breast」等の検索ワードを生成。

出力: food_aliases テーブルを SQLite に追加
"""

import sqlite3
import re
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "fooddb.sqlite"

# ========================================
# 読み → 漢字/カタカナ マッピング
# ========================================

KANA_KANJI_MAP = {
    # 肉類
    "にわとり": ["鶏", "鳥", "チキン", "とり", "トリ", "chicken"],
    "ぶた": ["豚", "ブタ", "ポーク", "pork"],
    "うし": ["牛", "ウシ", "ビーフ", "beef"],
    "ひつじ": ["羊", "ラム", "マトン", "lamb", "mutton"],
    "しか": ["鹿", "シカ", "venison"],
    "うま": ["馬", "ウマ"],
    "くじら": ["鯨", "クジラ", "whale"],
    "あひる": ["家鴨", "アヒル", "duck"],
    "かも": ["鴨", "カモ", "duck"],
    "うずら": ["鶉", "ウズラ", "quail"],

    # 魚介類
    "さけ": ["鮭", "サケ", "シャケ", "salmon"],
    "ます": ["鱒", "マス", "trout"],
    "まぐろ": ["鮪", "マグロ", "tuna"],
    "かつお": ["鰹", "カツオ", "bonito"],
    "さば": ["鯖", "サバ", "mackerel"],
    "いわし": ["鰯", "イワシ", "sardine"],
    "あじ": ["鯵", "アジ", "horse mackerel"],
    "さんま": ["秋刀魚", "サンマ", "pacific saury"],
    "ぶり": ["鰤", "ブリ", "yellowtail"],
    "たい": ["鯛", "タイ", "sea bream", "red snapper"],
    "たら": ["鱈", "タラ", "cod"],
    "さわら": ["鰆", "サワラ"],
    "うなぎ": ["鰻", "ウナギ", "eel"],
    "あなご": ["穴子", "アナゴ", "conger eel"],
    "いか": ["烏賊", "イカ", "squid"],
    "たこ": ["蛸", "タコ", "octopus"],
    "えび": ["海老", "エビ", "shrimp", "prawn"],
    "かに": ["蟹", "カニ", "crab"],
    "かき": ["牡蠣", "カキ", "oyster"],
    "あさり": ["浅蜊", "アサリ", "clam"],
    "しじみ": ["蜆", "シジミ"],
    "はまぐり": ["蛤", "ハマグリ"],
    "ほたて": ["帆立", "ホタテ", "scallop"],

    # 野菜
    "だいこん": ["大根", "ダイコン", "radish"],
    "にんじん": ["人参", "ニンジン", "carrot"],
    "たまねぎ": ["玉ねぎ", "玉葱", "タマネギ", "onion"],
    "じゃがいも": ["ジャガイモ", "じゃが芋", "potato"],
    "さつまいも": ["サツマイモ", "薩摩芋", "sweet potato"],
    "ほうれんそう": ["ほうれん草", "ホウレンソウ", "spinach"],
    "きゅうり": ["胡瓜", "キュウリ", "cucumber"],
    "なす": ["茄子", "ナス", "eggplant"],
    "トマト": ["とまと", "tomato"],
    "キャベツ": ["きゃべつ", "cabbage"],
    "レタス": ["れたす", "lettuce"],
    "ブロッコリー": ["ぶろっこりー", "broccoli"],
    "かぼちゃ": ["南瓜", "カボチャ", "pumpkin"],
    "ピーマン": ["ぴーまん", "bell pepper"],
    "ごぼう": ["牛蒡", "ゴボウ", "burdock"],
    "れんこん": ["蓮根", "レンコン", "lotus root"],
    "ねぎ": ["葱", "ネギ", "green onion", "leek"],
    "にら": ["韮", "ニラ", "chives"],
    "しょうが": ["生姜", "ショウガ", "ginger"],
    "にんにく": ["大蒜", "ニンニク", "garlic"],
    "もやし": ["モヤシ", "bean sprouts"],
    "たけのこ": ["筍", "タケノコ", "bamboo shoot"],
    "しいたけ": ["椎茸", "シイタケ", "shiitake"],
    "えのき": ["エノキ", "enoki"],
    "まいたけ": ["舞茸", "マイタケ", "maitake"],
    "しめじ": ["シメジ", "shimeji"],

    # 豆・穀物
    "だいず": ["大豆", "ダイズ", "soybean"],
    "あずき": ["小豆", "アズキ", "azuki bean"],
    "とうふ": ["豆腐", "トウフ", "tofu"],
    "なっとう": ["納豆", "ナットウ", "natto"],
    "こめ": ["米", "コメ", "rice"],
    "はくまい": ["白米"],
    "げんまい": ["玄米"],
    "こむぎ": ["小麦", "コムギ", "wheat"],
    "そば": ["蕎麦", "ソバ", "buckwheat"],
    "えんばく": ["燕麦", "オーツ", "oat"],
    "オートミール": ["おーとみーる", "oatmeal"],

    # 果物
    "りんご": ["林檎", "リンゴ", "apple"],
    "みかん": ["蜜柑", "ミカン", "mandarin"],
    "バナナ": ["ばなな", "banana"],
    "いちご": ["苺", "イチゴ", "strawberry"],
    "ぶどう": ["葡萄", "ブドウ", "grape"],
    "もも": ["桃", "モモ", "peach"],
    "なし": ["梨", "ナシ", "pear"],
    "かき": ["柿", "カキ"],
    "すいか": ["西瓜", "スイカ", "watermelon"],
    "メロン": ["めろん", "melon"],
    "キウイ": ["きうい", "kiwi"],
    "レモン": ["れもん", "lemon"],
    "グレープフルーツ": ["grapefruit"],
    "パイナップル": ["ぱいなっぷる", "pineapple"],
    "マンゴー": ["まんごー", "mango"],
    "アボカド": ["あぼかど", "avocado"],

    # 乳製品
    "ぎゅうにゅう": ["牛乳", "ミルク", "milk"],
    "チーズ": ["ちーず", "cheese"],
    "バター": ["ばたー", "butter"],
    "ヨーグルト": ["よーぐると", "yogurt"],

    # その他
    "たまご": ["卵", "タマゴ", "egg"],
    "鶏卵": ["けいらん", "たまご", "卵", "egg"],
    "しお": ["塩", "salt"],
    "さとう": ["砂糖", "シュガー", "sugar"],
    "しょうゆ": ["醤油", "ショウユ", "soy sauce"],
    "みそ": ["味噌", "ミソ", "miso"],
    "す": ["酢", "vinegar"],

    # 部位
    "むね": ["胸", "ムネ", "breast"],
    "もも": ["腿", "モモ", "thigh", "leg"],
    "ささみ": ["ササミ", "tenderloin"],
    "ひき肉": ["挽肉", "ミンチ", "ground meat"],
    "ロース": ["ろーす", "loin"],
    "かた": ["肩", "カタ", "shoulder"],
    "ばら": ["バラ", "belly"],
    "レバー": ["ればー", "肝臓", "liver"],
    "ハツ": ["はつ", "心臓", "heart"],
    "タン": ["たん", "舌", "tongue"],
}

# 調理法のエイリアス
COOKING_ALIASES = {
    "生": ["なま", "raw", "生の"],
    "焼き": ["やき", "焼いた", "グリル", "grilled", "roasted"],
    "ゆで": ["茹で", "ボイル", "boiled"],
    "蒸し": ["むし", "スチーム", "steamed"],
    "揚げ": ["あげ", "フライ", "fried", "deep fried"],
    "水煮": ["みずに", "煮た"],
    "干し": ["ほし", "乾燥", "dried"],
    "缶詰": ["かんづめ", "缶", "canned"],
}


def parse_food_name(name: str) -> dict:
    """正式名称をパースして構成要素を抽出"""
    result = {
        "original": name,
        "category": "",     # ＜＞
        "subcategory": "",  # （）
        "subgroup": "",     # ［］
        "base_name": "",
        "cooking": "",
    }

    # カテゴリ抽出
    m = re.search(r'＜(.+?)＞', name)
    if m:
        result["category"] = m.group(1)
        name = name.replace(m.group(0), "")

    # サブカテゴリ
    m = re.search(r'（(.+?)）', name)
    if m:
        result["subcategory"] = m.group(1)
        name = name.replace(m.group(0), "")

    # サブグループ
    m = re.search(r'［(.+?)］', name)
    if m:
        result["subgroup"] = m.group(1)
        name = name.replace(m.group(0), "")

    # 残りをクリーンアップ
    name = re.sub(r'[　\s]+', ' ', name).strip()
    result["base_name"] = name

    return result


def generate_aliases(food_number: str, food_name: str, group_name: str) -> list[str]:
    """食品名から検索エイリアスを生成"""
    aliases = set()

    # 1. 元の名前のクリーン版
    clean = re.sub(r'[＜＞（）［］]', '', food_name)
    clean = re.sub(r'[　\s]+', ' ', clean).strip()
    aliases.add(clean)

    # 2. パースした構成要素
    parsed = parse_food_name(food_name)
    if parsed["base_name"]:
        aliases.add(parsed["base_name"])

    # 3. 全角スペースを除去した版
    no_space = food_name.replace("　", "").replace(" ", "")
    no_space = re.sub(r'[＜＞（）［］]', '', no_space)
    aliases.add(no_space)

    # 4. キーワードマッチングでエイリアス追加
    name_lower = food_name.lower()
    for key, values in KANA_KANJI_MAP.items():
        if key in name_lower or key in food_name:
            for v in values:
                aliases.add(v)
                # 組み合わせ: 漢字+部位/調理法
                for other_key, other_values in KANA_KANJI_MAP.items():
                    if other_key != key and other_key in name_lower:
                        for ov in other_values:
                            aliases.add(f"{v}{ov}")
                            aliases.add(f"{ov}{v}")

    # 5. 食品群名
    if group_name:
        aliases.add(group_name)

    # 6. カテゴリ名のクリーン版
    if parsed["category"]:
        cat = parsed["category"].replace("類", "")
        aliases.add(cat)

    # Noneとか空文字を除去
    aliases = {a for a in aliases if a and len(a) > 1}

    return sorted(aliases)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # food_aliases テーブル作成
    cur.executescript("""
        DROP TABLE IF EXISTS food_aliases;
        CREATE TABLE food_aliases (
            food_number TEXT NOT NULL,
            alias       TEXT NOT NULL,
            FOREIGN KEY (food_number) REFERENCES foods(food_number)
        );
    """)

    # 全食品のエイリアス生成
    cur.execute("SELECT food_number, food_name, group_name FROM foods")
    foods = cur.fetchall()

    total_aliases = 0
    for food_number, food_name, group_name in foods:
        aliases = generate_aliases(food_number, food_name, group_name)
        for alias in aliases:
            cur.execute("INSERT INTO food_aliases VALUES (?, ?)", (food_number, alias))
            total_aliases += 1

    # FTS5 仮想テーブル作成
    cur.executescript("""
        DROP TABLE IF EXISTS food_search;
        CREATE VIRTUAL TABLE food_search USING fts5(
            food_number,
            food_name,
            aliases,
            content='',
            tokenize='unicode61'
        );
    """)

    # FTSにデータ投入
    cur.execute("SELECT food_number, food_name, group_name FROM foods")
    for food_number, food_name, group_name in cur.fetchall():
        aliases = generate_aliases(food_number, food_name, group_name)
        alias_text = " ".join(aliases)
        cur.execute(
            "INSERT INTO food_search (food_number, food_name, aliases) VALUES (?, ?, ?)",
            (food_number, food_name, alias_text),
        )

    # インデックス
    cur.execute("CREATE INDEX idx_aliases_food ON food_aliases(food_number)")
    cur.execute("CREATE INDEX idx_aliases_alias ON food_aliases(alias)")

    conn.commit()

    # 統計
    print(f"✅ food_aliases: {total_aliases} エイリアス（{len(foods)} 食品）")
    print(f"   平均: {total_aliases / len(foods):.1f} エイリアス/食品")

    # テスト
    test_queries = ["鶏むね", "豚ロース", "salmon", "卵", "オートミール", "牛乳", "ほうれん草"]
    print("\n=== 検索テスト ===")
    for q in test_queries:
        # FTS検索
        rows = cur.execute(
            "SELECT food_number, food_name FROM food_search WHERE food_search MATCH ? LIMIT 5",
            (q,),
        ).fetchall()
        if rows:
            print(f"\n🔍 「{q}」:")
            for r in rows:
                print(f"   {r[0]}: {r[1]}")
        else:
            # エイリアステーブルでフォールバック
            rows = cur.execute(
                """SELECT DISTINCT f.food_number, f.food_name 
                   FROM food_aliases fa 
                   JOIN foods f ON fa.food_number = f.food_number 
                   WHERE fa.alias LIKE ? LIMIT 5""",
                (f"%{q}%",),
            ).fetchall()
            if rows:
                print(f"\n🔍 「{q}」(alias):")
                for r in rows:
                    print(f"   {r[0]}: {r[1]}")
            else:
                print(f"\n❌ 「{q}」: 見つからず")

    conn.close()


if __name__ == "__main__":
    main()
