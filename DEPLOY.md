# Deploy no Streamlit Cloud

## Por que isso resolve o problema de acesso à API

O ambiente de chat da Claude só acessa URLs que já apareceram antes
numa busca — não deixa montar uma URL nova (ex: trocar o ano numa
chamada de API). O servidor do Streamlit Cloud não tem essa
restrição: ele faz requisições HTTP livres, então o botão "Buscar
dados" dentro do app vai funcionar para qualquer temporada, sem
travar.

## Estrutura do repositório (já pronta, não precisa reorganizar nada)

```
brasileirao_app/
├── streamlit_app.py       ← arquivo principal (aponte o Streamlit Cloud pra ele)
├── requirements.txt       ← dependências
└── sports_data_layer/     ← o pacote inteiro (coleta + hipóteses + testes)
    ├── models.py
    ├── capabilities.py
    ├── adapters/
    ├── tools/
    ├── hypotheses/
    └── tests/
```

## Passo a passo

### 1. Subir pro GitHub

```bash
cd brasileirao_app
git init
git add .
git commit -m "Motor de descobertas do Brasileirão"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/brasileirao-descobertas.git
git push -u origin main
```

(Crie o repositório vazio no GitHub antes, pelo site, sem README —
senão o `git push` vai dar conflito.)

### 2. Deploy no Streamlit Cloud

1. Acesse [share.streamlit.io](https://share.streamlit.io) e faça login com sua conta GitHub.
2. Clique em **"New app"**.
3. Selecione o repositório que você acabou de criar.
4. Em **"Main file path"**, digite: `streamlit_app.py`
5. Clique em **"Deploy"**.

Em 1-2 minutos o app estará no ar, com uma URL tipo
`https://seu-app.streamlit.app`.

### 3. Usando o app

- Na barra lateral, escolha o intervalo de temporadas (2014-2026).
- Clique em **"Buscar dados e rodar o motor"**.
- O app busca cada temporada, monta o mapeamento automático de
  campos (a mesma lógica que validamos no chat), extrai as
  partidas, e roda as 4 hipóteses com correção estatística.
- As descobertas aparecem embaixo; se nenhuma passar nos filtros
  (efeito prático + significância ajustada), o app avisa isso
  claramente em vez de mostrar uma tela vazia confusa.

## Limitações a saber

- A TheSportsDB pode não ter dados completos pra todas as 13
  temporadas (2014-2026) — o app mostra quais anos vieram vazios.
- O plano gratuito da TheSportsDB tem limite de requisições; o app
  já espera um intervalo curto entre chamadas (0.3s) pra ser gentil
  com isso, mas buscar as 13 temporadas de uma vez pode demorar
  ~10-15 segundos.
- O cache do Streamlit (`@st.cache_data`) guarda o resultado de cada
  temporada already buscada, então clicar em "buscar" de novo com o
  mesmo intervalo é instantâneo — só busca de verdade o que ainda
  não tem em cache.
