"""Interface de linha de comando para registrar e analisar amostras."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .core import (
    ErroValidacao,
    construir_tabela_memoria,
    criar_registro,
    resumir_registros,
)
from .storage import ErroArmazenamento, RepositorioJSON, exportar_relatorio


RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_DADOS_PADRAO = RAIZ_PROJETO / "dados" / "registros.json"


def mostrar_menu() -> None:
    """Procedimento sem retorno: somente apresenta opções ao usuário."""
    print("\n=== AGROPERDAS | COLHEITA DE CANA ===")
    print("1 - Cadastrar amostra")
    print("2 - Listar amostras e ranking")
    print("3 - Resumo das perdas")
    print("4 - Exportar relatório de texto")
    print("5 - Sincronizar com Oracle")
    print("0 - Sair")


def _cadastrar(repositorio: RepositorioJSON) -> None:
    print("\nCadastro de uma amostra representativa do talhão")
    print("Use vírgula ou ponto decimal. Área colhida em ha; amostra em m²; resíduo em kg.")
    dados = {
        "data_colheita": input("Data da colheita (AAAA-MM-DD): ").strip(),
        "talhao": input("Nome/código do talhão: ").strip(),
        "area_colhida_ha": input("Área colhida (ha): ").strip(),
        "area_amostrada_m2": input("Área da amostra (m²): ").strip(),
        "residuo_amostra_kg": input("Resíduo encontrado na amostra (kg): ").strip(),
        "massa_colhida_t": input("Massa efetivamente colhida (t): ").strip(),
        "limite_percentual": input("Limite de perda para alerta (% entre 0 e 100): ").strip(),
    }
    registro = criar_registro(**dados)
    repositorio.adicionar(registro)
    situacao = (
        "ACIMA DO LIMITE"
        if float(registro["percentual_perda"]) > float(registro["limite_percentual"])
        else "dentro do limite"
    )
    print(f"Amostra salva no JSON local com ID {registro['id']}.")
    print(
        f"Perda estimada: {registro['perda_estimada_t']:.3f} t | "
        f"Percentual: {registro['percentual_perda']:.2f}% | {situacao}."
    )


def _nome_curto(nome: object, largura: int = 18) -> str:
    texto = str(nome)
    return texto if len(texto) <= largura else texto[: largura - 1] + "…"


def exibir_tabela(registros: list[dict[str, str | float]]) -> None:
    """Procedimento sem retorno: mostra uma tabela de memória ordenada."""
    tabela_memoria = construir_tabela_memoria(registros)
    if not tabela_memoria:
        print("Nenhuma amostra cadastrada.")
        return
    print("\nRanking: maior perda estimada primeiro")
    cabecalho = (
        f"{'#':>2} {'Data':10} {'Talhão':18} {'Área ha':>8} {'Amostra m²':>11} "
        f"{'Resíduo kg':>10} {'Colhido t':>10} {'Perda t':>10} {'Perda %':>8} {'Limite %':>8} Status"
    )
    print(cabecalho)
    print("-" * len(cabecalho))
    for posicao, linha in enumerate(tabela_memoria, start=1):
        status = "ACIMA" if linha["acima_do_limite"] else "OK"
        print(
            f"{posicao:>2} {linha['data_colheita']:10} {_nome_curto(linha['talhao']):18} "
            f"{linha['area_colhida_ha']:>8.2f} {linha['area_amostrada_m2']:>11.2f} "
            f"{linha['residuo_amostra_kg']:>10.2f} {linha['massa_colhida_t']:>10.2f} "
            f"{linha['perda_estimada_t']:>10.3f} {linha['percentual_perda']:>8.2f} "
            f"{linha['limite_percentual']:>8.2f} {status}"
        )
        print(f"   ID: {linha['id']}")


def _resumo(repositorio: RepositorioJSON) -> None:
    registros = repositorio.carregar()
    resumo = resumir_registros(registros)
    print("\nResumo de todas as amostras cadastradas")
    print(f"Amostras: {resumo['quantidade']}")
    print(f"Área colhida informada: {resumo['area_colhida_ha']:.2f} ha")
    print(f"Massa colhida informada: {resumo['massa_colhida_t']:.3f} t")
    print(f"Perda estimada: {resumo['perda_estimada_t']:.3f} t")
    print(f"Percentual total ponderado: {resumo['percentual_total']:.2f}%")
    print(f"Amostras acima do respectivo limite: {resumo['acima_do_limite']}")
    print("A soma só é interpretável como total se as áreas dos registros não se sobrepõem.")


def _exportar(repositorio: RepositorioJSON) -> None:
    padrao = RAIZ_PROJETO / "relatorios" / f"agroperdas_{datetime.now():%Y%m%d_%H%M%S}.txt"
    caminho_texto = input(f"Destino do relatório [Enter = {padrao}]: ").strip()
    destino = Path(caminho_texto) if caminho_texto else padrao
    if destino.resolve() == repositorio.caminho.resolve():
        print("Exportação cancelada: o relatório não pode substituir o JSON de dados.")
        return
    if destino.exists() and input("Arquivo existe. Sobrescrever? [s/N]: ").strip().casefold() != "s":
        print("Exportação cancelada; arquivo existente preservado.")
        return
    registros = repositorio.carregar()
    exportar_relatorio(destino, registros)
    print(f"Relatório salvo em {destino.resolve()}.")


def _sincronizar_oracle(repositorio: RepositorioJSON) -> None:
    registros = repositorio.carregar()
    if not registros:
        print("Não há amostras para sincronizar.")
        return
    resposta = input(f"Enviar {len(registros)} amostra(s) ao Oracle? [s/N]: ").strip().casefold()
    if resposta != "s":
        print("Sincronização cancelada; nenhuma conexão foi aberta.")
        return
    try:
        from .oracle_db import (
            ConfiguracaoOracleError,
            SincronizacaoOracleError,
            sincronizar_registros,
        )

        quantidade = sincronizar_registros(registros)
    except (ImportError, ConfiguracaoOracleError, SincronizacaoOracleError) as erro:
        print(f"Sincronização não concluída: {erro}")
        return
    except Exception as erro:
        # Não exibir detalhes inesperados do driver, que podem conter dados de conexão.
        print(f"Sincronização não concluída ({type(erro).__name__}). O JSON local foi preservado.")
        return
    print(f"Oracle confirmou {quantidade} registro(s). O JSON local continua disponível.")


def executar_cli(caminho_dados: str | Path = CAMINHO_DADOS_PADRAO) -> None:
    """Laço principal da interface; não conecta ao Oracle automaticamente."""
    repositorio = RepositorioJSON(caminho_dados)
    while True:
        mostrar_menu()
        try:
            escolha = input("Escolha uma opção: ").strip()
            if escolha == "0":
                print("Até logo! Seus dados permanecem no JSON local.")
                return
            if escolha == "1":
                _cadastrar(repositorio)
            elif escolha == "2":
                exibir_tabela(repositorio.carregar())
            elif escolha == "3":
                _resumo(repositorio)
            elif escolha == "4":
                _exportar(repositorio)
            elif escolha == "5":
                _sincronizar_oracle(repositorio)
            else:
                print("Opção inválida. Escolha um número do menu.")
        except (EOFError, KeyboardInterrupt):
            print("\nOperação encerrada pelo usuário; dados já salvos permanecem intactos.")
            return
        except (ErroValidacao, ErroArmazenamento, OSError) as erro:
            print(f"Não foi possível concluir: {erro}")
