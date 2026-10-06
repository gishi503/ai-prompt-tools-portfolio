import io
import csv
import json

# results の各要素: {"file", "status", "warnings", "invoice"（dict）} または {"file", "status": "error", "error"}

INVOICE_FIELDS = ["file", "status", "warnings", "issuer_name", "issuer_registration_number", "recipient_name",
                  "invoice_number", "issue_date", "due_date", "subtotal", "tax_amount", "total_amount",
                  "bank_account", "line_items", "error"]

LINE_ITEM_FIELDS = ["file", "issuer_name", "invoice_number", "issue_date", "description", "quantity",
                    "unit_price", "amount", "tax_rate"]


def invoice_rows(results: list[dict]) -> list[dict]:
    """1請求書1行。明細はJSON文字列で1列にまとめる。"""
    rows = []
    for r in results:
        row = {"file": r["file"], "status": r["status"], "error": r.get("error", "")}
        if "invoice" in r:
            inv = r["invoice"]
            row.update({k: v for k, v in inv.items() if k != "line_items"})
            row["line_items"] = json.dumps(inv["line_items"], ensure_ascii=False)
            row["warnings"] = " / ".join(r["warnings"])
        rows.append(row)
    return rows


def line_item_rows(results: list[dict]) -> list[dict]:
    """1明細1行。スプレッドシートで集計しやすい形。"""
    rows = []
    for r in results:
        if "invoice" not in r:
            continue
        inv = r["invoice"]
        for item in inv["line_items"]:
            rows.append({
                "file": r["file"],
                "issuer_name": inv["issuer_name"],
                "invoice_number": inv["invoice_number"],
                "issue_date": inv["issue_date"],
                **item,
            })
    return rows


def to_csv_text(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def to_csv_bytes(rows: list[dict], fieldnames: list[str]) -> bytes:
    # Excelで文字化けしないようBOM付きUTF-8にする
    return to_csv_text(rows, fieldnames).encode("utf-8-sig")
