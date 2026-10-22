ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14, 2);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS other_charges NUMERIC(14, 2);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS project VARCHAR(255);
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS raw_extraction JSON;
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS validation_messages JSON NOT NULL DEFAULT '[]';
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS duplicate_status VARCHAR(30) NOT NULL DEFAULT 'not_checked';
ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS duplicate_basis VARCHAR(40);
ALTER TABLE financial_documents DROP CONSTRAINT IF EXISTS valid_expense_category;
UPDATE financial_documents SET category = 'operational_expenses' WHERE category = 'operations';
ALTER TABLE financial_documents ADD CONSTRAINT valid_expense_category CHECK (
    category IS NULL OR category IN ('personnel', 'travel', 'equipment', 'software', 'events', 'operational_expenses')
);
