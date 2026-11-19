# -*- coding: utf-8 -*-
"""
Gera o manuscrito em Word a partir do texto-fonte com marcação, usando o .docx entregue em 06/11/2026 como
molde de formatação e da Tabela 1. Cada figura ou tabela entra logo depois do parágrafo que a cita pela
primeira vez, no ponto marcado no texto-fonte.

Marcação do texto-fonte
  @idioma en                   texto em inglês (sem esta linha, português)
  @titulo                      título principal
  @titulo_en, _pt, _es         título nos outros idiomas
  # seção, ## subseção          títulos
  @palavras, @keywords, @palabras   palavras-chave em português, inglês e espanhol
  [@chave]                     citação (numerada na ordem em que aparece, a partir da Introdução)
  @ref chave | referência      lista de referências (Vancouver)
  @figura N | arquivo | texto  Figura N; imagem <pasta_figuras>/<arquivo>_<variante>.png
  @tabela N | texto            Tabela N, copiada do molde (a N-ésima tabela do molde; traduzida se o texto for em inglês)
  @nota texto, @fonte texto    nota e fonte da última figura ou tabela

Saídas em português (variantes de figura _cinza e _cor)
  Manuscrito_anonimo_revisado.docx            figuras em tons de cinza
  Manuscrito_anonimo_revisado_colorido.docx   o mesmo texto com as figuras em cores
  Manuscrito_anonimo_revisado_marcado.docx    figuras em cinza; em vermelho o que mudou em relação ao texto
                                              anterior e, se houver o .tsv, comentários da revisão
Saídas em inglês (variantes de figura _color e _gray)
  Manuscript_anonymous.docx                   figuras em cores (para envio; a versão impressa sai em cinza)
  Manuscript_anonymous_grayscale.docx         o mesmo texto com as figuras em tons de cinza
  Manuscript_anonymous_marked.docx            só se houver texto anterior em inglês

Uso
  python 16_gerar_docx_revisado.py <docx_molde> <texto_anterior ou -> <texto_atual> <pasta_figuras> <pasta_saida> [comentarios.tsv]
"""
import copy
import csv
import difflib
import os
import re
import sys

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.text.paragraph import Paragraph

DOCX_MOLDE, TXT_ANTERIOR, TXT_ATUAL, FIGS, OUT = sys.argv[1:6]
COMENT = sys.argv[6] if len(sys.argv) > 6 else None
os.makedirs(OUT, exist_ok=True)
VERMELHO = "FF0000"
LINHA_CORPO = "480"          # espaço duplo
LARGURA_TABELA = 8504        # 15 cm em twips
LARGURA_FIGURA = Cm(15)

# rótulos que dependem do idioma do texto
ROTULOS = {
    "pt": {"Figura": "Figura", "Tabela": "Tabela", "nota": "Nota: ", "fonte": "Fonte: ", "intro": "Introdução",
           "refs": "Referências", "lang": "pt-BR",
           "variantes": [("cinza", False, "Manuscrito_anonimo_revisado.docx"),
                         ("cor", False, "Manuscrito_anonimo_revisado_colorido.docx"),
                         ("cinza", True, "Manuscrito_anonimo_revisado_marcado.docx")]},
    "en": {"Figura": "Figure", "Tabela": "Table", "nota": "Note: ", "fonte": "Source: ", "intro": "Introduction",
           "refs": "References", "lang": "en-US",
           "variantes": [("color", False, "Manuscript_anonymous.docx"),
                         ("gray", False, "Manuscript_anonymous_grayscale.docx"),
                         ("color", True, "Manuscript_anonymous_marked.docx")]},
}
PALAVRAS_CHAVE = {"@palavras ": "Palavras-chave: ", "@keywords ": "Key words: ", "@palabras ": "Palabras clave: "}

