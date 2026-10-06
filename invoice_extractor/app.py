import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st
from anthropic import APIError
from pydantic import ValidationError

from extractor import extract_invoice_bytes, ExtractionError, MEDIA_TYPES
from schema import Invoice
from validator import validate
from exporter import INVOICE_FIELDS, LINE_ITEM_FIELDS, invoice_rows, line_item_rows, to_csv_bytes

st.set_page_config(page_title="請求書AI読み取り", page_icon="🧾", layout="wide")

SAMPLES_DIR = Path(__file__).parent / "samples"
STATUS_LABEL = {"ok": "✅ 問題なし", "warning": "⚠️ 要確認", "error": "❌ 読み取り失敗"}

# 項目名, 表示名, 必須かどうか
TEXT_FIELDS = [
    ("issuer_name", "請求元", True),
    ("issuer_registration_number", "登録番号", False),
    ("recipient_name", "請求先", True),
    ("invoice_number", "請求書番号", False),
    ("issue_date", "請求日（YYYY-MM-DD）", True),
    ("due_date", "支払期限（YYYY-MM-DD）", False),
    ("bank_account", "振込先", False),
]
AMOUNT_FIELDS = [("subtotal", "小計（税抜）"), ("tax_amount", "消費税"), ("total_amount", "請求金額（税込）")]

# 読み取り結果はファイルの中身のハッシュをキーにして保持する（画面の再描画のたびにAPIを呼ばないため）
if "extracted" not in st.session_state:
    st.session_state.extracted = {}


def file_key(name: str, data: bytes) -> str:
    return f"{name}-{hashlib.sha256(data).hexdigest()[:12]}"


def edit_invoice(key: str, original: dict) -> tuple[dict | None, list[str]]:
    """読み取り結果を編集できるフォームを表示し、(編集後の請求書, 警告) を返す。入力に不備があれば請求書は None。"""
    edited = {}
    col1, col2 = st.columns(2)
    for i, (field, label, required) in enumerate(TEXT_FIELDS):
        with (col1 if i % 2 == 0 else col2):
            value = st.text_input(label, value=original[field] or "", key=f"{key}-{field}").strip()
            edited[field] = value if value or required else None

    st.markdown("**明細**（セルを直接修正できます。行の追加・削除も可能です）")
    items = st.data_editor(
        pd.DataFrame(original["line_items"]),
        key=f"{key}-items",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "description": st.column_config.TextColumn("品目", required=True),
            "quantity": st.column_config.NumberColumn("数量", required=True),
            "unit_price": st.column_config.NumberColumn("単価（円）", format="%d", required=True),
            "amount": st.column_config.NumberColumn("金額（円）", format="%d", required=True),
            "tax_rate": st.column_config.SelectboxColumn("税率（%）", options=[10, 8], required=True),
        },
    )
    edited["line_items"] = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in items.to_dict("records")
    ]

    cols = st.columns(len(AMOUNT_FIELDS))
    for col, (field, label) in zip(cols, AMOUNT_FIELDS):
        with col:
            edited[field] = st.number_input(label, value=int(original[field]), step=1, key=f"{key}-{field}")

    try:
        invoice = Invoice(**edited)
    except ValidationError as e:
        problems = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
        return None, ["入力に不備があります → " + " / ".join(problems)]
    return invoice.model_dump(), validate(invoice)


st.title("🧾 請求書AI読み取り")
st.caption(
    "請求書のPDF・画像をアップロードすると、AI（Claude）が項目を読み取ります。"
    "金額の整合性をチェックしたうえで、内容を確認・修正してCSVでダウンロードできます。"
)

with st.sidebar:
    st.header("使い方")
    st.markdown(
        "1. 請求書をアップロード（複数可）\n"
        "2. 「読み取る」を押す\n"
        "3. 警告が出た項目を確認・修正\n"
        "4. CSVをダウンロード"
    )
    st.divider()
    st.markdown(
        "**チェックする内容**\n"
        "- 数量×単価＝金額\n"
        "- 明細の合計＝小計\n"
        "- 税率ごとの消費税\n"
        "- 小計＋消費税＝請求金額\n"
        "- 請求日と支払期限の前後"
    )
    st.divider()
    st.caption("AIは書類の値をそのまま読み取り、計算の誤りはプログラムのチェックで見つけます。")

