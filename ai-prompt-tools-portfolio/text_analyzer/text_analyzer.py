import os
import sys
import json
import time
import argparse
from dotenv import load_dotenv
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def analyze_text(text: str, max_retries: int = 3) -> dict:
    prompt = f"""次の文章を分析し、必ず以下のJSON形式のみで出力してください。他の文章（前置きや説明）は一切含めないでください。

{{
  "summary": "2〜3文程度の要約",
  "sentiment": "positive / negative / neutral のいずれか",
  "keywords": ["キーワード1", "キーワード2", "キーワード3"]
}}

分析対象の文章：
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
            wait = 2 ** attempt  # 2, 4, 8秒と待機時間を伸ばす
            print(f"[warn] レート制限に達しました。{wait}秒待機して再試行します（{attempt}/{max_retries}）", file=sys.stderr)
            time.sleep(wait)
        except APIConnectionError:
            print(f"[warn] 接続エラーです。再試行します（{attempt}/{max_retries}）", file=sys.stderr)
            time.sleep(2)
        except APIError as e:
            print(f"[error] APIエラー: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("[error] リトライ上限に達しました。時間をおいて再実行してください。", file=sys.stderr)
        sys.exit(1)

    raw_output = response.content[0].text.strip()

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        try:
            result = json.loads(raw_output[start:end])
        except (json.JSONDecodeError, ValueError):
            print("[error] モデルの出力をJSONとして解析できませんでした。", file=sys.stderr)
            print(f"--- 生の出力 ---\n{raw_output}", file=sys.stderr)
            sys.exit(1)

    # 概算コスト表示（Claude Sonnetの目安単価。正確な単価は都度公式ページで確認）
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    print(f"[info] トークン使用量: 入力{input_tokens} / 出力{output_tokens}", file=sys.stderr)

    return result


def main():
    parser = argparse.ArgumentParser(description="テキストの要約・感情分析ツール")
    parser.add_argument("input", help="分析したいテキスト、またはテキストファイルのパス")
    args = parser.parse_args()

    if os.path.isfile(args.input):
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.input

    result = analyze_text(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()