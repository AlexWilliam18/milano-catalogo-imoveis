"""Monta um site simulado com a mesma estrutura HTML das páginas de imóvel da ImoTools
(observada no site real da Milano) para testar o gerador sem acesso à internet."""
import json
import os
import sys

RAIZ = sys.argv[1] if len(sys.argv) > 1 else "site_teste"
BASE = "http://127.0.0.1:8765"

def pagina(slug, cod, titulo, fin_bc, bairro, valores, cac, itens, desc_html):
    bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": fin_bc},
        {"@type": "ListItem", "position": 2, "name": "Jacutinga"},
        {"@type": "ListItem", "position": 3, "name": bairro},
        {"@type": "ListItem", "position": 4, "name": titulo}]}
    listing = {"@context": "https://schema.org", "@type": "RealEstateListing", "name": titulo,
               "mainEntity": {"@type": "SingleFamilyResidence", "numberOfBedrooms": int(cac.get("Quartos", 0))}}
    box = "".join(f'<div class="t-box-lateral">{k}:</div><div class="valor-alug-comp vs-maior">{v}</div>' for k, v in valores)
    cacs = "".join(f'<div><div class="t-cac">{k}</div><div class="texto-cac-detalhe">{v}</div></div>' for k, v in cac.items())
    its = "".join(f'<div class="vs-todas-cat vs-imv"><span class="ico-marcador"></span>{i}</div>' for i in itens)
    return f"""<!DOCTYPE html><html><head>
<script type="application/ld+json">{json.dumps({"@type": "RealEstateAgent", "name": "Milano"})}</script>
<script type="application/ld+json">{json.dumps(listing, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(bc, ensure_ascii=False)}</script>
</head><body><header>Fale conosco WhatsApp (35) 9103-1292</header>
<main>
<div>Exclusividade</div>
<ul><li><a class="lk-migalha">{fin_bc}</a></li><li><a class="lk-migalha">Jacutinga</a></li><li><a class="lk-migalha">{bairro}</a></li></ul>
<div>Código: {cod}</div>
<h1>{titulo}</h1>
<div class="box-valores vv oculto-desktop">{box}</div>
<div class="box-valores vv oculto-mobile">{box}</div>
{cacs}
<div class="box-todas-caracteristicas">{its}</div>
<div class="bloco-texto-det"><h2 class="titulo-principal t-vs2">Sobre o imóvel</h2>
<div class="p-padrao"><style type="text/css">.cms-html-content{{line-height:1.42}}</style>{desc_html}</div></div>
<form><input name="nome"> SOLICITAR CONTATO DO CORRETOR</form>
<div class="limite"><h2 class="titulo-principal">Imóveis relacionados</h2>
<div class="lista-cards-imoveis"><div class="bx-imovel"><a href="{BASE}/imovel/casa-1-quartos-centro-jacutinga-locacao-id-6">Ver</a>
Aluguel Cod: I9Z117 Casa — Centro Jacutinga - MG 1 quartos R$ 990,00/mês
<div class="box-valores"><div class="t-box-lateral">Valor do aluguel:</div><div>R$ 990,00/mês</div></div></div></div></div>
<section><h2>Imóveis mais buscados</h2><a>Casa para alugar</a></section>
</main><footer>CRECI 3.304</footer></body></html>"""

imoveis = [
    ("casa-3-quartos-flamboyant-jacutinga-venda-id-101", pagina(
        "casa-3-quartos-flamboyant-jacutinga-venda-id-101", "18",
        "Casa com 3 quartos, 2 vagas e 357.46m² à venda no Flamboyant , Jacutinga/MG", "Imóvel à venda", "Flamboyant",
        [("Valor de compra do imóvel", "Sob consulta")],
        {"Quartos": "3", "Banheiro": "2", "Suítes": "2", "Vagas": "2", "Área construída": "357,46 m²"},
        ["Piscina", "Closet", "Churrasqueira"],
        "<p>CASA DE ALTO PADRÃO À VENDA</p><p>03 quartos, sendo 02 suíte;<br>Piscina;</p>")),
    ("casa-2-quartos-portal-das-estancias-jacutinga-locacao-id-92", pagina(
        "", "9", "Casa com 2 quartos, 1 vaga para locação no Portal das Estâncias, Jacutinga/MG",
        "Imóvel para alugar", "Portal das Estâncias",
        [("Valor de venda", "R$ 270.000,00"), ("Valor do aluguel", "R$ 1.560,00/mês")],
        {"Quartos": "2", "Banheiro": "1", "Vagas": "1"}, ["Área de Lazer"],
        "<p>🏡 ALUGA-SE CASA</p><p>💰 Valor: R$ 1.560,00</p>")),
    ("casa-2-quartos-jardim-dea-jacutinga-venda-id-72", pagina(
        "", "I9Z343", "Casa", "Imóvel à venda", "Jardim Déa",
        [("Valor de compra do imóvel", "R$ 310.000,00")],
        {"Quartos": "2", "Banheiro": "1", "Vagas": "0", "Área construída": "1 m²"}, [],
        "<p>🏡 CASA À VENDA – R$ 330.000,00</p><p>• 02 QUARTOS</p>")),
    ("galpao-centro-jacutinga-4000m2-locacao-id-105", pagina(
        "", "22", "Galpão para locação no Centro, Jacutinga/MG", "Imóvel para alugar", "Centro",
        [("Valor do aluguel", "Sob consulta")],
        {"Quartos": "0", "Banheiro": "0", "Vagas": "0", "Área total": "4.000 m²"}, [],
        "<p>Barracão com 4.000 m² e pé-direito de 8 metros.</p>")),
]

os.makedirs(os.path.join(RAIZ, "imovel"), exist_ok=True)
locs = [f"{BASE}/imovel/{slug}" for slug, _ in imoveis] + [f"{BASE}/imovel/imovel-removido-id-999"]
with open(os.path.join(RAIZ, "sitemap.xml"), "w", encoding="utf-8") as fh:
    fh.write("<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in [BASE, f"{BASE}/contato"] + locs) + "</urlset>")
for slug, conteudo in imoveis:
    with open(os.path.join(RAIZ, "imovel", slug), "w", encoding="utf-8") as fh:
        fh.write(conteudo)
print(f"Site de teste montado em {RAIZ} com {len(imoveis)} imóveis + 1 removido")
