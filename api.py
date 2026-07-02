"""
fooddb-jp REST API
日本食品標準成分表（八訂増補2023）の REST API

Usage:
    uv run uvicorn api:app --port 8800
"""

from dotenv import load_dotenv
load_dotenv()  # .env ファイルから環境変数を読み込み

import sqlite3
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Billing (optional — works without Stripe keys)
try:
    from billing import router as billing_router
    HAS_BILLING = True
except Exception:
    HAS_BILLING = False
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

# ========================================
# DB接続
# ========================================

DB_PATH = Path(__file__).parent / "fooddb.sqlite"
ADMIN_KEY = os.environ.get("FOODDB_ADMIN_KEY", "fdb_admin_dev")

# レート制限（日次）
PLAN_LIMITS = {
    "free": 100,
    "developer": 10_000,
    "pro": 100_000,
    "admin": 999_999_999,
}


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_api_keys_table():
    """APIキー管理テーブルを作成（なければ）"""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'developer',
            label TEXT DEFAULT '',
            email TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            requests_today INTEGER DEFAULT 0,
            last_reset TEXT NOT NULL
        )
    """)
    db.commit()
    db.close()


def init_alias_canonical_table():
    """主要食品の英語名→正規 food_number テーブル（無ければ空で作る）。

    seed_canonical_aliases.py が中身を投入する。未投入でも検索が落ちないよう、
    起動時に空テーブルを保証しておく（その場合 canonical ブーストが効かないだけ）。
    """
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS alias_canonical (
            alias       TEXT NOT NULL,
            food_number TEXT NOT NULL
        )
        """
    )
    db.commit()
    db.close()


init_api_keys_table()
init_alias_canonical_table()


# ========================================
# 認証 & レート制限
# ========================================

def get_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Free（匿名）ティアの日次 IP レート制限。単一 uvicorn worker 前提のインメモリ。
# 日付が変わったら丸ごとリセット（メモリ肥大防止）。
_free_hits: dict[str, int] = {}
_free_hits_day: str = ""


def _client_ip(request: Request) -> str:
    # Cloudflare Tunnel 経由なので実クライアント IP は CF-Connecting-IP に入る
    # （request.client.host は 127.0.0.1 になり区別がつかない）。
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(request: Request):
    """APIキー認証 + レート制限チェック"""
    auth = request.headers.get("Authorization", "")
    api_key = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    if not api_key:
        # Also accept X-API-Key — the header documented on the success page and in
        # the curl/MCP examples. Without this, paid keys sent that way were silently
        # ignored and the caller was treated as anonymous/free.
        api_key = request.headers.get("X-API-Key", "").strip()

    db = get_db()
    today = get_today()

    if api_key:
        # APIキーで認証
        row = db.execute("SELECT * FROM api_keys WHERE key = ?", (api_key,)).fetchone()
        if not row:
            db.close()
            raise HTTPException(status_code=401, detail="Invalid API key")

        plan = row["plan"]
        requests_today = row["requests_today"]
        last_reset = row["last_reset"]

        # 日次リセット
        if last_reset != today:
            db.execute(
                "UPDATE api_keys SET requests_today = 0, last_reset = ? WHERE key = ?",
                (today, api_key),
            )
            db.commit()
            requests_today = 0

        limit = PLAN_LIMITS.get(plan, 100)
        if requests_today >= limit:
            db.close()
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit}/day for {plan} plan)",
            )

        # カウンタ更新
        db.execute(
            "UPDATE api_keys SET requests_today = requests_today + 1 WHERE key = ?",
            (api_key,),
        )
        db.commit()
        db.close()

        request.state.plan = plan
        request.state.api_key = api_key
    else:
        # Free ティア: キー不要で使える代わりに IP ベースで日次制限。
        db.close()
        global _free_hits, _free_hits_day
        if today != _free_hits_day:
            _free_hits = {}
            _free_hits_day = today
        ip = _client_ip(request)
        limit = PLAN_LIMITS["free"]
        used = _free_hits.get(ip, 0)
        if used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit}/day for the free tier). Add an API key for higher limits.",
            )
        _free_hits[ip] = used + 1
        request.state.plan = "free"
        request.state.api_key = None


# ========================================
# FastAPI App
# ========================================

