"""Slack API（chat.postMessage）で、1日分のまとめをチャンネルに送る。"""
import os
import time

import httpx

API = "https://slack.com/api"
ERRORS = {
    "invalid_auth": "Slackのトークンが正しくありません。.env の SLACK_BOT_TOKEN を確認してください",
    "not_authed": "Slackのトークンが設定されていません。.env の SLACK_BOT_TOKEN を確認してください",
    "channel_not_found": "Slackのチャンネルが見つかりません。.env の SLACK_CHANNEL_ID を確認してください",
    "not_in_channel": "アプリがチャンネルに参加していません。チャンネルで「/invite @アプリ名」を送ってください",
    "missing_scope": "アプリに投稿の権限（chat:write）がありません。権限を追加して、アプリを入れ直してください",
}


class SlackError(Exception):
    pass


class Slack:
    def __init__(self, token: str | None = None, channel: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        token = token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel or os.getenv("SLACK_CHANNEL_ID")
        if not token or not self.channel:
            raise SlackError(".env に SLACK_BOT_TOKEN と SLACK_CHANNEL_ID を設定してください")
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token}"},
                                 timeout=30, transport=transport)

    def post(self, message: dict) -> None:
        payload = {"channel": self.channel, **message, "unfurl_links": False}
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
            raise SlackError(ERRORS.get(error, f"Slackでエラーが起きました（{error}）"))
        raise SlackError("Slackが混み合っています。時間をおいてやり直してください")
