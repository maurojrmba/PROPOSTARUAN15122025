import os
import logging
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
from report import gerar_excel, agendar_relatorio_sexta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados da conversa
(
    INICIO,
    AGUARDA_TIPO,
    AGUARDA_VALOR,
    AGUARDA_DESCRICAO,
    AGUARDA_OBRA,
    AGUARDA_PIX,
    AGUARDA_WHATSAPP,
    CONFIRMA,
) = range(8)

OBRAS = [
    "OBRA POSTO GOL",
    "OBRA CASA VENDA IPIRANGA",
    "OBRA HIPERPLAST",
]

TIPOS = ["MÃO DE OBRA", "MATERIAL", "EQUIPAMENTO"]

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))


def teclado_tipos():
    botoes = [[InlineKeyboardButton(t, callback_data=f"tipo:{t}")] for t in TIPOS]
    return InlineKeyboardMarkup(botoes)


def teclado_obras():
    botoes = [[InlineKeyboardButton(o, callback_data=f"obra:{o}")] for o in OBRAS]
    return InlineKeyboardMarkup(botoes)


def teclado_confirma():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ CONFIRMAR", callback_data="confirmar"),
            InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar"),
        ]
    ])


def resumo(ctx) -> str:
    d = ctx.user_data
    return (
        f"📋 *RESUMO DO LANÇAMENTO*\n\n"
        f"*TIPO:* {d.get('tipo', '-')}\n"
        f"*VALOR:* R$ {d.get('valor', '-')}\n"
        f"*DESCRIÇÃO:* {d.get('descricao', '-')}\n"
        f"*OBRA:* {d.get('obra', '-')}\n"
        f"*PIX:* {d.get('pix', '-')}\n"
        f"*WHATSAPP:* {d.get('whatsapp', '-')}\n"
    )


# ──────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "👷 *BEM-VINDO AO LANÇADOR DE DESPESAS!*\n\n"
        "ENVIE UMA FOTO DA NOTA FISCAL OU COMPROVANTE,\n"
        "OU ESCOLHA O TIPO DE PAGAMENTO ABAIXO:",
        parse_mode="Markdown",
        reply_markup=teclado_tipos(),
    )
    return INICIO


# ──────────────────────────────────────────────
# Recebeu foto
# ──────────────────────────────────────────────
async def receber_foto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 ANALISANDO A IMAGEM, AGUARDE...")

    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    imagem_bytes = await file.download_as_bytearray()

    imagem_path = salvar_imagem(bytes(imagem_bytes), update.effective_user.id)
    ctx.user_data["imagem_path"] = imagem_path

    try:
        dados = extrair_dados_imagem(bytes(imagem_bytes))
    except Exception as e:
        logger.error(f"Erro na extração de imagem: {e}")
        dados = {}

    await msg.delete()

    # Preenche o que foi extraído
    for campo in ("tipo", "valor", "descricao"):
        if dados.get(campo):
            ctx.user_data[campo] = dados[campo]

    # Mostra o que foi extraído e pede confirmação parcial
    extraido = ""
    if dados.get("tipo"):
        extraido += f"*TIPO:* {dados['tipo']}\n"
    if dados.get("valor"):
        extraido += f"*VALOR:* R$ {dados['valor']}\n"
    if dados.get("descricao"):
        extraido += f"*DESCRIÇÃO:* {dados['descricao']}\n"

    if extraido:
        await update.message.reply_text(
            f"✅ *DADOS EXTRAÍDOS DA IMAGEM:*\n\n{extraido}\nVERIFIQUE E CONTINUE:",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("⚠️ NÃO FOI POSSÍVEL EXTRAIR OS DADOS. PREENCHA MANUALMENTE.")

    # Avança para o próximo campo faltante
    return await proximo_campo_faltante(update, ctx)


async def proximo_campo_faltante(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
    if not d.get("whatsapp"):
        await send("📱 QUAL O NÚMERO DO WHATSAPP PARA ENVIO DO COMPROVANTE?")
        return AGUARDA_WHATSAPP

    # Tudo preenchido
    await send(resumo(ctx), parse_mode="Markdown", reply_markup=teclado_confirma())
    return CONFIRMA


# ──────────────────────────────────────────────
# Callbacks de botões inline
# ──────────────────────────────────────────────
async def callback_tipo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tipo = query.data.split(":", 1)[1]
    ctx.user_data["tipo"] = tipo
    await query.edit_message_text(f"✅ TIPO SELECIONADO: *{tipo}*", parse_mode="Markdown")
    await query.message.reply_text("💰 QUAL O VALOR? (ex: 1.500,00)")
    return AGUARDA_VALOR


async def callback_obra(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    obra = query.data.split(":", 1)[1]
    ctx.user_data["obra"] = obra
    await query.edit_message_text(f"✅ OBRA SELECIONADA: *{obra}*", parse_mode="Markdown")
    await query.message.reply_text("💳 QUAL A CHAVE PIX PARA PAGAMENTO?")
    return AGUARDA_PIX


async def callback_confirmar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = ctx.user_data
    inserir_pagamento(
        tipo=d["tipo"],
        valor=d["valor"],
        descricao=d["descricao"],
        obra=d["obra"],
        pix=d["pix"],
        whatsapp=d["whatsapp"],
        imagem_path=d.get("imagem_path"),
    )
    await query.edit_message_text(
        "✅ *LANÇAMENTO REGISTRADO COM SUCESSO!*\n\nOBRIGADO. AS INFORMAÇÕES FORAM SALVAS.",
        parse_mode="Markdown",
    )
    ctx.user_data.clear()
    return ConversationHandler.END


async def callback_cancelar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text("❌ LANÇAMENTO CANCELADO.")
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Handlers de texto para cada campo
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
    return AGUARDA_WHATSAPP


async def receber_whatsapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["whatsapp"] = update.message.text.strip()
    await update.message.reply_text(resumo(ctx), parse_mode="Markdown", reply_markup=teclado_confirma())
    return CONFIRMA


# ──────────────────────────────────────────────
# Comando /relatorio (apenas admin)
# ──────────────────────────────────────────────
async def cmd_relatorio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ ACESSO NEGADO.")
        return
    await update.message.reply_text("⏳ GERANDO RELATÓRIO...")
    excel_bytes = gerar_excel()
    from datetime import datetime
    nome = f"relatorio_{datetime.now().strftime('%d%m%Y')}.xlsx"
    await update.message.reply_document(
        document=excel_bytes,
        filename=nome,
        caption=f"📊 RELATÓRIO DE PAGAMENTOS PENDENTES — {datetime.now().strftime('%d/%m/%Y')}",
    )


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
            INICIO: [
                MessageHandler(filters.PHOTO, receber_foto),
                CallbackQueryHandler(callback_tipo, pattern="^tipo:"),
            ],
            AGUARDA_TIPO: [
                CallbackQueryHandler(callback_tipo, pattern="^tipo:"),
            ],
            AGUARDA_VALOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor),
            ],
            AGUARDA_DESCRICAO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_descricao),
            ],
            AGUARDA_OBRA: [
                CallbackQueryHandler(callback_obra, pattern="^obra:"),
            ],
            AGUARDA_PIX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pix),
            ],
            AGUARDA_WHATSAPP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receber_whatsapp),
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