app = FastAPI(
    title="fooddb-jp",
    description=(
        "日本食品標準成分表（八訂 増補2023年）の REST API\n\n"
        "文部科学省が Excel で公開している 2,541 食品 × 353 成分（440,441 レコード）を\n"
        "INFOODS Tagname 準拠で構造化した SQLite データベースを提供します。"
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Billing router (Stripe)
if HAS_BILLING:
    app.include_router(billing_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================
# 管理エンドポイント
# ========================================

def verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """マスターキー検証"""
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


@app.post("/admin/keys", dependencies=[Depends(verify_admin)])
def create_api_key(
    plan: str = Query("developer", description="Plan: developer / pro"),
    label: str = Query("", description="Key label"),
    email: str = Query("", description="User email"),
):
    """APIキーを発行する"""
    if plan not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan}")

    key = f"fdb_{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc).isoformat()
    today = get_today()

    db = get_db()
    db.execute(
        "INSERT INTO api_keys (key, plan, label, email, created_at, last_reset) VALUES (?, ?, ?, ?, ?, ?)",
        (key, plan, label, email, now, today),
    )
    db.commit()
    db.close()

    return {
        "key": key,
        "plan": plan,
        "label": label,
        "limit": PLAN_LIMITS[plan],
        "message": "Save this key — it won't be shown again in full.",
    }


@app.get("/admin/keys", dependencies=[Depends(verify_admin)])
def list_api_keys():
    """APIキー一覧（キーは末尾4文字のみ表示）"""
    db = get_db()
    rows = db.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
    db.close()

    return {
        "total": len(rows),
        "keys": [
            {
                "key_hint": f"fdb_...{r['key'][-4:]}",
                "plan": r["plan"],
                "label": r["label"],
                "email": r["email"],
                "requests_today": r["requests_today"],
                "limit": PLAN_LIMITS.get(r["plan"], 100),
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


@app.delete("/admin/keys/{key}", dependencies=[Depends(verify_admin)])
def delete_api_key(key: str):
    """APIキーを無効化する"""
    db = get_db()
    result = db.execute("DELETE FROM api_keys WHERE key = ?", (key,))
    db.commit()
    db.close()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"deleted": True, "key": key}


# ========================================
# エンドポイント
# ========================================

STATIC_DIR = Path(__file__).parent / "static"

@app.get("/")
def root(request: Request):
    """API ルート — ブラウザにはランディングページ、API クライアントには JSON を返す"""
    # Content Negotiation: ブラウザ → HTML、API クライアント → JSON
    accept = request.headers.get("accept", "")
    if "text/html" in accept and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    db = get_db()
    stats = {
        "name": "fooddb-jp",
        "version": "0.2.0",
        "source": "日本食品標準成分表（八訂）増補2023年",
        "source_url": "https://www.mext.go.jp/a_menu/syokuhinseibun/mext_00001.html",
        "foods": db.execute("SELECT COUNT(*) FROM foods").fetchone()[0],
        "nutrient_tags": db.execute("SELECT COUNT(*) FROM nutrient_defs").fetchone()[0],
        "nutrient_records": db.execute("SELECT COUNT(*) FROM food_nutrients").fetchone()[0],
        "tables": [dict(r) for r in db.execute("SELECT * FROM tables").fetchall()],
    }
    db.close()
    return stats


@app.get("/start")
def start_free():
    """無料で始めるページ — キー無しの MCP 設定と curl 例を表示する。

    Free ティアは API キー不要（IP ベース 100 req/日）で使えるため、
    FOODDB_API_KEY を含めない mcp_config.json をそのまま出す。
    メール登録で発行する専用キーは残タスク（TODO Phase 3 の signup）。
    """
    import json

    mcp_config = {
        "mcpServers": {
            "fooddb-jp": {
                "command": "uvx",
                "args": ["fooddb-jp"],
                "env": {
                    "FOODDB_API_URL": "https://fooddb.navii.online"
                },
            }
        }
    }
    mcp_json = json.dumps(mcp_config, indent=2, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>無料で始める — fooddb-jp</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Inter', -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem; }}
  .card {{ background: #1a1a2e; border-radius: 16px; padding: 2.5rem; max-width: 640px; width: 100%; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
  .badge {{ display: inline-block; background: #10b981; color: #fff; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; margin-bottom: 1.5rem; }}
  .section {{ background: #16213e; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.25rem; position: relative; }}
  .section-title {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.75rem; }}
  pre {{ font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.8rem; color: #a5b4fc; overflow-x: auto; white-space: pre; padding: 0.75rem; background: #0f172a; border-radius: 8px; }}
  .copy-btn {{ position: absolute; top: 1rem; right: 1rem; background: #334155; border: none; color: #e0e0e0; padding: 0.4rem 0.8rem; border-radius: 6px; cursor: pointer; font-size: 0.75rem; transition: background 0.2s; }}
  .copy-btn:hover {{ background: #475569; }}
  .copy-btn.copied {{ background: #10b981; }}
  .curl-example {{ font-size: 0.8rem; color: #94a3b8; }}
  .note {{ font-size: 0.85rem; color: #888; line-height: 1.6; }}
  a {{ color: #60a5fa; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="card">
  <h1>🍱 無料で始める</h1>
  <span class="badge">FREE — 100 req/日・APIキー不要</span>

  <div class="section">
    <div class="section-title">MCP Server 設定（mcp_config.json に追加）</div>
    <button class="copy-btn" onclick="copyText(document.getElementById('mcp').textContent, this)">Copy</button>
    <pre id="mcp">{mcp_json}</pre>
  </div>

  <div class="section">
    <div class="section-title">REST API で使う場合</div>
    <button class="copy-btn" onclick="copyText(document.getElementById('curl').textContent, this)">Copy</button>
    <pre id="curl" class="curl-example">curl "https://fooddb.navii.online/foods/search/rice"</pre>
  </div>

  <p class="note">
    Free ティアは API キー不要で、IP あたり <strong>100 リクエスト / 日</strong>まで使えます。<br>
    より高い上限（Developer 10,000 / Pro 100,000）は
    <a href="/#pricing">Pricing</a> から。
  </p>

  <p style="margin-top: 1.5rem; font-size: 0.85rem; color: #888;">
    <a href="/">← fooddb-jp トップに戻る</a> ・
    <a href="/docs">API ドキュメント</a>
  </p>
</div>
<script>
function copyText(text, btn) {{
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = '✓ Copied';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/foods", dependencies=[Depends(check_rate_limit)])
def list_foods(
    group: Optional[str] = Query(None, description="食品群コード (01-18)"),
    q: Optional[str] = Query(None, description="食品名検索"),
    category: Optional[str] = Query(None, description="カテゴリ (例: 魚類, 畜肉類)"),
    subcategory: Optional[str] = Query(None, description="サブカテゴリ (例: 和牛肉, 小麦粉)"),
    base_name: Optional[str] = Query(None, description="ベース食品名 (例: うし, こむぎ)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """食品一覧を返す"""
    db = get_db()
    conditions = []
    params = []

    if group:
        conditions.append("group_code = ?")
        params.append(group)
    if q:
        conditions.append("food_name LIKE ?")
        params.append(f"%{q}%")
    if category:
        conditions.append("category = ?")
        params.append(category)
    if subcategory:
        conditions.append("subcategory = ?")
        params.append(subcategory)
    if base_name:
        conditions.append("base_name = ?")
        params.append(base_name)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = db.execute(f"SELECT COUNT(*) FROM foods {where}", params).fetchone()[0]

    rows = db.execute(
        f"SELECT * FROM foods {where} ORDER BY food_number LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    db.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "foods": [dict(r) for r in rows],
    }


@app.get("/foods/{food_number}", dependencies=[Depends(check_rate_limit)])
def get_food(food_number: str, table: Optional[str] = Query(None, description="テーブルID (main, amino1, fatty1, ...)")):
    """食品の詳細と成分値を返す"""
    db = get_db()

    food = db.execute("SELECT * FROM foods WHERE food_number = ?", (food_number,)).fetchone()
    if not food:
        db.close()
        raise HTTPException(status_code=404, detail=f"Food {food_number} not found")

    # 成分値取得
    if table:
        nutrients = db.execute(
            """SELECT fn.tag, nd.label_jp, nd.label_en, nd.unit, fn.value, fn.estimated, fn.table_id
               FROM food_nutrients fn
               JOIN nutrient_defs nd ON fn.tag = nd.tag
               WHERE fn.food_number = ? AND fn.table_id = ?
               ORDER BY fn.tag""",
            (food_number, table),
        ).fetchall()
    else:
        nutrients = db.execute(
            """SELECT fn.tag, nd.label_jp, nd.label_en, nd.unit, fn.value, fn.estimated, fn.table_id
               FROM food_nutrients fn
               JOIN nutrient_defs nd ON fn.tag = nd.tag
               WHERE fn.food_number = ?
               ORDER BY fn.table_id, fn.tag""",
            (food_number,),
        ).fetchall()

    db.close()
    return {
        "food": dict(food),
        "nutrients": [dict(n) for n in nutrients],
    }


@app.get("/foods/search/{query}", dependencies=[Depends(check_rate_limit)])
def search_foods(query: str, limit: int = Query(20, ge=1, le=100)):
    """食品名であいまい検索（food_name + base_name + category + エイリアス横断）

    food_aliases には表記揺れ用の日本語別名と主要食品の英語別名（add_english_aliases.py）が
    入っており、英語クエリ（例: "egg" → 鶏卵）もここで解決される。
    並び順は「完全一致のエイリアスを持つ食品」を最優先（"egg" が "eggplant" より先に出る）。

    複数語クエリ（例: "chicken breast" / "鶏 むね"）はフレーズ全体が部分一致しない
    （データは日本語・英語別名は単語単位）。上の一致が空のときだけ、語ごとに分割して
    フォールバックする（一致した語数が多い食品を優先＝AND を上位に、OR で空振りを防ぐ）。
    単語クエリの挙動は従来どおり（フォールバックは複数語かつ0件のときのみ発火）。
    """
    db = get_db()
    q = query.strip()
    like = f"%{q}%"
    rows = db.execute(
        """SELECT f.* FROM foods f
           WHERE f.food_name LIKE :like OR f.base_name LIKE :like OR f.category LIKE :like
              OR f.food_number IN (SELECT food_number FROM food_aliases WHERE alias LIKE :like)
              OR f.food_number IN (SELECT food_number FROM alias_canonical WHERE alias LIKE :like)
           ORDER BY
              -- 1) 正規（基本形）の完全一致を最優先（"tofu" → 木綿豆腐）
              (SELECT 1 FROM alias_canonical c
                 WHERE c.food_number = f.food_number
                   AND LOWER(c.alias) = LOWER(:exact) LIMIT 1) IS NULL,
              -- 2) 次にエイリアス完全一致（"egg" を "eggplant" より先に）
              (SELECT 1 FROM food_aliases a
                 WHERE a.food_number = f.food_number
                   AND LOWER(a.alias) = LOWER(:exact) LIMIT 1) IS NULL,
              f.food_number
           LIMIT :lim""",
        {"like": like, "exact": q, "lim": limit},
    ).fetchall()

    # 複数語フォールバック: フレーズ全体が当たらなかったときだけ語分割で再検索。
    # 1文字の ASCII トークン（"vitamin c" の "c" 等）は部分一致でほぼ全件に当たる
    # ノイズなので除外。CJK の1文字（"鶏"）は意味があるので残す。
    tokens = [t for t in re.split(r"\s+", q) if t and not (len(t) == 1 and t.isascii())]
    if not rows and len(tokens) > 1:
        def _match(p: str) -> str:
            return (
                f"(f.food_name LIKE :{p} OR f.base_name LIKE :{p} OR f.category LIKE :{p}"
                f" OR f.food_number IN (SELECT food_number FROM food_aliases WHERE alias LIKE :{p})"
                f" OR f.food_number IN (SELECT food_number FROM alias_canonical WHERE alias LIKE :{p}))"
            )

        params = {"lim": limit}
        where_parts, score_parts = [], []
        for i, tok in enumerate(tokens):
            p = f"t{i}"
            params[p] = f"%{tok}%"
            where_parts.append(_match(p))
            score_parts.append(f"(CASE WHEN {_match(p)} THEN 1 ELSE 0 END)")
        sql = (
            "SELECT f.* FROM foods f WHERE "
            + " OR ".join(where_parts)
            + " ORDER BY (" + " + ".join(score_parts) + ") DESC, f.food_number LIMIT :lim"
        )
        rows = db.execute(sql, params).fetchall()

    db.close()
    return {"query": query, "total": len(rows), "foods": [dict(r) for r in rows]}


@app.get("/nutrients", dependencies=[Depends(check_rate_limit)])
def list_nutrients(table: Optional[str] = Query(None, description="テーブルID")):
    """成分定義一覧"""
    db = get_db()
    if table:
        rows = db.execute(
            "SELECT * FROM nutrient_defs WHERE table_id = ? ORDER BY tag", (table,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM nutrient_defs ORDER BY table_id, tag").fetchall()
    db.close()
    return {"total": len(rows), "nutrients": [dict(r) for r in rows]}


@app.get("/nutrients/{tag}", dependencies=[Depends(check_rate_limit)])
def get_nutrient(tag: str):
    """成分定義の詳細"""
    db = get_db()
    nd = db.execute("SELECT * FROM nutrient_defs WHERE tag = ?", (tag,)).fetchone()
    if not nd:
        db.close()
        raise HTTPException(status_code=404, detail=f"Nutrient tag '{tag}' not found")
    db.close()
    return dict(nd)


@app.get("/ranking/{tag}", dependencies=[Depends(check_rate_limit)])
def nutrient_ranking(
    tag: str,
    table: str = Query("main", description="テーブルID"),
    limit: int = Query(20, ge=1, le=100),
    order: str = Query("desc", description="asc or desc"),
):
    """特定の成分の含有量ランキング"""
    db = get_db()

    nd = db.execute("SELECT * FROM nutrient_defs WHERE tag = ?", (tag,)).fetchone()
    if not nd:
        db.close()
        raise HTTPException(status_code=404, detail=f"Nutrient tag '{tag}' not found")

    direction = "DESC" if order == "desc" else "ASC"
    rows = db.execute(
        f"""SELECT f.food_number, f.food_name, f.group_name,
                   fn.value, fn.estimated
            FROM food_nutrients fn
            JOIN foods f ON fn.food_number = f.food_number
            WHERE fn.tag = ? AND fn.table_id = ?
            ORDER BY fn.value {direction}
            LIMIT ?""",
        (tag, table, limit),
    ).fetchall()

    db.close()
    return {
        "tag": tag,
        "nutrient": dict(nd),
        "order": order,
        "ranking": [dict(r) for r in rows],
    }


@app.get("/calculate", dependencies=[Depends(check_rate_limit)])
def calculate_nutrition(
    foods: str = Query(..., description="食品番号:量(g) のカンマ区切り。例: 1004:100,10001:80"),
    table: str = Query("main", description="テーブルID"),
):
    """栄養計算 — 食品と量のリストから合計栄養素を計算"""
    db = get_db()

    # 入力パース
    items = []
    for item in foods.split(","):
        parts = item.strip().split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail=f"Invalid format: '{item}'. Use food_number:amount_g")
        try:
            items.append({"food_number": parts[0].strip(), "amount_g": float(parts[1].strip())})
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid amount: '{parts[1]}'")

    # 各食品の成分取得 & 計算
    totals = {}
    food_details = []

    for item in items:
        food = db.execute("SELECT * FROM foods WHERE food_number = ?", (item["food_number"],)).fetchone()
        if not food:
            raise HTTPException(status_code=404, detail=f"Food '{item['food_number']}' not found")

        nutrients = db.execute(
            """SELECT fn.tag, nd.label_jp, nd.unit, fn.value
               FROM food_nutrients fn
               JOIN nutrient_defs nd ON fn.tag = nd.tag
               WHERE fn.food_number = ? AND fn.table_id = ?""",
            (item["food_number"], table),
        ).fetchall()

        ratio = item["amount_g"] / 100.0
        food_item = {"food_number": item["food_number"], "food_name": food["food_name"], "amount_g": item["amount_g"]}
        food_details.append(food_item)

        for n in nutrients:
            tag = n["tag"]
            val = n["value"] * ratio
            if tag not in totals:
                totals[tag] = {"tag": tag, "label_jp": n["label_jp"], "unit": n["unit"], "value": 0.0}
            totals[tag]["value"] += val

    db.close()

    # 丸め
    for t in totals.values():
        t["value"] = round(t["value"], 2)

    return {
        "foods": food_details,
        "table": table,
        "totals": sorted(totals.values(), key=lambda x: x["tag"]),
    }


@app.get("/groups", dependencies=[Depends(check_rate_limit)])
def list_groups():
    """食品群一覧"""
    db = get_db()
    rows = db.execute(
        """SELECT group_code, group_name, COUNT(*) as food_count
           FROM foods
           GROUP BY group_code
           ORDER BY group_code"""
    ).fetchall()
    db.close()
    return {"groups": [dict(r) for r in rows]}
