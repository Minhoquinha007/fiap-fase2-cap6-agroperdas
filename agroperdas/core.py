"""Regras de negócio para estimar perdas na colheita de cana-de-açúcar.

Os valores representam uma extrapolação da amostra; não são medições da área
inteira nem uma recomendação agronômica automática.
"""

from __future__ import annotations

from datetime import date
from math import isclose, isfinite
import re
from typing import Mapping
from uuid import UUID, uuid4


class ErroValidacao(ValueError):
    """Entrada ou registro incompatível com as regras do projeto."""


MAX_ORACLE_18_4 = 10**14
MIN_POSITIVO_ORACLE_4 = 0.0001


def _numero(
    valor: object,
    nome: str,
    *,
    minimo: float = 0,
    estrito: bool = True,
    entrada_oracle: bool = False,
) -> float:
    if isinstance(valor, bool):
        raise ErroValidacao(f"{nome} deve ser um número, não um booleano.")
    try:
        numero = float(valor.strip().replace(",", ".") if isinstance(valor, str) else valor)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ErroValidacao(f"{nome} deve ser um número válido.") from erro
    if not isfinite(numero):
        raise ErroValidacao(f"{nome} deve ser finito.")
    if numero < minimo or (estrito and numero == minimo):
        comparacao = "maior que" if estrito else "maior ou igual a"
        raise ErroValidacao(f"{nome} deve ser {comparacao} {minimo}.")
    if entrada_oracle:
        if numero >= MAX_ORACLE_18_4:
            raise ErroValidacao(f"{nome} excede a capacidade da coluna Oracle.")
        if 0 < numero < MIN_POSITIVO_ORACLE_4:
            raise ErroValidacao(
                f"{nome} deve ser zero ou pelo menos {MIN_POSITIVO_ORACLE_4} "
                "para não ser arredondado a zero no Oracle."
            )
    return numero


def _data_iso(valor: object) -> str:
    if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        raise ErroValidacao("data_colheita deve estar no formato AAAA-MM-DD.")
    try:
        date.fromisoformat(valor)
    except ValueError as erro:
        raise ErroValidacao("data_colheita não é uma data válida.") from erro
    return valor


def _talhao(valor: object) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao("talhao deve ser um texto.")
    nome = valor.strip()
    if not 1 <= len(nome) <= 100 or any(ord(caractere) < 32 for caractere in nome):
        raise ErroValidacao("talhao deve ter de 1 a 100 caracteres, sem quebras de linha.")
    return nome


def validar_campo_cadastro(
    campo: str, valor: object, dados_anteriores: Mapping[str, object]
) -> str | float:
    """Valida uma resposta do formulário sem exigir os demais campos.

    O cadastro usa as mesmas regras numéricas do cálculo e do Oracle. A área
    amostrada é conferida contra a área colhida já informada.
    """
    if campo == "data_colheita":
        return _data_iso(valor)
    if campo == "talhao":
        return _talhao(valor)
    if campo not in {
        "area_colhida_ha", "area_amostrada_m2", "residuo_amostra_kg",
        "massa_colhida_t", "limite_percentual",
    }:
        raise ValueError(f"Campo de cadastro desconhecido: {campo}")

    numero = _numero(
        valor, campo, estrito=campo != "residuo_amostra_kg", entrada_oracle=True
    )
    if campo == "area_amostrada_m2":
        area_ha = dados_anteriores.get("area_colhida_ha")
        if area_ha is not None and numero > float(area_ha) * 10_000:
            raise ErroValidacao(
                "area_amostrada_m2 não pode superar a área colhida convertida para m²."
            )
    if campo == "limite_percentual" and numero >= 100:
        raise ErroValidacao("limite_percentual deve ser menor que 100.")
    return numero


def calcular_indicadores(registro: Mapping[str, object]) -> tuple[float, float, bool]:
    """Retorna (perda em toneladas, percentual, acima do limite).

    A tupla reúne os três resultados da mesma amostra. O percentual usa como
    denominador a soma da massa colhida com a perda estimada.
    """
    area_ha = _numero(registro.get("area_colhida_ha"), "area_colhida_ha", entrada_oracle=True)
    amostra_m2 = _numero(registro.get("area_amostrada_m2"), "area_amostrada_m2", entrada_oracle=True)
    if amostra_m2 > area_ha * 10_000:
        raise ErroValidacao(
            "area_amostrada_m2 não pode superar a área colhida convertida para m²."
        )
    residuo_kg = _numero(
        registro.get("residuo_amostra_kg"), "residuo_amostra_kg",
        estrito=False, entrada_oracle=True,
    )
    colhida_t = _numero(registro.get("massa_colhida_t"), "massa_colhida_t", entrada_oracle=True)
    limite = _numero(registro.get("limite_percentual"), "limite_percentual", entrada_oracle=True)
    if limite >= 100:
        raise ErroValidacao("limite_percentual deve ser menor que 100.")

    perda_t = residuo_kg * (area_ha * 10_000) / amostra_m2 / 1_000
    denominador = perda_t + colhida_t
    if not isfinite(perda_t) or not isfinite(denominador):
        raise ErroValidacao("Os números informados excedem a capacidade do cálculo.")
    if perda_t >= MAX_ORACLE_18_4:
        raise ErroValidacao("A perda estimada excede a capacidade da coluna Oracle.")
    if 0 < perda_t < MIN_POSITIVO_ORACLE_4:
        raise ErroValidacao(
            "A perda estimada ficou abaixo de 0,0001 t e seria arredondada a zero no Oracle."
        )
    percentual = perda_t / denominador * 100
    if not isfinite(percentual):
        raise ErroValidacao("Não foi possível calcular um percentual finito.")
    if 0 < percentual < MIN_POSITIVO_ORACLE_4:
        raise ErroValidacao(
            "O percentual de perda ficou abaixo de 0,0001% e seria arredondado a zero no Oracle."
        )
    return perda_t, percentual, percentual > limite


