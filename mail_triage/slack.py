"""Slack API（chat.postMessage）で、整理したメールをチャンネルに知らせる。"""
import os
import time

import httpx

from mail_source import Mail
from schema import display_sender, MailSummary

API = "https://slack.com/api"
URGENCY_MARK = {"高": "🔴", "中": "🟡", "低": "⚪"}
ERRORS = {
    "invalid_auth": "Slackのトークンが正しくありません。.env の SLACK_BOT_TOKEN を確認してください",
    "not_authed": "Slackのトークンが設定されていません。.env の SLACK_BOT_TOKEN を確認してください",
    "channel_not_found": "Slackのチャンネルが見つかりません。.env の SLACK_CHANNEL_ID を確認してください",
    "not_in_channel": "アプリがチャンネルに参加していません。チャンネルで「/invite @アプリ名」を送ってください",
    "missing_scope": "アプリに投稿の権限（chat:write）がありません。権限を追加して、アプリを入れ直してください",
}


class SlackError(Exception):
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal  # 設定の誤りなど、どのメールでも同じように失敗するもの


class Slack:
    def __init__(self, token: str | None = None, channel: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        token = token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel or os.getenv("SLACK_CHANNEL_ID")
        if not token or not self.channel:
            raise SlackError(".env に SLACK_BOT_TOKEN と SLACK_CHANNEL_ID を設定してください（README の準備手順を参照）")
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token}"},
                                 timeout=30, transport=transport)

    def notify(self, mail: Mail, s: MailSummary, notion_url: str) -> None:
        payload = {"channel": self.channel, **build_message(mail, s, notion_url), "unfurl_links": False}
        for attempt in range(4):
            try:
                r = self.http.post("/chat.postMessage", json=payload)
            except httpx.HTTPError as e:
                raise SlackError(f"Slackに接続できませんでした（{type(e).__name__}）") from e
            if r.status_code == 429 and attempt < 3:
                time.sleep(float(r.headers.get("Retry-After", "1")))
                continue
            data = r.json()
            if data.get("ok"):
                return
            error = data.get("error", "")
            if error in ERRORS:
                raise SlackError(ERRORS[error], fatal=True)
            raise SlackError(f"Slackでエラーが起きました（{error}）")
        raise SlackError("Slackが混み合っています。時間をおいてやり直してください")


def build_message(mail: Mail, s: MailSummary, notion_url: str) -> dict:
    """通知の本文。text は通知のプレビュー用、blocks が画面に出る形。"""
    mark = URGENCY_MARK[s.urgency]
    sender = display_sender(mail, s)
    fields = [f"*種類*\n{s.category}", f"*緊急度*\n{mark} {s.urgency}", f"*差出人*\n{sender}",
              f"*期限*\n{s.due_date or '－'}"]
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{mark} *新しいメール：{mail.subject}*"}},
        {"type": "section", "fields": [{"type": "mrkdwn", "text": f} for f in fields]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*要約*\n{s.summary}"}},
    ]
    if s.action_items:
        todo = "\n".join(f"• {a}" for a in s.action_items)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*やること*\n{todo}"}})
    if notion_url:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Notionで開く"}, "url": notion_url}
        ]})
    return {"text": f"{mark} 新しいメール：{mail.subject}（{s.category}・緊急度{s.urgency}）", "blocks": blocks}
