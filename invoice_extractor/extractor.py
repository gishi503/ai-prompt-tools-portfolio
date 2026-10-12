import os
import base64
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from anthropic import Anthropic
from pydantic import ValidationError

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
- 書類に記載がない項目は null にする。推測で埋めない
- 請求書ではない書類の場合は、請求元・請求日を空にし、明細は空のリスト、金額は0にする（項目を作り出さない）"""

# APIへのリクエストは32MBまで。base64にすると約4/3倍になるので、元のファイルは24MBまでにする
MAX_FILE_BYTES = 24 * 1024 * 1024


class ExtractionError(Exception):
    """そのファイルだけの失敗（壊れたPDF、請求書ではない書類など）。残りのファイルは処理を続ける。"""


class FatalExtractionError(ExtractionError):
    """どのファイルでも同じように失敗する問題（APIキー、接続、利用料など）。一括処理を止める。"""


def describe_api_error(e: anthropic.APIError) -> ExtractionError:
    """APIのエラーを、利用者が対処できる日本語のメッセージに置き換える。"""
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return FatalExtractionError("AIのサービスに接続できませんでした。インターネット接続を確認してください")
    if isinstance(e, anthropic.AuthenticationError):
        return FatalExtractionError("APIキーが正しくありません。.env の ANTHROPIC_API_KEY を確認してください")
    if isinstance(e, anthropic.PermissionDeniedError):
        return FatalExtractionError("このAPIキーでは利用できません（権限の設定を確認してください）")
    if isinstance(e, anthropic.NotFoundError):
        return FatalExtractionError(f"モデル「{MODEL}」が見つかりません。.env の CLAUDE_MODEL を確認してください")
    if isinstance(e, anthropic.RequestTooLargeError):
        return ExtractionError("ファイルが大きすぎます（24MBまで）。ページを分けるか、画質を下げてください")
    if isinstance(e, (anthropic.RateLimitError, anthropic.OverloadedError, anthropic.InternalServerError)):
        return ExtractionError("AIのサービスが混み合っています。時間をおいて、このファイルだけ読み取り直してください")
    if isinstance(e, anthropic.APIStatusError) and e.status_code == 402:
        return FatalExtractionError("APIの利用料（クレジット）が不足しています。Anthropic のコンソールで確認してください")
    if isinstance(e, anthropic.BadRequestError):
        message = str(e)
        if "password protected" in message:
            return ExtractionError("パスワード付きのPDFは読み取れません。パスワードを外してから読み込んでください")
        if "not valid" in message or "cannot be empty" in message:
            return ExtractionError("PDFを読み込めませんでした。ファイルが壊れていないか確認してください")
        if "image" in message:
            return ExtractionError("画像を読み込めませんでした。形式（PNG / JPEG / WebP）と大きさを確認してください")
    return ExtractionError(f"読み取りに失敗しました（{type(e).__name__}）: {e}")


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
    if not data:
        raise ExtractionError("ファイルが空です")
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError(f"ファイルが大きすぎます（{len(data) / 1024 / 1024:.1f}MB。24MBまで）。ページを分けるか、画質を下げてください")
    block = _file_block(data, suffix)
    try:
        response = _request(block)
    except anthropic.APIError as e:
        raise describe_api_error(e) from e
    except ValidationError as e:
        raise ExtractionError("出力を決められた形式として読み取れませんでした") from e

    if response.stop_reason == "refusal":
        raise ExtractionError("モデルが処理を断りました（refusal）")
    if response.stop_reason == "max_tokens":
        raise ExtractionError("出力が上限に達して途中で切れました")
    if response.parsed_output is None:
        raise ExtractionError("出力を決められた形式として読み取れませんでした")

    invoice = response.parsed_output
    # 請求元も明細も金額もない＝請求書として読めていない。空の請求書を「問題なし」として通さない
    if not invoice.issuer_name.strip() and not invoice.line_items and invoice.total_amount == 0:
        raise ExtractionError("請求書の項目を読み取れませんでした。請求書以外の書類か、文字が読めない画像の可能性があります")

    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return invoice, usage


def _request(block: dict):
    return client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        messages=[{
            "role": "user",
            "content": [block, {"type": "text", "text": PROMPT}],
        }],
        output_format=Invoice,
        # 安全上の理由で断られた場合に、サーバー側で別モデルに自動で切り替える
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
