# AgroPerdas — estimativa didática de resíduos na colheita de cana

Projeto da atividade da Fase 2, capítulo 6 (**Python e além**). O programa registra medições de campo, estima a massa de cana deixada no talhão por extrapolação de uma amostra, mostra um resumo, gera arquivos locais e permite sincronizar os registros com Oracle quando houver um banco configurado. A execução local e o cálculo **não dependem** da conexão Oracle.

## Acompanhamento acadêmico

- Tutor(a): Sabrina Otoni
- Coordenador(a): André Godoi

> **Escopo:** este é um indicador estimado para exercício de programação. Uma amostra pequena ou mal escolhida não representa necessariamente o talhão inteiro. O resultado não comprova a perda real da colheita, não identifica sua causa e não substitui um protocolo agronômico de amostragem.

## Problema e cálculo

Depois da colheita, pesa-se o resíduo de cana encontrado em uma área amostrada. O programa extrapola a densidade observada para a área colhida:

```text
perda_estimada_t = (residuo_amostra_kg / area_amostrada_m2)
                   × (area_colhida_ha × 10.000 m²/ha) / 1.000 kg/t

percentual_perda = perda_estimada_t
                   / (massa_colhida_t + perda_estimada_t) × 100
```

O denominador do percentual é a soma da massa efetivamente colhida com a perda **estimada**. Essa definição precisa ser mantida ao comparar medições; dividir apenas pela massa colhida seria outro indicador.

**Exemplo:** um talhão de **2 ha** tem **20.000 m²**. Em uma amostra de **10 m²** foi encontrado **1 kg** de resíduo. A extrapolação é `1 ÷ 10 × 20.000 = 2.000 kg`, ou **2 t**. Se foram colhidas **200 t**, o indicador é `2 ÷ (200 + 2) × 100 = 0,9901%`, apresentado como **0,99%**. A estimativa não significa que alguém tenha pesado 2 t de resíduo em toda a área.

Cada cadastro também recebe um limite percentual informado pelo usuário. O programa destaca medições cujo percentual calculado é **maior** que esse limite. O alerta é uma regra de acompanhamento escolhida no exercício, não um limite agronômico universal.

## Diferencial da proposta

O AgroPerdas transforma uma pesagem simples de campo em uma **triagem operacional**: calcula a estimativa por talhão, compara-a com um limite definido pelo próprio usuário e ordena as amostras para priorizar a investigação das maiores perdas. O percentual agregado usa as massas somadas, evitando a interpretação incorreta de uma média simples entre talhões de tamanhos diferentes.

O cadastro funciona mesmo sem rede e mantém as medições em JSON local. Uma amostra já salva pode ser corrigida sem mudar seu identificador; quando o Oracle está disponível, a sincronização por identificador único permite enviar essa correção sem duplicar linhas. Esse fluxo local-mais-banco é o diferencial técnico do exercício. Não se afirma que o programa descobriu uma causa agronômica ou realizou uma previsão por IA.

## O que o projeto demonstra

| Conteúdo estudado | Aplicação neste trabalho |
|---|---|
| Cap. 3 — funções e procedimentos | Funções separadas para validar entradas, calcular indicadores, registrar, resumir e apresentar resultados; o menu chama cada operação. |
| Cap. 4 — estruturas de dados | Uma **lista** reúne os registros; cada registro é um **dicionário** com campos nomeados; o cálculo retorna uma **tupla** `(perda_t, percentual, acima_do_limite)`; uma lista de dicionários forma a tabela/ranking em memória. |
| Cap. 5 — arquivos | Persistência local em **JSON**, correção de registros e exportação de resumo em **texto**. O JSON conserva os campos para reabrir os registros; o texto facilita a leitura humana. |
| Cap. 6 — exceções e banco de dados | Entradas incorretas geram mensagens tratadas; a sincronização opcional usa Oracle, SQL parametrizado, `commit()` após sucesso e `rollback()` em falha. |

O projeto **não** é um sistema de previsão por IA, nem uma medição automática com sensores. As entradas são informadas manualmente.

O capítulo usa **pandas** para exibir tabelas no exemplo do petshop. Aqui, a mesma necessidade de apresentação é resolvida por uma tabela em memória e formatação de texto, sem dependência adicional para o uso local. Para conectar ao Oracle, o pacote `oracledb` continua necessário.

