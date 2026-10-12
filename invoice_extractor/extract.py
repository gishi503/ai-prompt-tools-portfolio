import sys
import json
import argparse
from pathlib import Path

from batch import DEFAULT_WORKERS, process
from extractor import MEDIA_TYPES
from exporter import INVOICE_FIELDS, LINE_ITEM_FIELDS, invoice_rows, line_item_rows, to_csv_bytes
from sheets import SHEETS_ERRORS, open_spreadsheet, register

STATUS_LABEL = {"ok": "問題なし", "warning": "要確認", "error": "失敗", "skipped": "読み取りなし"}


def collect_files(inputs: list[str]) -> tuple[list[Path], list[Path]]:
    """(読み取るファイル, 対応していない形式のため飛ばすファイル) を返す。隠しファイル（.DS_Store など）は無視する。"""
    files, unsupported = [], []
    for p in map(Path, inputs):
        candidates = sorted(f for f in p.iterdir() if f.is_file() and not f.name.startswith(".")) if p.is_dir() else [p]
        for f in candidates:
            (files if f.suffix.lower() in MEDIA_TYPES else unsupported).append(f)
    return files, unsupported


def log(msg: str):
    print(msg, file=sys.stderr)


def write_output(results: list[dict], output_path: str):
    if output_path.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return None

    # CSVは1請求書1行（明細はJSON文字列で1列にまとめる）。明細ごとのCSVも「_明細」を付けて出す
    with open(output_path, "wb") as f:
        f.write(to_csv_bytes(invoice_rows(results), INVOICE_FIELDS))
    items_path = Path(output_path).with_name(Path(output_path).stem + "_明細.csv")
    with open(items_path, "wb") as f:
        f.write(to_csv_bytes(line_item_rows(results), LINE_ITEM_FIELDS))
    return items_path


def main():
    parser = argparse.ArgumentParser(description="請求書（PDF/画像）から項目を抜き出し、金額の整合性をチェックするツール")
    parser.add_argument("inputs", nargs="+", help="請求書ファイル、またはファイルが入ったフォルダ")
    parser.add_argument("-o", "--output", default="result.csv", help="出力ファイル（.csv または .json）")
    parser.add_argument("--sheet", metavar="URL", help="GoogleスプレッドシートのURL。指定すると「請求書」「明細」シートにも登録する")
    parser.add_argument("--include-warnings", action="store_true", help="要確認の請求書もスプレッドシートに登録する")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"同時に読み取るファイルの数（デフォルト: {DEFAULT_WORKERS}）")
    args = parser.parse_args()

    files, unsupported = collect_files(args.inputs)
    for f in unsupported:
        log(f"[warn] {f.name}: 対応していない形式のため飛ばします（PDF / PNG / JPEG / WebP に対応）")
    if not files:
        log("[error] 対象のファイルがありません（PDF / PNG / JPEG / WebP に対応）")
        sys.exit(1)

    inputs = []
    for f in files:
        try:
            inputs.append((f.name, f.read_bytes()))
        except OSError as e:
            log(f"[warn] {f.name}: ファイルを開けませんでした（{e.strerror}）")
    log(f"[info] {len(inputs)}件を読み取ります（同時に{args.workers}件まで）")
    results, fatal = process(inputs, args.workers, on_done=lambda n, total, name: log(f"[info] {n}/{total} 完了: {name}"))

    items_path = write_output(results, args.output)
    usage = [r["usage"] for r in results if "usage" in r]
    log(f"[info] トークン使用量: 入力{sum(u['input_tokens'] for u in usage):,} / 出力{sum(u['output_tokens'] for u in usage):,}")
    for r in results:
        if r["status"] in ("error", "skipped"):
            log(f"[{STATUS_LABEL[r['status']]}] {r['file']}: {r['error']}")
        elif r["status"] == "warning":
            log(f"[要確認] {r['file']}: " + " / ".join(r["warnings"]))
    counts = {s: sum(r["status"] == s for r in results) for s in STATUS_LABEL}
    log(
        f"[done] {len(results)}件を処理（問題なし{counts['ok']} / 要確認{counts['warning']} / 失敗{counts['error']}"
        + (f" / 重複で読み取りなし{counts['skipped']}" if counts["skipped"] else "")
        + f"）し、{args.output}" + (f" と {items_path.name}" if items_path else "") + " に出力しました。"
    )
    if fatal:
        log(f"[error] 途中で止めました：{fatal}")
        sys.exit(2)

    if args.sheet:
        try:
            report = register(open_spreadsheet(args.sheet), results, args.include_warnings)
        except SHEETS_ERRORS as e:
            print(f"[error] スプレッドシートに登録できませんでした: {e}", file=sys.stderr)
            sys.exit(1)
        print(
            f"[done] スプレッドシートに{len(report['added'])}件を登録しました"
            f"（登録済み{len(report['duplicates'])} / 要確認で保留{len(report['skipped_warnings'])}"
            f" / 失敗{len(report['skipped_errors'])}）",
            file=sys.stderr,
        )
    if counts["error"] == len(results):
        sys.exit(1)  # 1件も読み取れなかった


if __name__ == "__main__":
    main()
