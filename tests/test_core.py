"""Testes unitários das regras de amostragem e validação."""

import unittest

from agroperdas.core import (
    ErroValidacao,
    calcular_indicadores,
    construir_tabela_memoria,
    criar_registro,
    resumir_registros,
    validar_registro,
)


class TestCore(unittest.TestCase):
    def setUp(self) -> None:
        self.registro = criar_registro(
            data_colheita="2026-10-12",
            talhao="Talhão A",
            area_colhida_ha=2,
            area_amostrada_m2=10,
            residuo_amostra_kg=2,
            massa_colhida_t=96,
            limite_percentual=3,
        )

    def test_formula_e_alerta(self) -> None:
        perda, percentual, acima = calcular_indicadores(self.registro)
        self.assertAlmostEqual(perda, 4.0)
        self.assertAlmostEqual(percentual, 4.0)
        self.assertTrue(acima)
        self.assertEqual(self.registro["perda_estimada_t"], perda)
        self.assertEqual(self.registro["percentual_perda"], percentual)

    def test_zero_residuo_permitido(self) -> None:
        dados = dict(self.registro, residuo_amostra_kg=0)
        dados.pop("perda_estimada_t")
        dados.pop("percentual_perda")
        validado = validar_registro(dados)
        self.assertEqual(validado["perda_estimada_t"], 0)
        self.assertEqual(validado["percentual_perda"], 0)

    def test_numeros_e_datas_invalidos(self) -> None:
        casos = (
            ("area_colhida_ha", 0),
            ("area_colhida_ha", 1e14),
            ("area_amostrada_m2", -1),
            ("area_amostrada_m2", 1e-6),
            ("residuo_amostra_kg", -0.1),
            ("residuo_amostra_kg", 1e-6),
            ("massa_colhida_t", float("nan")),
            ("massa_colhida_t", 1e-6),
            ("limite_percentual", 100),
            ("limite_percentual", 0),
            ("limite_percentual", 1e-6),
            ("data_colheita", "2026-02-30"),
            ("talhao", "  "),
        )
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                dados = dict(self.registro, **{campo: valor})
                dados.pop("perda_estimada_t")
                dados.pop("percentual_perda")
                with self.assertRaises(ErroValidacao):
                    validar_registro(dados)

    def test_indicador_adulterado_e_detectado(self) -> None:
        with self.assertRaises(ErroValidacao):
            validar_registro(dict(self.registro, perda_estimada_t=900))

    def test_amostra_nao_excede_area_colhida(self) -> None:
        dados = dict(self.registro, area_amostrada_m2=20_000)
        dados.pop("perda_estimada_t")
        dados.pop("percentual_perda")
        # A borda é válida: a amostra cobre exatamente os 2 ha colhidos.
        self.assertAlmostEqual(validar_registro(dados)["perda_estimada_t"], 0.002)
        dados["area_amostrada_m2"] = 20_001
        with self.assertRaisesRegex(ErroValidacao, "não pode superar"):
            validar_registro(dados)

    def test_resultado_calculado_nao_pode_exceder_coluna_oracle(self) -> None:
        dados = dict(self.registro, area_colhida_ha=1e13, area_amostrada_m2=1, residuo_amostra_kg=100)
        dados.pop("perda_estimada_t")
        dados.pop("percentual_perda")
        with self.assertRaisesRegex(ErroValidacao, "perda estimada excede"):
            validar_registro(dados)

    def test_resultados_pequenos_nao_sao_arredondados_a_zero_no_oracle(self) -> None:
        dados = dict(self.registro, area_colhida_ha=1, area_amostrada_m2=10_000)
        dados.pop("perda_estimada_t")
        dados.pop("percentual_perda")
        dados["residuo_amostra_kg"] = 0.0001
        with self.assertRaisesRegex(ErroValidacao, "perda estimada ficou abaixo"):
            validar_registro(dados)

        dados["residuo_amostra_kg"] = 1
        dados["massa_colhida_t"] = 100_000
        with self.assertRaisesRegex(ErroValidacao, "percentual de perda ficou abaixo"):
            validar_registro(dados)

    def test_ranking_e_percentual_ponderado(self) -> None:
        segundo = criar_registro(
            data_colheita="2026-10-13",
            talhao="Talhão B",
            area_colhida_ha=1,
            area_amostrada_m2=10,
            residuo_amostra_kg=1,
            massa_colhida_t=49,
            limite_percentual=3,
        )
        tabela = construir_tabela_memoria([segundo, self.registro])
        self.assertEqual(tabela[0]["talhao"], "Talhão A")
        resumo = resumir_registros([segundo, self.registro])
        self.assertEqual(resumo["quantidade"], 2)
        self.assertAlmostEqual(resumo["perda_estimada_t"], 5)
        self.assertAlmostEqual(resumo["percentual_total"], 5 / 150 * 100)
        self.assertEqual(resumo["acima_do_limite"], 1)


if __name__ == "__main__":
    unittest.main()
