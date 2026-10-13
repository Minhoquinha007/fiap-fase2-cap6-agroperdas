"""Testes da correção de amostras sem perder dados já salvos."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agroperdas.cli import _corrigir
from agroperdas.core import criar_registro
from agroperdas.storage import RepositorioJSON


class TestCorrecaoInterativa(unittest.TestCase):
    def setUp(self) -> None:
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.repositorio = RepositorioJSON(Path(pasta.name) / "registros.json")
        self.original = criar_registro(
            data_colheita="2026-10-12",
            talhao="Talhão A",
            area_colhida_ha=2,
            area_amostrada_m2=10,
            residuo_amostra_kg=1,
            massa_colhida_t=200,
            limite_percentual=3,
        )
        self.repositorio.adicionar(self.original)
        self.conteudo_original = self.repositorio.caminho.read_bytes()

    def corrigir_com_respostas(self, respostas: list[str]) -> tuple[str, list[str]]:
        prompts: list[str] = []
        entradas = iter(respostas)

        def responder(prompt: str) -> str:
            prompts.append(prompt)
            try:
                return next(entradas)
            except StopIteration as erro:
                raise AssertionError("A correção pediu entradas inesperadas.") from erro

        saida = StringIO()
        with patch("builtins.input", side_effect=responder), redirect_stdout(saida):
            _corrigir(self.repositorio)
        return saida.getvalue(), prompts

    def test_selecao_invalida_repete_sem_modificar_registro(self) -> None:
        saida, prompts = self.corrigir_com_respostas(["texto", "2", "1", "0"])

        self.assertEqual(prompts[:3], ["Número da amostra [0 cancela]: "] * 3)
        self.assertEqual(saida.count("Escolha um número da lista"), 2)
        self.assertEqual(self.repositorio.caminho.read_bytes(), self.conteudo_original)

    def test_corrigir_campo_preserva_id_e_recalcula_indicadores(self) -> None:
        saida, _ = self.corrigir_com_respostas(["1", "5", "2", "8"])

        registros = self.repositorio.carregar()
        self.assertEqual(len(registros), 1)
        corrigido = registros[0]
        self.assertEqual(corrigido["id"], self.original["id"])
        self.assertEqual(corrigido["talhao"], self.original["talhao"])
        self.assertEqual(corrigido["residuo_amostra_kg"], 2)
        self.assertEqual(corrigido["perda_estimada_t"], 4)
        self.assertAlmostEqual(corrigido["percentual_perda"], 4 / 204 * 100)
        self.assertIn("corrigida no JSON local", saida)

    def test_cancelar_apos_alterar_descarta_todas_as_mudancas(self) -> None:
        saida, _ = self.corrigir_com_respostas(["1", "5", "2", "0"])

        self.assertIn("Correção cancelada", saida)
        self.assertEqual(self.repositorio.caminho.read_bytes(), self.conteudo_original)
        self.assertEqual(self.repositorio.carregar(), [self.original])

    def test_combinacao_invalida_nao_e_gravada(self) -> None:
        # 0,0001 ha corresponde a 1 m² e é menor que a amostra antiga de 10 m².
        saida, _ = self.corrigir_com_respostas(["1", "3", "0,0001", "8", "0"])

        self.assertIn("Combinação ainda inválida", saida)
        self.assertIn("Ainda não é possível salvar", saida)
        self.assertEqual(self.repositorio.caminho.read_bytes(), self.conteudo_original)

    def test_valor_invalido_repete_somente_o_campo_editado(self) -> None:
        saida, prompts = self.corrigir_com_respostas(["1", "6", "abc", "300", "8"])

        self.assertEqual(prompts.count("Massa efetivamente colhida (t): "), 2)
        self.assertEqual(prompts.count("Número da amostra [0 cancela]: "), 1)
        self.assertIn("Entrada inválida", saida)
        corrigido = self.repositorio.carregar()[0]
        self.assertEqual(corrigido["massa_colhida_t"], 300)
        self.assertEqual(corrigido["id"], self.original["id"])


if __name__ == "__main__":
    unittest.main()
