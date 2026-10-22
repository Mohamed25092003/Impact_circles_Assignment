ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS subtotal NUMERIC(14, 2);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS duplicate_key VARCHAR(64);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS financial_evidence JSON;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS extraction_model VARCHAR(100);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_documents_duplicate_key ON financial_documents (duplicate_key);
