import os
import io
import smtplib
from datetime import datetime
from email.message import EmailMessage

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from database import listar_pendentes, COLUNAS

LARANJA = colors.HexColor("#E65100")
LARANJA_CLARO = colors.HexColor("#FFF3E0")
CINZA = colors.HexColor("#F5F5F5")


# ──────────────────────────────────────────────
# Excel
# ──────────────────────────────────────────────
def gerar_excel() -> bytes:
    registros = listar_pendentes()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pagamentos Pendentes"

    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill("solid", fgColor="E65100")
    section_fill = PatternFill("solid", fgColor="FFF3E0")
    thin = Side(style="thin", color="BDBDBD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A1:L1")
    titulo = ws["A1"]
    titulo.value = f"RELATÓRIO DE PAGAMENTOS PENDENTES — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    titulo.font = Font(bold=True, size=12, color="E65100")
    titulo.alignment = center
    ws.row_dimensions[1].height = 26

    ws.append([])
    ws.append(COLUNAS)
    for col_idx, col_name in enumerate(COLUNAS, start=1):
        cell = ws.cell(row=3, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    obras: dict[str, list] = {}
    for r in registros:
        obra = r[7]  # coluna obra
        obras.setdefault(obra, []).append(r)

    row_num = 4
    total_geral = 0.0

    for obra, itens in obras.items():
        ws.merge_cells(f"A{row_num}:L{row_num}")
        cell = ws.cell(row=row_num, column=1)
        cell.value = f"  {obra}"
        cell.font = Font(bold=True, size=10, color="BF360C")
        cell.fill = section_fill
        cell.alignment = Alignment(vertical="center")
        ws.row_dimensions[row_num].height = 20
        row_num += 1

        subtotal = 0.0
        for item in itens:
            for col_idx, value in enumerate(item, start=1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.value = value
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            try:
                valor_str = str(item[5]).replace("R$", "").replace(".", "").replace(",", ".").strip()
                subtotal += float(valor_str)
            except ValueError:
                pass
            row_num += 1

        ws.merge_cells(f"A{row_num}:E{row_num}")
        ws.cell(row=row_num, column=1).value = f"SUBTOTAL — {obra}"
        ws.cell(row=row_num, column=1).font = Font(bold=True)
        ws.cell(row=row_num, column=6).value = _fmt_valor(subtotal)
        ws.cell(row=row_num, column=6).font = Font(bold=True)
        total_geral += subtotal
        row_num += 2

    ws.merge_cells(f"A{row_num}:E{row_num}")
    ws.cell(row=row_num, column=1).value = "TOTAL GERAL"
    ws.cell(row=row_num, column=1).font = Font(bold=True, size=11, color="FFFFFF")
    ws.cell(row=row_num, column=1).fill = PatternFill("solid", fgColor="E65100")
    ws.cell(row=row_num, column=6).value = _fmt_valor(total_geral)
    ws.cell(row=row_num, column=6).font = Font(bold=True, size=11, color="FFFFFF")
    ws.cell(row=row_num, column=6).fill = PatternFill("solid", fgColor="E65100")

    larguras = [5, 14, 16, 14, 12, 12, 36, 22, 22, 16, 10, 18]
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────
# PDF
# ──────────────────────────────────────────────
def gerar_pdf() -> bytes:
    registros = listar_pendentes()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elementos = []

    titulo_style = ParagraphStyle("titulo", parent=styles["Title"],
                                  textColor=LARANJA, fontSize=14, spaceAfter=12)
    elementos.append(Paragraph(
        f"RELATÓRIO DE PAGAMENTOS PENDENTES — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        titulo_style,
    ))
    elementos.append(Spacer(1, 0.3*cm))

    obras: dict[str, list] = {}
    for r in registros:
        obras.setdefault(r[7], []).append(r)

    total_geral = 0.0
    cabecalho = ["ID", "DATA", "NOME", "TELEFONE", "TIPO", "VALOR", "DESCRIÇÃO", "OBRA", "PIX", "WHATSAPP", "STATUS"]

    for obra, itens in obras.items():
        elementos.append(Paragraph(obra, ParagraphStyle(
            "obra", parent=styles["Normal"], textColor=LARANJA,
            fontSize=11, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=4,
        )))

        dados = [cabecalho]
        subtotal = 0.0
        for item in itens:
            linha = [str(v) if v else "" for v in item[:11]]
            dados.append(linha)
            try:
                subtotal += float(str(item[5]).replace("R$","").replace(".","").replace(",",".").strip())
            except ValueError:
                pass

        total_geral += subtotal
        dados.append(["", "", "", "", f"SUBTOTAL", _fmt_valor(subtotal), "", "", "", "", ""])

        col_widths = [1*cm, 3*cm, 4*cm, 3.2*cm, 2.8*cm, 2.5*cm, 6*cm, 4.5*cm, 4*cm, 3*cm, 2.2*cm]
        tabela = Table(dados, colWidths=col_widths, repeatRows=1)
        tabela.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LARANJA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CINZA]),
            ("BACKGROUND", (0, -1), (-1, -1), LARANJA_CLARO),
            ("FONTNAME", (4, -1), (5, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDBDBD")),
            ("WORDWRAP", (6, 1), (6, -1), True),
        ]))
        elementos.append(tabela)
        elementos.append(Spacer(1, 0.4*cm))

    # Total geral
    total_table = Table([["TOTAL GERAL", _fmt_valor(total_geral)]], colWidths=[8*cm, 4*cm])
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LARANJA),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWHEIGHT", (0, 0), (-1, -1), 22),
    ]))
    elementos.append(total_table)
    doc.build(elementos)
    return buf.getvalue()


