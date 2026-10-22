ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES document_uploads(id) ON DELETE CASCADE;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS invoice_index INTEGER;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS source_pages JSON;
DROP INDEX IF EXISTS uq_financial_documents_sha256;
ALTER TABLE financial_documents DROP CONSTRAINT IF EXISTS financial_documents_stored_filename_key;
CREATE INDEX IF NOT EXISTS ix_financial_documents_upload_id ON financial_documents (upload_id);

INSERT INTO document_uploads (
    id, original_filename, stored_filename, size_bytes, sha256, uploaded_at,
    processing_status, extracted_text, extraction_method, page_count, extracted_at, warnings, detected_count
)
SELECT id, original_filename, stored_filename, size_bytes, sha256, uploaded_at,
       processing_status, COALESCE(extracted_text, ''), COALESCE(extraction_method, 'text'),
       COALESCE(page_count, 1), COALESCE(extracted_at, uploaded_at), '[]'::json, 1
FROM financial_documents WHERE upload_id IS NULL
ON CONFLICT (sha256) DO NOTHING;

UPDATE financial_documents f
SET upload_id = u.id, invoice_index = COALESCE(f.invoice_index, 1),
    source_pages = COALESCE(f.source_pages, (SELECT json_agg(p) FROM generate_series(1, COALESCE(f.page_count, 1)) p))
FROM document_uploads u WHERE f.upload_id IS NULL AND f.sha256 = u.sha256;
