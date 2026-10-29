"""メールファイル（.eml）を読み込む。Gmail などから取り込む場合も、この Mail の形にそろえる。"""
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path


@dataclass
class Mail:
    message_id: str  # 二重登録を防ぐためのキー
    subject: str
    sender_name: str
    sender_address: str
    received_at: datetime | None
    body: str
    file: str


def parse_eml(data: bytes, file: str = "") -> Mail:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    name, address = parseaddr(str(msg.get("From", "")))
    part = msg.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    try:
        received_at = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except (TypeError, ValueError):
        received_at = None
    message_id = str(msg.get("Message-ID", "")).strip() or f"<no-id:{file}>"
    return Mail(
        message_id=message_id,
        subject=str(msg.get("Subject", "")).strip() or "（件名なし）",
        sender_name=name or address,
        sender_address=address,
        received_at=received_at,
        body=body.strip(),
        file=file,
    )


def load_folder(folder: str | Path) -> list[Mail]:
    """フォルダ内の .eml を受信日時の古い順に読み込む。"""
    paths = sorted(Path(folder).glob("*.eml"))
    mails = [parse_eml(p.read_bytes(), p.name) for p in paths]
    return sorted(mails, key=lambda m: m.received_at.timestamp() if m.received_at else 0)
