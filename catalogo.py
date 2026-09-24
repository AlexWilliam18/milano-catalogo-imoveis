#!/usr/bin/env python3
"""
Gerador de página-catálogo de imóveis para bases de conhecimento de agentes de IA.

Lê o sitemap de um site ImoTools, abre a página de cada imóvel e publica uma
página única e padronizada (um bloco por imóvel, todos os campos rotulados).
Assim o importador da base de conhecimento enxerga TODOS os imóveis, sem
paginação e sem misturar bairros.

Configuração por variáveis de ambiente (valores padrão = Milano Imóveis):
  BASE_URL           https://www.imobiliariamilano.com.br
  NOME_IMOBILIARIA   Milano Aluguel e Venda de Imóveis
  OUTPUT_DIR         docs
  UF                 MG
  MIN_RATIO          0.6   (trava: aborta se o total cair abaixo de 60% da última execução)
  REQUEST_DELAY      0.6   (segundos entre requisições, para não sobrecarregar o site)
"""

import html
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE_URL = os.environ.get("BASE_URL", "https://www.imobiliariamilano.com.br").rstrip("/")
NOME = os.environ.get("NOME_IMOBILIARIA", "Milano Aluguel e Venda de Imóveis")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "docs")
UF = os.environ.get("UF", "MG")
MIN_RATIO = float(os.environ.get("MIN_RATIO", "0.6"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "0.6"))
MAX_FALHAS = 0.2  # aborta se mais de 20% das páginas falharem
TZ = ZoneInfo("America/Sao_Paulo")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CatalogoImoveisBot/1.0; atualizacao de base de atendimento)",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Categoria do imóvel pelo início do endereço da página (é a categoria usada pelo filtro do site).
TIPOS = [
    ("sala-conjunto", "Sala comercial"),
    ("lote-terreno", "Lote / Terreno"),
    ("apartamento", "Apartamento"),
    ("sobrado", "Sobrado"),
    ("kitnet", "Kitnet"),
    ("chacara", "Chácara"),
    ("galpao", "Galpão / Barracão"),
    ("predio", "Prédio"),
    ("loja", "Loja / Ponto comercial"),
    ("andar", "Andar"),
    ("casa", "Casa"),
]

session = requests.Session()
session.headers.update(HEADERS)


def log(msg):
    print(msg, flush=True)


def limpar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def baixar(url):
    """GET com novas tentativas em caso de bloqueio temporário (429) ou erro de servidor."""
    for tentativa in range(6):
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            log(f"  erro de rede ({e}); tentando de novo")
            time.sleep(3 * (tentativa + 1))
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(4 * (tentativa + 1))
            continue
        return r
    return None


def urls_do_sitemap():
    r = baixar(f"{BASE_URL}/sitemap.xml")
    if r is None or r.status_code != 200:
        raise RuntimeError("Não foi possível ler o sitemap do site.")
    urls = re.findall(r"<loc>\s*([^<]+/imovel/[^<]+?)\s*</loc>", r.text)
    return list(dict.fromkeys(u.strip() for u in urls))


def tipo_pelo_endereco(url):
    slug = url.rstrip("/").split("/imovel/")[-1]
    for chave, rotulo in TIPOS:
        if slug.startswith(chave):
            return rotulo
    return None


def valor_informado(v, zero_invalido=True):
    """Converte campos vazios/placeholder do cadastro em None."""
    v = limpar(v)
    if not v:
        return None
    if zero_invalido and v in {"0", "0 m²", "1 m²"}:
        return None
    return v


