# db.py
"""Acceso a la base de datos SQLite: usuarios y documentos generados.

Se usa sqlite3 directo (sin ORM) para mantener la misma filosofía del resto
del proyecto: módulos simples, sin dependencias nuevas que no hagan falta.
La conexión vive en el contexto de la petición de Flask (flask.g), igual
que recomienda la documentación de Flask para sqlite3.
"""

import os
import sqlite3
import logging

from flask import g

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get('DATABASE_PATH', 'gullieth.db')

# Correos que se marcan como administradores automáticamente al registrarse
# o iniciar sesión (no hay UI para promover usuarios a admin: se resuelve
# por variable de entorno). Formato: "correo1@x.com,correo2@y.com".
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get('ADMIN_EMAILS', '').split(',')
    if e.strip()
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT,
    google_id     TEXT UNIQUE,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    plan          TEXT NOT NULL DEFAULT 'free',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    title        TEXT NOT NULL,
    doc_type     TEXT NOT NULL,
    tokens_used  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
"""


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(_exc=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


def _sync_admin_flag(db, user_id, email):
    """Si el correo está en ADMIN_EMAILS, asegura is_admin=1 para ese usuario."""
    if email.lower().strip() in ADMIN_EMAILS:
        db.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (user_id,))
        db.commit()


def create_user(email, name, password_hash=None, google_id=None):
    email = email.strip().lower()
    db = get_db()
    cur = db.execute(
        'INSERT INTO users (email, name, password_hash, google_id) VALUES (?, ?, ?, ?)',
        (email, name, password_hash, google_id),
    )
    db.commit()
    user_id = cur.lastrowid
    _sync_admin_flag(db, user_id, email)
    return user_id


def get_user_by_email(email):
    db = get_db()
    return db.execute(
        'SELECT * FROM users WHERE email = ?', (email.strip().lower(),)
    ).fetchone()


def get_user_by_google_id(google_id):
    db = get_db()
    return db.execute('SELECT * FROM users WHERE google_id = ?', (google_id,)).fetchone()


def get_user_by_id(user_id):
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def link_google_id(user_id, google_id):
    db = get_db()
    db.execute('UPDATE users SET google_id = ? WHERE id = ?', (google_id, user_id))
    db.commit()


def touch_admin_status(user):
    """Vuelve a chequear ADMIN_EMAILS en cada login, por si se agregó el
    correo a la variable de entorno después de que el usuario ya existía."""
    if user is not None and not user['is_admin']:
        _sync_admin_flag(get_db(), user['id'], user['email'])


def record_document(user_id, title, doc_type, tokens_used):
    db = get_db()
    db.execute(
        'INSERT INTO documents (user_id, title, doc_type, tokens_used) VALUES (?, ?, ?, ?)',
        (user_id, title, doc_type, tokens_used),
    )
    db.commit()


def list_users():
    db = get_db()
    return db.execute("""
        SELECT u.*,
               COUNT(d.id)                  AS documents_count,
               COALESCE(SUM(d.tokens_used), 0) AS tokens_used
        FROM users u
        LEFT JOIN documents d ON d.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """).fetchall()


def list_documents(limit=200):
    db = get_db()
    return db.execute("""
        SELECT d.*, u.email AS user_email, u.name AS user_name
        FROM documents d
        JOIN users u ON u.id = d.user_id
        ORDER BY d.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()


def get_stats():
    db = get_db()
    return db.execute("""
        SELECT
            (SELECT COUNT(*) FROM users)                        AS total_users,
            (SELECT COUNT(*) FROM documents)                    AS total_documents,
            (SELECT COALESCE(SUM(tokens_used), 0) FROM documents) AS total_tokens
    """).fetchone()
