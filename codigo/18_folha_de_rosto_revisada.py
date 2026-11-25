# -*- coding: utf-8 -*-
"""Folha de rosto final: título, autores na ordem definida, afiliações, autor correspondente com endereço,
contribuições, financiamento, conflitos de interesse, declaração de uso de IA, eixos da chamada e contagens.
Gera versão limpa e versão marcada (o que mudou em vermelho). Se for dada a folha da entrega anterior, a versão
marcada mostra só o que mudou em relação a ela; senão, o que mudou em relação à folha original.

Uso: python 18_folha_de_rosto_revisada.py <folha_original.docx> <pasta_saida> <manuscrito_revisado.docx> <dados.json> [folha_anterior.docx]
     As contagens de caracteres saem do manuscrito revisado. Autores, afiliações, endereço, contribuições,
     financiamento, conflitos e declaração de IA vêm do JSON (manuscrito/folha_de_rosto_dados.json ou, em inglês,
     manuscrito/title_page_data_en.json, com "idioma": "en"), que fica fora do repositório público durante a
     avaliação, como a própria folha de rosto. Em inglês, a saída é Title_page.docx (sem versão marcada).
"""
import copy
import json
import os
import re
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.text.paragraph import Paragraph

ORIG, OUT, MANUSCRITO, ARQ_DADOS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
ANTERIOR = sys.argv[5] if len(sys.argv) > 5 and os.path.exists(sys.argv[5]) else None

T_PT = "Atenção psicossocial e internações psiquiátricas após a enchente de 2024 no Rio Grande do Sul"
T_EN = "Psychosocial care and psychiatric admissions after the 2024 flood in southern Brazil"

DADOS = json.load(open(ARQ_DADOS, encoding="utf-8"))
AUTORES = [(a["nome"], a["afiliacao"], a["orcid"], a["email"]) for a in DADOS["autores"]]
AFILIACOES = DADOS["afiliacoes"]
CORRESPONDENTE = DADOS["correspondente"]
CONTRIBUICOES = DADOS["contribuicoes"]
FINANCIAMENTO = DADOS["financiamento"]
CONFLITOS = DADOS["conflitos"]
IA = DADOS["uso_ia"]
AGRADECIMENTOS = DADOS["agradecimentos"]
EIXOS = ("Eixo principal: Reforma Psiquiátrica e Atenção Psicossocial no contexto das crises climáticas e dos desastres "
         "socioambientais. O artigo dialoga também com os eixos Gestão, financiamento, intersetorialidade e planejamento "
         "das respostas psicossociais sustentáveis e Justiça climática, interseccionalidades, direitos fundamentais e "
         "proteção social.")
CONT = ("Título: {tit} caracteres (limite: 120). Caracteres com espaço da Introdução à última referência: {corpo} "
        "(limite: 40.000). Resumo, da palavra \"Resumo\" até a última palavra-chave: {res} caracteres; abstract, idem: "
        "{abs_} caracteres (limite: 1.400). Ilustrações: {tabs} tabela e {figs} figuras, compostas por painéis (limite: 5). "
        "Referências: {refs}. Sem material suplementar; os resultados completos estão no repositório do estudo.")


def mil(n):
    return f"{n:,}".replace(",", ".")


