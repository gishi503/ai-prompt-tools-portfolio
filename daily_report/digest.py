"""1日分の整理結果を、日本の担当者向けの「チームのまとめ」にする（画面表示・Slack共通）。"""
from report_source import Report
from schema import ReportSummary

MARK = {"高": "🔴", "中": "🟡", "低": "⚪"}
ORDER = {"高": 0, "中": 1, "低": 2}

Item = tuple[Report, ReportSummary]


def sort_items(items: list[Item]) -> list[Item]:
    """対応が必要な人から順に並べる。"""
    return sorted(items, key=lambda x: ORDER[x[1].attention])


def todo_for_japan(items: list[Item]) -> list[str]:
    """日本側がやること（質問への返事・あいまいな指示の説明・問題への対応）を1つの一覧にする。"""
    out = []
    for r, s in sort_items(items):
        out += [f"{r.staff}：{q}" for q in s.questions]
        out += [f"{r.staff}：指示の説明が必要 — {u}" for u in s.unclear]
        # 質問や迷いがない人の問題だけを足す（質問と同じ話が二重に並ばないように）
        if s.attention == "高" and not (s.questions or s.unclear):
            out += [f"{r.staff}：問題への対応 — {x}" for x in s.risks]
    return out


def as_text(date: str, items: list[Item]) -> str:
    lines = [f"■ {date} のチームの日報まとめ（{len(items)}人）", ""]
    todo = todo_for_japan(items)
    lines.append("【日本側がやること】" if todo else "【日本側がやること】なし")
    lines += [f"  ・{t}" for t in todo]
    lines.append("")
    for r, s in sort_items(items):
        lines.append(f"{MARK[s.attention]} {r.staff}（{r.role}）")
        lines.append(f"  {s.summary}")
        for label, values in (("済", s.done), ("途中", s.in_progress), ("問題", s.risks),
                              ("質問", s.questions), ("迷い", s.unclear), ("休み", s.absence)):
            lines += [f"  [{label}] {v}" for v in values]
        lines.append("")
    return "\n".join(lines).rstrip()


def as_slack(date: str, items: list[Item]) -> dict:
    todo = todo_for_japan(items)
    high = sum(1 for _, s in items if s.attention == "高")
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"{date} のチームの日報まとめ（{len(items)}人）"}}]
    todo_text = "\n".join(f"• {t}" for t in todo) if todo else "なし"
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*日本側がやること*\n{todo_text}"}})
    blocks.append({"type": "divider"})
    for r, s in sort_items(items):
        parts = [f"{MARK[s.attention]} *{r.staff}*（{r.role}）", s.summary]
        for label, values in (("問題", s.risks), ("質問", s.questions), ("迷い", s.unclear), ("休み", s.absence)):
            parts += [f"　*{label}*：{v}" for v in values]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(parts)}})
    return {"text": f"{date} の日報まとめ：対応が必要 {high}人 / やること {len(todo)}件", "blocks": blocks}
