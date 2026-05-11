import anthropic
import base64
import os
from typing import Optional


def extrair_dados_imagem(imagem_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Recebe os bytes de uma imagem (nota fiscal ou comprovante) e retorna
    um dicionário com os dados extraídos: tipo, valor, descricao.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    imagem_b64 = base64.standard_b64encode(imagem_bytes).decode("utf-8")

    prompt = """Analise esta imagem de nota fiscal ou comprovante de pagamento e extraia as seguintes informações:

1. TIPO: Classifique como "MÃO DE OBRA", "MATERIAL" ou "EQUIPAMENTO" com base no conteúdo.
2. VALOR: O valor total em reais (apenas números e vírgula, ex: 1.250,00).
3. DESCRICAO: Uma descrição completa e objetiva do serviço, material ou equipamento.

Responda APENAS no seguinte formato JSON, sem texto adicional:
{
  "tipo": "MÃO DE OBRA" ou "MATERIAL" ou "EQUIPAMENTO",
  "valor": "valor aqui",
  "descricao": "descrição aqui"
}

Se não conseguir identificar algum campo com certeza, use null para esse campo."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": imagem_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    import json
    texto = message.content[0].text.strip()
    # Remove markdown code block if present
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return json.loads(texto.strip())


def salvar_imagem(imagem_bytes: bytes, user_id: int) -> str:
    """Salva a imagem localmente e retorna o caminho."""
    from datetime import datetime
    images_dir = os.path.join(os.path.dirname(__file__), "images")
    os.makedirs(images_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{user_id}_{timestamp}.jpg"
    path = os.path.join(images_dir, filename)
    with open(path, "wb") as f:
        f.write(imagem_bytes)
    return path