def contar(caminho):
    """Mesma regra da revista: título; resumo e abstract da palavra-título até a última palavra-chave;
    corpo da Introdução à última referência, sem legendas, notas e fontes das ilustrações."""
    paras = [p.text for p in Document(caminho).paragraphs]
    idx = lambda s: next(i for i, t in enumerate(paras) if t.strip() == s)
    i_res, i_abs, i_intro = idx("Resumo"), idx("Abstract"), idx("Introdução")
    bloco = lambda a, b: " ".join(t for t in paras[a:b] if t.strip())
    legenda = re.compile(r"^(Tabela|Figura) \d+\. |^Nota: |^Fonte: ")  # legendas, notas e fontes das ilustrações
    corpo = " ".join(t for t in paras[i_intro:] if t.strip() and not legenda.match(t))
    i_ref = idx("Referências")
    refs = sum(1 for t in paras[i_ref + 1:] if re.match(r"^\d+\. ", t))
    tabs = len({m.group(1) for t in paras if (m := re.match(r"^Tabela (\d+)\. ", t))})
    figs = len({m.group(1) for t in paras if (m := re.match(r"^Figura (\d+)\. ", t))})
    return dict(tit=len(paras[0]), res=mil(len(bloco(i_res, i_abs))), abs_=mil(len(bloco(i_abs, i_intro))),
                corpo=mil(len(corpo)), refs=refs, tabs=tabs, figs=figs)


def vermelho(run, marcado):
    if marcado:
        run.font.color.rgb = RGBColor(0xFF, 0, 0)


def trocar(par, texto, marcado):
    """Troca o texto depois do rótulo em negrito (se houver) e apaga as demais runs."""
    runs = par.runs
    alvo = runs[1] if len(runs) > 1 and runs[0].bold else runs[0]
    alvo.text = texto
    alvo.bold = False
    for r in runs:
        if r is not alvo and r is not runs[0]:
            r._r.getparent().remove(r._r)
    vermelho(alvo, marcado)


def autor(par, nome, n, orcid, email, marcado):
    r_nome, r_sup, r_resto = par.runs[0], par.runs[1], par.runs[2]
    mudou = (r_nome.text != nome) or (r_sup.text != str(n))
    r_nome.text, r_sup.text = nome, str(n)
    r_resto.text = f"; ORCID: https://orcid.org/{orcid}; e-mail: {email}"
    for r in par.runs[3:]:
        r._r.getparent().remove(r._r)
    for r in (r_nome, r_sup) if mudou else ():
        vermelho(r, marcado)
    vermelho(r_resto, marcado)  # o separador mudou em todas as linhas (sem travessão)


def montar(marcado):
    if marcado and ANTERIOR:
        return marcar_diferencas()
    d = Document(ORIG)
    ps = d.paragraphs
    trocar(ps[1], T_PT, marcado)
    trocar(ps[2], T_EN, marcado)
    for par, (nome, n, orcid, email) in zip(ps[5:10], AUTORES):
        autor(par, nome, n, orcid, email, marcado)
    for par, (i, txt) in zip(ps[11:15], enumerate(AFILIACOES, start=1)):
        antigo = par.runs[1].text.strip()
        par.runs[0].text, par.runs[1].text = str(i), " " + txt
        if antigo != txt:
            vermelho(par.runs[1], marcado)
    trocar(ps[15], CORRESPONDENTE, marcado)
    trocar(ps[17], CONTRIBUICOES, marcado)
    trocar(ps[19], FINANCIAMENTO, marcado)
    trocar(ps[21], CONFLITOS, marcado)
    # disponibilidade: sai a pendência do DOI do Zenodo (opcional); sem suplementar, os resultados completos
    # ficam no repositório
    for r in ps[25].runs:
        if " [incluir DOI do Zenodo, se houver]" in r.text:
            r.text = r.text.replace(" [incluir DOI do Zenodo, se houver]", "")
        if "plano de análise com registro de alterações e dados agregados" in r.text:
            r.text = r.text.replace("plano de análise com registro de alterações e dados agregados",
                                    "plano de análise com registro de alterações, resultados completos de todas as "
                                    "análises e dados agregados")
            vermelho(r, marcado)
    trocar(ps[27], IA, marcado)
    trocar(ps[29], AGRADECIMENTOS, marcado)
    trocar(ps[31], CONT.format(**contar(MANUSCRITO)), marcado)
    # bloco "Eixos da chamada temática" antes de "Contagem"
    h = copy.deepcopy(ps[30]._p)
    p = copy.deepcopy(ps[29]._p)
    ps[30]._p.addprevious(h)
    ps[30]._p.addprevious(p)
    H, P = Paragraph(h, ps[30]._parent), Paragraph(p, ps[30]._parent)
    H.runs[0].text = "Eixos da chamada temática"
    P.runs[0].text = EIXOS
    for r in P.runs[1:]:
        r._r.getparent().remove(r._r)
    vermelho(H.runs[0], marcado)
    vermelho(P.runs[0], marcado)
    # nenhum travessão ou meia-risca como pontuação
    for par in d.paragraphs:
        for r in par.runs:
            if "–" in r.text or "—" in r.text:
                r.text = r.text.replace(" – ", "; ").replace(" — ", "; ")
    d.core_properties.author = ""
    d.core_properties.last_modified_by = ""
    nome = "Folha_de_rosto_revisada_marcada.docx" if marcado else "Folha_de_rosto_revisada.docx"
    d.save(os.path.join(OUT, nome))
    print(os.path.join(OUT, nome))


