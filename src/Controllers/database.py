from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from Models import document  # noqa: F401 - registers the database model
from Models.base import Base
from Models.constants import FINANCIAL_SCHEMA_MIGRATION, MULTI_INVOICE_MIGRATION, OCR_SCHEMA_MIGRATION, TRACKER_SCHEMA_MIGRATION
from Models.upload import DocumentUpload


def initialize_database(engine: Engine) -> None:
    if engine.dialect.name == "postgresql":
        # Upgrade existing tables before create_all inspects the new indexes.
        with engine.begin() as connection:
            if inspect(connection).has_table("financial_documents"):
                connection.exec_driver_sql(OCR_SCHEMA_MIGRATION.read_text())
                connection.exec_driver_sql(FINANCIAL_SCHEMA_MIGRATION.read_text())
                DocumentUpload.__table__.create(bind=connection, checkfirst=True)
                connection.exec_driver_sql(MULTI_INVOICE_MIGRATION.read_text())
                connection.exec_driver_sql(TRACKER_SCHEMA_MIGRATION.read_text())
    Base.metadata.create_all(bind=engine)
