"""動作確認用の架空の請求書PDFを samples/ に生成する。会社名・口座などはすべて架空。"""
import math
from collections import defaultdict
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

FONT = "HeiseiKakuGo-W5"  # reportlab標準の日本語フォント（追加のインストール不要）
pdfmetrics.registerFont(UnicodeCIDFont(FONT))

OUT_DIR = Path(__file__).parent / "samples"

SAMPLES = [
    {
        "file": "invoice_01_web.pdf",
        "issuer": "株式会社サンプルデザイン",
        "registration": "T1234567890123",
        "recipient": "架空商事株式会社",
        "number": "INV-2026-0101",
        "issue_date": "2026年9月30日",
        "due_date": "2026年10月31日",
        "items": [("Webサイト改修（トップページ）", 1, 150000, 10), ("保守サポート（9月分）", 1, 30000, 10)],
        "bank": "架空銀行 本店営業部 普通 1234567 カ）サンプルデザイン",
    },
    {
        "file": "invoice_02_mixed_tax.pdf",
        "issuer": "ダミー食品株式会社",
        "registration": "T9876543210987",
        "recipient": "架空商事株式会社",
        "number": "No.20261002-07",
        "issue_date": "令和8年10月2日",
        "due_date": "令和8年11月30日",
        "items": [("会議用弁当", 25, 980, 8), ("お茶（500ml）", 25, 150, 8), ("配送料", 1, 3000, 10)],
        "bank": "テスト信用金庫 中央支店 当座 7654321 ダミー食品（カ",
    },
    {
        # わざと合計を間違えた請求書（整合性チェックで警告が出ることを確認する用）
        "file": "invoice_03_total_mismatch.pdf",
        "issuer": "合同会社テストラボ",
        "registration": None,
        "recipient": "架空商事株式会社",
        "number": None,
        "issue_date": "2026/10/01",
        "due_date": None,
        "items": [("データ入力作業", 120, 300, 10), ("CSV整形", 1, 8000, 10)],
        "bank": None,
        "total_override": 52000,
    },
]


def yen(n: int) -> str:
    return f"¥{n:,}"


def draw_invoice(sample: dict, path: Path):
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    left = 20 * mm
    y = height - 25 * mm

    c.setFont(FONT, 20)
    c.drawCentredString(width / 2, y, "請 求 書")

    y -= 15 * mm
    c.setFont(FONT, 12)
    c.drawString(left, y, f"{sample['recipient']} 御中")

    c.setFont(FONT, 9)
    right_x = width - 20 * mm
    meta = [f"請求日：{sample['issue_date']}"]
    if sample["number"]:
        meta.insert(0, f"請求書番号：{sample['number']}")
    for i, line in enumerate(meta):
        c.drawRightString(right_x, y + (len(meta) - 1 - i) * 5 * mm, line)

    y -= 12 * mm
    c.drawRightString(right_x, y, sample["issuer"])
    if sample["registration"]:
        c.drawRightString(right_x, y - 5 * mm, f"登録番号：{sample['registration']}")

    subtotal = sum(round(q * p) for _, q, p, _ in sample["items"])
    by_rate = defaultdict(int)
    for _, q, p, rate in sample["items"]:
        by_rate[rate] += round(q * p)
    tax = sum(math.floor(amount * rate / 100) for rate, amount in by_rate.items())
    total = sample.get("total_override", subtotal + tax)

    y -= 15 * mm
    c.setFont(FONT, 11)
    c.drawString(left, y, "下記のとおりご請求申し上げます。")
    y -= 10 * mm
    c.setFont(FONT, 14)
    c.drawString(left, y, f"ご請求金額　{yen(total)}（税込）")
    if sample["due_date"]:
        c.setFont(FONT, 10)
        c.drawString(left, y - 7 * mm, f"お支払期限：{sample['due_date']}")

    # 明細
    y -= 20 * mm
    cols = [left, left + 85 * mm, left + 105 * mm, left + 135 * mm, left + 165 * mm]
    c.setFont(FONT, 9)
    for x, label in zip(cols, ["品目", "数量", "単価", "金額", "税率"]):
        c.drawString(x, y, label)
    c.line(left, y - 2 * mm, right_x, y - 2 * mm)
    for name, q, p, rate in sample["items"]:
        y -= 7 * mm
        c.drawString(cols[0], y, name + ("　※" if rate == 8 else ""))
        c.drawString(cols[1], y, f"{q:g}")
        c.drawString(cols[2], y, yen(p))
        c.drawString(cols[3], y, yen(round(q * p)))
        c.drawString(cols[4], y, f"{rate}%")
    c.line(left, y - 3 * mm, right_x, y - 3 * mm)

    y -= 10 * mm
    rows = [("小計", subtotal)]
    for rate in sorted(by_rate, reverse=True):
        rows.append((f"消費税（{rate}%対象 {yen(by_rate[rate])}）", math.floor(by_rate[rate] * rate / 100)))
    rows.append(("合計", total))
    for label, amount in rows:
        c.drawString(cols[2], y, label)
        c.drawRightString(right_x, y, yen(amount))
        y -= 6 * mm
    if 8 in by_rate:
        c.drawString(left, y, "※は軽減税率（8%）対象")
        y -= 6 * mm

    if sample["bank"]:
        y -= 6 * mm
        c.drawString(left, y, f"お振込先：{sample['bank']}")

    c.showPage()
    c.save()


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for sample in SAMPLES:
        path = OUT_DIR / sample["file"]
        draw_invoice(sample, path)
        print(f"[done] {path}")


if __name__ == "__main__":
    main()
