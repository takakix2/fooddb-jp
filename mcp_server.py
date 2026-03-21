"""
fooddb-jp MCP Server
日本食品標準成分表（八訂増補2023）を AI エージェントから直接クエリ

Architecture:
    MCP Server (thin wrapper) → REST API (billing gateway) → SQLite
    全アクセスが REST API を経由するため、認証・レート制限・課金が適用される。

Usage (stdio):
    uv run python mcp_server.py

Usage (HTTP):
    uv run python mcp_server.py --http --port 8801

Environment:
    FOODDB_API_URL  — API base URL (default: https://fooddb.navii.online)
    FOODDB_API_KEY  — API key for authentication (optional for free tier)
"""

import os
import argparse

import httpx
from mcp.server.fastmcp import FastMCP

# === Config ===
API_BASE = os.environ.get("FOODDB_API_URL", "https://fooddb.navii.online")
API_KEY = os.environ.get("FOODDB_API_KEY", "")

mcp = FastMCP(
    "fooddb-jp",
    instructions="日本食品標準成分表（八訂増補2023）— 2,541食品 × 353成分のデータベース",
)


def _headers() -> dict:
    """認証ヘッダーを生成する。"""
    h = {"User-Agent": "fooddb-mcp/1.0"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _get(path: str, params: dict | None = None) -> dict:
    """REST API に GET リクエストを送信する。"""
    with httpx.Client(base_url=API_BASE, headers=_headers(), timeout=10.0) as client:
        res = client.get(path, params=params)
        res.raise_for_status()
        return res.json()


# ============================================================
# MCP Tools — REST API の薄いラッパー
# ============================================================


@mcp.tool()
def search_food(query: str, limit: int = 10) -> str:
    """食品名であいまい検索する。例: 'オートミール', '鶏むね', '豆腐'"""
    try:
        data = _get(f"/foods/search/{query}", {"limit": limit})
    except httpx.HTTPStatusError as e:
        return f"API エラー: {e.response.status_code} — {e.response.text}"
    except Exception as e:
        return f"接続エラー: {e}"

    foods = data.get("foods", [])
    if not foods:
        return f"「{query}」に一致する食品は見つかりませんでした。"

    lines = [f"検索結果 ({len(foods)}件):"]
    for f in foods:
        parts = [f"{f['food_number']}: {f['food_name']}"]
        meta = []
        if f.get("group_name"):
            meta.append(f["group_name"])
        if f.get("category"):
            meta.append(f.get("category"))
        if f.get("subcategory"):
            meta.append(f"［{f['subcategory']}］")
        if meta:
            parts.append(f"({', '.join(meta)})")
        lines.append(" ".join(parts))
    return "\n".join(lines)


@mcp.tool()
def get_food_nutrients(food_number: str, table: str = "main") -> str:
    """食品番号から成分値を取得する。tableは 'main'(一般), 'amino1'(アミノ酸), 'fatty1'(脂肪酸) 等。"""
    try:
        data = _get(f"/foods/{food_number}", {"table": table})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"食品番号 {food_number} は見つかりませんでした。search_food で検索してください。"
        return f"API エラー: {e.response.status_code}"
    except Exception as e:
        return f"接続エラー: {e}"

    food = data.get("food", {})
    nutrients = data.get("nutrients", [])

    if not nutrients:
        return f"{food.get('food_name', food_number)}のテーブル '{table}' にデータがありません。"

    # ヘッダー構築
    cat_info = ""
    if food.get("category"):
        cat_info += f" ＜{food['category']}＞"
    if food.get("subcategory"):
        cat_info += f" ［{food['subcategory']}］"

    lines = [f"📋 {food.get('food_name', '')} ({food.get('group_name', '')}{cat_info}) — {table}"]
    for n in nutrients:
        est = " (推定)" if n.get("estimated") else ""
        lines.append(f"  {n['label_jp']}: {n['value']} {n['unit']}{est}")

    return "\n".join(lines)


@mcp.tool()
def calculate_nutrition(foods_and_amounts: str) -> str:
    """栄養計算する。入力は「食品番号:量g」のカンマ区切り。例: '1004:100,12004:60'（オートミール100g+卵60g）"""
    try:
        data = _get("/calculate", {"foods": foods_and_amounts})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return f"入力エラー: {e.response.text}"
        return f"API エラー: {e.response.status_code} — {e.response.text}"
    except Exception as e:
        return f"接続エラー: {e}"

    foods = data.get("foods", [])
    totals = data.get("totals", [])

    # 食事内容
    food_lines = [f"  {f['food_name']} {f['amount_g']}g" for f in foods]

    # 主要栄養素を優先表示
    key_tags = [
        "ENERC_KCAL", "PROT-", "FAT-", "CHOCDF-", "FIB-", "WATER",
        "NA", "K", "CA", "FE", "VITC", "THIA", "RIBF",
    ]
    totals_map = {t["tag"]: t for t in totals}

    lines = ["🍽️ 食事内容:"] + food_lines + ["", "📊 栄養素合計:"]
    for tag in key_tags:
        if tag in totals_map:
            t = totals_map[tag]
            lines.append(f"  {t['label_jp']}: {t['value']:.1f} {t['unit']}")

    return "\n".join(lines)


@mcp.tool()
def nutrient_ranking(tag: str, limit: int = 10) -> str:
    """指定した成分の含有量ランキングを取得する。tagはINFOODS識別子（例: VITC, ENERC_KCAL, FE, CA）"""
    try:
        data = _get(f"/ranking/{tag}", {"limit": limit})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return (
                f"タグ '{tag}' は見つかりませんでした。主なタグ: "
                "ENERC_KCAL(カロリー), PROT-(たんぱく質), FAT-(脂質), "
                "VITC(ビタミンC), FE(鉄), CA(カルシウム)"
            )
        return f"API エラー: {e.response.status_code}"
    except Exception as e:
        return f"接続エラー: {e}"

    nutrient = data.get("nutrient", {})
    ranking = data.get("ranking", [])

    lines = [f"🏆 {nutrient.get('label_jp', tag)}({nutrient.get('label_en', '')}) 含有量トップ{limit}:"]
    for i, r in enumerate(ranking, 1):
        lines.append(f"  {i}. {r['food_name']} ({r['group_name']}): {r['value']} {nutrient.get('unit', '')}")

    return "\n".join(lines)


@mcp.tool()
def list_food_groups() -> str:
    """食品群の一覧を取得する"""
    try:
        data = _get("/groups")
    except Exception as e:
        return f"接続エラー: {e}"

    groups = data.get("groups", [])
    lines = ["📂 食品群一覧:"]
    for g in groups:
        lines.append(f"  {g['group_code']}: {g['group_name']} ({g['food_count']}品)")
    return "\n".join(lines)


# ============================================================
# Entry Point
# ============================================================

def main():
    """uvx fooddb-jp のエントリーポイント。"""
    parser = argparse.ArgumentParser(
        description="fooddb-jp MCP Server — 日本食品標準成分表 API"
    )
    parser.add_argument("--http", action="store_true", help="HTTP transport mode")
    parser.add_argument("--port", type=int, default=8801, help="HTTP port")
    args = parser.parse_args()

    if args.http:
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
