import unittest

from agroperdas.oracle_db import SQL_MERGE, _sincronizar_com_conexao


class CursorFalso:
    def __init__(self, falhar=False):
        self.chamadas = []
        self.falhar = falhar
        self.fechado = False

    def execute(self, sql, parametros):
        self.chamadas.append((sql, parametros))
        if self.falhar:
            raise RuntimeError("falha simulada")

    def close(self):
        self.fechado = True


class ConexaoFalsa:
    def __init__(self, falhar=False):
        self.cursor_falso = CursorFalso(falhar)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_falso

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


REGISTRO = {
    "id": "8ff728b9-e1a2-470a-aef9-c71c3184b138",
    "data_colheita": "2026-10-13",
    "talhao": "T01",
    "area_colhida_ha": 2.0,
    "area_amostrada_m2": 10.0,
    "residuo_amostra_kg": 1.0,
    "massa_colhida_t": 200.0,
    "limite_percentual": 5.0,
    "perda_estimada_t": 2.0,
    "percentual_perda": 0.990099,
}


class TesteOracle(unittest.TestCase):
    def test_merge_usa_binds_e_confirma(self):
        self.assertIn(":id", SQL_MERGE)
        self.assertNotIn(REGISTRO["id"], SQL_MERGE)
        conexao = ConexaoFalsa()
        self.assertEqual(_sincronizar_com_conexao(conexao, [REGISTRO]), 1)
        self.assertEqual(conexao.commits, 1)
        self.assertEqual(conexao.rollbacks, 0)
        self.assertEqual(conexao.cursor_falso.chamadas[0][1]["id"], REGISTRO["id"])
        self.assertTrue(conexao.cursor_falso.fechado)

    def test_erro_desfaz_transacao(self):
        conexao = ConexaoFalsa(falhar=True)
        with self.assertRaises(RuntimeError):
            _sincronizar_com_conexao(conexao, [REGISTRO])
        self.assertEqual(conexao.commits, 0)
        self.assertEqual(conexao.rollbacks, 1)
        self.assertTrue(conexao.cursor_falso.fechado)


if __name__ == "__main__":
    unittest.main()