# Tabela 1 em inglês: rótulos traduzidos; números com ponto decimal e vírgula nos milhares
TABELA1_EN = {
    "Característica": "Characteristic", "Exposição <1%": "Least affected (<1%)", "Exposição ≥10%": "Most affected (≥10%)",
    "Rio Grande do Sul": "Rio Grande do Sul", "Antes": "Before", "Depois": "After",
    "A. Internações com diagnóstico principal F00-F99": "A. Admissions with a principal diagnosis of F00-F99",
    "Internações (n)": "Admissions (n)", "Taxa por 100 mil hab./ano": "Rate per 100,000 inhabitants/year",
    "Mulheres (%)": "Women (%)", "Idade, mediana (IIQ)": "Age, median (IQR)",
    "Preta ou parda (%)": "Black people (%)",
    "F10-F19, álcool e outras drogas (%)": "F10-F19, alcohol and other drugs (%)",
    "F20-F29, esquizofrenia e psicóticos (%)": "F20-F29, psychotic disorders (%)",
    "F30-F39, humor (%)": "F30-F39, mood disorders (%)", "Leito psiquiátrico (%)": "Psychiatric bed (%)",
    "Leito de saúde mental em hospital geral (%)": "Mental health bed in a general hospital (%)",
    "Caráter de urgência (%)": "Emergency admission (%)",
    "Fora do município de residência (%)": "Outside the municipality of residence (%)",
    "Permanência em dias, mediana (IIQ)": "Length of stay in days, median (IQR)",
    "B. Usuários atendidos nos CAPS (RAAS)": "B. CAPS users (RAAS)",
    "Usuários-mês atendidos (n)": "User-months (n)", "0-17 anos (%)": "Children and adolescents, 0-17 years (%)",
    "Raça/cor sem informação (%)": "Race/skin color missing (%)",
    "CID F10-F19, álcool e outras drogas (%)": "ICD F10-F19, alcohol and other drugs (%)",
    "CID F40-F48, neuróticos e estresse (%)": "ICD F40-F48, stress-related disorders (%)",
    "Usuários novos no mês (%)": "New users in the month (%)",
}
NUMERICO = re.compile(r"^[\d.,\s()\-–<>≥%]+$")


# ----------------------------------------------------------------------------- leitura do texto-fonte
def idioma_de(caminho):
    if caminho == "-":
        return None
    return "en" if any(l.strip() == "@idioma en" for l in open(caminho, encoding="utf-8")) else "pt"


def ler_fonte(caminho):
    """Blocos (tipo, valor, seção) e referências. Figuras e tabelas viram blocos 'ilu' com nota e fonte."""
    blocos, refs = [], {}
    if caminho == "-":
        return blocos, refs
    secao = None
    for linha in open(caminho, encoding="utf-8").read().splitlines():
        if not linha.strip() or linha.startswith("@idioma "):
            continue
        rot_kw = next((r for tag, r in PALAVRAS_CHAVE.items() if linha.startswith(tag)), None)
        if linha.startswith(("@titulo_en ", "@titulo_pt ", "@titulo_es ")):
            blocos.append(("title_en", linha[11:].strip(), secao))
        elif linha.startswith("@titulo "):
            blocos.append(("title", linha[8:].strip(), secao))
        elif rot_kw:
            blocos.append(("kw", (rot_kw, linha.split(" ", 1)[1].strip()), secao))
        elif linha.startswith("@ref "):
            chave, texto = linha[5:].split("|", 1)
            refs[chave.strip()] = texto.strip()
        elif linha.startswith("@figura "):
            n, arquivo, texto = [x.strip() for x in linha[8:].split("|", 2)]
            blocos.append(("ilu", {"tipo": "Figura", "n": n, "arquivo": arquivo, "legenda": texto,
                                   "nota": None, "fonte": None}, secao))
        elif linha.startswith("@tabela "):
            n, texto = [x.strip() for x in linha[8:].split("|", 1)]
            blocos.append(("ilu", {"tipo": "Tabela", "n": n, "legenda": texto, "nota": None, "fonte": None}, secao))
        elif linha.startswith(("@nota ", "@fonte ")):
            campo, texto = linha[1:].split(" ", 1)
            if not blocos or blocos[-1][0] != "ilu":
                raise SystemExit(f"@{campo} sem @figura ou @tabela antes: {texto[:60]}")
            blocos[-1][1][campo] = texto.strip()
        elif linha.startswith("## "):
            blocos.append(("h2", linha[3:].strip(), secao))
        elif linha.startswith("# "):
            secao = linha[2:].strip()
            blocos.append(("h1", secao, secao))
        else:
            blocos.append(("p", linha.strip(), secao))
    return blocos, refs


CIT = re.compile(r"((?:\[@[\w\-]+\])+)")


def tokens(texto):
    """Divide em palavras (com espaço à direita) e grupos de citação."""
    out = []
    for parte in CIT.split(texto):
        if not parte:
            continue
        if parte.startswith("[@"):
            out.append(("cit", tuple(re.findall(r"\[@([\w\-]+)\]", parte))))
        else:
            for w in re.findall(r"\S+\s*|\s+", parte):
                out.append(("txt", w))
    return out


