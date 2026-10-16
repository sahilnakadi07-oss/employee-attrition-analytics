import sqlite3
from pathlib import Path
from flask import current_app, g

def get_db():
    if 'db' not in g:
        Path(current_app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

def close_db(_error=None):
    db = g.pop('db', None)
    if db is not None: db.close()

def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'HR');
    CREATE TABLE IF NOT EXISTS employees (employee_id INTEGER PRIMARY KEY AUTOINCREMENT, employee_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, department TEXT NOT NULL, designation TEXT NOT NULL, joining_date TEXT NOT NULL, salary REAL NOT NULL DEFAULT 0, age INTEGER, gender TEXT, marital_status TEXT, job_satisfaction INTEGER DEFAULT 3, work_life_balance INTEGER DEFAULT 3, overtime TEXT DEFAULT 'No', years_at_company REAL DEFAULT 0, years_since_promotion REAL DEFAULT 0, training_hours REAL DEFAULT 0, performance_rating REAL DEFAULT 3, absent_days INTEGER DEFAULT 0, attrition TEXT DEFAULT 'No', attrition_date TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS attendance (attendance_id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, month TEXT NOT NULL, present_days INTEGER NOT NULL DEFAULT 0, leave_days INTEGER NOT NULL DEFAULT 0, record_source TEXT NOT NULL DEFAULT 'manual', FOREIGN KEY(employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE, UNIQUE(employee_id, month));
    CREATE TABLE IF NOT EXISTS performance (performance_id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL, rating REAL NOT NULL DEFAULT 3, training_hours REAL NOT NULL DEFAULT 0, appraisal_score REAL NOT NULL DEFAULT 3, review_date TEXT DEFAULT CURRENT_DATE, record_source TEXT NOT NULL DEFAULT 'manual', FOREIGN KEY(employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS attrition_predictions (prediction_id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER, probability REAL NOT NULL, risk_level TEXT NOT NULL, predicted_at TEXT DEFAULT CURRENT_TIMESTAMP, model_name TEXT DEFAULT 'Random Forest', FOREIGN KEY(employee_id) REFERENCES employees(employee_id) ON DELETE SET NULL);
    ''')
    # Safe additive migrations for databases created by earlier project versions.
    employee_columns = {row['name'] for row in db.execute('PRAGMA table_info(employees)').fetchall()}
    if 'attrition_date' not in employee_columns:
        db.execute('ALTER TABLE employees ADD COLUMN attrition_date TEXT')
    for table in ('attendance', 'performance'):
        columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}
        if 'record_source' not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN record_source TEXT NOT NULL DEFAULT 'manual'")
    db.commit()
