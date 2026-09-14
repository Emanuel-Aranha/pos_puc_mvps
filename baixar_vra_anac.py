"""
Download do histórico VRA (Voo Regular Ativo) - ANAC
======================================================
Roda LOCALMENTE (fora do Databricks) para evitar bloqueios de rede do
ambiente serverless da Free Edition. Ao final, gera um único arquivo
.zip com todos os CSVs mensais baixados, pronto para upload manual
em um Volume do Databricks (Catalog Explorer > seu volume > Upload).

Uso:
    python baixar_vra_anac.py

Requisitos:
    pip install requests
"""

import os
import time
import zipfile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------------------------------------------------
# Configuração
# ------------------------------------------------------------------
ANOS = [2023, 2024, 2025]
MESES = [f"{m:02d}" for m in range(1, 13)]
URL_BASE = "https://siros.anac.gov.br/siros/registros/diversos/vra"
PASTA_DESTINO = "vra_csv_temp"      # pasta local temporária com os CSVs
NOME_ZIP = "VRA_2023_2025.zip"      # arquivo final a ser enviado ao Databricks

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ------------------------------------------------------------------
# Sessão HTTP com retry automático (lida com instabilidades da rede)
# ------------------------------------------------------------------
def criar_sessao():
    sessao = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,           # espera 2s, 4s, 8s, 16s, 32s entre tentativas
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    sessao.mount("https://", adapter)
    sessao.mount("http://", adapter)
    return sessao


def baixar_arquivo(sessao, ano, mes, pasta_destino):
    nome_arquivo = f"VRA_{ano}_{mes}.csv"
    caminho_local = os.path.join(pasta_destino, nome_arquivo)
    url = f"{URL_BASE}/{ano}/{nome_arquivo}"

    # pula se já foi baixado em execução anterior (permite retomar)
    if os.path.exists(caminho_local) and os.path.getsize(caminho_local) > 0:
        print(f"  já existe localmente: {nome_arquivo}")
        return "ja_existia"

    try:
        resp = sessao.get(url, headers=HEADERS, timeout=60)
    except requests.exceptions.RequestException as e:
        print(f"  ERRO de conexão em {nome_arquivo}: {e}")
        return "erro"

    if resp.status_code == 200 and len(resp.content) > 0:
        with open(caminho_local, "wb") as f:
            f.write(resp.content)
        print(f"  OK  {nome_arquivo} ({len(resp.content) / 1e6:.1f} MB)")
        return "ok"
    elif resp.status_code == 404:
        print(f"  SKIP {nome_arquivo} (ainda não publicado pela ANAC - status 404)")
        return "nao_publicado"
    else:
        print(f"  FALHA {nome_arquivo} (status {resp.status_code})")
        return "erro"


def main():
    os.makedirs(PASTA_DESTINO, exist_ok=True)
    sessao = criar_sessao()

    resultado = {"ok": 0, "ja_existia": 0, "nao_publicado": 0, "erro": 0}
    arquivos_com_erro = []

    print(f"Iniciando download do VRA para os anos {ANOS}...\n")

    for ano in ANOS:
        print(f"Ano {ano}:")
        for mes in MESES:
            status = baixar_arquivo(sessao, ano, mes, PASTA_DESTINO)
            resultado[status] += 1
            if status == "erro":
                arquivos_com_erro.append(f"VRA_{ano}_{mes}.csv")
            time.sleep(0.5)  # pequena pausa para não sobrecarregar o servidor
        print()

    print("=" * 60)
    print("Resumo do download:")
    print(f"  Baixados agora:      {resultado['ok']}")
    print(f"  Já existiam:         {resultado['ja_existia']}")
    print(f"  Não publicados (404): {resultado['nao_publicado']}")
    print(f"  Falharam:            {resultado['erro']}")
    if arquivos_com_erro:
        print(f"\n  Arquivos com erro (rode o script de novo para tentar novamente):")
        for a in arquivos_com_erro:
            print(f"    - {a}")

    # ------------------------------------------------------------------
    # Empacotar tudo em um único .zip
    # ------------------------------------------------------------------
    arquivos_csv = sorted(
        f for f in os.listdir(PASTA_DESTINO) if f.lower().endswith(".csv")
    )

    if not arquivos_csv:
        print("\nNenhum CSV disponível para compactar. Verifique os erros acima.")
        return

    print(f"\nCompactando {len(arquivos_csv)} arquivos em '{NOME_ZIP}'...")
    with zipfile.ZipFile(NOME_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome_arquivo in arquivos_csv:
            caminho = os.path.join(PASTA_DESTINO, nome_arquivo)
            zf.write(caminho, arcname=nome_arquivo)

    tamanho_mb = os.path.getsize(NOME_ZIP) / 1e6
    print(f"\nPronto! Arquivo gerado: {os.path.abspath(NOME_ZIP)} ({tamanho_mb:.1f} MB)")
    print("\nPróximo passo: subir esse .zip no Databricks")
    print("  1. No Databricks, vá em Catalog > seu catálogo > seu schema > Volumes")
    print("  2. Crie (ou abra) o volume 'vra_raw'")
    print("  3. Clique em 'Upload to this volume' e selecione o VRA_2023_2025.zip")
    print("  4. No notebook, descompacte com o código da Etapa 2 (célula de unzip)")


if __name__ == "__main__":
    main()
