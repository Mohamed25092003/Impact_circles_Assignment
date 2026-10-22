from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from Models.document import FinancialDocument
from Models.financial_schema import ExpenseCategory
from Models.document_schema import ExpenseSummaryGroup, ExpenseSummaryResponse


def list_expenses(db: Session, category: ExpenseCategory | None, status: str | None, offset: int, limit: int):
    query = select(FinancialDocument)
    if category is not None:
        query = query.where(FinancialDocument.category == category.value)
    if status is not None:
        query = query.where(FinancialDocument.processing_status == status)
    return list(db.scalars(query.order_by(FinancialDocument.uploaded_at, FinancialDocument.id).offset(offset).limit(limit)))


def summarize_expenses(db: Session, category: ExpenseCategory | None = None):
    """Sum canonical, validated records in SQL using exact NUMERIC arithmetic."""
    expense = FinancialDocument
    filters = [expense.category == category.value] if category is not None else []
    eligible = [expense.processing_status == "validated", expense.duplicate_status == "checked_no_match",
                expense.duplicate_of_id.is_(None), expense.amount.is_not(None),
                expense.currency.is_not(None), expense.category.is_not(None)]
    rows = db.execute(select(expense.project, expense.category, expense.currency, func.count(), func.sum(expense.amount))
        .where(*filters, *eligible).group_by(expense.project, expense.category, expense.currency)
        .order_by(expense.project, expense.category, expense.currency)).all()
    groups = [ExpenseSummaryGroup(project=p, category=c, currency=currency, expense_count=count,
                                  total=total if isinstance(total, Decimal) else Decimal(str(total)))
              for p, c, currency, count, total in rows]
    included = sum(group.expense_count for group in groups)
    count = lambda *conditions: db.scalar(select(func.count()).select_from(expense).where(*filters, *conditions))
    return ExpenseSummaryResponse(groups=groups, included_count=included, excluded_count=count() - included,
        review_count=count(expense.processing_status == "needs_review"),
        potential_duplicate_count=count(expense.duplicate_status == "checked_match"))
