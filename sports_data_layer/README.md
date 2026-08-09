# Camada de dados autônoma — motor de descobertas esportivas

Pipeline que vai de "URL de uma API de futebol" a "dados normalizados
prontos para o motor de hipóteses", **sem nenhum passo manual** — nem
para adicionar um provedor novo, nem para manter os existentes
funcionando quando a API muda algo silenciosamente.

## Como funciona, em uma frase

Você aponta o pipeline pra uma URL nova; ele descobre o schema, decide
por conta própria quais campos usar, valida se os valores fazem
sentido, e só usa o que passou nas duas checagens. O que não passou
fica de fora — automaticamente, sem travar nada e sem pedir revisão.

## Arquitetura (do consumidor pra fonte)

```
Motor de hipóteses (D001-D1500)
        ↓ usa apenas
SportsDataRegistry (cache + fallback entre provedores)
        ↓ construída por
bootstrap.bootstrap_registry()
        ↓ que chama, por provedor
autonomous_pipeline.run_autonomous_ingestion()
        ↓ que orquestra
1. schema_discovery  → lista todos os campos da resposta bruta
2. auto_mapper       → propõe conceito por nome + valida por valor plausível
3. capabilities_from_mapping → deriva o que este provedor sabe entregar
4. GenericMappingAdapter → extrai Match/StandingRow usando só o mapping salvo
```

Nenhum adaptador novo precisa ser escrito à mão. `GenericMappingAdapter`
serve qualquer provedor, desde que exista um `mappings/<provider>.json`
— e esse arquivo é gerado e atualizado sozinho.

## As duas camadas de defesa (por que "autônomo" não é "sem controle")

Um sistema que decide sozinho precisa de garantias de que não vai
decidir errado silenciosamente — porque dado errado alimentando o
motor estatístico é pior que dado ausente: gera "descobertas"
publicadas com aparência de solidez que na verdade são ruído.

1. **Confiança por nome de campo** (`propose_mapping`): o nome do
   campo bruto precisa conter todos os tokens da assinatura de um
   conceito (ex: `home_score` exige os tokens `placar` + `mandante`
   juntos, não isolados — isso é o que evita confundir
   `placar_mandante` com o nome do time só por compartilharem
   `mandante`).
2. **Sanidade por valor de exemplo** (`apply_sanity_gate`): mesmo com
   nome perfeito, o valor de exemplo precisa ser fisicamente
   plausível (`home_score` entre 0 e 20, `match_date` precisa
   parsear como data, etc). Um nome que bate por coincidência mas
   aponta pra um valor absurdo é descartado aqui.

O que sobra depois das duas camadas vai para `mappings/<provider>.json`
e é usado. O que não sobra vai para `quarantine/<provider>.json` — só
como log de auditoria, nunca como bloqueio.

## Rodando o pipeline completo

```bash
pip install -r requirements.txt
python -m sports_data_layer.tools.bootstrap
```

Isso descobre schema, mapeia, deriva capacidades e monta a
`SportsDataRegistry` para todos os provedores configurados dentro de
`bootstrap.py` (edite a lista `specs` lá para adicionar/remover
provedores e competições).

## Agendando para rodar sozinho todo dia

```cron
# Todo dia às 6h da manhã, atualiza mappings e reprocessa dados.
0 6 * * * cd /caminho/do/projeto && /usr/bin/python3 -m sports_data_layer.tools.bootstrap >> logs/pipeline.log 2>&1
```

O log mostra, todo dia, quantos campos foram mapeados automaticamente,
quantos foram pra quarentena, e **o que mudou desde a última execução**
(`mudou_desde_ultima_vez` no retorno de `build_and_save_mapping`) — é
assim que você percebe uma API mudando de schema sem precisar ficar
checando manualmente.

## Adicionando um provedor novo

Edite `tools/bootstrap.py` e adicione um `ProviderSpec` com a URL nova.
Não é preciso escrever nenhuma classe de adaptador — só isso:

```python
ProviderSpec(
    provider="dados_futebol",
    url="https://dadosfutebol.com.br/api/partidas",
    competition="brasileirao_b",
    headers={"Authorization": "Bearer SEU_TOKEN"},
)
```

Na primeira execução, o pipeline descobre o schema dessa API sozinho.

## Rodando os testes de regressão

