# -*- coding: utf-8 -*-
"""
Mapa de localização da Figura 1A (o Brasil na América do Sul, com o Rio Grande do Sul em destaque).

Fonte: Natural Earth 1:50m, versão em GeoJSON do repositório oficial (nvkelso/natural-earth-vector), de domínio
público. Ficam os países da América do Sul (sem as Ilhas Malvinas) e as unidades da federação do Brasil, com os
contornos simplificados pelo algoritmo de Douglas-Peucker (tolerância de 0,04 grau), o bastante para um mapa
pequeno.

Só é preciso rodar esta etapa para refazer dados_agregados/localizacao_america_do_sul.geojson, que já está no
repositório. A etapa 15 lê esse arquivo.

Uso: python 15a_mapa_localizacao.py [raiz do repositório]
"""
import json
import os
import sys
import urllib.request

import numpy as np

RAIZ = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRUTOS = os.path.join(RAIZ, "dados", "brutos", "natural_earth")
SAIDA = os.path.join(RAIZ, "dados_agregados", "localizacao_america_do_sul.geojson")
URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
TOL = 0.04  # graus


def baixar(nome):
    caminho = os.path.join(BRUTOS, f"{nome}.geojson")
    if not os.path.exists(caminho):
        os.makedirs(BRUTOS, exist_ok=True)
        urllib.request.urlretrieve(URL.format(nome), caminho)
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def rdp(p, tol):
    """Douglas-Peucker iterativo."""
    if len(p) < 4:
        return p
    manter = np.zeros(len(p), bool)
    manter[0] = manter[-1] = True
    pilha = [(0, len(p) - 1)]
    while pilha:
        a, b = pilha.pop()
        if b - a < 2:
            continue
        seg = p[b] - p[a]
        nrm = np.hypot(*seg)
        q = p[a + 1:b] - p[a]
        d = np.abs(seg[0] * q[:, 1] - seg[1] * q[:, 0]) / nrm if nrm > 0 else np.hypot(q[:, 0], q[:, 1])
        i = int(np.argmax(d))
        if d[i] > tol:
            k = a + 1 + i
            manter[k] = True
            pilha += [(a, k), (k, b)]
    return p[manter]


def simplificar(geom):
    pols = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    novos = []
    for pol in pols:
        aneis = []
        for anel in pol:
            a = rdp(np.asarray(anel, float), TOL)
            if len(a) >= 4:
                aneis.append(np.round(a, 3).tolist())
        if aneis:
            novos.append(aneis)
    return {"type": "MultiPolygon", "coordinates": novos}


if __name__ == "__main__":
    paises = baixar("ne_50m_admin_0_countries")
    ufs = baixar("ne_50m_admin_1_states_provinces")
    feats = []
    for f in paises["features"]:
        p = f["properties"]
        if p.get("CONTINENT") == "South America" and p["ADM0_A3"] != "FLK":
            feats.append({"type": "Feature", "properties": {"tipo": "pais", "sigla": p["ADM0_A3"]},
                          "geometry": simplificar(f["geometry"])})
    for f in ufs["features"]:
        p = f["properties"]
        if p.get("adm0_a3") == "BRA":
            feats.append({"type": "Feature", "properties": {"tipo": "uf", "sigla": p["postal"]},
                          "geometry": simplificar(f["geometry"])})
    gj = {"type": "FeatureCollection",
          "fonte": "Natural Earth 1:50m (domínio público), países da América do Sul e UFs do Brasil, simplificado (tolerância 0,04 grau)",
          "features": feats}
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))
    print(len(feats), "feições ->", SAIDA)
