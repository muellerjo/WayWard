CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    wegewart_id INTEGER NOT NULL,
    date DATE NOT NULL,
    village TEXT NOT NULL,
    description TEXT NOT NULL,
    hours REAL NOT NULL,
    status TEXT DEFAULT 'eingereicht',  -- 'eingereicht', 'freigegeben', 'abgelehnt'
    approved BOOLEAN DEFAULT 0,
    approved_by INTEGER,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    admin_notes TEXT,
    FOREIGN KEY (wegewart_id) REFERENCES users(id),
    FOREIGN KEY (approved_by) REFERENCES users(id)
);

CREATE INDEX idx_jobs_date ON jobs(date);
CREATE INDEX idx_jobs_village ON jobs(village);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_approved ON jobs(approved);