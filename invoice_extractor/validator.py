import math
from collections import defaultdict

from schema import Invoice


def validate(invoice: Invoice) -> list[str]:
    """金額の整合性をルールで確かめ、問題があれば警告メッセージのリストを返す（問題なしなら空リスト）。"""
    warnings = []

    for i, item in enumerate(invoice.line_items, start=1):
        expected = round(item.quantity * item.unit_price)
        if expected != item.amount:
            warnings.append(
                f"明細{i}「{item.description}」: 数量×単価={expected:,}円ですが、金額は{item.amount:,}円です"
            )
        if item.tax_rate not in (8, 10):
            warnings.append(f"明細{i}「{item.description}」: 税率{item.tax_rate}%は想定外です（8% / 10%）")

    items_total = sum(item.amount for item in invoice.line_items)
    if items_total != invoice.subtotal:
        warnings.append(f"明細の合計={items_total:,}円ですが、小計は{invoice.subtotal:,}円です")

    # インボイス制度では、消費税は税率ごとに合計してから1回だけ端数処理する（ここでは切り捨てで計算）
    by_rate = defaultdict(int)
    for item in invoice.line_items:
        by_rate[item.tax_rate] += item.amount
    expected_tax = sum(math.floor(amount * rate / 100) for rate, amount in by_rate.items())
    if abs(expected_tax - invoice.tax_amount) > 1:  # 四捨五入・切り上げの差（1円）は許容する
        warnings.append(f"税率ごとに計算した消費税={expected_tax:,}円ですが、記載は{invoice.tax_amount:,}円です")

    if invoice.subtotal + invoice.tax_amount != invoice.total_amount:
        warnings.append(
            f"小計＋消費税={invoice.subtotal + invoice.tax_amount:,}円ですが、請求金額は{invoice.total_amount:,}円です"
        )

    if invoice.due_date and invoice.due_date < invoice.issue_date:
        warnings.append(f"支払期限（{invoice.due_date}）が請求日（{invoice.issue_date}）より前です")

    return warnings
