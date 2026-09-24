# Catálogo de imóveis para o agente de IA — Milano Imóveis

Página única, gerada automaticamente a partir do site da imobiliária, com **todos** os imóveis
anunciados em formato padronizado. Ela serve de fonte para a base de conhecimento do agente no Flowtalks.

## Por que existe

O importador de links da base de conhecimento lê o site como um robô. Nas listagens do site,
um robô só enxerga os 12 primeiros imóveis e o filtro por bairro é ignorado. Resultado: o agente
não encontrava a maior parte dos imóveis e misturava bairros.

Esta página resolve isso:

- lê o **sitemap** do site (atualizado sozinho pela ImoTools) e abre **cada imóvel**;
- ignora os blocos "Imóveis relacionados" e "Mais buscados", que causavam a mistura de bairros;
- publica **um bloco por imóvel**, com todos os campos rotulados, e um **índice por bairro**;
- roda **a cada hora**. Imóvel novo entra e imóvel removido sai, sem trabalho manual.

## Travas de segurança

O catálogo anterior é mantido, e a execução é marcada como falha (o GitHub envia um e-mail), se:

- mais de 20% das páginas de imóveis não puderem ser lidas;
- o total de imóveis cair abaixo de 60% do total da última execução (sinal de mudança de layout ou bloqueio do site).

O agente nunca recebe um catálogo vazio ou quebrado.

## Implantação (cerca de 10 minutos)

1. Crie um repositório no GitHub (ex.: `milano-catalogo`) e envie estes arquivos.
   O GitHub Pages gratuito exige repositório **público**. Os dados já são públicos no site da imobiliária.
2. Em **Settings → Actions → General → Workflow permissions**, marque **Read and write permissions**.
3. Em **Actions**, abra "Atualizar catálogo de imóveis" e clique em **Run workflow**.
   Aguarde terminar (cerca de 2 minutos) e confira o resumo: total de imóveis e alertas de cadastro.
4. Em **Settings → Pages**, escolha **Deploy from a branch**, branch `main`, pasta `/docs`.
5. O catálogo fica disponível em `https://<usuario>.github.io/milano-catalogo/`.
6. No Flowtalks, cadastre esse link na base de conhecimento, com ressincronização automática (diária, no mínimo).

## Arquivos gerados em `docs/`

| Arquivo | Uso |
|---|---|
| `index.html` | Página-catálogo: é o link cadastrado no Flowtalks |
| `catalogo.txt` | Mesmo conteúdo em texto puro, para importadores que preferem arquivo |
| `catalogo.json` | Dados estruturados, usados também pela trava de segurança |

A página tem `noindex`, para não competir com o site da imobiliária no Google.

## Alertas de cadastro

Cada execução lista, no resumo da Action, os cadastros que fazem o agente errar: quartos não
informados, área não informada e valor do campo diferente do valor citado na descrição.
Repasse periodicamente à imobiliária para correção no painel da ImoTools.

## Reaproveitar para outra imobiliária (sites ImoTools)

Troque as variáveis no workflow: `BASE_URL`, `NOME_IMOBILIARIA` e `UF`. O restante é igual.

## Alternativa sem GitHub

O script roda em qualquer servidor com Python 3.10+:

```bash
pip install -r requirements.txt
BASE_URL=https://www.imobiliariamilano.com.br OUTPUT_DIR=/var/www/catalogo python3 catalogo.py
```

Agende de hora em hora no cron e publique a pasta de saída em um servidor web.
