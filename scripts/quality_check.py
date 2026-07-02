#!/usr/bin/env python3
"""
fooddb-jp 値の品質チェックスクリプト

Phase 1: データ品質強化
- 負の値チェック
- 質量バランスチェック（100g あたり）
- エネルギー整合性チェック
- エネルギー0 でマクロ栄養素あり
- 推定値フラグの統計
- 極端な外れ値検出

Usage:
    uv run python scripts/quality_check.py
    uv run python scripts/quality_check.py --verbose
    uv run python scripts/quality_check.py --fix  # 将来的に自動修正
"""

import sqlite3
import sys
from pathlib import Path
from dataclasses import dataclass, field

DB_PATH = Path(__file__).resolve().parent.parent / "fooddb.sqlite"

# ── 主要タグ定義 ────────────────────────────────────────
# 質量バランス: 水分 + たんぱく質 + 脂質 + 炭水化物 + 灰分 ≒ 100g
MASS_TAGS = {
    "WATER": "水分",
    "PROT-": "たんぱく質",
    "FAT-": "脂質",
    "CHOCDF-": "炭水化物",  # 差引き法（質量バランス用はこちら）
    "ASH": "灰分",
}

# エネルギー計算: ENERC_KCAL ≈ PROT×4 + FAT×9 + CARB×4
ENERGY_TAG = "ENERC_KCAL"
MACRO_TAGS = {
    "PROT-": 4.0,   # kcal/g
    "FAT-": 9.0,
    "CHOAVLDF-": 4.0,  # 差引き法による利用可能炭水化物
}


@dataclass
class QualityIssue:
    """品質問題を表す"""
    food_number: str
    food_name: str
    check_name: str
    severity: str  # "ERROR", "WARNING", "INFO"
    message: str


@dataclass
class QualityReport:
    """品質チェックレポート"""
    total_foods: int = 0
    total_records: int = 0
    estimated_count: int = 0
    issues: list = field(default_factory=list)

    def add(self, issue: QualityIssue):
        self.issues.append(issue)

    def summary(self) -> dict:
        errors = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        infos = [i for i in self.issues if i.severity == "INFO"]
        return {
            "total_issues": len(self.issues),
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
        }


def get_food_values(conn: sqlite3.Connection, food_number: str,
                    tags: list[str], table_id: str = "main") -> dict[str, float | None]:
    """指定食品の成分値を取得"""
    placeholders = ",".join("?" * len(tags))
    rows = conn.execute(f"""
        SELECT tag, value FROM food_nutrients
        WHERE food_number = ? AND table_id = ? AND tag IN ({placeholders})
    """, [food_number, table_id] + tags).fetchall()
    result = {tag: None for tag in tags}
    for tag, value in rows:
        result[tag] = value
    return result


def check_negative_values(conn: sqlite3.Connection, report: QualityReport):
    """チェック1: 負の値"""
    print("  [1/6] 負の値チェック...")
    rows = conn.execute("""
        SELECT fn.food_number, f.food_name, fn.tag, nd.label_jp, fn.value, fn.table_id
        FROM food_nutrients fn
        JOIN foods f ON fn.food_number = f.food_number
        JOIN nutrient_defs nd ON fn.tag = nd.tag AND fn.table_id = nd.table_id
        WHERE fn.value < 0
        ORDER BY fn.food_number
    """).fetchall()
    for food_no, name, tag, label, value, table_id in rows:
        report.add(QualityIssue(
            food_number=food_no, food_name=name,
            check_name="negative_value",
            severity="ERROR",
            message=f"{label}({tag}) = {value} {table_id}"
        ))
    print(f"       → {len(rows)} 件検出")


def check_mass_balance(conn: sqlite3.Connection, report: QualityReport):
    """チェック2: 質量バランス（水分+たんぱく質+脂質+炭水化物+灰分 ≒ 100g）"""
    print("  [2/6] 質量バランスチェック...")
    TOLERANCE = 5.0  # ±5g の許容範囲
    tags = list(MASS_TAGS.keys())

    foods = conn.execute("SELECT food_number, food_name FROM foods").fetchall()
    count = 0
    for food_no, name in foods:
        vals = get_food_values(conn, food_no, tags)
        # 全タグ揃っていない場合はスキップ
        if any(v is None for v in vals.values()):
            continue
        # 廃棄部分を考慮して可食部100g換算
        total = sum(v for v in vals.values() if v is not None)
        if abs(total - 100.0) > TOLERANCE:
            severity = "ERROR" if abs(total - 100.0) > 10.0 else "WARNING"
            breakdown = ", ".join(f"{MASS_TAGS[t]}={vals[t]:.1f}" for t in tags)
            report.add(QualityIssue(
                food_number=food_no, food_name=name,
                check_name="mass_balance",
                severity=severity,
                message=f"合計={total:.1f}g (差={total-100:.1f}g) [{breakdown}]"
            ))
            count += 1
    print(f"       → {count} 件検出")