# ──────────────────────────────────────────────
# E-mail via Gmail
# ──────────────────────────────────────────────
def enviar_email(assunto: str, corpo: str, excel_bytes: bytes, pdf_bytes: bytes):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_app_password = os.environ["GMAIL_APP_PASSWORD"]
    destinatario = os.environ["EMAIL_DESTINATARIO"]
    data_str = datetime.now().strftime("%d%m%Y_%H%M")

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = gmail_user
    msg["To"] = destinatario
    msg.set_content(corpo)

    msg.add_attachment(excel_bytes, maintype="application",
                       subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       filename=f"relatorio_{data_str}.xlsx")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf",
                       filename=f"relatorio_{data_str}.pdf")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(msg)


def enviar_relatorio_email(novo_lancamento: dict | None = None):
    """Gera PDF + Excel e envia por e-mail. Chamado após cada lançamento e toda sexta."""
    excel_bytes = gerar_excel()
    pdf_bytes = gerar_pdf()

    if novo_lancamento:
        assunto = f"[NOVO LANÇAMENTO] {novo_lancamento['tipo']} — {novo_lancamento['obra']} — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        corpo = (
            f"Novo lançamento registrado:\n\n"
            f"NOME: {novo_lancamento.get('nome', '-')}\n"
            f"TELEFONE: {novo_lancamento.get('telefone', '-')}\n"
            f"TIPO: {novo_lancamento['tipo']}\n"
            f"VALOR: R$ {novo_lancamento['valor']}\n"
            f"DESCRIÇÃO: {novo_lancamento['descricao']}\n"
            f"OBRA: {novo_lancamento['obra']}\n"
            f"PIX: {novo_lancamento['pix']}\n\n"
            f"Segue o relatório atualizado em anexo (PDF e Excel)."
        )
    else:
        assunto = f"[RELATÓRIO SEMANAL] Pagamentos Pendentes — {datetime.now().strftime('%d/%m/%Y')}"
        corpo = "Segue o relatório semanal de pagamentos pendentes em anexo (PDF e Excel)."

    enviar_email(assunto, corpo, excel_bytes, pdf_bytes)


# ──────────────────────────────────────────────
# Agendamento sexta-feira
# ──────────────────────────────────────────────
def agendar_relatorio_sexta(app, admin_chat_id: int):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    async def enviar():
        excel_bytes = gerar_excel()
        nome = f"relatorio_{datetime.now().strftime('%d%m%Y')}.xlsx"
        await app.bot.send_document(
            chat_id=admin_chat_id,
            document=excel_bytes,
            filename=nome,
            caption=f"📊 RELATÓRIO DE PAGAMENTOS PENDENTES — {datetime.now().strftime('%d/%m/%Y')}",
        )

    scheduler.add_job(enviar, "cron", day_of_week="fri", hour=18, minute=0)
    scheduler.start()
    return scheduler


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _fmt_valor(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