def numerar(blocos, refs):
    num = {}
    dentro = False
    for tipo, val, secao in blocos:
        if tipo == "h1" and val == R["intro"]:
            dentro = True
        if dentro and tipo == "p":
            for t, v in tokens(val):
                if t == "cit":
                    for k in v:
                        if k not in num:
                            num[k] = len(num) + 1
    faltam = [k for k in num if k not in refs]
    sobram = [k for k in refs if k not in num]
    if faltam or sobram:
        raise SystemExit(f"Citações sem referência: {faltam}; referências não citadas: {sobram}")
    return num


def conferir_ilustracoes(blocos):
    """Cada figura e tabela precisa ser citada no texto antes do ponto em que entra, na ordem da numeração."""
    citadas, ordem = [], []
    interno = {R["Figura"]: "Figura", R["Tabela"]: "Tabela"}
    for tipo, val, secao in blocos:
        if tipo == "p":
            for m in re.finditer(rf"({R['Figura']}|{R['Tabela']})s? (\d+)", val):
                k = f"{interno[m.group(1)]} {m.group(2)}"
                if k not in citadas:
                    citadas.append(k)
        elif tipo == "ilu":
            k = f"{val['tipo']} {val['n']}"
            if k not in citadas:
                raise SystemExit(f"{k} entra no texto antes de ser citada")
            ordem.append(k)
    for tipo_ilu in ("Figura", "Tabela"):
        nums = [int(k.split()[1]) for k in ordem if k.startswith(tipo_ilu)]
        if nums != list(range(1, len(nums) + 1)):
            raise SystemExit(f"{tipo_ilu}s fora de ordem: {nums}")
    nao_inseridas = [k for k in citadas if k not in ordem]
    if nao_inseridas:
        raise SystemExit(f"Ilustrações citadas e não inseridas: {nao_inseridas}")
    return ordem