def check_energy_consistency(conn: sqlite3.Connection, report: QualityReport):
    """チェック3: エネルギー整合性（ENERC_KCAL ≈ P×4 + F×9 + C×4）"""
    print("  [3/6] エネルギー整合性チェック...")
    TOLERANCE_PCT = 0.20  # ±20%
    all_tags = [ENERGY_TAG] + list(MACRO_TAGS.keys())

    foods = conn.execute("SELECT food_number, food_name FROM foods").fetchall()
    count = 0
    for food_no, name in foods:
        vals = get_food_values(conn, food_no, all_tags)
        if any(v is None for v in vals.values()):
            continue
        kcal_actual = vals[ENERGY_TAG]
        if kcal_actual == 0:
            continue  # 別チェックで扱う
        kcal_calc = sum(vals[tag] * factor for tag, factor in MACRO_TAGS.items())
        if kcal_calc == 0:
            continue
        ratio = abs(kcal_actual - kcal_calc) / kcal_calc
        if ratio > TOLERANCE_PCT:
            severity = "ERROR" if ratio > 0.5 else "WARNING"
            report.add(QualityIssue(
                food_number=food_no, food_name=name,
                check_name="energy_consistency",
                severity=severity,
                message=f"DB={kcal_actual:.0f}kcal vs 計算={kcal_calc:.0f}kcal (差={ratio*100:.0f}%)"
            ))
            count += 1
    print(f"       → {count} 件検出")


def check_zero_energy_with_macros(conn: sqlite3.Connection, report: QualityReport):
    """チェック4: エネルギー0なのにマクロ栄養素がある"""
    print("  [4/6] エネルギー0 + マクロ栄養素チェック...")
    rows = conn.execute("""
        SELECT f.food_number, f.food_name,
               MAX(CASE WHEN fn.tag = 'ENERC_KCAL' THEN fn.value END) as kcal,
               MAX(CASE WHEN fn.tag = 'PROT-' THEN fn.value END) as protein,
               MAX(CASE WHEN fn.tag = 'FAT-' THEN fn.value END) as fat,
               MAX(CASE WHEN fn.tag = 'CHOCDF-' THEN fn.value END) as carb
        FROM foods f
        JOIN food_nutrients fn ON f.food_number = fn.food_number
        WHERE fn.table_id = 'main'
          AND fn.tag IN ('ENERC_KCAL', 'PROT-', 'FAT-', 'CHOCDF-')
        GROUP BY f.food_number
        HAVING kcal = 0 AND (protein > 0 OR fat > 0 OR carb > 0)
    """).fetchall()
    for food_no, name, kcal, prot, fat, carb in rows:
        report.add(QualityIssue(
            food_number=food_no, food_name=name,
            check_name="zero_energy_with_macros",
            severity="ERROR",
            message=f"エネルギー=0kcal だが P={prot}g, F={fat}g, C={carb}g"
        ))
    print(f"       → {len(rows)} 件検出")


def check_estimated_stats(conn: sqlite3.Connection, report: QualityReport):
    """チェック5: 推定値フラグの統計"""
    print("  [5/6] 推定値フラグ統計...")
    rows = conn.execute("""
        SELECT fn.table_id,
               COUNT(*) as total,
               SUM(fn.estimated) as est_count,
               ROUND(100.0 * SUM(fn.estimated) / COUNT(*), 1) as est_pct
        FROM food_nutrients fn
        GROUP BY fn.table_id
        ORDER BY fn.table_id
    """).fetchall()
    print(f"       {'テーブル':<20} {'総件数':>8} {'推定値':>8} {'割合':>8}")
    print(f"       {'─'*20} {'─'*8} {'─'*8} {'─'*8}")
    for table_id, total, est, pct in rows:
        print(f"       {table_id:<20} {total:>8,} {est:>8,} {pct:>7.1f}%")
        if pct > 50:
            report.add(QualityIssue(
                food_number="-", food_name=f"テーブル:{table_id}",
                check_name="high_estimated_ratio",
                severity="INFO",
                message=f"推定値が {pct:.1f}% ({est:,}/{total:,})"
            ))


