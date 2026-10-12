"""公開デモ用。APIキーがない環境（公開サーバー）では、サンプル請求書を事前にAIで読み取った結果を使い、APIを呼ばない。"""
import os
import json
from pathlib import Path

from batch import content_hash
from extractor import ExtractionError
from schema import Invoice

DEMO_RESULTS = Path(__file__).parent / "samples" / "demo_results.json"


def is_demo_mode() -> bool:
    """DEMO_MODE=1 のとき、または APIキーが設定されていないときはデモ版として動かす。"""
    return os.getenv("DEMO_MODE") == "1" or not os.getenv("ANTHROPIC_API_KEY")


def load_results() -> dict:
    return json.loads(DEMO_RESULTS.read_text(encoding="utf-8"))


def extract(data: bytes, suffix: str) -> tuple[Invoice, dict]:
    """batch.process に渡す読み取り関数。サンプル以外のファイルは読み取らない。"""
    saved = load_results().get(content_hash(data))
    if saved is None:
        raise ExtractionError("デモ版では、サンプルの請求書だけを読み取れます")
    return Invoice(**saved["invoice"]), saved["usage"]


def make_results():
    """サンプル請求書を実際にAIで読み取り、結果を samples/demo_results.json に保存する（APIキーが必要）。"""
    from extractor import extract_invoice_bytes

    results = {}
    for path in sorted((Path(__file__).parent / "samples").glob("*.pdf")):
        data = path.read_bytes()
        invoice, usage = extract_invoice_bytes(data, path.suffix)
        results[content_hash(data)] = {"file": path.name, "invoice": invoice.model_dump(), "usage": usage}
        print(f"[info] {path.name} を読み取りました")
    DEMO_RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] {DEMO_RESULTS} に保存しました")


if __name__ == "__main__":
    make_results()
