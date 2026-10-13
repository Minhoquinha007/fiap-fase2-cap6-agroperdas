"""Interface de linha de comando para registrar e analisar amostras."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .core import (
    ErroValidacao,
    construir_tabela_memoria,
    criar_registro,
    resumir_registros,
    validar_campo_cadastro,
    validar_registro,
)
from .storage import ErroArmazenamento, RepositorioJSON, exportar_relatorio


RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_DADOS_PADRAO = RAIZ_PROJETO / "dados" / "registros.json"
CAMPOS_CADASTRO = (
    ("data_colheita", "Data da colheita (AAAA-MM-DD): ", "Data da colheita"),
    ("talhao", "Nome/código do talhão: ", "Talhão"),
    ("area_colhida_ha", "Área colhida (ha): ", "Área colhida"),
    ("area_amostrada_m2", "Área da amostra (m²): ", "Área da amostra"),
    ("residuo_amostra_kg", "Resíduo encontrado na amostra (kg): ", "Resíduo da amostra"),
    ("massa_colhida_t", "Massa efetivamente colhida (t): ", "Massa colhida"),
    ("limite_percentual", "Limite de perda para alerta (% entre 0 e 100): ", "Limite de perda"),
)


class OperacaoCancelada(Exception):
    """O usuário preferiu voltar ao menu sem gravar a operação em andamento."""


def _ler_campo_cadastro(
    campo: str, prompt: str, rotulo: str, dados: dict[str, str | float]
) -> str | float:
    """Repete somente o campo inválido; as respostas anteriores são mantidas."""
    while True:
        valor = input(prompt).strip()
        if valor.casefold() == "/cancelar":
            raise OperacaoCancelada
        try:
            return validar_campo_cadastro(campo, valor, dados)
        except ErroValidacao as erro:
            print(f"Entrada inválida: {str(erro).replace(campo, rotulo)} Tente novamente.")


def mostrar_menu() -> None:
    """Procedimento sem retorno: somente apresenta opções ao usuário."""
    print("\n=== AGROPERDAS | COLHEITA DE CANA ===")
    print("1 - Cadastrar amostra")
    print("2 - Listar amostras e ranking")
    print("3 - Resumo das perdas")
    print("4 - Exportar relatório de texto")
    print("5 - Sincronizar com Oracle")
    print("6 - Corrigir uma amostra já cadastrada")
    print("0 - Sair")


def _cadastrar(repositorio: RepositorioJSON) -> None:
    print("\nCadastro de uma amostra representativa do talhão")
    print("Use vírgula ou ponto decimal. Área colhida em ha; amostra em m²; resíduo em kg.")
    print("Digite /cancelar em qualquer campo para voltar ao menu sem salvar a amostra.")
    dados: dict[str, str | float] = {}
    for campo, prompt, rotulo in CAMPOS_CADASTRO:
        dados[campo] = _ler_campo_cadastro(campo, prompt, rotulo, dados)

    while True:
        try:
            registro = criar_registro(**dados)
            break
        except ErroValidacao as erro:
            # Combinações extremas podem falhar mesmo com campos isolados válidos.
            print(f"Não foi possível calcular esta combinação: {erro}")
            print("Corrija apenas um campo; os demais valores serão preservados.")
            for indice, (_, _, rotulo) in enumerate(CAMPOS_CADASTRO, start=1):
                print(f"{indice} - {rotulo}")
            escolha = input("Campo a corrigir [1-7, 0 cancela]: ").strip()
            if escolha == "0":
                print("Cadastro cancelado; nenhuma amostra foi salva.")
                return
            if escolha not in {str(numero) for numero in range(1, 8)}:
                print("Escolha um número entre 1 e 7 ou 0 para cancelar.")
                continue
            campo, prompt, rotulo = CAMPOS_CADASTRO[int(escolha) - 1]
            dados[campo] = _ler_campo_cadastro(campo, prompt, rotulo, dados)
            if campo == "area_colhida_ha":
                try:
                    validar_campo_cadastro("area_amostrada_m2", dados["area_amostrada_m2"], dados)
                except ErroValidacao:
                    print("A área da amostra também precisa ser corrigida para a nova área colhida.")
                    amostra = CAMPOS_CADASTRO[3]
                    dados["area_amostrada_m2"] = _ler_campo_cadastro(*amostra, dados)
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


def _corrigir(repositorio: RepositorioJSON) -> None:
    """Edita uma amostra local sem alterar seu ID nem salvar etapas incompletas."""
    registros = repositorio.carregar()
    if not registros:
        print("Nenhuma amostra cadastrada para corrigir.")
        return

    print("\nAmostras no JSON local (na ordem de cadastro):")
    for indice, registro in enumerate(registros, start=1):
        print(
            f"{indice} - {registro['data_colheita']} | {registro['talhao']} "
            f"| ID {registro['id']}"
        )
    while True:
        escolha = input("Número da amostra [0 cancela]: ").strip()
        if escolha == "0":
            print("Correção cancelada; nenhum registro foi alterado.")
            return
        if escolha.isdecimal() and 1 <= int(escolha) <= len(registros):
            break
        print("Escolha um número da lista ou 0 para cancelar.")

    original = registros[int(escolha) - 1]
    dados = {campo: original[campo] for campo, _, _ in CAMPOS_CADASTRO}
    alteracoes: dict[str, str | float] = {}
    print("Escolha os campos a corrigir. Nada é gravado até você selecionar 8.")
    print("Digite /cancelar em uma pergunta para descartar a correção e voltar ao menu.")
    while True:
        print("\nValores atuais da amostra:")
        for indice, (campo, _, rotulo) in enumerate(CAMPOS_CADASTRO, start=1):
            print(f"{indice} - {rotulo}: {dados[campo]}")
        print("8 - Salvar correção | 0 - Cancelar")
        opcao = input("Sua escolha: ").strip()
        if opcao == "0":
            print("Correção cancelada; nenhum registro foi alterado.")
            return
        if opcao == "8":
            if not alteracoes:
                print("Nenhum campo foi modificado; registro mantido como estava.")
                return
            try:
                previa = validar_registro({"id": original["id"], **dados})
            except ErroValidacao as erro:
                print(f"Ainda não é possível salvar: {erro} Corrija o campo indicado.")
                continue
            corrigido = repositorio.atualizar(str(original["id"]), alteracoes)
            print(f"Amostra {corrigido['id']} corrigida no JSON local.")
            print(
                f"Perda estimada: {previa['perda_estimada_t']:.3f} t | "
                f"Percentual: {previa['percentual_perda']:.2f}%."
            )
            print("Se essa amostra já estava no Oracle, escolha 5 para sincronizar a correção.")
            return
        if not opcao.isdecimal() or not 1 <= int(opcao) <= len(CAMPOS_CADASTRO):
            print("Escolha um campo entre 1 e 7, 8 para salvar ou 0 para cancelar.")
            continue
        campo, prompt, rotulo = CAMPOS_CADASTRO[int(opcao) - 1]
        atual = dados[campo]
        print(f"Valor atual de {rotulo}: {atual}")
        dados[campo] = _ler_campo_cadastro(campo, prompt, rotulo, dados)
        alteracoes[campo] = dados[campo]
        try:
            previa = validar_registro({"id": original["id"], **dados})
        except ErroValidacao as erro:
            print(f"Combinação ainda inválida: {erro} Corrija o campo relacionado antes de salvar.")
        else:
            print(
                f"Prévia: perda {previa['perda_estimada_t']:.3f} t; "
                f"percentual {previa['percentual_perda']:.2f}%."
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
            elif escolha == "6":
                _corrigir(repositorio)
            else:
                print("Opção inválida. Escolha um número do menu.")
        except OperacaoCancelada:
            print("Operação cancelada; os registros já salvos permanecem intactos.")
        except (EOFError, KeyboardInterrupt):
            print("\nOperação encerrada pelo usuário; dados já salvos permanecem intactos.")
            return
        except (ErroValidacao, ErroArmazenamento, OSError) as erro:
            print(f"Não foi possível concluir: {erro}")
