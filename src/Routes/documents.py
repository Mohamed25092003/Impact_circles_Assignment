from fastapi import APIRouter, Depends, File, UploadFile, Query, status
from sqlalchemy.orm import Session

from Controllers import documents as documents_controller
from Controllers import expenses as expenses_controller
from Helpers.database import get_db
from Models.financial_schema import ExpenseCategory
from Models.document_schema import FinancialDocumentResponse, ExpenseSummaryResponse, UploadResponse


router = APIRouter(prefix="/documents", tags=["financial documents"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    return documents_controller.upload_pdf(file=file, db=db)


@router.get("/expenses", response_model=list[FinancialDocumentResponse])
def list_expenses(category: ExpenseCategory | None = None, processing_status: str | None = None,
                  offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return expenses_controller.list_expenses(db, category, processing_status, offset, limit)


@router.get("/summary", response_model=ExpenseSummaryResponse)
def summarize_expenses(category: ExpenseCategory | None = None, db: Session = Depends(get_db)):
    return expenses_controller.summarize_expenses(db, category)
