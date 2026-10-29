"""Notion API で、メールの一覧（データベース）を作り、1通を1行として登録する。"""
import json
import os
import time
from pathlib import Path

import httpx

from mail_source import Mail
from schema import display_sender, CATEGORIES, URGENCIES, MailSummary

API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
STATE_FILE = Path(__file__).parent / ".notion_state.json"  # 作ったデータベースのIDを覚えておく
STATUSES = ["未対応", "対応中", "完了"]
TEXT_LIMIT = 2000  # Notionのテキスト1かたまりの上限


class NotionError(Exception):
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal  # トークンや共有の設定の誤りなど、どのメールでも同じように失敗するもの


def _text(s: str) -> list[dict]:
    return [{"type": "text", "text": {"content": s[:TEXT_LIMIT]}}]


def _options(names: list[str], colors: list[str] | None = None) -> dict:
    colors = colors or ["default"] * len(names)
    return {"options": [{"name": n, "color": c} for n, c in zip(names, colors)]}


PROPERTIES = {
    "件名": {"title": {}},
    "緊急度": {"select": _options(URGENCIES, ["red", "yellow", "gray"])},
    "種類": {"select": _options(CATEGORIES, ["blue", "purple", "orange", "green", "gray", "default"])},
    "要約": {"rich_text": {}},
    "やること": {"rich_text": {}},
    "期限": {"date": {}},
    "差出人": {"rich_text": {}},
    "受信日時": {"date": {}},
    "対応状況": {"select": _options(STATUSES, ["red", "yellow", "green"])},
    "Message-ID": {"rich_text": {}},
}


class Notion:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None):
        token = token or os.getenv("NOTION_TOKEN")
        if not token:
            raise NotionError(".env に NOTION_TOKEN を設定してください（README の準備手順を参照）")
        self.http = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            timeout=30,
            transport=transport,
        )

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        for attempt in range(4):
            try:
                r = self.http.request(method, path, json=body)
            except httpx.HTTPError as e:
                raise NotionError(f"Notionに接続できませんでした（{type(e).__name__}）") from e
            if r.status_code == 429 and attempt < 3:  # 1秒に3回までの制限。指定された秒数だけ待ってやり直す
                time.sleep(float(r.headers.get("Retry-After", "1")))
                continue
            if r.is_success:
                return r.json()
            raise NotionError(self._describe(r), fatal=r.status_code in (401, 403, 404))
        raise NotionError("Notionが混み合っています。時間をおいてやり直してください")

    @staticmethod
    def _describe(r: httpx.Response) -> str:
        try:
            code, message = r.json().get("code", ""), r.json().get("message", "")
        except ValueError:
            code, message = "", r.text[:200]
        if code == "unauthorized":
            return "Notionのトークンが正しくありません。.env の NOTION_TOKEN を確認してください"
        if code == "object_not_found":
            return ("Notionのページが見つかりません。ページのURLが正しいか、ページの「…」→「接続」で"
                    "このツールの接続を追加したかを確認してください")
        if code == "restricted_resource":
            return "この接続には、そのページを編集する権限がありません"
        return f"Notionでエラーが起きました（{r.status_code} {code}）: {message}"

    # ---------- データベース ----------
    def ensure_database(self, parent_page_id: str) -> str:
        """メール一覧のデータベースを用意し、データソースのIDを返す。2回目以降は前回作ったものを使う。"""
        state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        if state.get("parent_page_id") == parent_page_id and state.get("data_source_id"):
            return state["data_source_id"]

        db = self._call("POST", "/databases", {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": _text("メール一覧（AI整理）"),
            "is_inline": True,
            "initial_data_source": {"properties": PROPERTIES},
        })
        sources = db.get("data_sources") or self._call("GET", f"/databases/{db['id']}").get("data_sources", [])
        if not sources:
            raise NotionError("データベースは作れましたが、データソースのIDを取得できませんでした")
        state = {"parent_page_id": parent_page_id, "database_id": db["id"], "data_source_id": sources[0]["id"]}
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        return state["data_source_id"]

    def find_by_message_id(self, data_source_id: str, message_id: str) -> str | None:
        """同じメールが登録済みなら、そのページのURLを返す。"""
        result = self._call("POST", f"/data_sources/{data_source_id}/query", {
            "filter": {"property": "Message-ID", "rich_text": {"equals": message_id}},
            "page_size": 1,
        })
        pages = result.get("results", [])
        return page_url(pages[0]) if pages else None

    def add_mail(self, data_source_id: str, mail: Mail, s: MailSummary) -> str:
        """1通を1行として登録し、ページのURLを返す。ページの中にはメールの本文を残す。"""
        sender = display_sender(mail, s)
        props = {
            "件名": {"title": _text(mail.subject)},
            "緊急度": {"select": {"name": s.urgency}},
            "種類": {"select": {"name": s.category}},
            "要約": {"rich_text": _text(s.summary)},
            "やること": {"rich_text": _text("\n".join(f"・{a}" for a in s.action_items))},
            "差出人": {"rich_text": _text(f"{sender} <{mail.sender_address}>")},
            "対応状況": {"select": {"name": "未対応" if s.action_items else "完了"}},
            "Message-ID": {"rich_text": _text(mail.message_id)},
        }
        if s.due_date:
            props["期限"] = {"date": {"start": s.due_date}}
        if mail.received_at:
            props["受信日時"] = {"date": {"start": mail.received_at.isoformat()}}

        body = [mail.body[i:i + TEXT_LIMIT] for i in range(0, min(len(mail.body), 20000), TEXT_LIMIT)]
        children = [{"type": "heading_3", "heading_3": {"rich_text": _text("メール本文")}}] + [
            {"type": "paragraph", "paragraph": {"rich_text": _text(chunk)}} for chunk in body
        ]
        page = self._call("POST", "/pages", {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": props,
            "children": children,
        })
        return page_url(page)


def page_url(page: dict) -> str:
    """ページのURL。一部の項目しか返ってこない場合は、IDから組み立てる。"""
    return page.get("url") or f"https://www.notion.so/{page['id'].replace('-', '')}"


def page_id_from_url(url_or_id: str) -> str:
    """NotionのページURL（…/ページ名-0123abcd…）から、末尾の32桁のIDを取り出す。"""
    tail = url_or_id.split("?")[0].rstrip("/").split("/")[-1].split("-")[-1].replace("-", "")
    if len(tail) != 32 or any(c not in "0123456789abcdef" for c in tail.lower()):
        raise NotionError(".env の NOTION_PAGE_URL が、NotionのページのURLになっていません")
    return tail
