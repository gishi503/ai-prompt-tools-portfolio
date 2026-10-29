"""メールをAIで要約・分類し、Notionに登録してSlackに知らせる。

  python run.py samples            # サンプルのメール5通を処理する
  python run.py samples --dry-run  # Notion・Slackには送らず、AIの整理結果だけを表示する
"""
import argparse
import os
import sys

from dotenv import load_dotenv

from mail_source import Mail, load_folder
from notion import Notion, NotionError, page_id_from_url
from schema import MailSummary
from slack import Slack, SlackError
from triage import FatalTriageError, TriageError, triage

load_dotenv()


def log(msg: str):
    print(msg, file=sys.stderr)


def show(mail: Mail, s: MailSummary):
    log(f"  件名　：{mail.subject}")
    log(f"  種類　：{s.category}　緊急度：{s.urgency}　期限：{s.due_date or '－'}")
    log(f"  要約　：{s.summary}")
    for a in s.action_items:
        log(f"  やること：{a}")


def process(mails: list[Mail], notion: Notion | None, slack: Slack | None, data_source_id: str | None,
            summarize=triage) -> dict:
    """1通ずつ処理する。1通の失敗では止めず、APIキーの誤りなど全部に効く失敗では止める。"""
    counts = {"done": 0, "skipped": 0, "failed": 0}
    usage = {"input_tokens": 0, "output_tokens": 0}
    for i, mail in enumerate(mails, 1):
        log(f"[{i}/{len(mails)}] {mail.file or mail.subject}")
        try:
            if notion and (url := notion.find_by_message_id(data_source_id, mail.message_id)):
                log(f"  登録済みのため飛ばします：{url}")
                counts["skipped"] += 1
                continue
            summary, u = summarize(mail)
            usage = {k: usage[k] + u[k] for k in usage}
            show(mail, summary)
            if notion:
                url = notion.add_mail(data_source_id, mail, summary)
                log(f"  Notionに登録しました：{url}")
                if slack:
                    slack.notify(mail, summary, url)
                    log("  Slackに通知しました")
            counts["done"] += 1
        except FatalTriageError as e:
            log(f"[error] 途中で止めました：{e}")
            counts["failed"] += 1
            break
        except (TriageError, NotionError, SlackError) as e:
            log(f"  [失敗] {e}")
            counts["failed"] += 1
            # NotionやSlackの設定の誤りは、残りのメールでも同じように失敗するので止める
            if getattr(e, "fatal", False):
                log("[error] 設定を直してから、もう一度実行してください（登録済みのメールは飛ばします）")
                break
    log(f"[info] トークン使用量：入力 {usage['input_tokens']:,} / 出力 {usage['output_tokens']:,}")
    return counts


def main():
    parser = argparse.ArgumentParser(description="メールをAIで要約・分類し、Notionに登録してSlackに知らせる")
    parser.add_argument("folder", help=".eml ファイルが入ったフォルダ")
    parser.add_argument("--dry-run", action="store_true", help="Notion・Slackには送らず、AIの整理結果だけを表示する")
    parser.add_argument("--no-slack", action="store_true", help="Notionへの登録だけ行い、Slackには知らせない")
    args = parser.parse_args()

    mails = load_folder(args.folder)
    if not mails:
        log(f"[error] {args.folder} に .eml ファイルがありません")
        sys.exit(1)

    notion = slack = data_source_id = None
    if not args.dry_run:
        try:
            notion = Notion()
            data_source_id = notion.ensure_database(page_id_from_url(os.getenv("NOTION_PAGE_URL", "")))
            slack = None if args.no_slack else Slack()
        except (NotionError, SlackError) as e:
            log(f"[error] {e}")
            sys.exit(1)

    log(f"[info] {len(mails)}通を処理します" + ("（お試し：Notion・Slackには送りません）" if args.dry_run else ""))
    c = process(mails, notion, slack, data_source_id)
    log(f"[done] 処理 {c['done']}通 / 登録済みで飛ばし {c['skipped']}通 / 失敗 {c['failed']}通")
    sys.exit(1 if c["failed"] else 0)


if __name__ == "__main__":
    main()
