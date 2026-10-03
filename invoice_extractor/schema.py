from typing import List, Optional
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="品目名")
    quantity: float = Field(description="数量")
    unit_price: int = Field(description="単価（円、税抜）")
    amount: int = Field(description="金額（円、税抜）。書類に記載された値をそのまま入れる")
    tax_rate: int = Field(description="適用税率（%）。10 または 8（軽減税率）")


class Invoice(BaseModel):
    issuer_name: str = Field(description="請求元の会社名")
    issuer_registration_number: Optional[str] = Field(
        description="適格請求書発行事業者の登録番号（T+13桁）。記載がなければ null"
    )
    recipient_name: str = Field(description="請求先の会社名")
    invoice_number: Optional[str] = Field(description="請求書番号。記載がなければ null")
    issue_date: str = Field(description="請求日（YYYY-MM-DD）")
    due_date: Optional[str] = Field(description="支払期限（YYYY-MM-DD）。記載がなければ null")
    line_items: List[LineItem] = Field(description="明細行")
    subtotal: int = Field(description="小計（円、税抜）。書類に記載された値をそのまま入れる")
    tax_amount: int = Field(description="消費税額の合計（円）。書類に記載された値をそのまま入れる")
    total_amount: int = Field(description="請求金額（税込、円）。書類に記載された値をそのまま入れる")
    bank_account: Optional[str] = Field(description="振込先（銀行名・支店・口座種別・口座番号・名義）。記載がなければ null")
