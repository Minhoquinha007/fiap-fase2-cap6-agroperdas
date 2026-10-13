"""Testes de persistência local e relatório, sem servidor Oracle."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agroperdas.cli import _exportar
from agroperdas.core import ErroValidacao, criar_registro
from agroperdas.storage import ErroArmazenamento, RepositorioJSON, exportar_relatorio


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.repositorio = RepositorioJSON(self.raiz / "dados" / "registros.json")
        self.registro = criar_registro(
            data_colheita="2026-10-12",
            talhao="Talhão A",
            area_colhida_ha=2,
            area_amostrada_m2=10,
            residuo_amostra_kg=2,
            massa_colhida_t=96,
            limite_percentual=3,
        )

    def test_gravar_recarregar_e_evitar_duplicata(self) -> None:
        self.assertEqual(self.repositorio.carregar(), [])
        self.repositorio.adicionar(self.registro)
        carregados = self.repositorio.carregar()
        self.assertEqual(len(carregados), 1)
        self.assertEqual(carregados[0]["perda_estimada_t"], 4.0)
        self.assertEqual(carregados[0]["percentual_perda"], 4.0)
        with self.assertRaises(ErroArmazenamento):
            self.repositorio.adicionar(self.registro)
        with self.assertRaises(ErroArmazenamento):
            self.repositorio.adicionar(dict(self.registro, id=self.registro["id"].upper()))
        self.assertEqual(len(self.repositorio.carregar()), 1)

    def test_json_corrompido_e_indicador_alterado(self) -> None:
        self.repositorio.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.repositorio.caminho.write_text("{", encoding="utf-8")
        with self.assertRaises(ErroArmazenamento):
            self.repositorio.carregar()
        adulterado = dict(self.registro, percentual_perda=0)
        self.repositorio.caminho.write_text(json.dumps([adulterado]), encoding="utf-8")
        with self.assertRaises(ErroValidacao):
            self.repositorio.carregar()

    def test_json_nao_utf8_gera_erro_tratado(self) -> None:
        self.repositorio.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.repositorio.caminho.write_bytes(b"\xff")
        with self.assertRaisesRegex(ErroArmazenamento, "UTF-8"):
            self.repositorio.carregar()

    def test_falha_na_troca_preserva_arquivo_antigo(self) -> None:
        self.repositorio.salvar([self.registro])
        original = self.repositorio.caminho.read_bytes()
        with patch("agroperdas.storage.os.replace", side_effect=OSError("falha simulada")):
            with self.assertRaises(OSError):
                self.repositorio.salvar([])
        self.assertEqual(self.repositorio.caminho.read_bytes(), original)
        self.assertEqual(list(self.repositorio.caminho.parent.glob("*.tmp")), [])

    def test_relatorio_explicita_metodo_e_ranking(self) -> None:
        destino = exportar_relatorio(self.raiz / "relatorios" / "saida.txt", [self.registro])
        texto = destino.read_text(encoding="utf-8")
        self.assertIn("RANKING POR PERDA ESTIMADA", texto)
        self.assertIn("Perda 4.000 t", texto)
        self.assertIn("ACIMA DO LIMITE", texto)
        self.assertIn("extrapolação didática", texto)

    def test_relatorio_nao_sobrescreve_json_de_dados(self) -> None:
        self.repositorio.salvar([self.registro])
        original = self.repositorio.caminho.read_bytes()
        with patch("builtins.input", return_value=str(self.repositorio.caminho)):
            _exportar(self.repositorio)
        self.assertEqual(self.repositorio.caminho.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
