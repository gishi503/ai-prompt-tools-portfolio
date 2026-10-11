import os
import json
from datetime import datetime
from pathlib import Path

import gspread
import requests
from dotenv import load_dotenv
from google.auth.exceptions import GoogleAuthError

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
INVOICE_SHEET = "請求書"
LINE_ITEM_SHEET = "明細"
STATUS_TEXT = {"ok": "問題なし", "warning": "要確認"}

# スプレッドシートの列（項目名, 見出し）。見出しは人が読むので日本語にする
INVOICE_COLUMNS = [
    ("registered_at", "登録日時"),
    ("file", "ファイル名"),
    ("status", "チェック結果"),
    ("warnings", "要確認の内容"),
    ("issuer_name", "請求元"),
    ("issuer_registration_number", "登録番号"),
    ("recipient_name", "請求先"),
    ("invoice_number", "請求書番号"),
    ("issue_date", "請求日"),
    ("due_date", "支払期限"),
    ("subtotal", "小計（税抜）"),
    ("tax_amount", "消費税"),
    ("total_amount", "請求金額（税込）"),
    ("bank_account", "振込先"),
]
LINE_ITEM_COLUMNS = [
    ("registered_at", "登録日時"),
    ("file", "ファイル名"),
    ("issuer_name", "請求元"),
    ("invoice_number", "請求書番号"),
    ("issue_date", "請求日"),
    ("description", "品目"),
    ("quantity", "数量"),
    ("unit_price", "単価"),
    ("amount", "金額"),
    ("tax_rate", "税率（%）"),
]


class SheetsError(Exception):
    pass


# 登録処理で起こりうる例外（呼び出し側でまとめて受けて、画面やコマンドにメッセージを出す）
SHEETS_ERRORS = (SheetsError, gspread.exceptions.APIError, GoogleAuthError, requests.RequestException)


def credentials_file() -> Path | None:
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    return Path(path) if path else None


def service_account_email() -> str | None:
    """スプレッドシートの共有先に指定するメールアドレス（認証情報のJSONから読む）。"""
    path = credentials_file()
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("client_email")
    except (ValueError, AttributeError):
        return None


def open_spreadsheet(url: str) -> gspread.Spreadsheet:
    path = credentials_file()
    if not path or not path.exists():
        raise SheetsError(".env の GOOGLE_SERVICE_ACCOUNT_FILE に、サービスアカウントの鍵（JSON）のパスを設定してください")
    try:
        client = gspread.service_account(filename=path, scopes=SCOPES)
    except (ValueError, KeyError):
        raise SheetsError(f"サービスアカウントの鍵（{path.name}）を読み込めません。Google Cloudからダウンロードした JSON か確認してください")
    try:
        return client.open_by_url(url)
    except GoogleAuthError:
        raise SheetsError("サービスアカウントの認証に失敗しました。鍵が削除・無効化されていないか確認してください")
    except gspread.exceptions.NoValidUrlKeyFound:
        raise SheetsError("スプレッドシートのURLが正しくありません")
    except (gspread.exceptions.SpreadsheetNotFound, PermissionError):
        raise SheetsError(
            f"スプレッドシートを開けません。共有設定で {service_account_email() or 'サービスアカウントのメールアドレス'} を「編集者」に追加してください"
        )


def get_worksheet(spreadsheet, title: str, columns: list[tuple[str, str]]):
    """シートを取得する。なければ見出し付きで作る。見出しが違うシートには書き込まない（列がずれるため）。"""
    header = [label for _, label in columns]
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(header))
        ws.append_rows([header])
        return ws

    current = ws.row_values(1)
    if not current:
        ws.append_rows([header])
    elif current != header:
        raise SheetsError(f"シート「{title}」の1行目の見出しが想定と違います。見出しを直すか、シート名を変えてください")
    return ws


def duplicate_key(issuer_name, invoice_number, issue_date, total_amount) -> tuple:
    """同じ請求書かどうかの判定キー。請求書番号があれば「請求元＋番号」、なければ「請求元＋請求日＋金額」。"""
    if invoice_number:
        return (str(issuer_name), str(invoice_number))
    return (str(issuer_name), str(issue_date), str(total_amount))


def registered_keys(ws) -> set[tuple]:
    # 表示形式（「48,400」など）に左右されないよう、書式なしの値で読む
    rows = ws.get_all_values(value_render_option="UNFORMATTED_VALUE")
    if len(rows) <= 1:
        return set()
    col = {label: i for i, label in enumerate(rows[0])}
    labels = dict(INVOICE_COLUMNS)
    return {
        duplicate_key(*(row[col[labels[f]]] for f in ("issuer_name", "invoice_number", "issue_date", "total_amount")))
        for row in rows[1:]
    }


def to_cell(value):
    # None は空欄にする。数値はそのまま渡し、スプレッドシートで集計できるようにする
    return "" if value is None else value


def register(spreadsheet, results: list[dict], include_warnings: bool = False) -> dict:
    """読み取り結果を「請求書」「明細」シートに追記する。

    - 読み取りに失敗したものは登録しない
    - 「要確認」のものは include_warnings が True のときだけ登録する
    - すでに登録済みの請求書（duplicate_key が同じもの）は登録しない
    """
    invoice_ws = get_worksheet(spreadsheet, INVOICE_SHEET, INVOICE_COLUMNS)
    line_item_ws = get_worksheet(spreadsheet, LINE_ITEM_SHEET, LINE_ITEM_COLUMNS)
    known = registered_keys(invoice_ws)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = {"added": [], "duplicates": [], "skipped_warnings": [], "skipped_errors": []}
    invoice_values, line_item_values = [], []
    for r in results:
        if r["status"] == "error":
            report["skipped_errors"].append(r["file"])
            continue
        if r["status"] == "warning" and not include_warnings:
            report["skipped_warnings"].append(r["file"])
            continue

        inv = r["invoice"]
        key = duplicate_key(inv["issuer_name"], inv["invoice_number"], inv["issue_date"], inv["total_amount"])
        if key in known:
            report["duplicates"].append(r["file"])
            continue
        known.add(key)  # 同じ回に同じ請求書が2つあっても1つだけ登録する

        row = {
            **inv,
            "registered_at": now,
            "file": r["file"],
            "status": STATUS_TEXT[r["status"]],
            "warnings": " / ".join(r["warnings"]),
        }
        invoice_values.append([to_cell(row[f]) for f, _ in INVOICE_COLUMNS])
        for item in inv["line_items"]:
            item_row = {**row, **item}
            line_item_values.append([to_cell(item_row[f]) for f, _ in LINE_ITEM_COLUMNS])
        report["added"].append(r["file"])

    # RAW で書き込む（USER_ENTERED だと請求書番号「0012」の先頭の0が消えるなど、値が変わることがあるため）
    if invoice_values:
        invoice_ws.append_rows(invoice_values, value_input_option="RAW")
    if line_item_values:
        line_item_ws.append_rows(line_item_values, value_input_option="RAW")
    return report