def check_outliers(conn: sqlite3.Connection, report: QualityReport):
    """チェック6: 極端な外れ値（主要成分で mean ± 5σ 超え）"""
    print("  [6/6] 外れ値チェック...")
    CHECK_TAGS = [
        ("ENERC_KCAL", "エネルギー(kcal)"),
        ("PROT-", "たんぱく質(g)"),
        ("FAT-", "脂質(g)"),
        ("WATER", "水分(g)"),
    ]
    count = 0
    for tag, label in CHECK_TAGS:
        row = conn.execute("""
            SELECT AVG(value), AVG(value*value) FROM food_nutrients
            WHERE tag = ? AND table_id = 'main'
        """, (tag,)).fetchone()
        if not row or row[0] is None:
            continue
        mean = row[0]
        # stddev = sqrt(E[X²] - E[X]²)
        variance = row[1] - mean * mean
        stddev = variance ** 0.5 if variance > 0 else 0.0
        if stddev == 0:
            continue
        threshold = mean + 5 * stddev
        outliers = conn.execute("""
            SELECT fn.food_number, f.food_name, fn.value
            FROM food_nutrients fn
            JOIN foods f ON fn.food_number = f.food_number
            WHERE fn.tag = ? AND fn.table_id = 'main' AND fn.value > ?
            ORDER BY fn.value DESC
        """, (tag, threshold)).fetchall()
        for food_no, name, value in outliers:
            report.add(QualityIssue(
                food_number=food_no, food_name=name,
                check_name="outlier",
                severity="WARNING",
                message=f"{label}={value:.1f} (mean={mean:.1f}, 5σ={threshold:.1f})"
            ))
            count += 1
    print(f"       → {count} 件検出")


def main():
    verbose = "--verbose" in sys.argv

    print(f"🔍 fooddb-jp 品質チェック")
    print(f"   DB: {DB_PATH}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    report = QualityReport()

    # 基本統計
    report.total_foods = conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
    report.total_records = conn.execute("SELECT COUNT(*) FROM food_nutrients").fetchone()[0]
    report.estimated_count = conn.execute(
        "SELECT COUNT(*) FROM food_nutrients WHERE estimated = 1"
    ).fetchone()[0]

    print(f"📊 基本統計:")
    print(f"   食品数:     {report.total_foods:,}")
    print(f"   レコード数: {report.total_records:,}")
    print(f"   推定値:     {report.estimated_count:,} ({100*report.estimated_count/report.total_records:.1f}%)")
    print()

    # 各チェック実行
    print("🔎 品質チェック実行中...")
    check_negative_values(conn, report)
    check_mass_balance(conn, report)
    check_energy_consistency(conn, report)
    check_zero_energy_with_macros(conn, report)
    check_estimated_stats(conn, report)
    check_outliers(conn, report)

    conn.close()

    # レポート出力
    print()
    s = report.summary()
    print("=" * 60)
    print(f"📋 品質チェックレポート")
    print(f"   🔴 ERROR:   {s['errors']}")
    print(f"   🟡 WARNING: {s['warnings']}")
    print(f"   🔵 INFO:    {s['infos']}")
    print(f"   合計:       {s['total_issues']}")
    print("=" * 60)

    if verbose or s['errors'] > 0:
        # ERROR と WARNING を表示
        errors = [i for i in report.issues if i.severity in ("ERROR", "WARNING")]
        if errors:
            print()
            print("📌 検出された問題:")
            print()
            current_check = None
            for issue in sorted(errors, key=lambda i: (i.check_name, i.severity)):
                if issue.check_name != current_check:
                    current_check = issue.check_name
                    print(f"  ── {current_check} ──")
                icon = "🔴" if issue.severity == "ERROR" else "🟡"
                name_display = issue.food_name[:20]
                print(f"  {icon} [{issue.food_number}] {name_display:<22} {issue.message}")

    # 終了コード
    if s['errors'] > 0:
        print(f"\n❌ {s['errors']} 件のエラーが検出されました")
        return 1
    else:
        print(f"\n✅ 重大なエラーなし")
        return 0


if __name__ == "__main__":
    sys.exit(main())