def rotulo_citacao(chaves, num):
    ns = sorted(num[k] for k in chaves)
    partes, i = [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        partes.append(f"{ns[i]}-{ns[j]}" if j - i >= 2 else ",".join(str(x) for x in ns[i:j + 1]))
        i = j + 1
    return ",".join(partes)


# ----------------------------------------------------------------------------- marcação das mudanças
def chave_token(t):
    return ("C:" + ",".join(t[1])) if t[0] == "cit" else t[1].strip()


def marcar(novo, antigos):
    """Lista de (token, alterado) para um texto novo, comparado com o mais parecido dos antigos."""
    tn = tokens(novo)
    kn = [chave_token(t) for t in tn]
    melhor, razao = None, 0.0
    for a in antigos:
        ka = [chave_token(t) for t in tokens(a)]
        r = difflib.SequenceMatcher(None, ka, kn, autojunk=False).ratio()
        if r > razao:
            melhor, razao = ka, r
    if melhor is None or razao < 0.35:
        return [(t, True) for t in tn]
    sm = difflib.SequenceMatcher(None, melhor, kn, autojunk=False)
    flags = [True] * len(tn)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            for k in range(b1, b2):
                flags[k] = False
    # palavras curtas iguais no meio de trechos alterados também ficam vermelhas (leitura mais limpa)
    for k in range(1, len(flags) - 1):
        if not flags[k] and flags[k - 1] and flags[k + 1] and tn[k][0] == "txt" and len(tn[k][1].strip()) <= 3:
            flags[k] = True
    return list(zip(tn, flags))


# ----------------------------------------------------------------------------- moldes de formatação
molde = Document(DOCX_MOLDE)
corpo_molde = list(molde.element.body.iterchildren())


def texto_el(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def achar(pred):
    for el in corpo_molde:
        if el.tag == qn("w:p") and pred(el):
            return el
    raise KeyError


def espacamento(el):
    ppr = el.find(qn("w:pPr"))
    sp = ppr.find(qn("w:spacing")) if ppr is not None else None
    return (sp.get(qn("w:before")), sp.get(qn("w:after"))) if sp is not None else (None, None)


def rpr_de(el, idx=0):
    return copy.deepcopy(el.findall(qn("w:r"))[idx].find(qn("w:rPr")))


P_TITULO = achar(lambda e: texto_el(e).startswith("Quando a água"))
P_TITULO_EN = achar(lambda e: texto_el(e).startswith("When the water"))
P_H1 = achar(lambda e: texto_el(e) == "Introdução")
P_H2 = achar(lambda e: texto_el(e) == "Desenho, dados e desfechos")
P_CORPO = achar(lambda e: texto_el(e).startswith("Desastres associados"))
P_KW = achar(lambda e: texto_el(e).startswith("Palavras-chave"))
P_REF = achar(lambda e: texto_el(e).startswith("1. Fernandez"))
P_LEGENDA = achar(lambda e: texto_el(e).startswith("Figura 1."))
P_IMAGEM = achar(lambda e: len(list(e.iter(qn("w:drawing")))) > 0)
P_NOTA = achar(lambda e: texto_el(e).startswith("Nota:"))
P_ESP_ANTES = achar(lambda e: texto_el(e) == "" and espacamento(e) == ("120", "0"))
P_ESP_DEPOIS = achar(lambda e: texto_el(e) == "" and espacamento(e) == ("0", "120"))
TABELAS_MOLDE = [el for el in corpo_molde if el.tag == qn("w:tbl")]
# textos das ilustrações do molde, para a versão marcada
TEXTOS_ILU_MOLDE = [texto_el(e) for e in corpo_molde if e.tag == qn("w:p") and texto_el(e).startswith(("Figura", "Tabela", "Nota:", "Fonte:"))]

RPR_CORPO = rpr_de(P_CORPO, 0)
RPR_TIT = rpr_de(P_TITULO, 0)
RPR_TIT_EN = rpr_de(P_TITULO_EN, 0)
RPR_H1 = rpr_de(P_H1, 0)
RPR_H2 = rpr_de(P_H2, 0)
RPR_KW_ROT = rpr_de(P_KW, 0)
RPR_LEGENDA = rpr_de(P_LEGENDA, 0)
RPR_NOTA_ROT = rpr_de(P_NOTA, 0)
RPR_NOTA = rpr_de(P_NOTA, 1)


def novo_p(molde_p, linha=None, manter_com_proximo=False):
    p = OxmlElement("w:p")
    ppr = copy.deepcopy(molde_p.find(qn("w:pPr")))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
    if manter_com_proximo and ppr.find(qn("w:keepNext")) is None:
        ppr.insert(0, OxmlElement("w:keepNext"))
    if linha:
        sp = ppr.find(qn("w:spacing"))
        if sp is None:
            sp = OxmlElement("w:spacing")
            ppr.append(sp)
        sp.set(qn("w:line"), linha)
        sp.set(qn("w:lineRule"), "auto")
    p.append(ppr)
    return p


def novo_r(texto, rpr_molde, vermelho=False, sobrescrito=False):
    r = OxmlElement("w:r")
    rpr = copy.deepcopy(rpr_molde)
    for tag in ("w:color", "w:vertAlign"):
        for x in rpr.findall(qn(tag)):
            rpr.remove(x)
    if vermelho:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), VERMELHO)
        sz = rpr.find(qn("w:sz"))  # w:color vem antes de w:sz no rPr
        (sz.addprevious(c) if sz is not None else rpr.append(c))
    if sobrescrito:
        v = OxmlElement("w:vertAlign")
        v.set(qn("w:val"), "superscript")
        rpr.append(v)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.text = texto
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    return r


def escrever(p, marcacao, rpr, num=None):
    """Acrescenta ao parágrafo as runs de uma lista de (token, vermelho), juntando palavras vizinhas."""
    buf, buf_v = "", None

    def flush():
        nonlocal buf
        if buf:
            p.append(novo_r(buf, rpr, vermelho=buf_v))
            buf = ""
    for (tipo, v), verm in marcacao:
        if tipo == "cit":
            flush()
            p.append(novo_r(rotulo_citacao(v, num), rpr, vermelho=verm, sobrescrito=True))
            buf_v = None
        else:
            if buf and verm != buf_v:
                flush()
            buf_v = verm
            buf += v
    flush()


def ajustar_tabela(tbl):
    """Largura de 15 cm; hífen no lugar do travessão das células vazias e do meia-risca dos intervalos."""
    grade = tbl.find(qn("w:tblGrid"))
    cols = grade.findall(qn("w:gridCol"))
    total = sum(int(c.get(qn("w:w"))) for c in cols)
    fator = LARGURA_TABELA / total
    for c in cols:
        c.set(qn("w:w"), str(int(round(int(c.get(qn("w:w"))) * fator))))
    tbl.find(qn("w:tblPr")).find(qn("w:tblW")).set(qn("w:w"), str(LARGURA_TABELA))
    for tc in tbl.iter(qn("w:tc")):
        tcpr = tc.find(qn("w:tcPr"))
        tcw = tcpr.find(qn("w:tcW")) if tcpr is not None else None
        if tcw is not None and tcw.get(qn("w:type")) == "dxa":
            tcw.set(qn("w:w"), str(int(round(int(tcw.get(qn("w:w"))) * fator))))
    for t in tbl.iter(qn("w:t")):
        if t.text and "–" in t.text:
            t.text = t.text.replace("–", "-")
        if t.text and t.text.strip() == "—":
            t.text = "-"
    if IDIOMA == "en":
        traduzir_tabela(tbl)


