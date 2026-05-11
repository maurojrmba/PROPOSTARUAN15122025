import os
import json
from flask import Flask, request, jsonify, render_template, send_file
from database import init_db, inserir_pagamento, listar_pendentes, COLUNAS
from report import gerar_excel, gerar_pdf
from vision import extrair_dados_imagem, salvar_imagem
import io

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

OBRAS = ["OBRA POSTO GOL", "OBRA CASA VENDA IPIRANGA", "OBRA HIPERPLAST"]
TIPOS = ["MÃO DE OBRA", "MATERIAL", "EQUIPAMENTO"]


@app.route("/")
def index():
    return render_template("index.html", obras=OBRAS, tipos=TIPOS)


@app.route("/salvar", methods=["POST"])
def salvar():
    data = request.get_json()
    try:
        inserir_pagamento(
            nome=data["nome"],
            telefone=data["telefone"],
            tipo=data["tipo"],
            valor=data["valor"],
            descricao=data["descricao"],
            obra=data["obra"],
            pix=data["pix"],
            whatsapp_comprovante=data["whatsapp_comprovante"],
            imagem_path=data.get("imagem_path"),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.route("/upload-imagem", methods=["POST"])
def upload_imagem():
    if "foto" not in request.files:
        return jsonify({"ok": False, "erro": "Nenhuma foto enviada"}), 400

    foto = request.files["foto"]
    imagem_bytes = foto.read()
    imagem_path = salvar_imagem(imagem_bytes, user_id=0)

    dados = {}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            dados = extrair_dados_imagem(imagem_bytes)
        except Exception as e:
            app.logger.error(f"Erro ao extrair dados da imagem: {e}")

    return jsonify({"ok": True, "imagem_path": imagem_path, "dados": dados})


@app.route("/relatorio/excel")
def relatorio_excel():
    excel_bytes = gerar_excel()
    from datetime import datetime
    nome = f"relatorio_{datetime.now().strftime('%d%m%Y_%H%M')}.xlsx"
    return send_file(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nome,
    )


@app.route("/relatorio/pdf")
def relatorio_pdf():
    pdf_bytes = gerar_pdf()
    from datetime import datetime
    nome = f"relatorio_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome,
    )


@app.route("/pendentes")
def pendentes():
    registros = listar_pendentes()
    return jsonify([dict(zip(COLUNAS, r)) for r in registros])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
