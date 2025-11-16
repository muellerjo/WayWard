from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from flask import g


#import variables from config.yaml
from config import app


# ==================== Datenbank ====================
def get_db():
    """Datenbankverbindung herstellen"""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


def create_user(username, password, name, vorname, ortsteil, roles, email=None, created_by=0):
    """Benutzer erstellen"""
    db = get_db()
    password_hash = generate_password_hash(password)
    db.execute('''
        INSERT INTO user (username, password_hash, name, vorname, ortsteil, roles, email, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (username, password_hash, name, vorname, ortsteil, roles, email, created_by))
    db.commit()
    print(f"Benutzer '{username}' erstellt.")



def close_db(error):
    """Datenbankverbindung schließen"""
    db = g.pop('db', None)
    if db is not None:
        db.close()



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
            aktiv INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabelle: Arbeitseinsätze
    db.execute('''
        CREATE TABLE IF NOT EXISTS arbeitseinsaetze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            datum DATE NOT NULL,
            arbeitsstunden REAL NOT NULL,
            taetigkeitsbeschreibung TEXT NOT NULL,
            machine_used INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'erfasst',
            rejection_reason TEXT,
            checked_time TIMESTAMP,
            checked_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user (id),
            FOREIGN KEY (checked_by) REFERENCES user (id),
            FOREIGN KEY (machine_used) REFERENCES machines (id)
        )
    ''')
    
    # Tabelle Rollen
    db.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_code VARCHAR(50) UNIQUE NOT NULL,
            role_name VARCHAR(100) NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()

    #Creating Table for Jobs using external sql file
    with open('sql/db_jobs.sql', 'r') as f:
        db.executescript(f.read())
    
    # Standard-Admin anlegen falls nicht vorhanden
    cursor = db.execute("""
                        SELECT COUNT(*) as count FROM user WHERE roles LIKE '%admin%'
                        """)
    if cursor.fetchone()['count'] == 0:
        print("No User with admin role found -> Creating Default Admin")
        create_user('admin', 'admin123', 'Administrator', 'System', 'Verwaltung', 'admin', 'admin@gemeinde.de')
        create_user(username='jonas',
                    password='jonas123',
                    name='Müller',
                    vorname='Jonas',
                    ortsteil='Krenkingen',
                    roles='ortsvorsteher,wegewart',
                    email='jonas.mueller@example.com')
        #create default user for each village
        villages = ['Krenkingen','Breitenfeld']
        for village in villages:
            print(f"Create Default User for {village}")
            create_user(username=village.lower(),
                        password='password',
                        name=village,
                        vorname='System',
                        ortsteil=village,
                        roles='ortsvorsteher',)
            
    # Rollen vordefinieren
    print("Database for Roles created")
    cursor = db.execute("SELECT COUNT(*) as count FROM roles")
    if cursor.fetchone()['count'] == 0:
        db.execute("""
            INSERT INTO roles (role_code, role_name, description) VALUES
            ('wegewart', 'Wegewart', 'Verantwortlich für die Pflege der Wege'),
            ('ortsvorsteher', 'Ortsvorsteher', 'Leiter des Ortsteils'),
            ('verwaltung', 'Verwaltung', 'Mitarbeiter der Gemeindeverwaltung'),
            ('admin', 'Administrator', 'Systemadministrator mit vollen Rechten')
        """)
        db.commit()
    print("Datenbank initialisiert.")