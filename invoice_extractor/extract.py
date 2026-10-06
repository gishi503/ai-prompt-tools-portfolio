import sys
import json
import argparse
from pathlib import Path

from anthropic import APIError
from extractor import extract_invoice, ExtractionError, MEDIA_TYPES
from validator import validate
from exporter import INVOICE_FIELDS, invoice_rows, to_csv_bytes


def collect_files(inputs: list[str]) -> list[Path]:
    files = []
    for p in map(Path, inputs):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in MEDIA_TYPES)
        else:
            files.append(p)
    return files


def process(files: list[Path]) -> list[dict]:
    results = []
    for i, path in enumerate(files, start=1):
        print(f"[info] 処理中 {i}/{len(files)}: {path.name}", file=sys.stderr)
        try:
            invoice, usage = extract_invoice(path)
        except (ExtractionError, APIError, OSError) as e:
            # 1件失敗しても全体は止めず、エラー理由を残して次へ進む
            print(f"[warn] {path.name}: {e}", file=sys.stderr)
            results.append({"file": path.name, "status": "error", "error": str(e)})
            continue

        warnings = validate(invoice)
        print(
            f"[info] トークン使用量: 入力{usage['input_tokens']} / 出力{usage['output_tokens']}"
            + (f" / 警告{len(warnings)}件" if warnings else ""),
            file=sys.stderr,
        )
        results.append({
            "file": path.name,
            "status": "warning" if warnings else "ok",
            "warnings": warnings,
            "invoice": invoice.model_dump(),
        })
    return results


def write_output(results: list[dict], output_path: str):
    if output_path.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return

    # CSVは1請求書1行（明細はJSON文字列で1列にまとめる）
    with open(output_path, "wb") as f:
        f.write(to_csv_bytes(invoice_rows(results), INVOICE_FIELDS))


def main():
    parser = argparse.ArgumentParser(description="請求書（PDF/画像）から項目を抜き出し、金額の整合性をチェックするツール")
    parser.add_argument("inputs", nargs="+", help="請求書ファイル、またはファイルが入ったフォルダ")
    parser.add_argument("-o", "--output", default="result.csv", help="出力ファイル（.csv または .json）")
    args = parser.parse_args()

    files = collect_files(args.inputs)
    if not files:
        print("[error] 対象のファイルがありません（PDF / PNG / JPEG / WebP に対応）", file=sys.stderr)
        sys.exit(1)

    results = process(files)
    write_output(results, args.output)

    counts = {s: sum(r["status"] == s for r in results) for s in ("ok", "warning", "error")}
    print(
        f"[done] {len(results)}件を処理（問題なし{counts['ok']} / 要確認{counts['warning']} / 失敗{counts['error']}）"
        f"し、{args.output} に出力しました。",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
