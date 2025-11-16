CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            valid_from_datetime TIMESTAMP NOT NULL,
            valid_to_datetime TIMESTAMP NOT NULL,
            aktiv INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );


INSERT INTO machines (name, category, aktiv,valid_from_datetime, valid_to_datetime) VALUES
    ('Traktor John Deere 5075E', 'Schlepper', 1,'2000-01-01 00:00:00', '2099-12-31 23:59:59'),
    ('Anhänger Krone TX 340', 'Anhänger', 1,'2000-01-01 00:00:00', '2099-12-31 23:59:59'),
    ('Mähwerk Kuhn GMD 8730', 'Mähwerk', 1,'2000-01-01 00:00:00', '2099-12-31 23:59:59');
    