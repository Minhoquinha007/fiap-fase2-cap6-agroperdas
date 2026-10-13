"""Confere o acesso Oracle e, se solicitado, cria a tabela do projeto.

Uso:
    python verificar_oracle.py
    python verificar_oracle.py --criar-tabela

O script nunca imprime as credenciais. A criação só ocorre com a opção explícita
e apenas quando AGROPERDAS_MEDICOES ainda não existe no usuário conectado.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agroperdas.oracle_db import ConfiguracaoOracleError, _carregar_configuracao


NOME_TABELA = "AGROPERDAS_MEDICOES"


def _sql_criacao() -> str:
    caminho = Path(__file__).resolve().parent / "schema.sql"
    linhas = [
        linha for linha in caminho.read_text(encoding="utf-8").splitlines()
        if not linha.lstrip().startswith("--")
    ]
    return "\n".join(linhas).strip().removesuffix(";")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--criar-tabela",
        action="store_true",
        help="cria AGROPERDAS_MEDICOES se ela não existir",
    )
    argumentos = parser.parse_args()

    try:
        usuario, senha, dsn = _carregar_configuracao()
        import oracledb
    except (ConfiguracaoOracleError, ImportError) as erro:
        print(f"Configuração incompleta: {erro}")
        return 1

    conexao = None
    cursor = None
    try:
        conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
        cursor = conexao.cursor()
        cursor.execute("SELECT 1 FROM dual")
        cursor.fetchone()
        print("Conexão e consulta Oracle: OK")

        cursor.execute(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = :nome",
            {"nome": NOME_TABELA},
        )
        existe = cursor.fetchone()[0] > 0
        if existe:
            print(f"Tabela {NOME_TABELA}: já existe; nenhuma alteração feita")
        elif argumentos.criar_tabela:
            cursor.execute(_sql_criacao())
            print(f"Tabela {NOME_TABELA}: criada e confirmada")
        else:
            print(f"Tabela {NOME_TABELA}: ausente; use --criar-tabela para criá-la")
        return 0
    except Exception as erro:
        # Mensagens completas do driver podem conter detalhes privados da conexão.
        detalhe = erro.args[0] if erro.args else erro
        codigo = getattr(detalhe, "code", None)
        print(f"Falha Oracle; código: {codigo if codigo is not None else 'indisponível'}")
        return 1
    finally:
        if cursor is not None:
            cursor.close()
        if conexao is not None:
            conexao.close()


if __name__ == "__main__":
    raise SystemExit(main())