def validar_registro(dados: Mapping[str, object]) -> dict[str, str | float]:
    """Valida e normaliza um registro, incluindo indicadores calculados.

    Valores calculados eventualmente presentes no JSON são conferidos para
    detectar alterações acidentais; a fonte da verdade são os dados da amostra.
    """
    if not isinstance(dados, Mapping):
        raise ErroValidacao("Cada registro deve ser um dicionário.")
    identificador = dados.get("id")
    if not isinstance(identificador, str):
        raise ErroValidacao("id deve ser um UUID em texto.")
    try:
        identificador = str(UUID(identificador))
    except ValueError as erro:
        raise ErroValidacao("id deve ser um UUID válido.") from erro

    registro: dict[str, str | float] = {
        "id": identificador,
        "data_colheita": _data_iso(dados.get("data_colheita")),
        "talhao": _talhao(dados.get("talhao")),
        "area_colhida_ha": _numero(dados.get("area_colhida_ha"), "area_colhida_ha"),
        "area_amostrada_m2": _numero(dados.get("area_amostrada_m2"), "area_amostrada_m2"),
        "residuo_amostra_kg": _numero(
            dados.get("residuo_amostra_kg"), "residuo_amostra_kg", estrito=False
        ),
        "massa_colhida_t": _numero(dados.get("massa_colhida_t"), "massa_colhida_t"),
        "limite_percentual": _numero(dados.get("limite_percentual"), "limite_percentual"),
    }
    perda_t, percentual, _ = calcular_indicadores(registro)
    for chave, esperado in (("perda_estimada_t", perda_t), ("percentual_perda", percentual)):
        if chave in dados:
            informado = _numero(dados[chave], chave, estrito=False)
            if not isclose(informado, esperado, rel_tol=1e-9, abs_tol=1e-9):
                raise ErroValidacao(f"{chave} não confere com os dados da amostra.")
        registro[chave] = esperado
    return registro


def criar_registro(
    *,
    data_colheita: str,
    talhao: str,
    area_colhida_ha: object,
    area_amostrada_m2: object,
    residuo_amostra_kg: object,
    massa_colhida_t: object,
    limite_percentual: object,
) -> dict[str, str | float]:
    """Cria um registro com UUID novo; parâmetros ficam explícitos no cadastro."""
    return validar_registro(
        {
            "id": str(uuid4()),
            "data_colheita": data_colheita,
            "talhao": talhao,
            "area_colhida_ha": area_colhida_ha,
            "area_amostrada_m2": area_amostrada_m2,
            "residuo_amostra_kg": residuo_amostra_kg,
            "massa_colhida_t": massa_colhida_t,
            "limite_percentual": limite_percentual,
        }
    )


def construir_tabela_memoria(registros: list[Mapping[str, object]]) -> list[dict[str, object]]:
    """Lista de dicionários equivalente a uma pequena tabela em memória.

    A ordenação, maior perda primeiro, forma o ranking exibido no menu.
    """
    tabela: list[dict[str, object]] = []
    for dados in registros:
        registro = validar_registro(dados)
        _, _, acima = calcular_indicadores(registro)
        tabela.append({**registro, "acima_do_limite": acima})
    tabela.sort(key=lambda linha: float(linha["perda_estimada_t"]), reverse=True)
    return tabela


def resumir_registros(registros: list[Mapping[str, object]]) -> dict[str, int | float]:
    """Agrega massas e calcula percentual total ponderado pelas toneladas."""
    tabela = construir_tabela_memoria(registros)
    colhida = sum(float(linha["massa_colhida_t"]) for linha in tabela)
    perdida = sum(float(linha["perda_estimada_t"]) for linha in tabela)
    area = sum(float(linha["area_colhida_ha"]) for linha in tabela)
    denominador = colhida + perdida
    if not all(isfinite(valor) for valor in (area, colhida, perdida, denominador)):
        raise ErroValidacao("A soma das amostras excede a capacidade do cálculo.")
    return {
        "quantidade": len(tabela),
        "area_colhida_ha": area,
        "massa_colhida_t": colhida,
        "perda_estimada_t": perdida,
        "percentual_total": perdida / denominador * 100 if denominador else 0.0,
        "acima_do_limite": sum(bool(linha["acima_do_limite"]) for linha in tabela),
    }
