import os
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from database import init_db, inserir_pagamento
from vision import extrair_dados_imagem, salvar_imagem
from report import gerar_excel, gerar_pdf, enviar_relatorio_email, agendar_relatorio_sexta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados da conversa
(
    AGUARDA_NOME,
    AGUARDA_TELEFONE,
    INICIO,
    AGUARDA_TIPO,
    AGUARDA_VALOR,
    AGUARDA_DESCRICAO,
    AGUARDA_OBRA,
    AGUARDA_PIX,
    AGUARDA_WHATSAPP_COMPROVANTE,
    CONFIRMA,
) = range(10)

OBRAS = [
    "OBRA POSTO GOL",
    "OBRA CASA VENDA IPIRANGA",
    "OBRA HIPERPLAST",
]

TIPOS = ["MÃO DE OBRA", "MATERIAL", "EQUIPAMENTO"]

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))


def teclado_tipos():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=f"tipo:{t}")] for t in TIPOS]
    )


def teclado_obras():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(o, callback_data=f"obra:{o}")] for o in OBRAS]
    )


def teclado_confirma():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ CONFIRMAR", callback_data="confirmar"),
        InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar"),
    ]])


def resumo(ctx) -> str:
    d = ctx.user_data
    return (
        f"📋 *RESUMO DO LANÇAMENTO*\n\n"
        f"*NOME:* {d.get('nome', '-')}\n"
        f"*TELEFONE:* {d.get('telefone', '-')}\n"
        f"*TIPO:* {d.get('tipo', '-')}\n"
        f"*VALOR:* R$ {d.get('valor', '-')}\n"
        f"*DESCRIÇÃO:* {d.get('descricao', '-')}\n"
        f"*OBRA:* {d.get('obra', '-')}\n"
        f"*PIX:* {d.get('pix', '-')}\n"
        f"*WHATSAPP COMPROVANTE:* {d.get('whatsapp_comprovante', '-')}\n"
    )


# ──────────────────────────────────────────────
# /start — pede nome
# ──────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👷 *BEM-VINDO AO LANÇADOR DE DESPESAS!*\n\n"
        "QUAL É O SEU *NOME COMPLETO*?",
        parse_mode="Markdown",
    )
    return AGUARDA_NOME


async def receber_nome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["nome"] = update.message.text.strip().upper()
    await update.message.reply_text("📱 QUAL É O SEU *NÚMERO DE TELEFONE* (com DDD)?",
                                    parse_mode="Markdown")
    return AGUARDA_TELEFONE


async def receber_telefone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["telefone"] = update.message.text.strip()
    await update.message.reply_text(
        "ENVIE UMA *FOTO DA NOTA FISCAL/COMPROVANTE*\n"
        "OU ESCOLHA O TIPO DE PAGAMENTO:",
        parse_mode="Markdown",
        reply_markup=teclado_tipos(),
    )
    return INICIO