```bash
python -m pytest sports_data_layer/tests/ -v
```

Os testes cobrem os dois bugs reais encontrados durante o
desenvolvimento (confusão entre `home_score` e nome do time por
substring; rejeição injusta de campos aninhados legítimos por causa
do limiar de confiança) — existem justamente para que uma mudança
futura na heurística não reintroduza esses erros silenciosamente.

## Motor de descobertas (hipóteses)

Implementado em `hypotheses/`, com 4 hipóteses reais do MVP original,
cada uma com dois filtros independentes antes de publicar algo:

1. **Efeito prático** — a diferença precisa ser grande o suficiente
   pra importar de verdade (limiar em pontos percentuais, definido
   por hipótese).
2. **Significância estatística ajustada** — depois que todas as
   hipóteses rodam, `apply_multiple_comparisons_correction` aplica
   Benjamini-Hochberg sobre o LOTE INTEIRO de candidatos, corrigindo
   pelo fato de estarmos testando vários times/hipóteses ao mesmo
   tempo (o "elefante na sala" da primeira conversa deste projeto).

| Código | Hipótese | Capacidades necessárias |
|---|---|---|
| D006 | Desempenho em casa vs fora | `BASIC_RESULTS` |
| D010 | Sequência quente/fria | `BASIC_RESULTS` |
| D022 | Impacto dos dias de descanso | `BASIC_RESULTS` |
| D101 | Aproveitamento por faixa de tabela do adversário (G6/meio/Z4) | `BASIC_RESULTS` + `STANDINGS` |

Rodar tudo:

```python
from sports_data_layer.hypotheses.run_all_hypotheses import run_daily_discoveries
discoveries = run_daily_discoveries(matches, standings)
```

### As 6 hipóteses do MVP original que ficaram de fora — e por quê

Isto é deliberado, não esquecido. Cada uma exige uma capacidade de
dado que nenhum provedor testado até agora entrega de forma confiável:

| Hipótese do MVP | Bloqueada por |
|---|---|
| Melhor desempenho por faixa de minutos | Precisa de `MATCH_EVENTS` com minuto exato — extração genérica não implementada ainda para eventos aninhados dentro de cada partida |
| Dependência de jogador-chave | Precisa de estatística de jogador por partida — nenhum provedor gratuito testado entrega isso de forma confiável |
| Eficiência das substituições | Precisa de `SUBSTITUTIONS` com minuto — mesma limitação de eventos aninhados acima |
| Rendimento contra estilos de jogo | Precisa de uma classificação de "estilo tático" por time — não existe fonte de dado pra isso no projeto hoje |
| Efeito das viagens longas | Precisa de geolocalização de estádio pra calcular distância — não coletado |
| xG (gols esperados) vs gols marcados | Precisa de dado de posição em jogadores em campo — nenhum provedor gratuito testado tem isso |

Quando (e se) uma dessas capacidades for adicionada — por exemplo,
integrando a API Futebol paga, que promete escalação e eventos — a
hipótese correspondente pode ser escrita seguindo o mesmo molde de
`Hypothesis` em `hypotheses/base.py`.

### Limitação estatística conhecida do D101

`opponent_tier.py` usa a tabela de classificação FINAL da temporada
pra decidir quem é G6/meio/Z4, não a tabela como estava no dia de
cada jogo. Isso é um viés de "olhar pra trás" documentado no próprio
código — pra corrigir de verdade seria preciso guardar um histórico
de tabela por rodada, que não existe ainda no `StandingRow`.



- `get_match_detail` (lineups, substituições, eventos por minuto)
  ainda não tem extração genérica — o `GenericMappingAdapter` cobre
  hoje resultados básicos e tabela de classificação. Estender pra
  eventos aninhados é o próximo passo natural, mas exige mapear listas
  dentro de listas (eventos dentro de cada partida), que é mais
  complexo que o caso atual.
- A heurística de nomes (`CONCEPT_SIGNATURES` em `schema_discovery.py`)
  só reconhece os padrões de nomenclatura que já vimos (português e
  inglês, estilos API Futebol / TheSportsDB). Um provedor com
  convenção de nomes muito diferente vai ter menos campos mapeados
  automaticamente até alguém ampliar as assinaturas — o sistema não
  quebra nesse caso, só fica mais conservador.