## Estrutura

```text
Fase2_Trabalho3_AgroPerdas/
├── main.py                  # menu de execução
├── agroperdas/
│   ├── core.py              # validação, cálculo e resumo
│   ├── cli.py               # interface e procedimentos do menu
│   ├── storage.py           # leitura/gravação JSON e relatório texto
│   └── oracle_db.py         # sincronização por escolha do usuário
├── tests/                   # testes automatizados
├── schema.sql               # criação da tabela Oracle
├── verificar_oracle.py       # teste de conexão e criação opcional da tabela
├── requirements.txt         # dependências da integração Oracle
├── .env.example             # nomes das variáveis, sem segredos
└── .gitignore               # exclui credenciais e dados gerados
```

Os diretórios `dados/` e `relatorios/` são usados para saídas locais. O arquivo padrão de registros é `dados/registros.json`; arquivos gerados não devem entrar no Git.

## Como executar

Na pasta deste projeto, em Windows com Python 3 instalado:

```powershell
py main.py
```

O uso **local** não precisa de credenciais Oracle. Para habilitar a opção de sincronização, instale as dependências:

```powershell
py -m pip install -r requirements.txt
```

No menu, a sequência esperada é:

1. **Cadastrar medição:** informar data da colheita, talhão, área colhida em hectares, área amostrada em metros quadrados, resíduo encontrado em quilogramas, massa colhida em toneladas e limite percentual. Cada resposta é validada na hora: se estiver incorreta, o programa explica o problema e pede **somente aquele campo novamente**, mantendo os anteriores. Depois, calcula os indicadores.
2. **Listar medições:** visualizar os registros e o ranking de perdas estimadas.
3. **Mostrar resumo:** consultar totais de área, massa colhida, perda estimada e percentual agregado. O percentual total é calculado sobre as massas somadas, não pela média simples dos percentuais de cada linha.
4. **Exportar relatório:** salvar um resumo legível em arquivo de texto. Os registros locais são mantidos em JSON.
5. **Sincronizar com Oracle:** enviar os registros locais para a tabela criada por `schema.sql`. A integração foi implementada e validada; a execução dessa opção exige configuração e conectividade no ambiente de quem usar o programa.
6. **Corrigir uma amostra:** escolha a opção `6`, selecione o número mostrado na lista, altere um ou mais campos (`1` a `7`) e escolha `8` para gravar. O ID é preservado e a perda e o percentual são recalculados. Se a amostra já tiver sido enviada ao Oracle, use depois a opção `5` para atualizar a linha remota.
7. **Sair:** no menu, digite `0`.

Durante um cadastro ou ao digitar um novo valor na correção, `/cancelar` volta ao menu sem salvar a operação em andamento. Na lista de correção, `0` também cancela. Uma combinação inválida de campos não é gravada: o programa mostra o motivo e permite ajustar os valores antes de escolher `8` novamente.

Use ponto ou vírgula para números decimais conforme a entrada solicitada pelo programa. A data deve estar em `AAAA-MM-DD`. Áreas amostrada e colhida e massa colhida devem ser positivas; a amostra não pode superar a área colhida convertida para m²; resíduo pode ser zero; limite deve ser maior que zero e menor que 100. Para evitar falhas ou arredondamento a zero nas colunas numéricas do Oracle, valores positivos abaixo de `0,0001` e valores a partir de `100.000.000.000.000` são rejeitados; a perda e o percentual calculados também são conferidos. Em combinações numéricas extremas, o programa deixa corrigir um campo sem recomeçar o cadastro. Entradas inválidas não viram medições gravadas.

## Integração Oracle — configuração pelo estudante

Esta etapa exige uma instância Oracle acessível, usuário com permissão para criar tabela e dados de conexão fornecidos pela instituição ou pelo proprietário do banco. A conexão e a sincronização foram validadas em uma conta de estudante; os testes simulados continuam úteis para regressão, mas não substituem uma configuração própria para quem clonar o projeto.