def extrair(html_text, url):
    soup = BeautifulSoup(html_text, "html.parser")

    # Dados estruturados (JSON-LD) antes de remover os scripts.
    breadcrumb, listing = [], {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(j, dict) and j.get("@type") == "BreadcrumbList":
            breadcrumb = [i.get("name", "") for i in j.get("itemListElement", [])]
        if isinstance(j, dict) and j.get("@type") == "RealEstateListing":
            listing = j

    main = soup.find("main") or soup.body or soup
    for tag in main.find_all(["script", "style", "form", "noscript"]):
        tag.decompose()

    # Remove blocos com OUTROS imóveis (relacionados / mais buscados): causa de mistura de bairros.
    alvos = []
    for h in main.find_all(["h2", "h3"]):
        if re.search(r"relacionados|mais buscados", h.get_text(), re.I):
            alvos.append(h.find_parent("section") or h.parent)
    for alvo in alvos:
        if alvo is not None and alvo.parent is not None:
            alvo.decompose()

    texto = main.get_text(" ", strip=True)
    m = re.search(r"c[óo]digo:\s*([A-Za-z0-9]+)", texto, re.I)
    if not m:
        return None
    codigo = m.group(1).upper()

    # Valores (aluguel / venda). Um imóvel pode ter os dois.
    valores = {}
    for rotulo in main.select(".box-valores .t-box-lateral"):
        chave = limpar(rotulo.get_text()).rstrip(":")
        prox = rotulo.find_next_sibling()
        if chave and prox:
            valores.setdefault(chave, limpar(prox.get_text()))
    if not valores:  # alternativa por texto, caso o layout mude
        for chave, val in re.findall(
            r"(Valor do aluguel|Valor de compra do imóvel|Valor de venda):\s*(Sob consulta|R\$\s*[\d\.,]+(?:/mês)?)",
            texto,
        ):
            valores.setdefault(chave, val)

    aluguel = valores.get("Valor do aluguel")
    venda = valores.get("Valor de compra do imóvel") or valores.get("Valor de venda")
    finalidades = [f for f, v in (("Venda", venda), ("Aluguel", aluguel)) if v]
    if not finalidades:
        return None

    # Características numéricas (quartos, banheiros, vagas, áreas).
    cac = {}
    for rotulo in main.select(".t-cac"):
        prox = rotulo.find_next_sibling()
        if prox:
            cac.setdefault(limpar(rotulo.get_text()), limpar(prox.get_text()))
    entidade = listing.get("mainEntity", {}) if isinstance(listing, dict) else {}
    if "Quartos" not in cac and entidade.get("numberOfBedrooms") is not None:
        cac["Quartos"] = str(entidade["numberOfBedrooms"])

    itens = list(dict.fromkeys(limpar(e.get_text()) for e in main.select(".vs-todas-cat") if limpar(e.get_text())))

    descricao = ""
    desc_el = main.select_one(".bloco-texto-det .p-padrao")
    if desc_el:
        for br in desc_el.find_all("br"):
            br.replace_with("\n")
        linhas = [limpar(l) for l in desc_el.get_text("\n").split("\n")]
        descricao = "\n".join(l for l in linhas if l)

    bairro = breadcrumb[2] if len(breadcrumb) > 2 else None
    cidade = breadcrumb[1] if len(breadcrumb) > 1 else None
    if not bairro:
        return None

    return {
        "codigo": codigo,
        "tipo": tipo_pelo_endereco(url) or limpar((main.find("h1") or soup.new_tag("x")).get_text()) or "Imóvel",
        "finalidades": finalidades,
        "bairro": limpar(bairro),
        "cidade": f"{limpar(cidade)}/{UF}" if cidade else "",
        "valor_venda": venda,
        "valor_aluguel": aluguel,
        "quartos": valor_informado(cac.get("Quartos")),
        "suites": valor_informado(cac.get("Suítes")),
        "banheiros": valor_informado(cac.get("Banheiro") or cac.get("Banheiros")),
        "vagas": valor_informado(cac.get("Vagas")),
        "area_total": valor_informado(cac.get("Área total")),
        "area_construida": valor_informado(cac.get("Área construída")),
        "itens": itens,
        "descricao": descricao,
        "link": f"{BASE_URL}/imoveis?codigo={codigo}",
        "pagina": url,
    }


# ---------------------------------------------------------------- saída

def finalidade_texto(im):
    if im["finalidades"] == ["Venda", "Aluguel"]:
        return "Venda e Aluguel"
    return im["finalidades"][0]


def titulo(im):
    fin = {"Venda": "à venda", "Aluguel": "para alugar", "Venda e Aluguel": "à venda e para alugar"}[finalidade_texto(im)]
    return f"Imóvel Cód. {im['codigo']} — {im['tipo']} {fin} no bairro {im['bairro']}, {im['cidade']}"


def linhas_campos(im):
    bairro = im["bairro"]
    alt = sem_acento(bairro)
    campos = [
        ("Código", im["codigo"]),
        ("Tipo", im["tipo"]),
        ("Finalidade", finalidade_texto(im)),
        ("Bairro", bairro if alt == bairro else f"{bairro} (também escrito {alt})"),
        ("Cidade", im["cidade"]),
        ("Valor de venda", im["valor_venda"]),
        ("Valor do aluguel", im["valor_aluguel"]),
        ("Quartos", im["quartos"]),
        ("Suítes", im["suites"]),
        ("Banheiros", im["banheiros"]),
        ("Vagas de garagem", im["vagas"]),
        ("Área total", im["area_total"]),
        ("Área construída", im["area_construida"]),
        ("Itens do imóvel", ", ".join(im["itens"]) if im["itens"] else None),
        ("Link do imóvel", im["link"]),
    ]
    return [(k, v) for k, v in campos if v]


def resumo_curto(im):
    partes = [im["tipo"]]
    if im["quartos"]:
        partes.append(f"{im['quartos']} quarto(s)")
    if "Aluguel" in im["finalidades"]:
        partes.append(f"aluguel {im['valor_aluguel']}")
    if "Venda" in im["finalidades"]:
        partes.append(f"venda {im['valor_venda']}")
    return f"Cód. {im['codigo']} ({', '.join(partes)})"


def ordenar(imoveis):
    return sorted(imoveis, key=lambda i: (sem_acento(i["bairro"]).lower(), i["tipo"], i["codigo"]))


def gerar_html(imoveis, atualizado):
    e = html.escape
    total_venda = sum(1 for i in imoveis if "Venda" in i["finalidades"])
    total_aluguel = sum(1 for i in imoveis if "Aluguel" in i["finalidades"])

    # Índice por bairro: responde "tem imóvel no bairro X?" numa linha só.
    indice = {}
    for im in imoveis:
        for fin in im["finalidades"]:
            indice.setdefault(im["bairro"], {}).setdefault(fin, []).append(im)
    linhas_indice = []
    for bairro in sorted(indice, key=lambda b: sem_acento(b).lower()):
        for fin, rot in (("Aluguel", "para alugar"), ("Venda", "à venda")):
            lista = indice[bairro].get(fin)
            if lista:
                itens = "; ".join(resumo_curto(i) for i in lista)
                linhas_indice.append(f"<li>Bairro {e(bairro)} — imóveis {rot} ({len(lista)}): {e(itens)}</li>")

    blocos = []
    for im in imoveis:
        campos = "".join(f"<li><strong>{e(k)}:</strong> {e(v)}</li>" for k, v in linhas_campos(im))
        desc = ""
        if im["descricao"]:
            ref = f"(Descrição do imóvel Cód. {im['codigo']}, {im['tipo']}, bairro {im['bairro']}. Os valores oficiais são os dos campos acima.)"
            desc = f"<p>{e(ref)}</p><p>" + "<br>".join(e(l) for l in im["descricao"].split("\n")) + "</p>"
        blocos.append(
            f'<article id="imovel-{e(im["codigo"])}">\n<h2>{e(titulo(im))}</h2>\n<ul>{campos}</ul>\n{desc}\n'
            f"<p>Fim do imóvel Cód. {e(im['codigo'])}.</p>\n</article>"
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Catálogo de imóveis — {e(NOME)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;line-height:1.5;color:#1a1a1a;background:#fff}}article{{border-top:1px solid #ddd;padding:12px 0}}h2{{font-size:1.05rem}}ul{{padding-left:18px}}</style>
</head>
<body>
<h1>Catálogo de imóveis disponíveis — {e(NOME)}</h1>
<p>Lista completa dos imóveis anunciados no site {e(BASE_URL)}. Atualizada automaticamente a partir do site.</p>
<p>Atualizado em: {e(atualizado)}. Total: {len(imoveis)} imóveis ({total_aluguel} para alugar, {total_venda} à venda).</p>
<p>Como ler: cada imóvel está em um bloco próprio que começa com "Imóvel Cód." e termina com "Fim do imóvel Cód.". As informações de um bloco valem somente para aquele imóvel. Campos que não aparecem não foram informados no cadastro.</p>

<h2>Índice por bairro</h2>
<ul>
{chr(10).join(linhas_indice)}
</ul>

<h2>Imóveis</h2>
{chr(10).join(blocos)}
</body>
</html>
"""


def gerar_txt(imoveis, atualizado):
    partes = [f"CATÁLOGO DE IMÓVEIS — {NOME}", f"Atualizado em: {atualizado}. Total: {len(imoveis)} imóveis.", ""]
    for im in imoveis:
        partes.append("=" * 60)
        partes.append(titulo(im))
        partes += [f"{k}: {v}" for k, v in linhas_campos(im)]
        if im["descricao"]:
            partes.append(f"Descrição (imóvel Cód. {im['codigo']}, bairro {im['bairro']}):")
            partes.append(im["descricao"])
        partes.append(f"Fim do imóvel Cód. {im['codigo']}.")
    return "\n".join(partes) + "\n"


def alertas_de_cadastro(imoveis):
    """Inconsistências que fazem o agente errar. Vão para o log/resumo da execução."""
    residenciais = {"Casa", "Apartamento", "Sobrado", "Kitnet", "Chácara"}
    alertas = []
    for im in imoveis:
        c = im["codigo"]
        if im["tipo"] in residenciais and not im["quartos"]:
            alertas.append(f"Cód. {c}: quartos não informados (residencial)")
        if not im["area_total"] and not im["area_construida"]:
            alertas.append(f"Cód. {c}: área não informada")
        campos = [im.get(k) for k in ("valor_venda", "valor_aluguel")]
        nums = {re.sub(r"[^\d,]", "", v.split("/")[0]) for v in campos if v and v.startswith("R$")}
        valores_desc = re.findall(r"R\$\s*([\d\.]+,\d{2})", im["descricao"] or "")
        if nums and valores_desc and not any(d.replace(".", "") in nums for d in valores_desc):
            fonte = ", ".join(v for v in campos if v)
            alertas.append(f"Cód. {c}: valor do cadastro ({fonte}) difere do valor citado na descrição ({', '.join('R$ ' + d for d in valores_desc)})")
    return alertas


def main():
    agora = datetime.now(TZ)
    atualizado = agora.strftime("%d/%m/%Y")  # só a data: evita commits a cada hora sem mudança real
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    caminho_json = os.path.join(OUTPUT_DIR, "catalogo.json")

    urls = urls_do_sitemap()
    log(f"Sitemap: {len(urls)} páginas de imóveis")
    if not urls:
        log("ERRO: sitemap sem imóveis. Catálogo anterior mantido.")
        return 1

    imoveis, falhas = {}, []
    for n, url in enumerate(urls, 1):
        r = baixar(url)
        if r is None or r.status_code != 200:
            falhas.append(f"{url} (HTTP {getattr(r, 'status_code', 'sem resposta')})")
        else:
            im = extrair(r.text, url)
            if im:
                imoveis.setdefault(im["codigo"], im)
            else:
                falhas.append(f"{url} (não foi possível ler os dados)")
        if n % 20 == 0:
            log(f"  {n}/{len(urls)} páginas lidas")
        time.sleep(REQUEST_DELAY)

    lista = ordenar(imoveis.values())
    log(f"Imóveis extraídos: {len(lista)} | falhas: {len(falhas)}")
    for f in falhas:
        log(f"  falha: {f}")

    # Travas de segurança: nunca publicar um catálogo quebrado por cima de um bom.
    anterior = 0
    if os.path.exists(caminho_json):
        try:
            with open(caminho_json, encoding="utf-8") as fh:
                anterior = json.load(fh).get("total", 0)
        except (json.JSONDecodeError, OSError):
            anterior = 0
    if len(falhas) > MAX_FALHAS * len(urls):
        log(f"ERRO: {len(falhas)} de {len(urls)} páginas falharam. Catálogo anterior mantido.")
        return 1
    if anterior and len(lista) < MIN_RATIO * anterior:
        log(f"ERRO: total caiu de {anterior} para {len(lista)}. Parece falha de leitura; catálogo anterior mantido.")
        return 1

    dados = {"atualizado": atualizado, "fonte": BASE_URL, "total": len(lista), "imoveis": lista}
    novo_json = json.dumps(dados, ensure_ascii=False, indent=1)

    # Só reescreve se algo mudou (evita commits desnecessários).
    if os.path.exists(caminho_json):
        with open(caminho_json, encoding="utf-8") as fh:
            if fh.read() == novo_json:
                log("Nenhuma mudança no catálogo.")
                return 0

    with open(caminho_json, "w", encoding="utf-8") as fh:
        fh.write(novo_json)
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(gerar_html(lista, atualizado))
    with open(os.path.join(OUTPUT_DIR, "catalogo.txt"), "w", encoding="utf-8") as fh:
        fh.write(gerar_txt(lista, atualizado))

    alertas = alertas_de_cadastro(lista)
    resumo = [f"## Catálogo atualizado: {len(lista)} imóveis", "", f"Alertas de cadastro: {len(alertas)}", ""]
    resumo += [f"- {a}" for a in alertas]
    log("\n".join(resumo))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("\n".join(resumo) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
