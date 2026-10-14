"""Additive, isolated application workflow tables."""
def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS quote_drafts(id TEXT PRIMARY KEY,inquiry_id INTEGER REFERENCES inquiries(id),quote_id INTEGER REFERENCES quotes(id),data TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,published_version_id INTEGER REFERENCES quote_versions(id),updated_at TEXT NOT NULL,actor TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS communications(id TEXT PRIMARY KEY,inquiry_id INTEGER REFERENCES inquiries(id),kind TEXT NOT NULL,direction TEXT NOT NULL,sender TEXT NOT NULL,recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,external_id TEXT UNIQUE,send_key TEXT UNIQUE,quote_id INTEGER REFERENCES quotes(id),version INTEGER,analysis TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS project_tasks(id TEXT PRIMARY KEY,inquiry_id INTEGER REFERENCES inquiries(id),communication_id TEXT REFERENCES communications(id),title TEXT NOT NULL,due_at TEXT,status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS integration_state(id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS communications_project ON communications(inquiry_id,created_at);
    CREATE INDEX IF NOT EXISTS drafts_project ON quote_drafts(inquiry_id,updated_at);
    ''')
