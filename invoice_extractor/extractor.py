import os
import base64
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

from schema import Invoice

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))  # 429・5xx・接続エラーはSDKが自動で再試行する
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

PROMPT = """添付の請求書から項目を抜き出してください。

ルール：
- 金額・数量は、書類に書かれている値をそのまま転記する（計算し直したり、誤りを修正したりしない。整合性のチェックは別の工程で行う）
- 金額は円単位の整数にする（「¥」「,」「円」は除く）
- 日付は YYYY-MM-DD 形式にする（和暦は西暦に変換する）
- 書類に記載がない項目は null にする。推測で埋めない"""


class ExtractionError(Exception):
    pass


def _file_block(data: bytes, suffix: str) -> dict:
    media_type = MEDIA_TYPES.get(suffix.lower())
    if media_type is None:
        raise ExtractionError(f"対応していないファイル形式です: {suffix}（PDF / PNG / JPEG / WebP に対応）")

    encoded = base64.standard_b64encode(data).decode("utf-8")
    block_type = "document" if media_type == "application/pdf" else "image"
    return {"type": block_type, "source": {"type": "base64", "media_type": media_type, "data": encoded}}


def extract_invoice(path: str | Path) -> tuple[Invoice, dict]:
    """請求書ファイル1件を読み取り、(Invoice, トークン使用量) を返す。失敗したら ExtractionError を投げる。"""
    path = Path(path)
    return extract_invoice_bytes(path.read_bytes(), path.suffix)


def extract_invoice_bytes(data: bytes, suffix: str) -> tuple[Invoice, dict]:
    """ファイルの中身（bytes）と拡張子から読み取る。画面からアップロードされたファイル用。"""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        messages=[{
            "role": "user",
            "content": [_file_block(data, suffix), {"type": "text", "text": PROMPT}],
        }],
        output_format=Invoice,
        # 安全上の理由で断られた場合に、サーバー側で別モデルに自動で切り替える
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )

    if response.stop_reason == "refusal":
        raise ExtractionError("モデルが処理を断りました（refusal）")
    if response.stop_reason == "max_tokens":
        raise ExtractionError("出力が上限に達して途中で切れました")
    if response.parsed_output is None:
        raise ExtractionError("出力を決められた形式として読み取れませんでした")

    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return response.parsed_output, usage