uploaded = st.file_uploader(
    "請求書ファイル（PDF / PNG / JPEG / WebP）",
    type=[ext.lstrip(".") for ext in MEDIA_TYPES],
    accept_multiple_files=True,
)
use_samples = st.checkbox("サンプルの請求書（架空のデータ3枚）で試す")

inputs = [(f.name, f.getvalue()) for f in uploaded or []]
if use_samples:
    inputs += [(p.name, p.read_bytes()) for p in sorted(SAMPLES_DIR.glob("*.pdf"))]
keys = [file_key(name, data) for name, data in inputs]

pending = [(k, name, data) for k, (name, data) in zip(keys, inputs) if k not in st.session_state.extracted]
if st.button(f"読み取る（{len(pending)}件）", type="primary", disabled=not pending):
    progress = st.progress(0.0)
    for i, (k, name, data) in enumerate(pending, start=1):
        with st.spinner(f"{name} を読み取っています…"):
            try:
                invoice, usage = extract_invoice_bytes(data, Path(name).suffix)
                st.session_state.extracted[k] = {"file": name, "invoice": invoice.model_dump(), "usage": usage}
            except (ExtractionError, APIError) as e:
                # 1件失敗しても残りは処理を続ける
                st.session_state.extracted[k] = {"file": name, "error": str(e)}
        progress.progress(i / len(pending))
    st.rerun()  # ボタンの件数表示を更新するため、読み取りが終わったら画面を描き直す

done = [(k, st.session_state.extracted[k]) for k in keys if k in st.session_state.extracted]
if not done:
    st.info("請求書をアップロードするか、サンプルにチェックを入れて「読み取る」を押してください。")
    st.stop()

st.divider()
summary = st.empty()  # 全件の確認が終わってから集計を表示する
results = []

for k, item in done:
    with st.container(border=True):
        heading = st.empty()
        notes = st.container()

        if "error" in item:
            heading.subheader(f"{STATUS_LABEL['error']}　{item['file']}")
            notes.error(item["error"])
            results.append({"file": item["file"], "status": "error", "error": item["error"]})
            continue

        invoice, warnings = edit_invoice(k, item["invoice"])
        status = "warning" if warnings else "ok"
        heading.subheader(f"{STATUS_LABEL[status]}　{item['file']}")
        for w in warnings:
            notes.warning(w)
        usage = item["usage"]
        notes.caption(f"トークン使用量：入力 {usage['input_tokens']:,} / 出力 {usage['output_tokens']:,}")

        if invoice is None:
            results.append({"file": item["file"], "status": "error", "error": warnings[0]})
        else:
            results.append({"file": item["file"], "status": status, "warnings": warnings, "invoice": invoice})

with summary.container():
    counts = {s: sum(r["status"] == s for r in results) for s in STATUS_LABEL}
    cols = st.columns(4)
    cols[0].metric("読み取り件数", len(results))
    cols[1].metric("問題なし", counts["ok"])
    cols[2].metric("要確認", counts["warning"])
    cols[3].metric("失敗", counts["error"])

    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "請求書ごとのCSVをダウンロード",
        to_csv_bytes(invoice_rows(results), INVOICE_FIELDS),
        file_name="invoices.csv",
        mime="text/csv",
        width="stretch",
    )
    dl2.download_button(
        "明細ごとのCSVをダウンロード",
        to_csv_bytes(line_item_rows(results), LINE_ITEM_FIELDS),
        file_name="invoice_line_items.csv",
        mime="text/csv",
        width="stretch",
    )
    if counts["warning"]:
        st.caption("⚠️ 要確認の請求書があります。下の内容を確認・修正すると、CSVにも修正が反映されます。")