def marcar_diferencas():
    """Versão marcada em relação à folha da entrega anterior: palavras novas ou alteradas em vermelho (o parágrafo
    inteiro, quando ele tem mais de uma formatação)."""
    import difflib
    d = Document(os.path.join(OUT, "Folha_de_rosto_revisada.docx"))
    antes = [p.text for p in Document(ANTERIOR).paragraphs]
    for i, par in enumerate(d.paragraphs):
        if i < len(antes) and par.text == antes[i]:
            continue
        com_texto = [r for r in par.runs if r.text]
        if i >= len(antes) or len(com_texto) != 1:
            for r in par.runs:
                vermelho(r, True)
            continue
        run = com_texto[0]
        novo, velho = re.findall(r"\S+\s*", run.text), re.findall(r"\S+\s*", antes[i])
        sm = difflib.SequenceMatcher(None, [w.strip() for w in velho], [w.strip() for w in novo], autojunk=False)
        trechos = []  # (texto, alterado)
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if b2 > b1:
                trechos.append(("".join(novo[b1:b2]), op != "equal"))
        run.text = trechos[0][0]
        vermelho(run, trechos[0][1])
        anterior_r = run._r
        for texto, alterado in trechos[1:]:
            r = copy.deepcopy(run._r)
            anterior_r.addnext(r)
            anterior_r = r
            from docx.text.run import Run
            rr = Run(r, par)
            rr.text = texto
            rr.font.color.rgb = RGBColor(0xFF, 0, 0) if alterado else None
    nome = os.path.join(OUT, "Folha_de_rosto_revisada_marcada.docx")
    d.save(nome)
    print(nome)


# ----------------------------------------------------------------------------- versão em inglês
CONT_EN = ("Title: {tit} characters (limit: 120). Characters with spaces from the Introduction to the last reference: "
           "{corpo} (limit: 40,000). Abstract, from the word \"Abstract\" to the last keyword: {abs_} characters; Resumo "
           "and Resumen, counted the same way: {res} and {resu} characters (limit: 1,400 each). Illustrations: {tabs} "
           "table and {figs} figures made up of panels (limit: 5). References: {refs}. No supplementary material; the "
           "full results are in the study repository.")


