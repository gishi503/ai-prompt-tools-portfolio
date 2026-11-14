"""日報ファイルを読み込む。Slack・Googleフォームなどから集める場合も、この Report の形にそろえる。

ファイルの形：
    Name: 名前
    Role: 役割
    Date: YYYY-MM-DD
    ---
    本文（英語・タガログ語まじりでもよい）
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Report:
    staff: str
    role: str
    date: str
    body: str
    file: str


def parse_report(text: str, file: str = "") -> Report:
    head, sep, body = text.partition("\n---\n")
    if not sep:
        raise ValueError(f"{file}：見出しと本文の区切り（---）がありません")
    fields = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    if not fields.get("name") or not fields.get("date"):
        raise ValueError(f"{file}：Name と Date は必ず書いてください")
    return Report(staff=fields["name"], role=fields.get("role", ""), date=fields["date"], body=body.strip(), file=file)


def load_folder(folder: str | Path) -> list[Report]:
    return [parse_report(p.read_text(encoding="utf-8"), p.name) for p in sorted(Path(folder).glob("*.txt"))]