# ──────────────────────────────────────────────
# Recebeu foto (nota fiscal)
# ──────────────────────────────────────────────
async def receber_foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Se ainda não temos nome, pede primeiro
    if not ctx.user_data.get("nome"):
        await update.message.reply_text(
            "ANTES DE CONTINUAR, QUAL É O SEU *NOME COMPLETO*?",
            parse_mode="Markdown",
        )
        return AGUARDA_NOME

    msg = await update.message.reply_text("🔍 ANALISANDO A IMAGEM, AGUARDE...")
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    imagem_bytes = bytes(await file.download_as_bytearray())

    imagem_path = salvar_imagem(imagem_bytes, update.effective_user.id)
    ctx.user_data["imagem_path"] = imagem_path

    try:
        dados = extrair_dados_imagem(imagem_bytes)
    except Exception as e:
        logger.error(f"Erro na extração de imagem: {e}")
        dados = {}

    await msg.delete()

    for campo in ("tipo", "valor", "descricao"):
        if dados.get(campo):
            ctx.user_data[campo] = dados[campo]

    extraido = ""
    if dados.get("tipo"):
        extraido += f"*TIPO:* {dados['tipo']}\n"
    if dados.get("valor"):
        extraido += f"*VALOR:* R$ {dados['valor']}\n"
    if dados.get("descricao"):
        extraido += f"*DESCRIÇÃO:* {dados['descricao']}\n"

    if extraido:
        await update.message.reply_text(
            f"✅ *DADOS EXTRAÍDOS DA IMAGEM:*\n\n{extraido}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("⚠️ NÃO FOI POSSÍVEL EXTRAIR OS DADOS. PREENCHA MANUALMENTE.")

    return await _proximo_campo(update, ctx)


async def _proximo_campo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.user_data
    send = update.message.reply_text if update.message else update.callback_query.message.reply_text

    if not d.get("tipo"):
        await send("QUAL O TIPO DE PAGAMENTO?", reply_markup=teclado_tipos())
        return AGUARDA_TIPO
    if not d.get("valor"):
        await send("💰 QUAL O VALOR? (ex: 1.500,00)")
        return AGUARDA_VALOR
    if not d.get("descricao"):
        await send("📝 QUAL A DESCRIÇÃO COMPLETA DO SERVIÇO/MATERIAL/EQUIPAMENTO?")
        return AGUARDA_DESCRICAO
    if not d.get("obra"):
        await send("🏗️ AONDE FOI EMPREGADO OU PRESTADO?", reply_markup=teclado_obras())
        return AGUARDA_OBRA
    if not d.get("pix"):
        await send("💳 QUAL A CHAVE PIX PARA PAGAMENTO?")
        return AGUARDA_PIX
    if not d.get("whatsapp_comprovante"):
        await send("📱 QUAL O NÚMERO DO WHATSAPP PARA ENVIO DO COMPROVANTE?")
        return AGUARDA_WHATSAPP_COMPROVANTE

    await send(resumo(ctx), parse_mode="Markdown", reply_markup=teclado_confirma())
    return CONFIRMA


# ──────────────────────────────────────────────
# Callbacks botões inline
# ──────────────────────────────────────────────
async def callback_tipo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["tipo"] = query.data.split(":", 1)[1]
    await query.edit_message_text(f"✅ TIPO: *{ctx.user_data['tipo']}*", parse_mode="Markdown")
    await query.message.reply_text("💰 QUAL O VALOR? (ex: 1.500,00)")
    return AGUARDA_VALOR


async def callback_obra(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["obra"] = query.data.split(":", 1)[1]
    await query.edit_message_text(f"✅ OBRA: *{ctx.user_data['obra']}*", parse_mode="Markdown")
    await query.message.reply_text("💳 QUAL A CHAVE PIX PARA PAGAMENTO?")
    return AGUARDA_PIX


async def callback_confirmar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = ctx.user_data

    inserir_pagamento(
        nome=d["nome"],
        telefone=d["telefone"],
        tipo=d["tipo"],
        valor=d["valor"],
        descricao=d["descricao"],
        obra=d["obra"],
        pix=d["pix"],
        whatsapp_comprovante=d["whatsapp_comprovante"],
        imagem_path=d.get("imagem_path"),
    )

    await query.edit_message_text(
        "✅ *LANÇAMENTO REGISTRADO COM SUCESSO!*\n\nOBRIGADO. AS INFORMAÇÕES FORAM SALVAS.",
        parse_mode="Markdown",
    )

    # Envia relatório no Telegram (admin) + e-mail em background
    lancamento = dict(d)
    app = ctx.application
    threading.Thread(
        target=_notificar_background, args=(app, lancamento), daemon=True
    ).start()

    ctx.user_data.clear()
    return ConversationHandler.END


def _notificar_background(app, lancamento: dict):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_enviar_notificacoes(app, lancamento))
    loop.close()


async def _enviar_notificacoes(app, lancamento: dict):
    from datetime import datetime

    # Monta mensagem resumo para o Telegram do admin
    texto = (
        f"🔔 *NOVO LANÇAMENTO REGISTRADO*\n\n"
        f"*NOME:* {lancamento.get('nome', '-')}\n"
        f"*TELEFONE:* {lancamento.get('telefone', '-')}\n"
        f"*TIPO:* {lancamento.get('tipo', '-')}\n"
        f"*VALOR:* R$ {lancamento.get('valor', '-')}\n"
        f"*DESCRIÇÃO:* {lancamento.get('descricao', '-')}\n"
        f"*OBRA:* {lancamento.get('obra', '-')}\n"
        f"*PIX:* {lancamento.get('pix', '-')}\n"
        f"*WHATSAPP:* {lancamento.get('whatsapp_comprovante', '-')}\n"
    )

    try:
        excel_bytes = gerar_excel()
        pdf_bytes = gerar_pdf()
        data_str = datetime.now().strftime("%d%m%Y_%H%M")

        await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=texto, parse_mode="Markdown")
        await app.bot.send_document(
            chat_id=ADMIN_CHAT_ID,
            document=excel_bytes,
            filename=f"relatorio_{data_str}.xlsx",
            caption="📊 Relatório atualizado — Excel",
        )
        await app.bot.send_document(
            chat_id=ADMIN_CHAT_ID,
            document=pdf_bytes,
            filename=f"relatorio_{data_str}.pdf",
            caption="📄 Relatório atualizado — PDF",
        )
        logger.info("Relatório enviado no Telegram do admin.")
    except Exception as e:
        logger.error(f"Erro ao enviar no Telegram: {e}")

    # E-mail
    try:
        enviar_relatorio_email(novo_lancamento=lancamento)
        logger.info("E-mail enviado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail: {e}")


