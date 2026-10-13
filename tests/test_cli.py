"""Testes do fluxo interativo de cadastro no menu."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agroperdas.cli import _cadastrar, executar_cli
from agroperdas.storage import RepositorioJSON


class TestCadastroInterativo(unittest.TestCase):
    def test_campo_invalido_e_repedido_sem_perder_os_anteriores(self) -> None:
        # Cada par traz uma resposta inválida e sua correção. Se o cadastro
        # recomeçar desde a data, a sequência deixa de corresponder aos campos.
        respostas = iter(
            [
                "2026-02-30", "2026-10-12",  # data impossível -> data válida
                "   ", "Talhão A",          # talhão em branco -> preenchido
                "abc", "2",                  # área não numérica -> 2 ha
                "20001", "10",               # amostra > 2 ha -> 10 m²
                "-1", "2",                   # resíduo negativo -> 2 kg
                "nan", "96",                 # massa não finita -> 96 t
                "100", "3",                  # limite inválido -> 3%
            ]
        )
        prompts: list[str] = []

        def responder(prompt: str) -> str:
            prompts.append(prompt)
            try:
                return next(respostas)
            except StopIteration as erro:
                raise AssertionError("O cadastro pediu campos extras ou reiniciou.") from erro

        with TemporaryDirectory() as pasta:
            repositorio = RepositorioJSON(Path(pasta) / "registros.json")
            saida = StringIO()
            with patch("builtins.input", side_effect=responder), redirect_stdout(saida):
                _cadastrar(repositorio)

            registros = repositorio.carregar()

        self.assertEqual(len(prompts), 14)
        self.assertEqual(len(registros), 1)
        registro = registros[0]
        self.assertEqual(registro["data_colheita"], "2026-10-12")
        self.assertEqual(registro["talhao"], "Talhão A")
        self.assertEqual(registro["area_colhida_ha"], 2)
        self.assertEqual(registro["area_amostrada_m2"], 10)
        self.assertEqual(registro["residuo_amostra_kg"], 2)
        self.assertEqual(registro["massa_colhida_t"], 96)
        self.assertEqual(registro["limite_percentual"], 3)
        self.assertIn("Amostra salva", saida.getvalue())

    def test_virgula_decimal_e_residuo_zero_sao_aceitos(self) -> None:
        respostas = ["2026-10-12", "Talhão B", "1,5", "10", "0", "75,5", "2,5"]

        with TemporaryDirectory() as pasta:
            repositorio = RepositorioJSON(Path(pasta) / "registros.json")
            with patch("builtins.input", side_effect=respostas) as entrada:
                with redirect_stdout(StringIO()):
                    _cadastrar(repositorio)
            registros = repositorio.carregar()

        self.assertEqual(entrada.call_count, 7)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["area_colhida_ha"], 1.5)
        self.assertEqual(registros[0]["residuo_amostra_kg"], 0)
        self.assertEqual(registros[0]["massa_colhida_t"], 75.5)
        self.assertEqual(registros[0]["limite_percentual"], 2.5)

    def test_combinacao_extrema_permite_corrigir_um_campo(self) -> None:
        # Os campos isolados são válidos, mas a combinação gera perda maior
        # que a coluna Oracle comporta. Corrigir o resíduo não deve reiniciar.
        respostas = [
            "2026-10-12", "Talhão C", "10000000000000", "1", "100", "96", "3",
            "5", "0,5",  # campo 5: resíduo da amostra
        ]
        with TemporaryDirectory() as pasta:
            repositorio = RepositorioJSON(Path(pasta) / "registros.json")
            saida = StringIO()
            with patch("builtins.input", side_effect=respostas) as entrada:
                with redirect_stdout(saida):
                    _cadastrar(repositorio)
            registros = repositorio.carregar()

        self.assertEqual(entrada.call_count, 9)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["talhao"], "Talhão C")
        self.assertEqual(registros[0]["residuo_amostra_kg"], 0.5)
        self.assertIn("Corrija apenas um campo", saida.getvalue())

    def test_corrigir_area_revalida_amostra_sem_recomecar(self) -> None:
        respostas = [
            "2026-10-12", "Talhão D", "10000000000000", "1000", "1000", "96", "3",
            "3", "0,01", "10",  # corrigir área colhida; amostra antiga agora é grande demais
        ]
        with TemporaryDirectory() as pasta:
            repositorio = RepositorioJSON(Path(pasta) / "registros.json")
            saida = StringIO()
            with patch("builtins.input", side_effect=respostas) as entrada:
                with redirect_stdout(saida):
                    _cadastrar(repositorio)
            registros = repositorio.carregar()

        self.assertEqual(entrada.call_count, 10)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["area_colhida_ha"], 0.01)
        self.assertEqual(registros[0]["area_amostrada_m2"], 10)
        self.assertIn("área da amostra também precisa ser corrigida", saida.getvalue())

    def test_cancelar_correcao_nao_grava_registro(self) -> None:
        respostas = [
            "2026-10-12", "Talhão E", "10000000000000", "1", "100", "96", "3", "0",
        ]
        with TemporaryDirectory() as pasta:
            repositorio = RepositorioJSON(Path(pasta) / "registros.json")
            saida = StringIO()
            with patch("builtins.input", side_effect=respostas):
                with redirect_stdout(saida):
                    _cadastrar(repositorio)
            registros = repositorio.carregar()

        self.assertEqual(registros, [])
        self.assertIn("nenhuma amostra foi salva", saida.getvalue())

    def test_cancelar_em_um_campo_volta_ao_menu_sem_gravar(self) -> None:
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "registros.json"
            saida = StringIO()
            with patch("builtins.input", side_effect=["1", "2026-10-12", "/cancelar", "0"]):
                with redirect_stdout(saida):
                    executar_cli(caminho)
            registros = RepositorioJSON(caminho).carregar()

        self.assertEqual(registros, [])
        self.assertIn("Operação cancelada", saida.getvalue())
        self.assertIn("Até logo", saida.getvalue())


if __name__ == "__main__":
    unittest.main()
