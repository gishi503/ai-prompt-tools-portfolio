from typing import Literal
from pydantic import BaseModel, Field

Attention = Literal["高", "中", "低"]


class ReportSummary(BaseModel):
    """日報1通をAIで整理した結果。日本の担当者向けのまとめの1人分になる。"""
    summary: str = Field(description="日本語の要約（80字以内、です・ます調）")
    done: list[str] = Field(description="今日終わったこと（日本語、1件40字以内）")
    in_progress: list[str] = Field(description="途中のこと（進み具合が書かれていれば入れる）")
    risks: list[str] = Field(description="遅れ・問題・遅れそうなこと。期限への影響があれば書く。なければ空のリスト")
    questions: list[str] = Field(description="スタッフが日報の中で日本側に聞いたこと・頼んだことだけ。返事の期限があれば入れる。頼まれていない対応は入れない。なければ空のリスト")
    unclear: list[str] = Field(description="日本側の指示があいまいで、スタッフが迷っている点。なければ空のリスト")
    absence: list[str] = Field(description="休み・遅刻・稼働できない予定（日付つき）。なければ空のリスト")
    attention: Attention = Field(description="日本側の対応の必要度。高＝今日〜数日内に判断・返事が必要、または期限に遅れそう／中＝確認が必要／低＝読むだけでよい")
