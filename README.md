# fooddb-jp 🇯🇵🍱

**The complete Japanese Standard Tables of Food Composition (8th ed. 2023) as a structured SQLite database + REST API + MCP Server.**

Japan's Ministry of Education (MEXT) provides food composition data only as Excel files.
This project converts **2,541 foods × 353 nutrients (440,441 records)** into an [INFOODS Tagname](https://www.fao.org/infoods/infoods/standards-guidelines/food-component-identifiers-tagnames/en/)-compliant SQLite database, queryable via API or AI agents (MCP).

> 🇯🇵 [日本語 README はこちら](./README_ja.md)

## Quick Start

```bash
# Install dependencies
uv sync

# Start REST API (Swagger UI at http://localhost:8800/docs)
uv run uvicorn api:app --port 8800

# Start MCP Server (stdio mode)
uv run python mcp_server.py
```

## 🌐 Live API

A public API is available — no setup required:

```bash
# Search for chicken breast
curl "https://fooddb.navii.online/foods/search/chicken%20breast"

# Get vitamin C ranking (top 10)
curl "https://fooddb.navii.online/ranking/VITC?limit=10"

# Calculate nutrition (100g oatmeal + 200g milk)
curl "https://fooddb.navii.online/calculate?foods=1004:100,13003:200"
```

**Base URL:** `https://fooddb.navii.online`
**Swagger UI:** [https://fooddb.navii.online/docs](https://fooddb.navii.online/docs)

### Pricing

| Plan | Rate Limit | Price |
|------|-----------|-------|
| **Free** | 100 req/day | $0 |
| **Developer** | 10,000 req/day | $9.99/mo |
| **Pro** | 100,000 req/day | $29.99/mo |

Free tier requires no API key. For higher limits, visit `/billing/checkout`.

## Database Scale

| Metric | Value |
|--------|-------|
| Foods | 2,541 |
| Nutrient tags | 353 (INFOODS-compliant) |
| Nutrient records | 440,441 |
| Tables | 11 (Main + Amino acids ×4 + Fatty acids ×3 + Carbohydrates ×3) |
| JP/EN label coverage | 100% |
| Search aliases | 31,504 |
| Food name parsing | 27 categories + 44 subcategories |
| SQLite size | ~65 MB |

## Why fooddb-jp?

| Feature | fooddb-jp | USDA FoodData Central | MEXT Official Site |
|---------|-----------|----------------------|-------------------|
| Japanese foods | ✅ 2,541 | ❌ US-centric | ✅ 2,541 |
| API access | ✅ REST + MCP | ✅ REST | ❌ Web only |
| INFOODS tags | ✅ 353 tags | ❌ NDB numbers | ❌ None |
| SQLite download | ✅ Single file | ❌ CSV dumps | ❌ Excel only |
| Fuzzy search | ✅ 4-stage hybrid | ✅ Basic | ❌ Exact match |
| AI agent support | ✅ MCP Server | ❌ None | ❌ None |
| Bilingual labels | ✅ JP + EN | ✅ EN only | ✅ JP only |
| Free & OSS | ✅ MIT | ✅ Public domain | ⚠️ No API |

## Data Source

- **Standard Tables of Food Composition in Japan (8th Revised Edition, Supplementary 2023)**
- Published by: Ministry of Education, Culture, Sports, Science and Technology (MEXT)
- URL: https://www.mext.go.jp/a_menu/syokuhinseibun/mext_00001.html
- All 11 Excel files (Main table, Amino acids ×4, Fatty acids ×3, Carbohydrates ×3)

## Data Quality

Automated quality checks (6 validations):

- ✅ **No negative values** in the entire dataset
- ✅ **Mass balance** (Water + Protein + Fat + Carbs + Ash ≈ 100g) — no anomalies
- ✅ **Energy consistency** — calculated vs. recorded values within tolerance
- ✅ **Estimated value flags** — 18.8% of records flagged as estimated (expected)
- ✅ **Excel cross-check** — 10 foods verified against original Excel (10/10 PASS)

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Database stats (no auth) |
| GET | `/foods` | List foods (`?q=query&group=code&category=cat`) |
| GET | `/foods/{id}` | Food detail + all nutrient values |
| GET | `/foods/search/{query}` | Fuzzy search (4-stage hybrid) |
| GET | `/nutrients` | Nutrient definitions |
| GET | `/nutrients/{tag}` | Nutrient detail |
| GET | `/ranking/{tag}` | Nutrient content ranking |
| GET | `/calculate` | Nutrition calculator (`?foods=1004:100,12004:60`) |
| GET | `/groups` | Food group list |

### Performance (Mac Mini, SQLite)

| Query | Latency | QPS |
|-------|---------|-----|
| Food search (LIKE) | 431 µs | 2,322 |
| Food detail + nutrients (JOIN) | 86 µs | 11,600 |
| Ranking (ORDER BY) | 3.1 ms | 326 |
| Nutrition calculation (2 foods) | 90 µs | 11,100 |

## MCP Tools (for AI Agents)

5 tools for direct AI agent integration:

| Tool | Description | Example |
|------|-------------|---------|
| `search_food` | Fuzzy food search | "chicken breast", "豆腐" |
| `get_food_nutrients` | Get nutrients by food number | 11220 |
| `calculate_nutrition` | Calculate nutrition | "1004:100,12004:60" |
| `nutrient_ranking` | Nutrient ranking | VITC (Vitamin C) |
| `list_food_groups` | List food groups | — |

## Nutrient Identifiers (INFOODS Tagnames)

Key tags:

| Tag | Japanese | English | Unit |
|-----|----------|---------|------|
| ENERC_KCAL | エネルギー | Energy | kcal |
| PROT- | たんぱく質 | Protein | g |
| FAT- | 脂質 | Total fat | g |
| CHOCDF- | 炭水化物 | Carbohydrate | g |
| FIB- | 食物繊維総量 | Dietary fiber | g |
| NA | ナトリウム | Sodium | mg |
| CA | カルシウム | Calcium | mg |
| FE | 鉄 | Iron | mg |
| VITC | ビタミンC | Vitamin C | mg |
| ... | (353 total) | | |

> The trailing `-` is an official INFOODS suffix meaning "analytical method unspecified".

## Project Structure

```
fooddb-jp/
├── data/
│   ├── raw/                     # Source data (MEXT Excel ×11)
│   └── output/                  # Converted intermediate files
├── scripts/
│   ├── convert_all.py           # Excel → SQLite pipeline
│   ├── build_nutrient_master.py # Nutrient definition builder
│   ├── build_aliases.py         # Search alias generator
│   ├── quality_check.py         # Data quality validation (6 checks)
│   └── test_food_name_parse.py  # Excel cross-validation test
├── fooddb.sqlite                # SQLite database (download from Releases)
├── api.py                       # FastAPI REST API
├── mcp_server.py                # MCP Server (stdio/HTTP)
└── pyproject.toml
```

## License

- **Code**: [MIT License](./LICENSE)
- **Data**: MEXT Government Standard Terms of Use 2.0 (equivalent to CC BY 4.0). Attribution: Ministry of Education, Culture, Sports, Science and Technology (MEXT), Japan.
