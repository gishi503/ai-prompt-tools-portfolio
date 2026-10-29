"""APIを呼ばずに、Notion・Slackとのやり取りを確かめるテスト。  python test_offline.py"""
import json
from pathlib import Path

import httpx

import notion as notion_mod
from mail_source import load_folder
from notion import Notion, NotionError, page_id_from_url
from run import process
from schema import MailSummary
from slack import Slack, SlackError

SAMPLES = Path(__file__).parent / "samples"


def fake_summary(mail):
    s = MailSummary(category="日程調整", urgency="高", summary=f"{mail.subject}の要約", action_items=["返信する"],
                    due_date="2026-10-30", sender_company="テスト株式会社")
    return s, {"input_tokens": 100, "output_tokens": 50}


class FakeNotion:
    """Notion APIのふり。登録したページを覚えておき、Message-IDでの検索に答える。"""
    def __init__(self):
        self.pages, self.calls = [], []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.method, request.url.path, body))
        assert request.headers["Notion-Version"] == notion_mod.NOTION_VERSION
        path = request.url.path
        if path == "/v1/databases":
            return httpx.Response(200, json={"id": "db1", "data_sources": [{"id": "ds1", "name": "メール一覧"}]})
        if path == "/v1/data_sources/ds1/query":
            want = body["filter"]["rich_text"]["equals"]
            hits = [p for p in self.pages if p["properties"]["Message-ID"]["rich_text"][0]["text"]["content"] == want]
            return httpx.Response(200, json={"results": [{"id": h["id"], "url": h["url"]} for h in hits]})
        if path == "/v1/pages":
            page = {**body, "id": f"p{len(self.pages)}", "url": f"https://www.notion.so/p{len(self.pages)}"}
            self.pages.append(page)
            return httpx.Response(200, json={"id": page["id"], "url": page["url"]})
        return httpx.Response(404, json={"code": "object_not_found", "message": "not found"})


class FakeSlack:
    def __init__(self, error: str | None = None):
        self.posts, self.error = [], error

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.error:
            return httpx.Response(200, json={"ok": False, "error": self.error})
        self.posts.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})


def setup(tmp_state: Path):
    notion_mod.STATE_FILE = tmp_state
    if tmp_state.exists():
        tmp_state.unlink()


def test_samples_load():
    mails = load_folder(SAMPLES)
    assert len(mails) == 5
    assert all(m.message_id.startswith("<sample-") for m in mails)
    assert mails[0].received_at <= mails[-1].received_at  # 古い順
    assert "面接" in [m for m in mails if m.file.startswith("01")][0].body


def test_register_and_notify_then_skip_duplicates(tmp: Path):
    setup(tmp)
    fn, fs = FakeNotion(), FakeSlack()
    n = Notion(token="t", transport=httpx.MockTransport(fn))
    s = Slack(token="t", channel="C1", transport=httpx.MockTransport(fs))
    ds = n.ensure_database("a" * 32)
    mails = load_folder(SAMPLES)

    c = process(mails, n, s, ds, summarize=fake_summary)
    assert c == {"done": 5, "skipped": 0, "failed": 0}
    assert len(fn.pages) == 5 and len(fs.posts) == 5
    first = fn.pages[0]
    assert first["parent"] == {"type": "data_source_id", "data_source_id": "ds1"}
    assert first["properties"]["期限"]["date"]["start"] == "2026-10-30"
    assert first["properties"]["対応状況"]["select"]["name"] == "未対応"
    assert first["children"][1]["paragraph"]["rich_text"][0]["text"]["content"]  # 本文がページの中に入る
    assert fs.posts[0]["channel"] == "C1"
    assert fs.posts[0]["blocks"][-1]["elements"][0]["url"] == "https://www.notion.so/p0"  # Notionへのボタン

    # 2回目は全部登録済み。AIもSlackも呼ばない
    c = process(mails, n, s, ds, summarize=lambda m: (_ for _ in ()).throw(AssertionError("AIを呼んだ")))
    assert c == {"done": 0, "skipped": 5, "failed": 0}
    assert len(fs.posts) == 5

    # データベースは作り直さない
    assert n.ensure_database("a" * 32) == "ds1"
    assert sum(1 for m, p, _ in fn.calls if p == "/v1/databases") == 1


def test_slack_setting_error_stops(tmp: Path):
    setup(tmp)
    n = Notion(token="t", transport=httpx.MockTransport(FakeNotion()))
    s = Slack(token="t", channel="C1", transport=httpx.MockTransport(FakeSlack("not_in_channel")))
    ds = n.ensure_database("b" * 32)
    c = process(load_folder(SAMPLES), n, s, ds, summarize=fake_summary)
    assert c["failed"] == 1 and c["done"] == 0  # 1通目で止まる（残り4通で同じ失敗をくり返さない）


def test_notion_not_shared_message(tmp: Path):
    setup(tmp)
    n = Notion(token="t", transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={"code": "object_not_found", "message": "x"})))
    try:
        n.ensure_database("c" * 32)
    except NotionError as e:
        assert "接続" in str(e)
    else:
        raise AssertionError("エラーにならなかった")


def test_page_id_from_url():
    assert page_id_from_url("https://www.notion.so/myws/abc-0123456789abcdef0123456789abcdef?pvs=4") == "0123456789abcdef0123456789abcdef"
    for bad in ["", "https://www.notion.so/myws/abc"]:
        try:
            page_id_from_url(bad)
        except NotionError:
            pass
        else:
            raise AssertionError(bad)


if __name__ == "__main__":
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(tmp) if fn.__code__.co_argcount else fn()
            print(f"ok  {name}")
