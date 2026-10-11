import os
import sys
import json
from typing import Literal

from anthropic import Anthropic, APIError
from dotenv import load_dotenv
from pydantic import BaseModel, Field, create_model

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))  # 429・5xx・接続エラーはSDKが自動で再試行する
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
BATCH_SIZE = 20  # 1回のリクエストで分類する回答の数（短い回答をまとめて送り、回数と料金を抑える）
OTHER = "その他"
SENTIMENT_LABEL = {"positive": "良い", "negative": "悪い", "neutral": "どちらでもない"}


class ClassificationError(Exception):
    pass


def _parse(prompt: str, output_format, max_tokens: int = 16000):
    """構造化出力で1回呼び出し、(パース結果, トークン使用量) を返す。"""
    response = client.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        output_config={"effort": "low"},  # 分類のような単純な作業は low で十分
        messages=[{"role": "user", "content": prompt}],
        output_format=output_format,
        # 安全上の理由で断られた場合に、サーバー側で別モデルに自動で切り替える
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise ClassificationError("モデルが処理を断りました（refusal）")
    if response.stop_reason == "max_tokens":
        raise ClassificationError("出力が上限に達して途中で切れました")
    if response.parsed_output is None:
        raise ClassificationError("出力を決められた形式として読み取れませんでした")
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return response.parsed_output, usage


# ---------- 分類案の作成（おまかせの場合） ----------

class CategoryIdea(BaseModel):
    name: str = Field(description="分類名（10文字以内の短い名詞）")
    description: str = Field(description="どんな回答が入るかの説明（1文）")


class CategoryIdeas(BaseModel):
    categories: list[CategoryIdea]


def suggest_categories(texts: list[str], n: int = 6, purpose: str = "") -> tuple[list[dict], dict]:
    """回答の一部を読ませて、分類の案を作る。お客様に確認してもらってから全件の分類に使う。"""
    listing = "\n".join(f"- {t}" for t in texts)
    prompt = f"""次はアンケート・口コミの自由記述の一部です。全体を分類するための分類項目を{n}個前後で提案してください。

ルール：
- 項目どうしが重ならないようにする
- 「{OTHER}」は自動で追加するので、提案には含めない
- 分類名は短い名詞にする（例：「接客」「価格」「待ち時間」）
{f"- 分析の目的：{purpose}" if purpose else ""}

回答：
{listing}"""
    ideas, usage = _parse(prompt, CategoryIdeas, max_tokens=4000)
    return [c.model_dump() for c in ideas.categories], usage


# ---------- 全件の分類 ----------

def _result_models(categories: list[str]):
    """指定された分類名だけを選べるスキーマを作る（それ以外の分類名は返ってこない）。"""
    Category = Literal[tuple([c for c in categories if c != OTHER] + [OTHER])]
    Item = create_model(
        "ClassifiedItem",
        id=(int, Field(description="回答の番号")),
        category=(Category, Field(description=f"最も当てはまる分類。どれにも当てはまらなければ「{OTHER}」")),
        sentiment=(Literal["positive", "negative", "neutral"], Field(description="回答の感情")),
        summary=(str, Field(description="回答のひと言要約（30文字以内）")),
    )
    return create_model("ClassifiedBatch", items=(list[Item], ...))


def _classify_batch(batch: list[tuple[int, str]], categories: list[dict], model) -> tuple[dict[int, dict], dict]:
    category_lines = "\n".join(f"- {c['name']}：{c.get('description', '')}" for c in categories)
    answers = "\n".join(json.dumps({"id": i, "text": t}, ensure_ascii=False) for i, t in batch)
    prompt = f"""次の回答を1件ずつ分類してください。すべての id について1件ずつ結果を返してください。

分類項目：
{category_lines}
- {OTHER}：上のどれにも当てはまらないもの

ルール：
- 複数の内容に触れている回答は、いちばん強く述べている内容で分類する
- 回答に書かれていないことを推測しない
- summary は回答の言葉を使って30文字以内でまとめる

回答（1行に1件のJSON）：
{answers}"""
    parsed, usage = _parse(prompt, model)
    return {item.id: item.model_dump() for item in parsed.items}, usage


def classify(texts: list[str], categories: list[dict], log=print) -> tuple[list[dict], dict]:
    """全件を分類して、回答ごとの結果（順番は texts と同じ）とトークン使用量の合計を返す。

    - BATCH_SIZE 件ずつまとめて送る
    - 返ってこなかった回答は1件ずつ送り直す
    - それでも失敗した回答は error を付けて残し、全体は止めない
    """
    model = _result_models([c["name"] for c in categories])
    total = {"input_tokens": 0, "output_tokens": 0}
    results: dict[int, dict] = {}

    def add(usage):
        for k in total:
            total[k] += usage[k]

    indexed = [(i, t) for i, t in enumerate(texts) if t.strip()]
    for i, t in enumerate(texts):
        if not t.strip():
            results[i] = {"error": "空欄"}

    batches = [indexed[s:s + BATCH_SIZE] for s in range(0, len(indexed), BATCH_SIZE)]
    for n, batch in enumerate(batches, start=1):
        log(f"[info] 分類中 {n}/{len(batches)}（{batch[0][0] + 1}〜{batch[-1][0] + 1}件目）")
        try:
            got, usage = _classify_batch(batch, categories, model)
            add(usage)
        except (ClassificationError, APIError) as e:
            log(f"[warn] まとめて分類できませんでした: {e}。1件ずつ送り直します")
            got = {}
        for i, t in batch:
            if i in got:
                results[i] = got[i]
                continue
            try:
                one, usage = _classify_batch([(i, t)], categories, model)
                add(usage)
                results[i] = one.get(i, {"error": "結果が返ってきませんでした"})
            except (ClassificationError, APIError) as e:
                results[i] = {"error": str(e)}

    rows = []
    for i, t in enumerate(texts):
        r = results[i]
        rows.append({
            "text": t,
            "category": r.get("category"),
            "sentiment": SENTIMENT_LABEL.get(r.get("sentiment")),
            "summary": r.get("summary"),
            "error": r.get("error", ""),
        })
    return rows, total


# ---------- 代表的な声 ----------

class Picks(BaseModel):
    ids: list[int] = Field(description="選んだ回答の番号")


def pick_representatives(rows: list[dict], category: str, n: int = 3, limit: int = 100) -> tuple[list[int], dict]:
    """分類ごとに、内容がよく伝わる回答を n 件選ぶ。返り値は rows のインデックス。"""
    candidates = [(i, r["text"]) for i, r in enumerate(rows) if r["category"] == category][:limit]
    if len(candidates) <= n:
        return [i for i, _ in candidates], {"input_tokens": 0, "output_tokens": 0}
    answers = "\n".join(json.dumps({"id": i, "text": t}, ensure_ascii=False) for i, t in candidates)
    prompt = f"""次は「{category}」に分類された回答です。この分類でよく出ている意見が伝わる回答を{n}件選び、id を返してください。
似た内容ばかりにならないようにし、具体的に書かれているものを優先してください。

{answers}"""
    picks, usage = _parse(prompt, Picks, max_tokens=4000)
    valid = {i for i, _ in candidates}
    return [i for i in picks.ids if i in valid][:n], usage


def estimate_note(usage: dict) -> str:
    return f"トークン使用量：入力 {usage['input_tokens']:,} / 出力 {usage['output_tokens']:,}（モデル：{MODEL}）"


if __name__ == "__main__":
    print("このファイルは survey_report.py から使います", file=sys.stderr)
