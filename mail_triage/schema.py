from typing import Literal
from pydantic import BaseModel, Field

Category = Literal["問い合わせ", "日程調整", "書類・手続き", "請求・支払い", "案内・お知らせ", "その他"]
Urgency = Literal["高", "中", "低"]

CATEGORIES: list[str] = list(Category.__args__)
URGENCIES: list[str] = list(Urgency.__args__)


class MailSummary(BaseModel):
    """メール1通をAIで整理した結果。Notionの1行・Slackの1通知になる。"""
    category: Category = Field(description="メールの種類")
    urgency: Urgency = Field(description="対応の緊急度。高＝期限が2週間以内か、放置すると支障が出る／中＝返信や対応が必要／低＝読むだけでよい")
    summary: str = Field(description="要約（100字以内、です・ます調）")
    action_items: list[str] = Field(description="こちらがやるべきこと（なければ空のリスト）。1件30字以内")
    due_date: str | None = Field(description="対応の期限（YYYY-MM-DD）。本文に書かれていなければ null")
    sender_company: str | None = Field(description="差出人の会社・団体名。分からなければ null")


def display_sender(mail, s: MailSummary) -> str:
    """差出人の表示名。会社名が名前に含まれていなければ「名前（会社名）」にする。"""
    company = s.sender_company
    if company and company not in mail.sender_name:
        return f"{mail.sender_name}（{company}）"
    return mail.sender_name
