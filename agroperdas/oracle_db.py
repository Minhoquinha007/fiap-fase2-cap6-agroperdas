"""Sincronização opcional de registros locais com Oracle Database.

As credenciais nunca ficam no código: o usuário as fornece em variáveis de
ambiente (ou em um arquivo .env local, ignorado pelo Git). A tabela precisa
ser criada antes com ``schema.sql``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class ConfiguracaoOracleError(RuntimeError):
    """Configuração incompleta ou dependência Oracle ausente."""


class SincronizacaoOracleError(RuntimeError):
    """O banco rejeitou a sincronização; nenhuma alteração foi confirmada."""


SQL_MERGE = """
MERGE INTO AGROPERDAS_MEDICOES destino
USING (
    SELECT :id AS ID,
           TO_DATE(:data_colheita, 'YYYY-MM-DD') AS DATA_COLHEITA,
           :talhao AS TALHAO,
           :area_colhida_ha AS AREA_COLHIDA_HA,
           :area_amostrada_m2 AS AREA_AMOSTRADA_M2,
           :residuo_amostra_kg AS RESIDUO_AMOSTRA_KG,
           :massa_colhida_t AS MASSA_COLHIDA_T,
           :limite_percentual AS LIMITE_PERCENTUAL,
           :perda_estimada_t AS PERDA_ESTIMADA_T,
           :percentual_perda AS PERCENTUAL_PERDA
    FROM dual
) origem
ON (destino.ID = origem.ID)
WHEN MATCHED THEN UPDATE SET
    destino.DATA_COLHEITA = origem.DATA_COLHEITA,
    destino.TALHAO = origem.TALHAO,
    destino.AREA_COLHIDA_HA = origem.AREA_COLHIDA_HA,
    destino.AREA_AMOSTRADA_M2 = origem.AREA_AMOSTRADA_M2,
    destino.RESIDUO_AMOSTRA_KG = origem.RESIDUO_AMOSTRA_KG,
    destino.MASSA_COLHIDA_T = origem.MASSA_COLHIDA_T,
    destino.LIMITE_PERCENTUAL = origem.LIMITE_PERCENTUAL,
    destino.PERDA_ESTIMADA_T = origem.PERDA_ESTIMADA_T,
    destino.PERCENTUAL_PERDA = origem.PERCENTUAL_PERDA
WHEN NOT MATCHED THEN INSERT (
    ID, DATA_COLHEITA, TALHAO, AREA_COLHIDA_HA, AREA_AMOSTRADA_M2,
    RESIDUO_AMOSTRA_KG, MASSA_COLHIDA_T, LIMITE_PERCENTUAL,
    PERDA_ESTIMADA_T, PERCENTUAL_PERDA
) VALUES (
    origem.ID, origem.DATA_COLHEITA, origem.TALHAO,
    origem.AREA_COLHIDA_HA, origem.AREA_AMOSTRADA_M2,
    origem.RESIDUO_AMOSTRA_KG, origem.MASSA_COLHIDA_T,
    origem.LIMITE_PERCENTUAL, origem.PERDA_ESTIMADA_T,
    origem.PERCENTUAL_PERDA
)
"""


CAMPOS_ORACLE = (
    "id",
    "data_colheita",
    "talhao",
    "area_colhida_ha",
    "area_amostrada_m2",
    "residuo_amostra_kg",
    "massa_colhida_t",
    "limite_percentual",
    "perda_estimada_t",
    "percentual_perda",
)


def _carregar_configuracao() -> tuple[str, str, str]:
    """Lê configuração sem imprimir nem guardar a senha em arquivos de saída."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ConfiguracaoOracleError(
            "Instale as dependências com: py -m pip install -r requirements.txt"
        ) from exc

    raiz = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=raiz / ".env", override=False)
    usuario = os.getenv("AGRO_ORACLE_USER", "").strip()
    senha = os.getenv("AGRO_ORACLE_PASSWORD", "")
    dsn = os.getenv("AGRO_ORACLE_DSN", "").strip()
    if not usuario or not senha or not dsn:
        raise ConfiguracaoOracleError(
            "Defina AGRO_ORACLE_USER, AGRO_ORACLE_PASSWORD e AGRO_ORACLE_DSN "
            "no .env local (veja .env.example)."
        )
    return usuario, senha, dsn


def _sincronizar_com_conexao(conexao: Any, registros: list[dict]) -> int:
    """Faz upsert idempotente em uma transação; útil também para testes."""
    cursor = None
    try:
        cursor = conexao.cursor()
        for registro in registros:
            parametros = {campo: registro[campo] for campo in CAMPOS_ORACLE}
            cursor.execute(SQL_MERGE, parametros)
        conexao.commit()
        return len(registros)
    except Exception:
        conexao.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()


def sincronizar_registros(registros: list[dict]) -> int:
    """Envia os registros da memória ao Oracle; repetir não cria duplicatas."""
    if not registros:
        return 0
    usuario, senha, dsn = _carregar_configuracao()
    try:
        import oracledb
    except ImportError as exc:
        raise ConfiguracaoOracleError(
            "Driver Oracle ausente. Instale: py -m pip install -r requirements.txt"
        ) from exc

    conexao = None
    try:
        conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
        return _sincronizar_com_conexao(conexao, registros)
    except Exception as exc:
        # Não ecoar exceções do driver: algumas contêm detalhes da conexão.
        raise SincronizacaoOracleError(
            "Não foi possível sincronizar. Confira serviço Oracle, credenciais, "
            "conectividade e se schema.sql foi executado. O JSON local foi preservado."
        ) from None
    finally:
        if conexao is not None:
            conexao.close()
