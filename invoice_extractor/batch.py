import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from extractor import ExtractionError, FatalExtractionError, extract_invoice_bytes
from schema import Invoice
from validator import duplicate_key, validate

DEFAULT_WORKERS = 4  # 同時に読み取るファイルの数。増やしすぎるとAPIの回数制限にかかりやすい


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def process(files: list[tuple[str, bytes]], workers: int = DEFAULT_WORKERS, on_done=None,
            extract=extract_invoice_bytes) -> tuple[list[dict], str | None]:
    """複数の請求書ファイルを並行して読み取り、(結果のリスト, 一括処理を止めた理由) を返す。

    - 結果の順番は files と同じ。1件ごとに {"file", "status", ...}（status は ok / warning / error / skipped）
    - 中身がまったく同じファイルは2件目以降を読み取らない（status: skipped）
    - APIキーや接続の問題（FatalExtractionError）が起きたら、まだ始めていないファイルは読み取らずに止める
    - 別のファイルに同じ請求書（請求元＋請求書番号など）があれば、後のほうに「要確認」の警告を付ける
    - on_done(終わった件数, 全体の件数, ファイル名) は、呼び出し元のスレッドで呼ばれる（画面の進み具合の更新用）
    """
    results: list[dict | None] = [None] * len(files)
    first_seen: dict[str, str] = {}
    todo = []
    for i, (name, data) in enumerate(files):
        h = content_hash(data)
        if h in first_seen:
            results[i] = {"file": name, "status": "skipped", "error": f"「{first_seen[h]}」と同じファイルのため読み取りませんでした"}
        else:
            first_seen[h] = name
            todo.append(i)

    fatal = None
    done = len(files) - len(todo)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(extract, files[i][1], _suffix(files[i][0])): i for i in todo}
        for future in as_completed(futures):
            if future.cancelled():  # 取り消したもの（CancelledError は Exception ではないので先に除く）
                continue
            i = futures[future]
            name = files[i][0]
            try:
                invoice, usage = future.result()
                results[i] = {"file": name, "invoice": invoice.model_dump(), "usage": usage}
            except FatalExtractionError as e:
                fatal = fatal or str(e)
                results[i] = {"file": name, "status": "error", "error": str(e)}
                for f in futures:  # まだ始まっていないものは取り消す（同じ理由で失敗するだけなので）
                    f.cancel()
            except ExtractionError as e:
                results[i] = {"file": name, "status": "error", "error": str(e)}
            except Exception as e:  # 想定外の失敗でも、ほかのファイルは止めない
                results[i] = {"file": name, "status": "error", "error": f"想定外のエラー（{type(e).__name__}）: {e}"}
            done += 1
            if on_done:
                on_done(done, len(files), name)

    for i, r in enumerate(results):
        if r is None:  # 取り消したもの
            results[i] = {"file": files[i][0], "status": "error", "error": f"処理を中止しました（{fatal}）"}
    add_checks(results)
    return results, fatal


def add_checks(results: list[dict]) -> None:
    """読み取れた請求書に、金額の整合性チェックと、同じ請求書の重複チェックの結果を付ける。"""
    for r in results:
        if "invoice" in r:
            r["warnings"] = validate(Invoice(**r["invoice"]))
    mark_duplicates(results)


def mark_duplicates(results: list[dict]) -> None:
    """同じ請求書が複数のファイルにあれば、後のほうに警告を付けて「要確認」にする。画面で修正した後にも呼ぶ。"""
    seen: dict[tuple, str] = {}
    for r in results:
        if "invoice" not in r:
            continue
        inv = r["invoice"]
        key = duplicate_key(inv["issuer_name"], inv["invoice_number"], inv["issue_date"], inv["total_amount"])
        if key in seen:
            r["warnings"].append(f"「{seen[key]}」と同じ請求書の可能性があります（請求元・請求書番号などが一致）")
        else:
            seen[key] = r["file"]
        r["status"] = "warning" if r["warnings"] else "ok"


def _suffix(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""
