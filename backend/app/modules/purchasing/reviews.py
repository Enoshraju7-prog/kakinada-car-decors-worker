"""Partner-reviewed ordered goods remain separate from posted stock documents."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import select
from app.infrastructure import database as db
from app.ledger import RuleError, now, identifier

class ReviewLine(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=1, max_length=200)
    amount_paise: StrictInt = Field(ge=0)
    quantity_candidate: StrictInt | None = Field(default=None,ge=1)

class OrderReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supplier: str = Field(min_length=1,max_length=200)
    invoice_number: str = Field(min_length=1,max_length=100)
    order_date: str
    buyer_gstin: str
    subtotal_paise: StrictInt = Field(ge=0)
    igst_paise: StrictInt = Field(ge=0)
    total_paise: StrictInt = Field(ge=0)
    lines: list[ReviewLine] = Field(min_length=1,max_length=100)
    unresolved: list[str]
    physical_arrival_confirmed: Literal[False] = False
    stock_posted: Literal[False] = False

    @model_validator(mode='after')
    def arithmetic(self):
        if sum(l.amount_paise for l in self.lines) != self.subtotal_paise or self.subtotal_paise+self.igst_paise != self.total_paise:
            raise ValueError('Review amounts do not reconcile')
        return self

def import_review(engine, review_id, payload, actor):
    cleaned=OrderReview.model_validate(payload).model_dump()
    with engine.begin() as conn:
        from sqlalchemy.dialects.postgresql import insert
        inserted=conn.execute(insert(db.order_reviews).values(id=review_id,payload=cleaned,actor=actor,created_at=now()).on_conflict_do_nothing().returning(db.order_reviews.c.id)).scalar()
        saved=conn.execute(select(db.order_reviews).where(db.order_reviews.c.id==review_id)).mappings().one()
        if saved['payload'] != cleaned:
            raise RuleError('Review identity already has different details; preserve the original and review a revision')
        if inserted:
            conn.execute(db.audit.insert().values(id=identifier(),actor=actor,event='order_review_import',source_id=review_id,created_at=now(),data={'stock_posted':False}))
        return dict(saved)
