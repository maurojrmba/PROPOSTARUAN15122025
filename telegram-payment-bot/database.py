import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "pagamentos.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                tipo TEXT NOT NULL,
                valor TEXT NOT NULL,
                descricao TEXT NOT NULL,
                obra TEXT NOT NULL,
                pix TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDENTE',
                imagem_path TEXT
            )
        """)
        conn.commit()


def inserir_pagamento(tipo, valor, descricao, obra, pix, whatsapp, imagem_path=None):
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO pagamentos (data, tipo, valor, descricao, obra, pix, whatsapp, status, imagem_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDENTE', ?)""",
            (data, tipo, valor, descricao, obra, pix, whatsapp, imagem_path),
        )
        conn.commit()


def listar_pendentes():
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM pagamentos WHERE status = 'PENDENTE' ORDER BY obra, data"
        )
        return cursor.fetchall()


def listar_todos():
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM pagamentos ORDER BY data DESC")
        return cursor.fetchall()


def marcar_como_pago(pagamento_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE pagamentos SET status = 'PAGO' WHERE id = ?", (pagamento_id,)
        )
        conn.commit()


COLUNAS = ["ID", "DATA", "TIPO", "VALOR", "DESCRIÇÃO", "OBRA", "PIX", "WHATSAPP", "STATUS", "IMAGEM"]
