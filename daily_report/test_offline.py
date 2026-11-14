"""APIを呼ばずに、読み込み・まとめ・Slackへの送信を確かめるテスト。  python test_offline.py"""
import json
from pathlib import Path

import httpx

from digest import as_slack, as_text, todo_for_japan
from report_source import load_folder, parse_report
from run import process
from schema import ReportSummary
from slack import Slack, SlackError
from summarize import FatalSummarizeError, SummarizeError

SAMPLES = Path(__file__).parent / "samples"


def fake(attention="低", questions=(), unclear=(), risks=()):
    def fn(r):
        s = ReportSummary(summary=f"{r.staff}の要約", done=["作業A"], in_progress=[], risks=list(risks),
                          questions=list(questions), unclear=list(unclear), absence=[], attention=attention)
        return s, {"input_tokens": 100, "output_tokens": 50}
    return fn


def test_load_samples():
    reports = load_folder(SAMPLES)
    assert len(reports) == 5
    assert reports[0].staff == "Maria Santos" and reports[0].date == "2026-11-13"
    assert "Hanaya Bakery" in reports[0].body


def test_bad_file():
    try:
        parse_report("Name: A\nbody only", "x.txt")
    except ValueError as e:
        assert "---" in str(e)
    else:
        raise AssertionError("区切りのないファイルを受け付けてしまった")


def test_digest_orders_and_collects_todo():
    reports = load_folder(SAMPLES)[:2]
    items = [(reports[0], fake("低")(reports[0])[0]),
             (reports[1], fake("高", questions=["割引の可否を月曜までに"], risks=["返事が遅れると失注"])(reports[1])[0])]
    text = as_text("2026-11-13", items)
    assert text.index("John Reyes") < text.index("Maria Santos")  # 対応が必要な人が先
    todo = todo_for_japan(items)
    assert todo == ["John Reyes：割引の可否を月曜までに"]  # 質問がある人の問題は二重に並べない
    only_risk = [(reports[0], fake("高", risks=["写真が未着で納期に遅れそう"])(reports[0])[0])]
    assert todo_for_japan(only_risk) == ["Maria Santos：問題への対応 — 写真が未着で納期に遅れそう"]
    msg = as_slack("2026-11-13", items)
    assert "対応が必要 1人" in msg["text"] and msg["blocks"][0]["type"] == "header"


def test_one_failure_does_not_stop():
    reports = load_folder(SAMPLES)
    ok = fake()

    def flaky(r):
        if r.staff == "John Reyes":
            raise SummarizeError("混み合っています")
        return ok(r)
    by_date, usage, failed = process(reports, flaky)
    assert failed == 1 and len(by_date["2026-11-13"]) == 4 and usage["input_tokens"] == 400


def test_fatal_stops():
    def broken(r):
        raise FatalSummarizeError("APIキーが正しくありません")
    by_date, _, failed = process(load_folder(SAMPLES), broken)
    assert failed == 1 and not by_date


def test_slack_post_and_error():
    posts = []

    def ok(request):
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})
    Slack("xoxb-test", "C1", transport=httpx.MockTransport(ok)).post({"text": "t", "blocks": []})
    assert posts[0]["channel"] == "C1"

    bad = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": False, "error": "not_in_channel"}))
    try:
        Slack("xoxb-test", "C1", transport=bad).post({"text": "t"})
    except SlackError as e:
        assert "/invite" in str(e)
    else:
        raise AssertionError("Slackのエラーを見逃した")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)}件すべて通過")