def traduzir_tabela(tbl):
    """Traduz cada parágrafo das células (texto inteiro na primeira run) e troca a notação dos números."""
    for p in tbl.iter(qn("w:p")):
        ts = list(p.iter(qn("w:t")))
        texto = "".join(t.text or "" for t in ts)
        if not texto.strip():
            continue
        chave = texto.strip()
        if chave in TABELA1_EN:
            novo = TABELA1_EN[chave]
        elif NUMERICO.match(chave):
            novo = chave.replace(".", "\0").replace(",", ".").replace("\0", ",")
        else:
            raise SystemExit(f"célula da tabela sem tradução: {chave!r}")
        ts[0].text = novo
        ts[0].set(qn("xml:space"), "preserve")
        for t in ts[1:]:
            t.text = ""


# ----------------------------------------------------------------------------- montagem
IDIOMA = idioma_de(TXT_ATUAL)
R = ROTULOS[IDIOMA]
# versão marcada só quando há texto anterior no mesmo idioma
MARCADA = idioma_de(TXT_ANTERIOR) == IDIOMA
blocos_atuais, refs_atuais = ler_fonte(TXT_ATUAL)
blocos_anteriores, refs_anteriores = ler_fonte(TXT_ANTERIOR if MARCADA else "-")
num = numerar(blocos_atuais, refs_atuais)
ILUSTRACOES = conferir_ilustracoes(blocos_atuais)
paragrafos_anteriores = [v for t, v, s in blocos_anteriores if t == "p"]
titulos_anteriores = {v for t, v, s in blocos_anteriores if t in ("h1", "h2", "title", "title_en")}
textos_ilu_anteriores = (TEXTOS_ILU_MOLDE if IDIOMA == "pt" else []) + [
    f"{R[v['tipo']]} {v['n']}. {v['legenda']}" for t, v, s in blocos_anteriores if t == "ilu"] + [
    f"{R[c]}{v[c]}" for t, v, s in blocos_anteriores if t == "ilu" for c in ("nota", "fonte") if v[c]]


