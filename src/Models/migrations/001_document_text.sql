ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS extracted_text TEXT;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS page_count INTEGER;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS processing_error TEXT;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;
