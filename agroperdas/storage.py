"""Persistência local e exportação legível do projeto AgroPerdas."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from .core import construir_tabela_memoria, resumir_registros, validar_registro


class ErroArmazenamento(ValueError):
    """Arquivo JSON inválido ou IDs repetidos."""


def _sem_duplicatas(registros: list[Mapping[str, object]]) -> list[dict[str, str | float]]:
    normalizados: list[dict[str, str | float]] = []
    vistos: set[str] = set()
    for indice, dados in enumerate(registros, start=1):
        registro = validar_registro(dados)
        identificador = str(registro["id"])
        if identificador in vistos:
            raise ErroArmazenamento(f"ID duplicado no registro {indice}: {identificador}")
        vistos.add(identificador)
        normalizados.append(registro)
    return normalizados


def _gravar_atomico(caminho: Path, conteudo: str) -> None:
    """Grava no mesmo diretório e troca o destino somente após concluir a escrita."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=caminho.parent,
            prefix=f".{caminho.name}.",
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
        temporario = None
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


class RepositorioJSON:
    """Repositório pequeno, local e de um processo por vez."""

    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)

    def carregar(self) -> list[dict[str, str | float]]:
        if not self.caminho.exists():
            return []
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as erro:
            raise ErroArmazenamento(
                "O arquivo de dados não contém JSON UTF-8 válido."
            ) from erro
        if not isinstance(dados, list):
            raise ErroArmazenamento("O arquivo de dados deve conter uma lista de registros.")
        return _sem_duplicatas(dados)

    def salvar(self, registros: list[Mapping[str, object]]) -> None:
        normalizados = _sem_duplicatas(registros)
        conteudo = json.dumps(normalizados, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        _gravar_atomico(self.caminho, conteudo)

    def adicionar(self, dados: Mapping[str, object]) -> None:
        registro = validar_registro(dados)
        registros = self.carregar()
        if any(item["id"] == registro["id"] for item in registros):
            raise ErroArmazenamento(f"Já existe registro com ID {registro['id']}.")
        registros.append(registro)
        self.salvar(registros)

    def atualizar(
        self, identificador: str, alteracoes: Mapping[str, object]
    ) -> dict[str, str | float]:
        """Corrige campos informados, preserva o ID e recalcula os indicadores."""
        campos_editaveis = {
            "data_colheita", "talhao", "area_colhida_ha", "area_amostrada_m2",
            "residuo_amostra_kg", "massa_colhida_t", "limite_percentual",
        }
        desconhecidos = set(alteracoes) - campos_editaveis
        if desconhecidos:
            raise ErroArmazenamento("Somente os campos de entrada podem ser corrigidos.")
        registros = self.carregar()
        for indice, atual in enumerate(registros):
            if atual["id"] != identificador:
                continue
            dados = {**atual, **alteracoes}
            dados.pop("perda_estimada_t", None)
            dados.pop("percentual_perda", None)
            corrigido = validar_registro(dados)
            registros[indice] = corrigido
            self.salvar(registros)
            return corrigido
        raise ErroArmazenamento("A amostra escolhida não foi encontrada no JSON local.")


def exportar_relatorio(caminho: str | Path, registros: list[Mapping[str, object]]) -> Path:
    """Exporta um relatório de texto com método, totais e ranking."""
    destino = Path(caminho)
    normalizados = _sem_duplicatas(registros)
    tabela = construir_tabela_memoria(normalizados)
    resumo = resumir_registros(normalizados)
    linhas = [
        "AGROPERDAS - RELATÓRIO DE PERDAS ESTIMADAS NA COLHEITA DE CANA",
        f"Gerado em: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "Método: resíduo da amostra (kg) × área colhida (ha) × 10.000 / área amostrada (m²) / 1.000.",
        "Percentual: perda estimada / (perda estimada + massa colhida) × 100.",
        "Atenção: extrapolação didática; a representatividade da amostra deve ser avaliada em campo.",
        "",
        f"Registros: {resumo['quantidade']}",
        f"Área total informada: {resumo['area_colhida_ha']:.2f} ha",
        f"Massa colhida total: {resumo['massa_colhida_t']:.3f} t",
        f"Perda estimada total: {resumo['perda_estimada_t']:.3f} t",
        f"Percentual total ponderado: {resumo['percentual_total']:.2f}%",
        f"Amostras acima do próprio limite: {resumo['acima_do_limite']}",
        "",
        "RANKING POR PERDA ESTIMADA (MAIOR PARA MENOR)",
    ]
    if not tabela:
        linhas.append("Nenhuma amostra cadastrada.")
    for posicao, linha in enumerate(tabela, start=1):
        status = "ACIMA DO LIMITE" if linha["acima_do_limite"] else "dentro do limite"
        linhas.extend(
            [
                f"{posicao}. {linha['talhao']} | colheita {linha['data_colheita']} | ID {linha['id']}",
                f"   Área {linha['area_colhida_ha']:.3f} ha; amostra {linha['area_amostrada_m2']:.3f} m²; "
                f"resíduo {linha['residuo_amostra_kg']:.3f} kg; colhido {linha['massa_colhida_t']:.3f} t.",
                f"   Perda {linha['perda_estimada_t']:.3f} t; percentual {linha['percentual_perda']:.2f}%; "
                f"limite {linha['limite_percentual']:.2f}%: {status}.",
            ]
        )
    _gravar_atomico(destino, "\n".join(linhas) + "\n")
    return destino
