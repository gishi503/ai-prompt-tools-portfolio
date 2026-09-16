import os
import sys
import json
import csv
import time
import argparse
from dotenv import load_dotenv
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def analyze_text(text: str, max_retries: int = 3) -> dict:
    prompt = f"""次の分sy方を分析し、必ず以下のJSON形式のみで出力してください。他の文章 (前置きや説明) は一切含めないでください。

{{
  "summary": "2〜3文程度の要約",
  "sentiment": "positive / negative / neutral のいずれか",
  "keywords": ["キーワード1", "キーワード2", "キーワード3"]
}}

分析対象の文章:
{text}"""

    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            break
        except RateLimitError:
            wait = 2 ** attempt
            print(f"[warn] レート制限。{wait}秒待機 ({attempt}/{max_retries}) ", fike=sys.stderr)
            time.sleep(wait)
        except APIConnectionError:
            time.sleep(2)
        except APIError as e:
            print(f"[error] APIエラー: {e}", file=sys.stderr)
            return {"summary": None, "sentiment": None, "keywords": [],"error": str(e)}
    else:
        return {"summary": None, "sentiment": None, "keywords": [], "error": "retry_exceeded"}

    raw_output = response.content[0].text.strip()
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        start = raw_output.find("{{")
        end = raw_output.rfind("}") + 1
        try:
            return json.loads(raw_output[start:end])
        except (json.JSONDecodeError, ValueError):
            return {"summary": None, "sentiment": None, "keywords": [], "error": "json_parse_failed", "raw_output": raw_output}

def process_csv(input_path: str, output_path: str, text_column: str = "text"):
    with open(input_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    total = len(reader)
    results = []

    for i, row in enumerate(reader, start=1):
        print(f"[info] 処理中 {i}/{total} ...", file=sys.stderr)
        analysis = analyze_text(row[text_column])
        merged = {**row, **analysis}
        results.append(merged)
        time.sleep(0.5) # レート制限を避けるための軽いウェイト

        # 出力 (CSV or JSON、拡張子で自動判定)
    if output_path.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    else:
        fieldnames = list(results[0].keys())
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                # keywordsのリストは文字列化してCSVに収める
                r = {**r, "keywords": ", ".join(r.get("keywords") or [])}
                writer.writerow(r)

    print(f"[done] {total}件を処理し、 {output_path} に出力しました。", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="CSVの一括テキスト分析ツール")
    parser.add_argument("input_csv", help="入力CSVファイルのパス")
    parser.add_argument("-o", "--output", default="result.csv", help="出力ファイル (.csv または .json) ")
    parser.add_argument("-c", "--column", default="text", help="分析対象の列名 (デフォルト: text) ")
    args = parser.parse_args()

    process_csv(args.input_csv, args.output, args.column)


if __name__ == "__main__":
    main()