def montar(variante, marcado, nome):
    doc = Document(DOCX_MOLDE)
    body = doc.element.body
    sect = body.find(qn("w:sectPr"))
    for el in list(body.iterchildren()):
        if el is not sect:
            body.remove(el)
    ancoras = {}

    def add(el):
        sect.addprevious(el)
        return el

    def marc(texto, antigos):
        return marcar(texto, antigos) if marcado else [(t, False) for t in tokens(texto)]

    def ilustracao(v):
        rotulo = f"{R[v['tipo']]} {v['n']}."
        add(copy.deepcopy(P_ESP_ANTES))
        cap = novo_p(P_LEGENDA)
        escrever(cap, marc(f"{rotulo} {v['legenda']}", textos_ilu_anteriores), RPR_LEGENDA)
        ancoras["ILU:" + rotulo] = add(cap)
        if v["tipo"] == "Figura":
            arq = os.path.join(FIGS, f"{v['arquivo']}_{variante}.png")
            if not os.path.exists(arq):
                raise SystemExit(f"figura não encontrada: {arq}")
            img = novo_p(P_IMAGEM, manter_com_proximo=True)
            sp = OxmlElement("w:spacing")  # espaçamento simples: evita a figura cortada
            for k, x in (("before", "0"), ("after", "60"), ("line", "240"), ("lineRule", "auto")):
                sp.set(qn(f"w:{k}"), x)
            jc = img.find(qn("w:pPr")).find(qn("w:jc"))
            (jc.addprevious(sp) if jc is not None else img.find(qn("w:pPr")).append(sp))
            add(img)
            Paragraph(img, doc._body).add_run().add_picture(arq, width=LARGURA_FIGURA)
        else:
            tbl = copy.deepcopy(TABELAS_MOLDE[int(v["n"]) - 1])
            ajustar_tabela(tbl)
            add(tbl)
        for campo, rot in (("nota", R["nota"]), ("fonte", R["fonte"])):
            if v[campo]:
                p = novo_p(P_NOTA, manter_com_proximo=(campo == "nota" and bool(v["fonte"])))
                p.append(novo_r(rot, RPR_NOTA_ROT))
                m = marc(f"{rot}{v[campo]}", textos_ilu_anteriores)
                escrever(p, m[len(tokens(rot)):], RPR_NOTA)
                ancoras[f"ILU:{rotulo}:{campo}"] = add(p)
        add(copy.deepcopy(P_ESP_DEPOIS))

    for tipo, val, secao in blocos_atuais:
        if tipo == "title":
            p = novo_p(P_TITULO)
            p.append(novo_r(val, RPR_TIT, vermelho=marcado and val not in titulos_anteriores))
            ancoras["@titulo"] = add(p)
        elif tipo == "title_en":
            p = novo_p(P_TITULO_EN)
            p.append(novo_r(val, RPR_TIT_EN, vermelho=marcado and val not in titulos_anteriores))
            ancoras["@titulo_en"] = add(p)
        elif tipo == "h1":
            p = novo_p(P_H1)
            p.append(novo_r(val, RPR_H1, vermelho=marcado and val not in titulos_anteriores))
            ancoras["#" + val] = add(p)
            if val == R["refs"]:
                for chave, n in sorted(num.items(), key=lambda x: x[1]):
                    pr = novo_p(P_REF, LINHA_CORPO)
                    nova = chave not in refs_anteriores or refs_anteriores[chave] != refs_atuais[chave]
                    pr.append(novo_r(f"{n}. {refs_atuais[chave]}", RPR_CORPO, vermelho=marcado and nova))
                    ancoras["@ref:" + chave] = add(pr)
        elif tipo == "h2":
            p = novo_p(P_H2)
            p.append(novo_r(val, RPR_H2, vermelho=marcado and val not in titulos_anteriores))
            ancoras["##" + val] = add(p)
        elif tipo == "kw":
            rot, txt = val
            p = novo_p(P_KW, LINHA_CORPO)
            p.append(novo_r(rot, RPR_KW_ROT))
            p.append(novo_r(txt, RPR_CORPO))
            add(p)
        elif tipo == "p":
            p = novo_p(P_CORPO, LINHA_CORPO)
            escrever(p, marc(val, paragrafos_anteriores), RPR_CORPO, num)
            ancoras[val] = add(p)
        elif tipo == "ilu":
            ilustracao(val)

    if marcado and COMENT and os.path.exists(COMENT):
        for linha in csv.reader(open(COMENT, encoding="utf-8"), delimiter="\t"):
            if not linha or linha[0].startswith("# ") or len(linha) < 2:  # "# " abre linha de comentário do .tsv
                continue
            ancora, texto = linha[0], linha[1]
            alvo = next((el for k, el in ancoras.items() if k.startswith(ancora)), None)
            if alvo is None:
                print("âncora não encontrada:", ancora)
                continue
            par = Paragraph(alvo, doc._body)
            runs = [r for r in par.runs if r.text.strip()] or par.runs
            if runs:
                doc.add_comment(runs[:1], text=texto, author="Revisão", initials="R")
    for sp in doc.styles.element.iter(qn("w:spacing")):
        if sp.get(qn("w:line")) and not sp.get(qn("w:lineRule")):
            sp.set(qn("w:lineRule"), "auto")
    # idioma da revisão ortográfica do Word
    rpr_padrao = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
    if rpr_padrao.find(qn("w:lang")) is None:
        rpr_padrao.append(OxmlElement("w:lang"))
    for raiz in (doc.styles.element, body):
        for lg in raiz.iter(qn("w:lang")):
            lg.set(qn("w:val"), R["lang"])
    doc.core_properties.language = R["lang"]
    # imagens do molde que ficaram sem uso (figuras antigas): saem do arquivo
    usadas = {b.get(qn("r:embed")) for b in body.iter(qn("a:blip"))}
    for rid, rel in list(doc.part.rels.items()):
        if rel.reltype.endswith("/image") and rid not in usadas:
            doc.part.rels.pop(rid)
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    destino = os.path.join(OUT, nome)
    doc.save(destino)
    return destino


if __name__ == "__main__":
    for variante, marcado, nome in R["variantes"]:
        if marcado and not MARCADA:
            continue
        print(montar(variante, marcado, nome))
    print("idioma:", IDIOMA, "| referências:", len(num), "| ilustrações:", ", ".join(ILUSTRACOES))