async def callback_cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text("❌ LANÇAMENTO CANCELADO.")
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Handlers de texto
# ──────────────────────────────────────────────
async def receber_valor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["valor"] = update.message.text.strip()
    await update.message.reply_text("📝 QUAL A DESCRIÇÃO COMPLETA DO SERVIÇO/MATERIAL/EQUIPAMENTO?")
    return AGUARDA_DESCRICAO


async def receber_descricao(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["descricao"] = update.message.text.strip()
    await update.message.reply_text("🏗️ AONDE FOI EMPREGADO OU PRESTADO?", reply_markup=teclado_obras())
    return AGUARDA_OBRA


async def receber_pix(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["pix"] = update.message.text.strip()
    await update.message.reply_text("📱 QUAL O NÚMERO DO WHATSAPP PARA ENVIO DO COMPROVANTE?")
    return AGUARDA_WHATSAPP_COMPROVANTE


async def receber_whatsapp_comprovante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["whatsapp_comprovante"] = update.message.text.strip()
    await update.message.reply_text(resumo(ctx), parse_mode="Markdown", reply_markup=teclado_confirma())
    return CONFIRMA


# ──────────────────────────────────────────────
# /relatorio — apenas admin
# ──────────────────────────────────────────────
async def cmd_relatorio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ ACESSO NEGADO.")
        return
    await update.message.reply_text("⏳ GERANDO RELATÓRIO...")
    excel_bytes = gerar_excel()
    pdf_bytes = gerar_pdf()
    from datetime import datetime
    data_str = datetime.now().strftime("%d%m%Y")
    await update.message.reply_document(document=excel_bytes,
                                        filename=f"relatorio_{data_str}.xlsx",
                                        caption="📊 Relatório Excel")
    await update.message.reply_document(document=pdf_bytes,
                                        filename=f"relatorio_{data_str}.pdf",
                                        caption="📄 Relatório PDF")


async def cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ OPERAÇÃO CANCELADA. USE /start PARA COMEÇAR.")
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    init_db()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.PHOTO, receber_foto),
            CallbackQueryHandler(callback_tipo, pattern="^tipo:"),
        ],
        states={
            AGUARDA_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            AGUARDA_TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone)],
            INICIO: [
                MessageHandler(filters.PHOTO, receber_foto),
                CallbackQueryHandler(callback_tipo, pattern="^tipo:"),
            ],
            AGUARDA_TIPO: [CallbackQueryHandler(callback_tipo, pattern="^tipo:")],
            AGUARDA_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            AGUARDA_DESCRICAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_descricao)],
            AGUARDA_OBRA: [CallbackQueryHandler(callback_obra, pattern="^obra:")],
            AGUARDA_PIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pix)],
            AGUARDA_WHATSAPP_COMPROVANTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_whatsapp_comprovante)
            ],
            CONFIRMA: [
                CallbackQueryHandler(callback_confirmar, pattern="^confirmar$"),
                CallbackQueryHandler(callback_cancelar, pattern="^cancelar$"),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("relatorio", cmd_relatorio))

    if ADMIN_CHAT_ID:
        agendar_relatorio_sexta(app, ADMIN_CHAT_ID)

    logger.info("Bot iniciado!")
    app.run_polling()


if __name__ == "__main__":
    main()