1. Copie `.env.example` para um arquivo chamado `.env` **na pasta do projeto** e preencha localmente `AGRO_ORACLE_USER`, `AGRO_ORACLE_PASSWORD` e `AGRO_ORACLE_DSN`. A orientação da turma informa o usuário no formato `rm` seguido do RM; confirme os dados de acesso no seu ambiente. Não envie senha ou `.env` por chat e não os publique no GitHub.
2. Instale `requirements.txt`. Execute `py verificar_oracle.py` para testar a autenticação e verificar se a tabela existe. Se ela estiver ausente, use `py verificar_oracle.py --criar-tabela`: o script só a cria se não existir. Também é possível executar o conteúdo de [`schema.sql`](schema.sql) **uma vez** pelo SQL Developer. O SQL Developer é um cliente; não é o servidor de banco.
3. Execute `py main.py`, cadastre uma amostra e escolha **Sincronizar com Oracle**. Consulte a tabela `AGROPERDAS_MEDICOES` para verificar se o registro chegou.

A operação usa parâmetros SQL em vez de concatenar valores digitados ao comando. Cada registro tem um UUID; repetir a sincronização atualiza o mesmo identificador, sem criar uma segunda linha para ele. A correção local só modifica o JSON até que o usuário escolha sincronizar. Em caso de falha, a transação é desfeita e o arquivo JSON local é preservado. Isso não garante que problemas externos de rede, permissão ou configuração estejam resolvidos; esses itens precisam ser testados no ambiente real.

**Validação real em 13/10/2026:** a autenticação e a consulta ao Oracle da FIAP passaram. A tabela `AGROPERDAS_MEDICOES` foi criada no usuário do estudante. Pelo menu do programa, uma amostra fictícia `DEMO-ORACLE` foi registrada localmente e sincronizada; consulta separada confirmou **2,0000 t** de perda estimada e **0,9901%**. Uma segunda sincronização da mesma amostra manteve **uma única linha**, confirmando o comportamento idempotente. As credenciais e o arquivo `.env` permaneceram apenas no computador local.

## Testes e conferência

Execute os testes automatizados na pasta do projeto:

```powershell
py -m unittest discover -s tests -v
```

Os testes verificam regras de cálculo/validação, repetição do campo incorreto no menu, cancelamento e correção de uma amostra preservando o ID, arquivos e o comportamento da transação Oracle com objetos simulados. Para a conferência manual, escolha `1` e digite primeiro uma data impossível, como `2026-02-30`: o programa deve pedir **novamente só a data**. Depois, cadastre o exemplo de **2 ha / 10 m² / 1 kg / 200 t**, confirme **2 t** e **0,99%**. Escolha `6`, mude o resíduo para `2 kg` e salve com `8`: a perda deve passar a **4 t** e o ID deve continuar igual. Feche e reabra o programa para conferir o JSON, liste/resuma as medições e exporte o relatório. A integração também foi executada e consultada no banco real, conforme o registro de validação acima.

## Limitações e boas práticas de entrega

- A confiabilidade depende do plano de amostragem: localização, quantidade de amostras, uniformidade do talhão, umidade e modo de coleta podem alterar muito a estimativa. O programa não calcula intervalo de confiança nem corrige viés de amostragem.
- O percentual é um **indicador calculado**, não uma certificação de perdas. Não use o número isolado para decisões financeiras ou agronômicas reais.
- Não altere resultados manualmente no JSON: na leitura, os indicadores são recalculados e conferidos contra os dados da amostra.
- A opção de exclusão não foi copiada do projeto FarmTech: apagar só o JSON não removeria a linha que já tivesse sido sincronizada no Oracle. O foco aqui é corrigir e sincronizar com consistência; exclusão remota exigiria um fluxo próprio.
- Publique código, testes, este README, `schema.sql`, `requirements.txt` e `.env.example`; mantenha fora do Git o `.env`, senhas, dados reais e saídas locais geradas. Confira `git status` antes de publicar.
- A página do portal aceita anexos (até 20, máximo de 256 MB por arquivo) e mostra prazo de **14/10/2026 às 23h59**. Depois de publicar o repositório, anexe o arquivo de encaminhamento solicitado e confirme o estado **enviado para avaliação**. A publicação no GitHub e o envio ao portal são etapas distintas.

Quem reproduzir o projeto precisa configurar seus próprios dados de acesso Oracle. Não coloque credenciais no repositório nem em capturas de tela. Depois de publicar, confira se o professor consegue abrir o repositório ou se precisa de convite, conforme as instruções específicas desta atividade.