def contar_en(caminho):
    """Mesma regra de contar(), com os rótulos do manuscrito em inglês."""
    paras = [p.text for p in Document(caminho).paragraphs]
    idx = lambda s: next(i for i, t in enumerate(paras) if t.strip() == s)
    i_abs, i_res, i_resu, i_intro, i_ref = (idx(s) for s in ("Abstract", "Resumo", "Resumen", "Introduction", "References"))
    bloco = lambda a, b: " ".join(t for t in paras[a:b] if t.strip())
    legenda = re.compile(r"^(Table|Figure) \d+\. |^Note: |^Source: ")  # legendas, notas e fontes das ilustrações
    corpo = " ".join(t for t in paras[i_intro:] if t.strip() and not legenda.match(t))
    return dict(tit=len(paras[0]), abs_=f"{len(bloco(i_abs, i_res)):,}", res=f"{len(bloco(i_res, i_resu)):,}",
                resu=f"{len(bloco(i_resu, i_intro)):,}", corpo=f"{len(corpo):,}",
                refs=sum(1 for t in paras[i_ref + 1:] if re.match(r"^\d+\. ", t)),
                tabs=len({m.group(1) for t in paras if (m := re.match(r"^Table (\d+)\. ", t))}),
                figs=len({m.group(1) for t in paras if (m := re.match(r"^Figure (\d+)\. ", t))}))


def montar_en():
    d = Document(ORIG)
    ps = d.paragraphs

    def rotulo(par, texto):
        par.runs[0].text = texto

    def com_rotulo(par, rot, texto):
        trocar(par, texto, False)
        rotulo(par, rot)

    rotulo(ps[0], "Title page")
    com_rotulo(ps[1], "Title: ", DADOS["titulo"])
    com_rotulo(ps[2], "Title in Portuguese: ", DADOS["titulo_pt"])
    es = copy.deepcopy(ps[2]._p)
    ps[2]._p.addnext(es)
    com_rotulo(Paragraph(es, ps[2]._parent), "Title in Spanish: ", DADOS["titulo_es"])
    com_rotulo(ps[3], "Short title: ", DADOS["titulo_resumido"])
    rotulo(ps[4], "Authors")
    for par, (nome, n, orcid, email) in zip(ps[5:10], AUTORES):
        autor(par, nome, n, orcid, email, False)
    rotulo(ps[10], "Affiliations")
    for par, (i, txt) in zip(ps[11:15], enumerate(AFILIACOES, start=1)):
        par.runs[0].text, par.runs[1].text = str(i), " " + txt
    com_rotulo(ps[15], "Corresponding author: ", CORRESPONDENTE)
    for i_rot, i_txt, rot, chave in [(16, 17, "Author contributions", "contribuicoes"), (18, 19, "Funding", "financiamento"),
                                     (20, 21, "Conflicts of interest", "conflitos"), (22, 23, "Ethics", "etica"),
                                     (24, 25, "Data and code availability (Open Science)", "disponibilidade"),
                                     (26, 27, "Use of artificial intelligence", "uso_ia"),
                                     (28, 29, "Acknowledgements", "agradecimentos")]:
        rotulo(ps[i_rot], rot)
        trocar(ps[i_txt], DADOS[chave], False)
    rotulo(ps[30], "Character counts")
    trocar(ps[31], CONT_EN.format(**contar_en(MANUSCRITO)), False)
    h, p = copy.deepcopy(ps[30]._p), copy.deepcopy(ps[29]._p)
    ps[30]._p.addprevious(h)
    ps[30]._p.addprevious(p)
    Paragraph(h, ps[30]._parent).runs[0].text = "Thematic call axes"
    P = Paragraph(p, ps[30]._parent)
    P.runs[0].text = DADOS["eixos"]
    for r in P.runs[1:]:
        r._r.getparent().remove(r._r)
    for par in d.paragraphs:
        for r in par.runs:
            if "–" in r.text or "—" in r.text:
                r.text = r.text.replace(" – ", "; ").replace(" — ", "; ")
    # idioma da revisão ortográfica do Word
    for raiz in (d.styles.element, d.element.body):
        for lg in raiz.iter(qn("w:lang")):
            lg.set(qn("w:val"), "en-US")
    d.core_properties.language = "en-US"
    d.core_properties.author = ""
    d.core_properties.last_modified_by = ""
    destino = os.path.join(OUT, "Title_page.docx")
    d.save(destino)
    print(destino)


if DADOS.get("idioma") == "en":
    montar_en()
else:
    montar(False)
    montar(True)
