"""現地スタッフの英語の日報をAIで日本語に整理し、1日分のまとめをSlackに送る。

  python run.py samples --dry-run  # Slackには送らず、まとめを表示する
  python run.py samples            # Slackに送る
"""
import argparse
import sys
from collections import defaultdict

from dotenv import load_dotenv

from digest import as_slack, as_text
from report_source import Report, load_folder
from slack import Slack, SlackError
from summarize import MODEL, FatalSummarizeError, SummarizeError, summarize

load_dotenv()

# 100万トークンあたりの料金（米ドル、2026-11時点）。費用の目安の表示にだけ使う
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}


def log(msg: str):
    print(msg, file=sys.stderr)


def cost_usd(model: str, usage: dict) -> float | None:
    if model not in PRICES:
        return None
    p_in, p_out = PRICES[model]
    return (usage["input_tokens"] * p_in + usage["output_tokens"] * p_out) / 1_000_000


def process(reports: list[Report], summarize_fn=summarize):
    """1通ずつ整理する。1通の失敗では止めず、APIキーの誤りなど全部に効く失敗では止める。"""
    by_date, failed = defaultdict(list), 0
    usage = {"input_tokens": 0, "output_tokens": 0}
    for i, r in enumerate(reports, 1):
        log(f"[{i}/{len(reports)}] {r.file}（{r.staff}）")
        try:
            s, u = summarize_fn(r)
        except FatalSummarizeError as e:
            log(f"[error] 途中で止めました：{e}")
            failed += 1
            break
        except SummarizeError as e:
            log(f"  [失敗] {e}")
            failed += 1
            continue
        usage = {k: usage[k] + u[k] for k in usage}
        by_date[r.date].append((r, s))
    return by_date, usage, failed


def main():
    parser = argparse.ArgumentParser(description="英語の日報をAIで日本語に整理し、1日分のまとめをSlackに送る")
    parser.add_argument("folder", help="日報（.txt）が入ったフォルダ")
    parser.add_argument("--dry-run", action="store_true", help="Slackには送らず、まとめを表示する")
    args = parser.parse_args()

    try:
        reports = load_folder(args.folder)
    except ValueError as e:
        log(f"[error] {e}")
        sys.exit(1)
    if not reports:
        log(f"[error] {args.folder} に .txt の日報がありません")
        sys.exit(1)

    slack = None
    if not args.dry_run:
        try:
            slack = Slack()
        except SlackError as e:
            log(f"[error] {e}")
            sys.exit(1)

    log(f"[info] {len(reports)}通の日報を整理します" + ("（お試し：Slackには送りません）" if args.dry_run else ""))
    by_date, usage, failed = process(reports)

    for date in sorted(by_date):
        print(as_text(date, by_date[date]))
        print()
        if slack:
            try:
                slack.post(as_slack(date, by_date[date]))
                log(f"[info] {date} のまとめをSlackに送りました")
            except SlackError as e:
                log(f"[error] {e}")
                failed += 1

    done = sum(len(v) for v in by_date.values())
    log(f"[info] トークン使用量：入力 {usage['input_tokens']:,} / 出力 {usage['output_tokens']:,}（モデル {MODEL}）")
    if done and (c := cost_usd(MODEL, usage)) is not None:
        log(f"[info] 費用の目安：合計 ${c:.4f}（日報1通あたり ${c / done:.4f}）")
    log(f"[done] 整理 {done}通 / 失敗 {failed}通")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
