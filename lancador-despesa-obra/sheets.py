import os
import gspread
from google.oauth2.service_account import Credentials
from database import listar_todos, COLUNAS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheet():
    creds = Credentials.from_service_account_file(
        os.path.join(os.path.dirname(__file__), "credentials.json"),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    return client.open_by_key(sheet_id).sheet1


def sincronizar_planilha():
    """Apaga a planilha e reescreve todos os registros do banco."""
    sheet = get_sheet()
    sheet.clear()
    sheet.append_row(COLUNAS)
    registros = listar_todos()
    if registros:
        sheet.append_rows([list(r) for r in registros])
