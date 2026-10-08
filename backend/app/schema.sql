PRAGMA user_version = 1;
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 category TEXT NOT NULL, brand TEXT NOT NULL, model TEXT NOT NULL,
 compatibility TEXT NOT NULL, specification TEXT NOT NULL,
 unit TEXT NOT NULL CHECK(unit IN ('piece','pair','set','kit','carton','service')),
 kind TEXT NOT NULL CHECK(kind IN ('goods','service')),
 threshold INTEGER NOT NULL CHECK(threshold>=0), price_paise INTEGER NOT NULL CHECK(price_paise>=0),
 conversions TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('purchase','receipt','sale','return')),
 parent_id TEXT REFERENCES transactions(id), actor TEXT NOT NULL, created_at TEXT NOT NULL,
 data TEXT NOT NULL, total_paise INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchase_identity (
 supplier_key TEXT NOT NULL, financial_year TEXT NOT NULL, invoice_key TEXT NOT NULL,
 transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(id),
 PRIMARY KEY(supplier_key, financial_year, invoice_key)
);
CREATE TABLE IF NOT EXISTS lines (
 id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL REFERENCES transactions(id),
 product_id TEXT NOT NULL REFERENCES products(id), parent_line_id TEXT REFERENCES lines(id),
 quantity INTEGER NOT NULL CHECK(quantity>0), damaged INTEGER NOT NULL DEFAULT 0 CHECK(damaged>=0 AND damaged<=quantity),
 price_paise INTEGER NOT NULL CHECK(price_paise>=0), snapshot TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lines_transaction ON lines(transaction_id);
CREATE INDEX IF NOT EXISTS lines_parent ON lines(parent_line_id);
CREATE TABLE IF NOT EXISTS movements (
 id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL REFERENCES transactions(id),
 line_id TEXT NOT NULL UNIQUE REFERENCES lines(id), product_id TEXT NOT NULL REFERENCES products(id),
 available_delta INTEGER NOT NULL, damaged_delta INTEGER NOT NULL,
 actor TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS movements_product ON movements(product_id);
CREATE TABLE IF NOT EXISTS requests (
 key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS movement_no_update BEFORE UPDATE ON movements BEGIN SELECT RAISE(ABORT,'movement history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS movement_no_delete BEFORE DELETE ON movements BEGIN SELECT RAISE(ABORT,'movement history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS transaction_no_update BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT,'posted transactions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS transaction_no_delete BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT,'posted transactions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS line_no_update BEFORE UPDATE ON lines BEGIN SELECT RAISE(ABORT,'posted lines are immutable'); END;
CREATE TRIGGER IF NOT EXISTS line_no_delete BEFORE DELETE ON lines BEGIN SELECT RAISE(ABORT,'posted lines are immutable'); END;

