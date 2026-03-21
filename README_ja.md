# fooddb-jp 🇯🇵🍱

**日本食品標準成分表（八訂増補2023年）を構造化SQLiteデータベース + REST API + MCPサーバーとして提供**

文部科学省（MEXT）が公開する食品成分データはExcelファイルのみです。
本プロジェクトは **2,541食品 × 353成分（440,441レコード）** を [INFOODS Tagname](https://www.fao.org/infoods/infoods/standards-guidelines/food-component-identifiers-tagnames/en/) 準拠のSQLiteデータベースに変換し、APIやAIエージェント（MCP）から検索可能にします。

> 🇺🇸 [English README](./README.md)

## クイックスタート

```bash
# 依存関係のインストール
uv sync

# REST APIの起動（Swagger UI: http://localhost:8800/docs）
uv run uvicorn api:app --port 8800

# MCPサーバーの起動（stdioモード）
uv run python mcp_server.py
```

## 🌐 公開API

セットアップ不要の公開APIを利用できます：

```bash
# 鶏むね肉を検索
curl "https://fooddb.navii.online/foods/search/鶏むね肉"

# ビタミンCランキング（上位10件）
curl "https://fooddb.navii.online/ranking/VITC?limit=10"

# 栄養計算（オートミール100g + 牛乳200g）
curl "https://fooddb.navii.online/calculate?foods=1004:100,13003:200"
```

**ベースURL:** `https://fooddb.navii.online`
**Swagger UI:** [https://fooddb.navii.online/docs](https://fooddb.navii.online/docs)

### 料金プラン

| プラン | レート制限 | 料金 |
|--------|-----------|------|
| **Free** | 100リクエスト/日 | 無料 |
| **Developer** | 10,000リクエスト/日 | $9.99/月 |
| **Pro** | 100,000リクエスト/日 | $29.99/月 |

Freeプランは APIキー不要です。上位プランは `/billing/checkout` から申し込みできます。

## データベース規模

| 項目 | 値 |
|------|-----|
| 食品数 | 2,541 |
| 成分タグ数 | 353（INFOODS準拠） |
| 成分レコード数 | 440,441 |
| テーブル数 | 11（本表 + アミノ酸×4 + 脂肪酸×3 + 炭水化物×3） |
| 日英ラベルカバー率 | 100% |
| 検索エイリアス数 | 31,504 |
| 食品名パース | 27カテゴリ + 44サブカテゴリ |
| SQLiteサイズ | 約65 MB |

## なぜ fooddb-jp？

| 特徴 | fooddb-jp | USDA FoodData Central | MEXT公式サイト |
|------|-----------|----------------------|----------------|
| 日本の食品 | ✅ 2,541品 | ❌ 米国中心 | ✅ 2,541品 |
| APIアクセス | ✅ REST + MCP | ✅ REST | ❌ Webのみ |
| INFOODSタグ | ✅ 353タグ | ❌ NDB番号 | ❌ なし |
| SQLiteダウンロード | ✅ 単一ファイル | ❌ CSVダンプ | ❌ Excelのみ |
| あいまい検索 | ✅ 4段階ハイブリッド | ✅ 基本的 | ❌ 完全一致のみ |
| AIエージェント対応 | ✅ MCPサーバー | ❌ なし | ❌ なし |
| バイリンガルラベル | ✅ 日本語 + 英語 | ✅ 英語のみ | ✅ 日本語のみ |
| 無料 & OSS | ✅ MIT | ✅ パブリックドメイン | ⚠️ APIなし |

## データソース

- **日本食品標準成分表（八訂増補2023年）**
- 発行元: 文部科学省（MEXT）
- URL: https://www.mext.go.jp/a_menu/syokuhinseibun/mext_00001.html
- 全11種のExcelファイル（本表、アミノ酸×4、脂肪酸×3、炭水化物×3）

## データ品質

自動品質チェック（6項目）：

- ✅ **負の値なし** — データセット全体で検証済み
- ✅ **質量バランス** — 水分 + たんぱく質 + 脂質 + 炭水化物 + 灰分 ≈ 100g（異常なし）
- ✅ **エネルギー整合性** — 計算値と記録値が許容範囲内
- ✅ **推定値フラグ** — レコードの18.8%が推定値としてフラグ付き（想定通り）
- ✅ **Excel照合** — 元Excelと10食品を照合（10/10 PASS）

## REST APIエンドポイント

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/` | データベース統計情報（認証不要） |
| GET | `/foods` | 食品一覧（`?q=検索語&group=コード&category=カテゴリ`） |
| GET | `/foods/{id}` | 食品詳細 + 全成分値 |
| GET | `/foods/search/{query}` | あいまい検索（4段階ハイブリッド） |
| GET | `/nutrients` | 成分定義一覧 |
| GET | `/nutrients/{tag}` | 成分詳細 |
| GET | `/ranking/{tag}` | 成分含有量ランキング |
| GET | `/calculate` | 栄養計算（`?foods=1004:100,12004:60`） |
| GET | `/groups` | 食品群一覧 |

### パフォーマンス（Mac Mini, SQLite）

| クエリ | レイテンシ | QPS |
|--------|-----------|-----|
| 食品検索（LIKE） | 431 µs | 2,322 |
| 食品詳細 + 成分（JOIN） | 86 µs | 11,600 |
| ランキング（ORDER BY） | 3.1 ms | 326 |
| 栄養計算（2食品） | 90 µs | 11,100 |

## MCPツール（AIエージェント向け）

AIエージェントから直接利用可能な5つのツール：

| ツール | 説明 | 使用例 |
|--------|------|--------|
| `search_food` | あいまい食品検索 | 「鶏むね肉」「豆腐」 |
| `get_food_nutrients` | 食品番号から成分取得 | 11220 |
| `calculate_nutrition` | 栄養計算 | "1004:100,12004:60" |
| `nutrient_ranking` | 成分ランキング | VITC（ビタミンC） |
| `list_food_groups` | 食品群一覧 | — |

## 成分識別子（INFOODS Tagname）

主要タグ：

| タグ | 日本語 | 英語 | 単位 |
|------|--------|------|------|
| ENERC_KCAL | エネルギー | Energy | kcal |
| PROT- | たんぱく質 | Protein | g |
| FAT- | 脂質 | Total fat | g |
| CHOCDF- | 炭水化物 | Carbohydrate | g |
| FIB- | 食物繊維総量 | Dietary fiber | g |
| NA | ナトリウム | Sodium | mg |
| CA | カルシウム | Calcium | mg |
| FE | 鉄 | Iron | mg |
| VITC | ビタミンC | Vitamin C | mg |
| ... | （全353タグ） | | |

> 末尾の `-` は INFOODS公式の接尾辞で「分析方法未指定」を意味します。

## プロジェクト構成

```
fooddb-jp/
├── data/
│   ├── raw/                     # ソースデータ（MEXT Excel ×11）
│   └── output/                  # 変換中間ファイル
├── scripts/
│   ├── convert_all.py           # Excel → SQLite パイプライン
│   ├── build_nutrient_master.py # 成分定義ビルダー
│   ├── build_aliases.py         # 検索エイリアス生成
│   ├── quality_check.py         # データ品質チェック（6項目）
│   └── test_food_name_parse.py  # Excel照合テスト
├── fooddb.sqlite                # SQLiteデータベース（Releasesからダウンロード）
├── api.py                       # FastAPI REST API
├── mcp_server.py                # MCPサーバー（stdio/HTTP）
└── pyproject.toml
```

## ライセンス

- **コード**: [MIT License](./LICENSE)
- **データ**: 文部科学省 政府標準利用規約 2.0（CC BY 4.0 相当）。出典: 文部科学省
