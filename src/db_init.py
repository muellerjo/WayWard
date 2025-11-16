
from flask import g
import sqlite3

def get_db():
    """Datenbankverbindung herstellen"""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    """Datenbank initialisieren"""
    db = get_db()
    
    # Tabelle: Benutzer
    db.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            vorname TEXT NOT NULL,
            ortsteil TEXT NOT NULL,
            roles TEXT NOT NULL,
            email TEXT,
            aktiv INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES user (id)
        )
    ''')
    
    # Tabelle: Maschinen (vereinfacht - nur Name)
    db.execute('''
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bezeichnung TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabelle: Arbeitseinsätze
    db.execute('''
        CREATE TABLE IF NOT EXISTS arbeitseinsaetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            datum DATE NOT NULL,
            arbeitsstunden REAL NOT NULL,
            taetigkeitsbeschreibung TEXT NOT NULL,
            machine_used INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'erfasst',
            rejection_reason TEXT,
            check TIMESTAMP,
            checked_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES user (id),
            FOREIGN KEY (checked_by) REFERENCES user (id),
            FOREIGN KEY (machine_used) REFERENCES machines (id)
        )
    ''')
    
    # Tabelle: Maschineneinsätze
    db.execute('''
        CREATE TABLE IF NOT EXISTS maschineneinsaetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arbeitseinsatz_id INTEGER NOT NULL,
            maschine_id INTEGER NOT NULL,
            betriebsstunden REAL NOT NULL,
            leistung_ps INTEGER,
            bemerkung TEXT,
            erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (arbeitseinsatz_id) REFERENCES arbeitseinsaetze (id) ON DELETE CASCADE,
            FOREIGN KEY (maschine_id) REFERENCES maschinen (id)
        )
    ''')
    
    db.commit()
    
    # Migration: leistung_ps Feld für bestehende Datenbanken hinzufügen
    try:
        db.execute('SELECT leistung_ps FROM maschineneinsaetze LIMIT 1')
    except:
        print("Migriere Maschineneinsätze-Tabelle: Füge leistung_ps hinzu...")
        db.execute('ALTER TABLE maschineneinsaetze ADD COLUMN leistung_ps INTEGER')
        db.commit()
        print("Migration abgeschlossen!")
    
    # Standard-Admin anlegen falls nicht vorhanden
    cursor = db.execute('SELECT COUNT(*) as count FROM benutzer WHERE rolle = ?', ('admin',))
    if cursor.fetchone()['count'] == 0:
        admin_hash = generate_password_hash('admin123')
        db.execute('''
            INSERT INTO benutzer (benutzername, passwort_hash, name, vorname, ortsteil, rolle, email)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', admin_hash, 'Administrator', 'System', 'Verwaltung', 'admin', 'admin@gemeinde.de'))
        db.commit()
        print("Standard-Admin erstellt: admin / admin123 (BITTE PASSWORT ÄNDERN!)")
