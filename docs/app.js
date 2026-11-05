// Painel interativo: lê dados/painel.json (gerado por codigo/13_painel.py) e desenha com D3.
"use strict";
(() => {
  // ------------------------------------------------------------------ formatação (pt-BR)
  const LOC = d3.formatLocale({ decimal: ",", thousands: ".", grouping: [3], currency: ["R$", ""], minus: "−" });
  const fInt = LOC.format(",.0f");
  const f1 = LOC.format(",.1f");
  const f2 = LOC.format(",.2f");
  const f3 = LOC.format(",.3f");
  const fEixo = LOC.format(",~r");
  const fRT = LOC.format(".2~f");
  const fNum = (v) => (v == null || !isFinite(v) ? "—" : Math.abs(v) >= 100 ? fInt(v) : f1(v));
  const fVar = (r) => (r == null ? "—" : (r >= 1 ? "+" : "") + f1((r - 1) * 100) + "%");
  const fIC = (a, b, f = f2) => `IC95%: ${f(a)}–${f(b)}`;
  const fP = (p) => (p == null ? "" : p < 0.001 ? "p < 0,001" : `p = ${p < 0.01 ? f3(p) : f2(p)}`);
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const dataDe = (s) => new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, 1));
  const fMes = (d) => `${MESES[d.getUTCMonth()]}/${d.getUTCFullYear()}`;
  const fMesCurto = (d) => `${MESES[d.getUTCMonth()]}/${String(d.getUTCFullYear()).slice(2)}`;
  const semAcento = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  const ESTRATOS = [["estado", "Todo o RS"], ["<1%", "<1%"], ["1-<10%", "1–<10%"], [">=10%", "≥10%"]];
  const ROT_ESTRATO = { estado: "Rio Grande do Sul", "<1%": "municípios com <1% atingida", "1-<10%": "municípios com 1–<10% atingida", ">=10%": "municípios com ≥10% atingida" };
  const ROT_CAT = { "<1%": "<1%", "1-<10%": "1–<10%", ">=10%": "≥10%" };
  const MODELOS = [["ensemble", "Média dos 3 modelos"], ["qp", "Quase-Poisson"], ["sarima", "SARIMA"], ["lgbm", "LightGBM"]];
  const ESPECS = [["principal", "Principal"], ["sem_porto_alegre", "Sem Porto Alegre"], ["sem_vale_taquari", "Sem Vale do Taquari"], ["macro_x_ano", "Região intermediária × ano"]];
  const PERIODOS = [["agudo", "Agudo", "mai–jul/2024"], ["subagudo", "Subagudo", "ago/2024–abr/2025"], ["tardio", "Tardio", "mai/2025–mar/2026"]];
  const JANELAS = [["2022", "Desde 2022"], ["tudo", "2015–2026"]];
  const LAGOAS = new Set(["4300001", "4300002"]);

  // ------------------------------------------------------------------ estado
  let D, GEO, SERIES_MUN = null, promessaSeries;
  let DATAS = [];
  const MUN = new Map(); // cod (6 dígitos) -> município
  const MUN7 = new Map(); // cod7 -> município
  const E = {
    aba: "visao",
    cf: { desfecho: "caps_usuarios", estrato: ">=10%", modelo: "ensemble", janela: "2022" },
    dr: { desfecho: "caps_usuarios", espec: "principal" },
    mun: { cod: null, desfecho: "caps_usuarios", janela: "2022", suavizar: false, busca: "", ordem: ["pct", -1] },
    des: { desfecho: "Usuários dos CAPS", dimensao: "raça/cor" },
  };

  // ------------------------------------------------------------------ DOM
  const $ = (id) => document.getElementById(id);
  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "style") e.style.cssText = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos) if (f != null) e.append(f);
    return e;
  }
  function segmentado(cont, opcoes, valor, aoMudar) {
    cont.replaceChildren(...opcoes.map(([v, rot]) =>
      el("button", { type: "button", "aria-pressed": String(v === valor), onclick: () => aoMudar(v) }, rot)));
  }
  function preencherSelect(sel, grupos, valor) {
    sel.replaceChildren();
    for (const g of grupos) {
      const destino = g.nome ? el("optgroup", { label: g.nome }) : sel;
      for (const [v, rot] of g.itens) destino.append(el("option", { value: v, selected: v === valor }, rot));
      if (g.nome) sel.append(destino);
    }
    sel.value = valor;
  }
  function kpis(cont, itens) {
    cont.replaceChildren(...itens.map((k) => el("div", { class: "kpi" },
      el("div", { class: "rotulo" }, k.rotulo), el("div", { class: "valor" }, k.valor), el("div", { class: "rodape" }, k.rodape || ""))));
  }
  function legenda(cont, itens) {
    cont.replaceChildren(...itens.map((i) => {
      const chave = el("i", { class: `chave-${i.tipo || "linha"}`, "aria-hidden": "true" });
      if (i.tipo === "faixa") { chave.style.background = `color-mix(in srgb, ${i.cor} 18%, transparent)`; chave.style.color = i.cor; }
      else chave.style.background = i.cor;
      return el("span", {}, chave, i.rotulo);
    }));
  }

  // ------------------------------------------------------------------ tooltip
  const tip = $("tooltip");
  function mostrarTip(x, y, titulo, linhas) {
    tip.replaceChildren(el("div", { class: "tt-titulo" }, titulo), ...linhas.map((l) => {
      const chave = l.cor ? el("i", { class: l.tipo === "caixa" ? "chave-caixa" : l.tipo === "ponto" ? "chave-ponto" : "chave-linha" }) : null;
      if (chave) chave.style.background = l.cor;
      return el("div", { class: "tt-linha" }, chave, el("strong", {}, l.valor), el("span", { class: "rot" }, l.rotulo || ""));
    }));
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }
  const esconderTip = () => { tip.hidden = true; };

  // ------------------------------------------------------------------ vista de tabela (gêmea de cada gráfico)
  const TABELAS = {};
  function montarTabela(colunas, linhas) {
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ...colunas.map((c) => el("th", { class: c.txt ? "txt" : null, scope: "col" }, c.rot)))));
    t.append(el("tbody", {}, ...linhas.map((l) => el("tr", {}, ...l.map((v, j) => el("td", { class: colunas[j].txt ? "txt" : null }, v))))));
    return t;
  }
  function definirTabela(id, colunas, linhas) { TABELAS[id] = { colunas, linhas }; atualizarVistaTabela(id); }
  function atualizarVistaTabela(id) {
    const btn = document.querySelector(`[data-tabela="${id}"]`);
    const graf = $(id);
    if (!btn || !graf || !TABELAS[id]) return;
    const ativo = btn.getAttribute("aria-pressed") === "true";
    let vt = $(`${id}-tabela`);
    if (!ativo) { if (vt) vt.hidden = true; graf.hidden = false; return; }
    if (!vt) { vt = el("div", { id: `${id}-tabela`, class: "vista-tabela" }); graf.after(vt); }
    vt.replaceChildren(montarTabela(TABELAS[id].colunas, TABELAS[id].linhas));
    vt.hidden = false; graf.hidden = true;
  }
  document.querySelectorAll(".btn-tabela").forEach((b) => {
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => {
      const ativo = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(ativo));
      b.textContent = ativo ? "Gráfico" : "Tabela";
      if (!ativo) { $(b.dataset.tabela).hidden = false; renderizar(); } else atualizarVistaTabela(b.dataset.tabela);
    });
  });

  // ------------------------------------------------------------------ peças de gráfico
  function novoSvg(div, w, h, aria) {
    div.replaceChildren();
    return d3.select(div).append("svg").attr("width", w).attr("height", h).attr("viewBox", `0 0 ${w} ${h}`)
      .attr("role", "img").attr("aria-label", aria);
  }
  const largura = (div) => Math.max(280, Math.floor(div.clientWidth || div.parentElement.clientWidth || 600));
  const linhaH = (g, x1, x2, y, cor = "var(--grade)") => g.append("line").attr("x1", x1).attr("x2", x2).attr("y1", y).attr("y2", y)
    .style("stroke", cor).style("stroke-width", 1).attr("shape-rendering", "crispEdges");
  const linhaV = (g, x, y1, y2, cor = "var(--grade)") => g.append("line").attr("x1", x).attr("x2", x).attr("y1", y1).attr("y2", y2)
    .style("stroke", cor).style("stroke-width", 1).attr("shape-rendering", "crispEdges");
  const texto = (g, x, y, t, { ancora = "start", cor = "var(--muda)", tam = 11.5, peso = 400, dy = "0.32em" } = {}) =>
    g.append("text").attr("x", x).attr("y", y).attr("dy", dy).attr("text-anchor", ancora).style("fill", cor)
      .style("font-size", `${tam}px`).style("font-weight", peso).text(t);
  // Marcas do eixo log por prioridade (1 primeiro), sem duas mais próximas que minPx na tela.
  function ticksLog(esc, minPx) {
    const [d0, d1] = esc.domain();
    const prioridade = [1, 0.5, 2, 0.8, 1.25, 0.9, 1.1, 0.7, 1.5, 0.6, 1.2, 0.25, 3, 0.33, 2.5, 4, 0.2, 5, 0.1, 10];
    const ok = [];
    for (const v of prioridade) {
      if (v < d0 || v > d1) continue;
      if (ok.every((u) => Math.abs(esc(u) - esc(v)) >= minPx)) ok.push(v);
    }
    return ok.sort((a, b) => a - b);
  }
  function dominioLog(valores) {
    const v = valores.filter((x) => x > 0 && isFinite(x));
    const lo = Math.min(1, d3.min(v) ?? 1), hi = Math.max(1, d3.max(v) ?? 1);
    return [lo / 1.04, hi * 1.04];
  }
  function colunaPath(x0, larg, yTopo, yBase, r = 4) {
    const rr = Math.max(0, Math.min(r, yBase - yTopo, larg / 2));
    return `M${x0},${yBase}V${yTopo + rr}Q${x0},${yTopo} ${x0 + rr},${yTopo}H${x0 + larg - rr}Q${x0 + larg},${yTopo} ${x0 + larg},${yTopo + rr}V${yBase}Z`;
  }

  // Linhas no tempo com faixa de IC, marcador da enchente e cruz que acompanha o mês.
  function graficoLinhas(div, cfg) {
    const w = largura(div), h = cfg.altura || 330;
    const m = { t: 30, r: 16, b: 28, l: 50 };
    const svg = novoSvg(div, w, h, cfg.aria);
    const x = d3.scaleUtc().domain(cfg.dominioX).range([m.l, w - m.r]);
    const dentro = (p) => p.x >= cfg.dominioX[0] && p.x <= cfg.dominioX[1];
    const series = cfg.series.map((s) => ({ ...s, pontos: s.pontos.filter(dentro), banda: s.banda ? s.banda.filter(dentro) : null }));
    const vals = [];
    series.forEach((s) => { s.pontos.forEach((p) => isFinite(p.y) && vals.push(p.y)); (s.banda || []).forEach((b) => vals.push(b.y1)); });
    const y = d3.scaleLinear().domain([0, (d3.max(vals) || 1) * 1.04]).nice(5).range([h - m.b, m.t]);
    const fundo = svg.append("g").attr("class", "eixo");
    y.ticks(5).forEach((t) => {
      linhaH(fundo, m.l, w - m.r, y(t), t === 0 ? "var(--eixo)" : "var(--grade)");
      texto(fundo, m.l - 8, y(t), fEixo(t), { ancora: "end" });
    });
    const anos = (cfg.dominioX[1] - cfg.dominioX[0]) / 31557600000;
    let ticks = anos > 5 ? d3.utcYear.range(d3.utcYear.ceil(cfg.dominioX[0]), cfg.dominioX[1]) : d3.utcMonth.every(6).range(cfg.dominioX[0], cfg.dominioX[1]);
    const minimo = anos > 5 ? 44 : 50;
    while (ticks.length > 1 && (w - m.l - m.r) / ticks.length < minimo) ticks = ticks.filter((_, i) => i % 2 === 0);
    ticks.forEach((t) => texto(fundo, x(t), h - m.b + 15, anos > 5 ? String(t.getUTCFullYear()) : fMesCurto(t), { ancora: "middle" }));
    for (const f of cfg.faixas || []) {
      if (f.x0 > cfg.dominioX[0]) linhaV(fundo, x(f.x0), m.t - 4, h - m.b);
      const meio = (x(Math.max(f.x0, cfg.dominioX[0])) + x(Math.min(f.x1, cfg.dominioX[1]))) / 2;
      if (x(f.x1) - x(f.x0) > 46) texto(fundo, meio, m.t - 14, f.rotulo, { ancora: "middle" });
    }
    for (const ev of cfg.eventos || []) {
      linhaV(fundo, x(ev.x), m.t - 4, h - m.b, "var(--tinta2)");
      texto(fundo, x(ev.x) - 4, m.t - 14, ev.rotulo, { ancora: "end", cor: "var(--tinta2)" });
    }
    const plot = svg.append("g");
    series.filter((s) => s.banda && s.banda.length).forEach((s) => plot.append("path").datum(s.banda)
      .attr("d", d3.area().x((b) => x(b.x)).y0((b) => y(b.y0)).y1((b) => y(b.y1)))
      .style("fill", s.cor).style("fill-opacity", 0.12));
    series.forEach((s) => plot.append("path").datum(s.pontos.filter((p) => isFinite(p.y)))
      .attr("d", d3.line().x((p) => x(p.x)).y((p) => y(p.y)))
      .style("fill", "none").style("stroke", s.cor).style("stroke-width", 2).style("stroke-linejoin", "round").style("stroke-linecap", "round"));

    // cruz + tooltip (ponteiro e teclado)
    const xs = Array.from(new Set(series.flatMap((s) => s.pontos.map((p) => +p.x)))).sort((a, b) => a - b);
    const cruz = svg.append("line").style("stroke", "var(--eixo)").style("stroke-width", 1).style("display", "none");
    const marcas = svg.append("g");
    let atual = xs.length - 1;
    function mostrar(i, cx, cy) {
      atual = i;
      const xv = xs[i], px = x(xv);
      cruz.attr("x1", px).attr("x2", px).attr("y1", m.t).attr("y2", h - m.b).style("display", null);
      marcas.selectAll("*").remove();
      series.forEach((s) => {
        const p = s.pontos.find((q) => +q.x === xv);
        if (p && isFinite(p.y)) marcas.append("circle").attr("cx", px).attr("cy", y(p.y)).attr("r", 4)
          .style("fill", s.cor).style("stroke", "var(--superficie)").style("stroke-width", 2);
      });
      const t = cfg.tooltip(new Date(xv));
      if (cx == null) { const r = svg.node().getBoundingClientRect(); cx = r.left + px; cy = r.top + m.t; }
      mostrarTip(cx, cy, t.titulo, t.linhas);
    }
    const esconder = () => { cruz.style("display", "none"); marcas.selectAll("*").remove(); esconderTip(); };
    svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", Math.max(0, w - m.l - m.r)).attr("height", h - m.t - m.b)
      .style("fill", "transparent").style("cursor", "crosshair")
      .on("pointermove", (ev) => {
        const [px] = d3.pointer(ev);
        const alvo = +x.invert(px);
        let i = d3.bisectLeft(xs, alvo);
        if (i > 0 && (i === xs.length || alvo - xs[i - 1] < xs[i] - alvo)) i -= 1;
        mostrar(i, ev.clientX, ev.clientY);
      })
      .on("pointerleave", esconder);
    svg.attr("tabindex", 0)
      .on("focus", () => mostrar(atual))
      .on("blur", esconder)
      .on("keydown", (ev) => {
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
          ev.preventDefault();
          mostrar(Math.max(0, Math.min(xs.length - 1, atual + (ev.key === "ArrowLeft" ? -1 : 1))));
        }
      });
  }

  // Pontos com IC por trimestre (estudo de eventos), eixo log.
  function graficoEventos(div, pts, cfg) {
    const w = largura(div), h = cfg.altura || 300;
    const m = { t: 26, r: 12, b: 44, l: 46 };
    const svg = novoSvg(div, w, h, cfg.aria);
    const ks = pts.map((p) => p.k);
    const x = d3.scalePoint().domain(ks).range([m.l, w - m.r]).padding(0.6);
    const [d0, d1] = dominioLog(pts.flatMap((p) => [p.inf, p.sup, p.rr]));
    const y = d3.scaleLog().domain([d0, d1]).range([h - m.b, m.t]);
    const fundo = svg.append("g").attr("class", "eixo");
    ticksLog(y, 22).forEach((t) => {
      linhaH(fundo, m.l, w - m.r, y(t), t === 1 ? "var(--eixo)" : "var(--grade)");
      texto(fundo, m.l - 8, y(t), fRT(t), { ancora: "end" });
    });
    const passo = x.step();
    const iRef = ks.indexOf(-1);
    if (iRef >= 0 && iRef < ks.length - 1) {
      const xe = (x(-1) + x(0)) / 2;
      linhaV(fundo, xe, m.t - 4, h - m.b, "var(--tinta2)");
      texto(fundo, xe + 4, m.t - 12, "Enchente (mai/2024)", { cor: "var(--tinta2)" });
    }
    // Em telas estreitas, rótulos alternados; o primeiro (≤−9) não encosta no vizinho.
    const mostrarK = passo >= 22 ? () => true : (k) => k === ks[0] || (k % 2 === 0 && k - ks[0] >= 2);
    pts.forEach((p) => { if (mostrarK(p.k)) texto(fundo, x(p.k), h - m.b + 15, p.k === ks[0] && cfg.agrupado ? `≤${LOC.format("d")(p.k)}` : LOC.format("d")(p.k), { ancora: "middle" }); });
    texto(fundo, (m.l + w - m.r) / 2, h - 8, w < 560 ? cfg.tituloXCurto : cfg.tituloX, { ancora: "middle", cor: "var(--tinta2)" });
    const plot = svg.append("g");
    pts.forEach((p) => {
      const px = x(p.k);
      if (!p.ref) plot.append("line").attr("x1", px).attr("x2", px).attr("y1", y(p.inf)).attr("y2", y(p.sup))
        .style("stroke", cfg.cor).style("stroke-width", 2).style("stroke-linecap", "round");
      plot.append("circle").attr("cx", px).attr("cy", y(p.rr)).attr("r", 4.5)
        .style("fill", p.ref ? "var(--superficie)" : cfg.cor).style("stroke", p.ref ? cfg.cor : "var(--superficie)").style("stroke-width", 2);
    });
    const alvos = svg.append("g");
    pts.forEach((p) => {
      const mostrar = (cx, cy) => mostrarTip(cx, cy, cfg.rotuloK(p.k), p.ref
        ? [{ valor: "1", rotulo: "trimestre de referência" }]
        : [{ valor: `RT ${f2(p.rr)}`, rotulo: fIC(p.inf, p.sup), cor: cfg.cor, tipo: "ponto" }, { valor: fP(p.p), rotulo: "" }]);
      alvos.append("rect").attr("x", x(p.k) - Math.max(passo, 24) / 2).attr("y", m.t).attr("width", Math.max(passo, 24)).attr("height", h - m.t - m.b)
        .style("fill", "transparent").attr("tabindex", 0).attr("aria-label", cfg.rotuloK(p.k))
        .on("pointermove", (ev) => mostrar(ev.clientX, ev.clientY))
        .on("pointerleave", esconderTip)
        .on("focus", function () { const r = this.getBoundingClientRect(); mostrar(r.left + r.width / 2, r.top + 20); })
        .on("blur", esconderTip);
    });
  }

  // Linhas horizontais (floresta): uma linha por período, 1 ou 2 séries, eixo log.
  function graficoFloresta(div, linhas, cfg) {
    const w = largura(div);
    const nS = cfg.series.length;
    const alt = nS > 1 ? 48 : 42;
    const m = { t: 8, r: 16, b: 30, l: Math.min(150, Math.round(w * 0.36)) };
    const h = m.t + linhas.length * alt + m.b;
    const svg = novoSvg(div, w, h, cfg.aria);
    const todos = linhas.flatMap((l) => l.valores.filter(Boolean).flatMap((v) => [v.inf, v.sup, v.rr]));
    const [d0, d1] = dominioLog(todos);
    const x = d3.scaleLog().domain([d0, d1]).range([m.l, w - m.r]);
    const fundo = svg.append("g").attr("class", "eixo");
    ticksLog(x, 34).forEach((t) => {
      linhaV(fundo, x(t), m.t, h - m.b, t === 1 ? "var(--eixo)" : "var(--grade)");
      texto(fundo, x(t), h - m.b + 14, fRT(t), { ancora: "middle" });
    });
    linhas.forEach((l, i) => {
      const yc = m.t + i * alt + alt / 2;
      const rot = texto(svg, m.l - 12, yc - (l.sub ? 7 : 0), l.rotulo, { ancora: "end", cor: "var(--tinta)", tam: 13 });
      if (l.sub) texto(svg, m.l - 12, yc + 9, l.sub, { ancora: "end", tam: 11.5 });
      void rot;
      l.valores.forEach((v, j) => {
        if (!v) return;
        const yy = yc + (j - (nS - 1) / 2) * 12;
        const cor = cfg.series[j].cor;
        svg.append("line").attr("x1", x(v.inf)).attr("x2", x(v.sup)).attr("y1", yy).attr("y2", yy)
          .style("stroke", cor).style("stroke-width", 2).style("stroke-linecap", "round");
        svg.append("circle").attr("cx", x(v.rr)).attr("cy", yy).attr("r", 4.5)
          .style("fill", cor).style("stroke", "var(--superficie)").style("stroke-width", 2);
      });
      const mostrar = (cx, cy) => mostrarTip(cx, cy, l.sub ? `${l.rotulo} (${l.sub})` : l.rotulo,
        l.valores.flatMap((v, j) => (v ? [{ valor: `${cfg.prefixo || "RT"} ${f2(v.rr)}`, rotulo: `${nS > 1 ? cfg.series[j].nome + " · " : ""}${fIC(v.inf, v.sup)}${v.p != null ? " · " + fP(v.p) : ""}`, cor: cfg.series[j].cor, tipo: "ponto" }] : [])));
      svg.append("rect").attr("x", 0).attr("y", yc - alt / 2).attr("width", w).attr("height", alt)
        .style("fill", "transparent").attr("tabindex", 0).attr("aria-label", l.rotulo)
        .on("pointermove", (ev) => mostrar(ev.clientX, ev.clientY))
        .on("pointerleave", esconderTip)
        .on("focus", function () { const r = this.getBoundingClientRect(); mostrar(r.left + m.l, r.top + 8); })
        .on("blur", esconderTip);
    });
  }

  // Colunas finas, valor no topo.
  function graficoColunas(div, barras, cfg) {
    const w = largura(div), h = cfg.altura || 260;
    const m = { t: 22, r: 12, b: 30, l: 40 };
    const svg = novoSvg(div, w, h, cfg.aria);
    const x = d3.scaleBand().domain(barras.map((b) => b.rotulo)).range([m.l, w - m.r]).padding(0.3);
    const y = d3.scaleLinear().domain([0, (d3.max(barras, (b) => b.valor) || 1) * 1.1]).nice(4).range([h - m.b, m.t]);
    const fundo = svg.append("g").attr("class", "eixo");
    y.ticks(4).forEach((t) => {
      linhaH(fundo, m.l, w - m.r, y(t), t === 0 ? "var(--eixo)" : "var(--grade)");
      texto(fundo, m.l - 8, y(t), `${fEixo(t)}%`, { ancora: "end" });
    });
    const larg = Math.min(24, x.bandwidth());
    barras.forEach((b) => {
      const x0 = x(b.rotulo) + (x.bandwidth() - larg) / 2;
      svg.append("path").attr("d", colunaPath(x0, larg, y(b.valor), y(0))).style("fill", cfg.cor);
      texto(svg, x0 + larg / 2, y(b.valor) - 9, `${f1(b.valor)}%`, { ancora: "middle", cor: "var(--tinta)", tam: 12.5, peso: 600 });
      texto(fundo, x0 + larg / 2, h - m.b + 15, b.rotulo, { ancora: "middle" });
      const mostrar = (cx, cy) => mostrarTip(cx, cy, b.rotulo, [{ valor: `${f1(b.valor)}%`, rotulo: cfg.rotuloValor, cor: cfg.cor, tipo: "caixa" }]);
      svg.append("rect").attr("x", x(b.rotulo)).attr("y", m.t).attr("width", x.bandwidth()).attr("height", h - m.t - m.b)
        .style("fill", "transparent").attr("tabindex", 0).attr("aria-label", `${b.rotulo}: ${f1(b.valor)}%`)
        .on("pointermove", (ev) => mostrar(ev.clientX, ev.clientY)).on("pointerleave", esconderTip)
        .on("focus", function () { const r = this.getBoundingClientRect(); mostrar(r.left + r.width / 2, r.top); }).on("blur", esconderTip);
    });
  }

  // Mapa coroplético da exposição (3 categorias, rampa ordinal azul).
  const COR_CAT = { "<1%": "var(--m1)", "1-<10%": "var(--m2)", ">=10%": "var(--m3)" };
  function legendaMapa(cont) {
    const n = d3.rollup(D.municipios, (v) => v.length, (m) => m.cat);
    legenda(cont, [
      ...Object.keys(COR_CAT).map((c) => ({ tipo: "caixa", cor: COR_CAT[c], rotulo: `${ROT_CAT[c]} (${n.get(c) || 0} municípios)` })),
      { tipo: "caixa", cor: "var(--agua)", rotulo: "Lagoas" },
    ]);
  }
  function mapa(div, cfg) {
    const w = largura(div);
    const proj = d3.geoMercator().fitWidth(w - 4, GEO);
    const path = d3.geoPath(proj);
    const [[, y0], [, y1]] = path.bounds(GEO);
    const h = Math.ceil(y1 - y0) + 4;
    proj.translate([proj.translate()[0], proj.translate()[1] - y0 + 2]);
    const svg = novoSvg(div, w, h, cfg.aria);
    const g = svg.append("g");
    const destaque = svg.append("path").style("fill", "none").style("stroke", "var(--tinta)").style("stroke-width", 1.5).style("pointer-events", "none");
    const selecao = svg.append("path").style("fill", "none").style("stroke", "var(--tinta)").style("stroke-width", 2.5).style("pointer-events", "none");
    g.selectAll("path").data(GEO.features).join("path")
      .attr("d", path)
      .style("fill", (f) => (LAGOAS.has(f.properties.CD_MUN) ? "var(--agua)" : COR_CAT[MUN7.get(f.properties.CD_MUN)?.cat] || "var(--agua)"))
      .style("stroke", "var(--superficie)").style("stroke-width", 0.6)
      .style("cursor", (f) => (MUN7.has(f.properties.CD_MUN) ? "pointer" : "default"))
      .on("pointermove", function (ev, f) {
        const mu = MUN7.get(f.properties.CD_MUN);
        destaque.attr("d", path(f));
        if (!mu) { mostrarTip(ev.clientX, ev.clientY, f.properties.CD_MUN === "4300001" ? "Lagoa Mirim" : "Lagoa dos Patos", []); return; }
        mostrarTip(ev.clientX, ev.clientY, mu.nome, [
          { valor: `${f1(mu.pct)}%`, rotulo: "da população na área atingida", cor: COR_CAT[mu.cat], tipo: "caixa" },
          { valor: fInt(mu.pop_afetada || 0), rotulo: "pessoas na área atingida" },
          { valor: fInt(mu.pop || 0), rotulo: "habitantes (mai/2024)" },
        ]);
      })
      .on("pointerleave", () => { destaque.attr("d", null); esconderTip(); })
      .on("click", (ev, f) => { const mu = MUN7.get(f.properties.CD_MUN); if (mu) cfg.aoClicar(mu.cod); });
    const sel = cfg.selecionado && MUN.get(cfg.selecionado);
    if (sel) {
      const f = GEO.features.find((q) => q.properties.CD_MUN === sel.cod7);
      if (f) selecao.attr("d", path(f));
    }
  }

  // ------------------------------------------------------------------ Visão geral
  function renderVisao() {
    const X = D.destaques;
    kpis($("visao-kpis"), [
      { rotulo: "Pessoas residentes na área atingida", valor: fInt(X.pop_afetada),
        rodape: `em ${X.mun_afetados} municípios; os ${X.mun_10} municípios com ≥10% da população atingida somavam ${f2(X.pop_10 / 1e6)} milhões de habitantes` },
      { rotulo: "Usuários dos CAPS nos municípios com ≥10% atingida, mai–jul/2024, em relação ao esperado", valor: fVar(X.caps_oe_agudo_10.oe),
        rodape: `${fInt(X.caps_oe_agudo_10.obs)} observados; ${fInt(X.caps_oe_agudo_10.esp)} esperados (O/E ${f2(X.caps_oe_agudo_10.oe)}; ${fIC(X.caps_oe_agudo_10.inf, X.caps_oe_agudo_10.sup)})` },
      { rotulo: "Usuários dos CAPS a cada 10 p.p. de população atingida, mai–jul/2024", valor: fVar(X.caps_rt_agudo.rr),
        rodape: `RT ${f2(X.caps_rt_agudo.rr)} (${fIC(X.caps_rt_agudo.inf, X.caps_rt_agudo.sup)}); controle sintético: ${f1(X.caps_sdid_agudo.rel)}%` },
      { rotulo: "Internações psiquiátricas no RS, mai/2024–mar/2026, em relação ao esperado", valor: fVar(X.f_oe_23_estado.oe),
        rodape: `${fInt(X.f_oe_23_estado.obs)} observadas; ${fInt(X.f_oe_23_estado.esp)} esperadas (O/E ${f2(X.f_oe_23_estado.oe)}; ${fIC(X.f_oe_23_estado.inf, X.f_oe_23_estado.sup)})` },
    ]);
    const pre = (d) => D.dose.pretendencia.find((p) => p.desfecho === d && p.espec === "principal" && p.exposicao === "continua_10pp");
    const rt = (d, per) => D.dose.periodo.find((p) => p.desfecho === d && p.espec === "principal" && p.exposicao === "continua_10pp" && p.periodo === per);
    const abaixo = (r) => `${Math.round(Math.abs(r - 1) * 100)}% ${r < 1 ? "abaixo" : "acima"} do esperado`;
    const desc = Object.fromEntries(D.desigualdades.descritivo.map((d) => [d.cat, d]));
    const pDif = D.desigualdades.rt.map((r) => r.p_diferenca);
    const psicRT = rt("f_psicoticos", "agudo");
    const preCaps = pre("caps_usuarios");
    const achados = [
      `Nos ${X.mun_10} municípios com ≥10% da população atingida, os usuários atendidos nos CAPS ficaram ${abaixo(X.caps_oe_agudo_10.oe)} de maio a julho de 2024 (O/E ${f2(X.caps_oe_agudo_10.oe)}; ${fIC(X.caps_oe_agudo_10.inf, X.caps_oe_agudo_10.sup)}) e se recuperaram só em parte depois (O/E em 23 meses: ${f2(X.caps_oe_23_10.oe)}; ${fIC(X.caps_oe_23_10.inf, X.caps_oe_23_10.sup)}).`,
      `A queda foi maior onde a enchente atingiu mais gente: cada 10 p.p. de população atingida reduziu em ${Math.round((1 - X.caps_rt_agudo.rr) * 100)}% os usuários no período agudo (RT ${f2(X.caps_rt_agudo.rr)}; ${fIC(X.caps_rt_agudo.inf, X.caps_rt_agudo.sup)})${preCaps && preCaps.p >= 0.05 ? `, sem tendência prévia significativa (${fP(preCaps.p)})` : ""}. O controle sintético estimou redução de ${Math.round(-X.caps_sdid_agudo.rel)}% (IC95%: ${f1(X.caps_sdid_agudo.inf)} a ${f1(X.caps_sdid_agudo.sup)}).`,
      `As internações psiquiátricas ficaram estáveis no estado (O/E em 23 meses: ${f2(X.f_oe_23_estado.oe)}; ${fIC(X.f_oe_23_estado.inf, X.f_oe_23_estado.sup)}) e não variaram com a exposição (RT agudo: ${f2(X.f_rt_agudo.rr)}; ${fIC(X.f_rt_agudo.inf, X.f_rt_agudo.sup)}). As internações por esquizofrenia e transtornos psicóticos ficaram acima do esperado nos municípios mais atingidos no período agudo (O/E ${f2(X.psic_oe_agudo_10.oe)}; ${fIC(X.psic_oe_agudo_10.inf, X.psic_oe_agudo_10.sup)})${psicRT && psicRT.p >= 0.05 ? ", sem relação dose-resposta significativa" : ""}.`,
      `Os partos também diminuíram com a exposição (RT ${f3(X.parto_rt_agudo.rr)} por 10 p.p.; ${fIC(X.parto_rt_agudo.inf, X.parto_rt_agudo.sup, f3)}): a enchente interrompeu o acesso aos serviços de saúde em geral.`,
      `${pDif.every((p) => p > 0.05) ? "O efeito não diferiu por sexo nem por raça/cor. " : ""}Antes da enchente, pessoas pretas ou pardas eram ${f1(desc[">=10%"].caps_negra)}% dos usuários dos CAPS nos municípios mais atingidos, ante ${f1(desc["<1%"].caps_negra)}% nos menos atingidos.`,
    ];
    $("visao-achados").replaceChildren(...achados.map((t) => el("li", {}, t)));
    legendaMapa($("visao-mapa-legenda"));
    mapa($("visao-mapa"), { aria: "Mapa do Rio Grande do Sul com a proporção da população de cada município na área atingida", aoClicar: (cod) => { E.mun.cod = cod; location.hash = "municipios"; } });
    const ord = [...D.municipios].sort((a, b) => b.pct - a.pct);
    definirTabela("visao-mapa", [{ rot: "Município", txt: true }, { rot: "% atingida" }, { rot: "Pessoas atingidas" }, { rot: "População (mai/2024)" }, { rot: "Categoria", txt: true }],
      ord.map((m) => [m.nome, f1(m.pct), fInt(m.pop_afetada || 0), fInt(m.pop || 0), ROT_CAT[m.cat]]));
  }

  // ------------------------------------------------------------------ Observado × esperado
  const FAIXAS = [
    { x0: dataDe("2024-04").getTime() + 15 * 864e5, x1: dataDe("2024-07").getTime() + 15 * 864e5, rotulo: "agudo" },
    { x0: dataDe("2024-07").getTime() + 15 * 864e5, x1: dataDe("2025-04").getTime() + 15 * 864e5, rotulo: "subagudo" },
    { x0: dataDe("2025-04").getTime() + 15 * 864e5, x1: dataDe("2026-03").getTime() + 15 * 864e5, rotulo: "tardio" },
  ];
  const ENCHENTE = new Date(dataDe("2024-04").getTime() + 15 * 864e5);
  const dominio = (janela) => [janela === "tudo" ? dataDe("2015-01") : dataDe("2022-01"), dataDe(D.meses[D.meses.length - 1])];

  function renderCf() {
    const c = E.cf;
    const rot = D.rotulos;
    preencherSelect($("cf-desfecho"), D.grupos.map((g) => ({ nome: g.nome, itens: g.desfechos.filter((d) => D.desfechos_contrafactual.includes(d)).map((d) => [d, rot[d]]) })).filter((g) => g.itens.length), c.desfecho);
    segmentado($("cf-estrato"), ESTRATOS, c.estrato, (v) => { c.estrato = v; renderizar(); });
    preencherSelect($("cf-modelo"), [{ itens: MODELOS }], c.modelo);
    segmentado($("cf-janela"), JANELAS, c.janela, (v) => { c.janela = v; renderizar(); });

    const per = D.contrafactual.periodos.filter((p) => p.desfecho === c.desfecho && p.estrato === c.estrato);
    const achar = (modelo, periodo) => per.find((p) => p.modelo === modelo && p.periodo === periodo);
    kpis($("cf-kpis"), [...PERIODOS.map(([k, nome, meses]) => [k, `${nome}, ${meses}`]), ["23 meses", "23 meses, mai/2024–mar/2026"]].map(([k, rotulo]) => {
      const p = achar(c.modelo, k);
      return p ? { rotulo, valor: fVar(p.oe), rodape: `O/E ${f2(p.oe)} (${fIC(p.inf, p.sup)}) · ${fInt(p.obs)} observados; ${fInt(p.esp)} esperados` } : { rotulo, valor: "—" };
    }));

    const ob = D.contrafactual.observado[c.desfecho][c.estrato];
    const taxa = (n, i) => (ob.pop[i] ? (n / ob.pop[i]) * 1e5 : NaN);
    const obs = D.meses.map((_, i) => ({ x: DATAS[i], y: taxa(ob.n[i], i), n: ob.n[i] }));
    const es = D.contrafactual.esperado[c.desfecho]?.[c.estrato]?.[c.modelo];
    const esp = [], banda = [];
    if (es) es.esp.forEach((v, j) => {
      const i = es.inicio + j;
      esp.push({ x: DATAS[i], y: taxa(v, i), n: v });
      banda.push({ x: DATAS[i], y0: taxa(es.inf[j], i), y1: taxa(es.sup[j], i) });
    });
    $("cf-titulo").textContent = `${rot[c.desfecho]}: ${ROT_ESTRATO[c.estrato]}`;
    legenda($("cf-legenda"), [{ cor: "var(--s1)", rotulo: "Observado" }, { tipo: "faixa", cor: "var(--s2)", rotulo: `Esperado sem a enchente (${MODELOS.find((m) => m[0] === c.modelo)[1].toLowerCase()}) e IC95%` }]);
    const porX = new Map(esp.map((p, j) => [+p.x, { p, b: banda[j] }]));
    graficoLinhas($("cf-grafico"), {
      aria: `Taxa mensal observada e esperada de ${rot[c.desfecho]}`,
      dominioX: dominio(c.janela),
      series: [{ cor: "var(--s1)", pontos: obs }, { cor: "var(--s2)", pontos: esp, banda }],
      faixas: FAIXAS, eventos: [{ x: ENCHENTE, rotulo: "Enchente" }],
      tooltip: (d) => {
        const i = DATAS.findIndex((q) => +q === +d);
        const e = porX.get(+d);
        const linhas = [{ valor: f1(obs[i].y), rotulo: `observado (${fInt(obs[i].n)})`, cor: "var(--s1)" }];
        if (e) linhas.push({ valor: f1(e.p.y), rotulo: `esperado (${f1(e.b.y0)}–${f1(e.b.y1)})`, cor: "var(--s2)" });
        return { titulo: `${fMes(d)} · por 100 mil hab.`, linhas };
      },
    });
    definirTabela("cf-grafico", [{ rot: "Mês", txt: true }, { rot: "Observado (n)" }, { rot: "Taxa observada" }, { rot: "Esperado (n)" }, { rot: "Taxa esperada" }, { rot: "IC95% da taxa" }],
      obs.filter((p) => p.x >= dominio(c.janela)[0]).map((p) => {
        const e = porX.get(+p.x);
        return [fMes(p.x), fInt(p.n), f1(p.y), e ? fInt(e.p.n) : "", e ? f1(e.p.y) : "", e ? `${f1(e.b.y0)}–${f1(e.b.y1)}` : ""];
      }));
    const v = D.contrafactual.validacao.find((q) => q.desfecho === c.desfecho && q.estrato === c.estrato);
    $("cf-validacao").textContent = v
      ? `Validação da média dos 3 modelos em ${v.cortes} datas fictícias (mai/2018, 2019, 2022 e 2023), sem enchente: erro médio do total de 12 meses de ${f1(v.erro)}% e erro mensal absoluto médio de ${f1(v.erro_abs)}%; o IC95% conteve o total observado em ${v.cortes === v.cobre ? "todas" : `${v.cobre} das ${v.cortes}`}.`
      : "";
    $("cf-modelos").replaceChildren(montarTabela([{ rot: "Período", txt: true }, ...MODELOS.map(([, n]) => ({ rot: n }))],
      [...PERIODOS.map(([k, n, mm]) => [k, `${n} (${mm})`]), ["23 meses", "23 meses"]].map(([k, n]) =>
        [n, ...MODELOS.map(([mo]) => { const p = achar(mo, k); return p ? `${f2(p.oe)} (${f2(p.inf)}–${f2(p.sup)})` : "—"; })])));
  }

  // ------------------------------------------------------------------ Dose-resposta
  const inicioTrimestre = (k) => new Date(Date.UTC(2024, 4 + 3 * k, 1));
  function rotuloK(k, kmin) {
    if (k === kmin) return `Trimestre ≤${LOC.format("d")(k)}: até abr/2022`;
    const a = inicioTrimestre(k), b = new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth() + 2, 1));
    const fim = b > DATAS[DATAS.length - 1] ? DATAS[DATAS.length - 1] : b;
    return `Trimestre ${LOC.format("d")(k)}: ${MESES[a.getUTCMonth()]}–${fMesCurto(fim)}`;
  }
  function renderDr() {
    const c = E.dr, rot = D.rotulos;
    preencherSelect($("dr-desfecho"), D.grupos.map((g) => ({ nome: g.nome, itens: g.desfechos.map((d) => [d, rot[d]]) })), c.desfecho);
    preencherSelect($("dr-espec"), [{ itens: ESPECS }], c.espec);
    const doPer = (espec, exposicao) => D.dose.periodo.filter((p) => p.desfecho === c.desfecho && p.espec === espec && p.exposicao === exposicao);
    const per = doPer(c.espec, "continua_10pp");
    const pre = D.dose.pretendencia.find((p) => p.desfecho === c.desfecho && p.espec === c.espec && p.exposicao === "continua_10pp");
    kpis($("dr-kpis"), [
      ...PERIODOS.map(([k, n, mm]) => {
        const p = per.find((q) => q.periodo === k);
        return p ? { rotulo: `${n} (${mm}), a cada 10 p.p.`, valor: fVar(p.rr), rodape: `RT ${f2(p.rr)} (${fIC(p.inf, p.sup)}) · ${fP(p.p)}` } : { rotulo: n, valor: "—" };
      }),
      { rotulo: "Tendência prévia (teste conjunto dos trimestres anteriores)", valor: pre ? fP(pre.p) : "—",
        rodape: pre ? (pre.p < 0.05 ? "Há tendência antes da enchente: ler o efeito com cautela." : "Sem tendência prévia significativa.") : "" },
    ]);
    const ev = D.dose.evento.filter((p) => p.desfecho === c.desfecho && p.espec === c.espec).sort((a, b) => a.k - b.k);
    const kmin = ev.length ? ev[0].k : -9;
    const pts = [...ev, { k: -1, rr: 1, inf: 1, sup: 1, ref: true }].sort((a, b) => a.k - b.k);
    $("dr-titulo-evento").textContent = `Estudo de eventos: ${rot[c.desfecho]}`;
    graficoEventos($("dr-evento"), pts, {
      aria: `Estudo de eventos de ${rot[c.desfecho]}`, cor: "var(--s1)", agrupado: true,
      tituloX: "Trimestres em relação a mai/2024 (0 = mai–jul/2024; −1 = referência)", tituloXCurto: "Trimestres desde mai/2024 (−1 = referência)",
      rotuloK: (k) => rotuloK(k, kmin),
    });
    definirTabela("dr-evento", [{ rot: "Trimestre", txt: true }, { rot: "RT" }, { rot: "IC95%" }, { rot: "p" }],
      pts.map((p) => [rotuloK(p.k, kmin), p.ref ? "1 (referência)" : f3(p.rr), p.ref ? "" : `${f3(p.inf)}–${f3(p.sup)}`, p.ref ? "" : fP(p.p).replace("p = ", "").replace("p ", "")]));
    $("dr-pretendencia").textContent = pre ? `Teste de tendência prévia (Wald, ${c.espec === "principal" ? "especificação principal" : ESPECS.find((e) => e[0] === c.espec)[1].toLowerCase()}): ${fP(pre.p)}.` : "";

    const linhas = PERIODOS.map(([k, n, mm]) => ({ rotulo: n, sub: mm, valores: [per.find((q) => q.periodo === k)] }));
    if (c.espec === "principal") {
      const pl = doPer("placebo_mai2023", "continua_10pp").find((q) => q.periodo === "placebo");
      if (pl) linhas.push({ rotulo: "Data fictícia", sub: "mai/2023", valores: [pl] });
    }
    graficoFloresta($("dr-periodo"), linhas, { aria: "Razão de taxas por período", series: [{ nome: "RT", cor: "var(--s1)" }] });
    definirTabela("dr-periodo", [{ rot: "Período", txt: true }, { rot: "RT por 10 p.p." }, { rot: "IC95%" }, { rot: "p" }],
      linhas.map((l) => { const v = l.valores[0]; return [`${l.rotulo} (${l.sub})`, v ? f3(v.rr) : "—", v ? `${f3(v.inf)}–${f3(v.sup)}` : "", v ? fP(v.p) : ""]; }));

    const cat = doPer("principal", "categorias");
    const seriesCat = [{ nome: "1–<10% vs <1%", cor: "var(--s1)", grupo: "1-<10%" }, { nome: "≥10% vs <1%", cor: "var(--s2)", grupo: ">=10%" }];
    legenda($("dr-categorias-legenda"), seriesCat.map((s) => ({ tipo: "ponto", cor: s.cor, rotulo: s.nome })));
    const linhasCat = PERIODOS.map(([k, n, mm]) => ({ rotulo: n, sub: mm, valores: seriesCat.map((s) => cat.find((q) => q.periodo === k && q.grupo === s.grupo)) }));
    if (cat.length) graficoFloresta($("dr-categorias"), linhasCat, { aria: "Razão de taxas por categoria de exposição", series: seriesCat });
    else $("dr-categorias").replaceChildren(el("p", { class: "aviso" }, "Não estimado para este desfecho."));
    definirTabela("dr-categorias", [{ rot: "Período", txt: true }, { rot: "Categoria", txt: true }, { rot: "RT vs <1%" }, { rot: "IC95%" }, { rot: "p" }],
      linhasCat.flatMap((l) => l.valores.map((v, j) => [`${l.rotulo} (${l.sub})`, seriesCat[j].nome, v ? f3(v.rr) : "—", v ? `${f3(v.inf)}–${f3(v.sup)}` : "", v ? fP(v.p) : ""])));

    // robustez: SDID e margens dos CAPS, quando houver
    const rob = $("dr-robustez");
    const sd = D.robustez.sdid.filter((s) => s.desfecho === c.desfecho);
    const blocos = [];
    if (sd.length) {
      blocos.push(el("h2", {}, "Controle sintético de diferenças em diferenças (SDID)"),
        el("p", { class: "nota-titulo" }, "55 municípios com ≥10% atingida comparados a uma combinação ponderada dos 358 com <1%. Cada município tratado tem o mesmo peso."),
        el("div", { class: "vista-tabela", style: "margin:10px 0 16px" }, montarTabela(
          [{ rot: "Período", txt: true }, { rot: "Efeito relativo" }, { rot: "IC95%" }, { rot: "Diferença por 100 mil hab./mês" }, { rot: "IC95%" }],
          sd.map((s) => [s.periodo === "todo o pós" ? "Todo o pós (mai/2024–mar/2026)" : `${s.periodo[0].toUpperCase()}${s.periodo.slice(1)}`, `${f1(s.rel)}%`, `${f1(s.rel_inf)} a ${f1(s.rel_sup)}`, f1(s.att), `${f1(s.att_inf)} a ${f1(s.att_sup)}`]))));
    }
    if (c.desfecho === "caps_usuarios") {
      const mg = D.robustez.margens;
      const nomeP = { abr_2024: "Abril/2024 (antes)", agudo: "Agudo", subagudo: "Subagudo", tardio: "Tardio" };
      blocos.push(el("h2", {}, `CAPS por estabelecimento (${mg[0].caps} CAPS ativos no 1º trimestre de 2024)`),
        el("p", { class: "nota-titulo" }, "Margem extensiva: diferença na probabilidade de um mês sem registro de produção, por 10 p.p. Margem intensiva: razão de taxas de usuários por CAPS nos meses com registro."),
        el("div", { class: "vista-tabela", style: "margin-top:10px" }, montarTabela(
          [{ rot: "Período", txt: true }, { rot: "Extensiva (p.p.)" }, { rot: "IC95%" }, { rot: "Intensiva (RT)" }, { rot: "IC95%" }],
          Object.keys(nomeP).map((k) => {
            const a = mg.find((q) => q.margem === "extensiva" && q.periodo === k), b = mg.find((q) => q.margem === "intensiva" && q.periodo === k);
            return [nomeP[k], a ? f1(a.est * 100) : "—", a ? `${f1(a.inf * 100)} a ${f1(a.sup * 100)}` : "", b ? f2(b.est) : "—", b ? `${f2(b.inf)}–${f2(b.sup)}` : ""];
          }))));
    }
    rob.hidden = !blocos.length;
    rob.replaceChildren(...blocos);
  }

  // ------------------------------------------------------------------ Municípios
  const media3 = (v) => v.map((_, i) => { const j = v.slice(Math.max(0, i - 1), i + 2).filter(isFinite); return j.length ? d3.mean(j) : NaN; });
  const IDX = (s) => D.meses.indexOf(s);
  const MIN_BASE = 10; // registros nos 12 meses antes; abaixo disso a variação % não é mostrada
  function taxaMedia(n, pop, i0, i1) {
    let sn = 0, sp = 0;
    for (let i = i0; i <= i1; i++) { sn += n[i]; sp += pop[i]; }
    return sp ? (sn / sp) * 1e5 : NaN;
  }
  function renderMun() {
    const c = E.mun, rot = D.rotulos;
    if (!c.cod) c.cod = [...D.municipios].sort((a, b) => (b.pop_afetada || 0) - (a.pop_afetada || 0))[0].cod;
    preencherSelect($("mun-sel"), [{ itens: D.municipios.map((m) => [m.cod, `${m.nome} (${f1(m.pct)}% atingida)`]) }], c.cod);
    preencherSelect($("mun-desfecho"), [{ itens: D.desfechos_municipio.map((d) => [d, rot[d]]) }], c.desfecho);
    segmentado($("mun-janela"), JANELAS, c.janela, (v) => { c.janela = v; renderizar(); });
    $("mun-suavizar").checked = c.suavizar;
    legendaMapa($("mun-mapa-legenda"));
    mapa($("mun-mapa"), { aria: "Mapa para escolher o município", selecionado: c.cod, aoClicar: (cod) => { c.cod = cod; renderizar(); } });
    const mu = MUN.get(c.cod);
    $("mun-titulo").textContent = `${mu.nome}: ${rot[c.desfecho]}`;
    $("mun-subtitulo").textContent = "Taxa mensal por 100 mil habitantes; em cinza, o Rio Grande do Sul.";
    $("mun-ficha").replaceChildren(...[
      ["Região imediata", mu.reg_imediata || "—"], ["População atingida", `${f1(mu.pct)}%`],
      ["Pessoas na área atingida", fInt(mu.pop_afetada || 0)], ["Habitantes (mai/2024)", fInt(mu.pop || 0)], ["Categoria", ROT_CAT[mu.cat]],
    ].map(([a, b]) => el("div", {}, el("span", {}, a), el("strong", {}, b))));
    legenda($("mun-legenda"), [{ cor: "var(--s1)", rotulo: mu.nome }, { cor: "var(--cinza)", rotulo: "Rio Grande do Sul" }]);
    if (!SERIES_MUN) {
      $("mun-grafico").replaceChildren(el("p", { class: "carregando" }, "Carregando as séries dos municípios…"));
      $("mun-tabela").replaceChildren(el("p", { class: "carregando", style: "padding:12px" }, "Carregando…"));
      promessaSeries.then(() => { if (E.aba === "municipios") renderizar(); });
      return;
    }
    const n = SERIES_MUN[c.desfecho][c.cod], pop = SERIES_MUN.pop[c.cod];
    const est = D.contrafactual.observado[c.desfecho].estado;
    let tm = n.map((v, i) => (pop[i] ? (v / pop[i]) * 1e5 : NaN));
    let te = est.n.map((v, i) => (v / est.pop[i]) * 1e5);
    if (c.suavizar) { tm = media3(tm); te = media3(te); }
    graficoLinhas($("mun-grafico"), {
      aria: `Taxa mensal de ${rot[c.desfecho]} em ${mu.nome} e no estado`, altura: 300,
      dominioX: dominio(c.janela),
      series: [{ cor: "var(--cinza)", pontos: te.map((y, i) => ({ x: DATAS[i], y })) }, { cor: "var(--s1)", pontos: tm.map((y, i) => ({ x: DATAS[i], y })) }],
      faixas: FAIXAS, eventos: [{ x: ENCHENTE, rotulo: "Enchente" }],
      tooltip: (d) => {
        const i = DATAS.findIndex((q) => +q === +d);
        return { titulo: `${fMes(d)} · por 100 mil hab.${c.suavizar ? " (média de 3 meses)" : ""}`, linhas: [
          { valor: f1(tm[i]), rotulo: `${mu.nome} (${fInt(n[i])} no mês)`, cor: "var(--s1)" },
          { valor: f1(te[i]), rotulo: "Rio Grande do Sul", cor: "var(--cinza)" }] };
      },
    });
    const d0 = dominio(c.janela)[0];
    definirTabela("mun-grafico", [{ rot: "Mês", txt: true }, { rot: `${mu.nome} (n)` }, { rot: "Taxa" }, { rot: "Taxa no RS" }],
      DATAS.map((d, i) => [d, i]).filter(([d]) => d >= d0).map(([d, i]) => [fMes(d), fInt(n[i]), f1(tm[i]), f1(te[i])]));
    tabelaMunicipios();
  }
  function tabelaMunicipios() {
    const c = E.mun, d = c.desfecho;
    const a0 = IDX("2023-05"), a1 = IDX("2024-04"), b0 = IDX("2024-05"), b1 = IDX("2025-04");
    $("mun-tabela-nota").textContent = `${D.rotulos[d]}: taxa mensal média por 100 mil habitantes nos 12 meses antes (mai/2023–abr/2024) e depois (mai/2024–abr/2025) do início da enchente. A variação só aparece com ${MIN_BASE} ou mais registros nos 12 meses antes. Clique no cabeçalho para ordenar e na linha para ver o município.`;
    const linhas = D.municipios.map((m) => {
      const n = SERIES_MUN[d][m.cod], pop = SERIES_MUN.pop[m.cod];
      const antes = n ? taxaMedia(n, pop, a0, a1) : NaN, depois = n ? taxaMedia(n, pop, b0, b1) : NaN;
      const base = n ? d3.sum(n.slice(a0, a1 + 1)) : 0;
      return { ...m, antes, depois, var: base >= MIN_BASE ? depois / antes - 1 : NaN };
    });
    const busca = semAcento(c.busca.trim());
    const filtradas = busca ? linhas.filter((l) => semAcento(`${l.nome} ${l.reg_imediata || ""} ${l.reg_intermediaria || ""}`).includes(busca)) : linhas;
    const [chave, dir] = c.ordem;
    filtradas.sort((a, b) => {
      const va = a[chave], vb = b[chave];
      if (typeof va === "string") return dir * va.localeCompare(vb, "pt-BR");
      const na = isFinite(va) ? va : -Infinity, nb = isFinite(vb) ? vb : -Infinity;
      return dir * (na - nb);
    });
    const cols = [["nome", "Município", true], ["reg_imediata", "Região imediata", true], ["pct", "% atingida"], ["cat", "Categoria", true],
      ["pop", "Habitantes"], ["antes", "Taxa antes"], ["depois", "Taxa depois"], ["var", "Variação"]];
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ...cols.map(([k, r, txt]) => el("th", {
      class: `ordenavel${txt ? " txt" : ""}`, scope: "col", tabindex: 0,
      "aria-sort": chave === k ? (dir > 0 ? "ascending" : "descending") : "none",
      onclick: () => { c.ordem = [k, chave === k ? -dir : (txt ? 1 : -1)]; tabelaMunicipios(); },
      onkeydown: (ev) => { if (ev.key === "Enter") ev.target.click(); },
    }, `${r}${chave === k ? (dir > 0 ? " ↑" : " ↓") : ""}`)))));
    t.append(el("tbody", {}, ...filtradas.map((l) => el("tr", {
      class: `clicavel${l.cod === c.cod ? " sel" : ""}`, tabindex: 0,
      onclick: () => { c.cod = l.cod; renderizar(); $("municipios").scrollIntoView({ behavior: "smooth", block: "start" }); },
      onkeydown: (ev) => { if (ev.key === "Enter") ev.currentTarget.click(); },
    }, el("td", { class: "txt" }, l.nome), el("td", { class: "txt" }, l.reg_imediata || ""), el("td", {}, f1(l.pct)), el("td", { class: "txt" }, ROT_CAT[l.cat]),
      el("td", {}, fInt(l.pop || 0)), el("td", {}, fNum(l.antes)), el("td", {}, fNum(l.depois)), el("td", {}, isFinite(l.var) ? fVar(l.var + 1) : "—")))));
    $("mun-tabela").replaceChildren(t);
  }

  // ------------------------------------------------------------------ Desigualdades
  const DIMENSOES = [["sexo", "Mulheres × homens (2015–2026)"], ["raça/cor", "Pretos ou pardos × brancos (desde jul/2023)"], ["raça/cor (desde out/2023)", "Pretos ou pardos × brancos (desde out/2023)"]];
  const maiuscula = (s) => s[0].toUpperCase() + s.slice(1);
  function renderDes() {
    const c = E.des;
    segmentado($("des-desfecho"), [["Usuários dos CAPS", "Usuários dos CAPS"], ["Internações F00–F99", "Internações psiquiátricas"]], c.desfecho, (v) => { c.desfecho = v; renderizar(); });
    preencherSelect($("des-dimensao"), [{ itens: DIMENSOES }], c.dimensao);
    const rt = D.desigualdades.rt.filter((r) => r.desfecho === c.desfecho && r.dimensao === c.dimensao);
    const ref = rt[0]?.grupo_ref || "", comp = rt[0]?.grupo_comp || "";
    const series = [{ nome: maiuscula(ref), cor: "var(--s1)" }, { nome: maiuscula(comp), cor: "var(--s2)" }];
    $("des-titulo").textContent = `${c.desfecho === "Usuários dos CAPS" ? "Usuários dos CAPS" : "Internações psiquiátricas"}: efeito por ${c.dimensao.startsWith("sexo") ? "sexo" : "raça/cor"}`;
    legenda($("des-legenda"), series.map((s) => ({ tipo: "ponto", cor: s.cor, rotulo: s.nome })));
    const linhas = PERIODOS.map(([k, n, mm]) => {
      const r = rt.find((q) => q.periodo === k);
      return { rotulo: n, sub: mm, r, valores: r ? [{ rr: r.rt_ref, inf: r.rt_ref_inf, sup: r.rt_ref_sup }, { rr: r.rt_comp, inf: r.rt_comp_inf, sup: r.rt_comp_sup }] : [null, null] };
    });
    graficoFloresta($("des-grafico"), linhas, { aria: "Razão de taxas por grupo e período", series });
    definirTabela("des-grafico", [{ rot: "Período", txt: true }, { rot: `RT ${ref}` }, { rot: "IC95%" }, { rot: `RT ${comp}` }, { rot: "IC95%" }, { rot: "Razão entre RT" }, { rot: "IC95%" }, { rot: "p" }],
      linhas.filter((l) => l.r).map((l) => [`${l.rotulo} (${l.sub})`, f3(l.r.rt_ref), `${f3(l.r.rt_ref_inf)}–${f3(l.r.rt_ref_sup)}`, f3(l.r.rt_comp), `${f3(l.r.rt_comp_inf)}–${f3(l.r.rt_comp_sup)}`, f2(l.r.razao_rt), `${f2(l.r.razao_inf)}–${f2(l.r.razao_sup)}`, fP(l.r.p_diferenca)]));
    $("des-nota").textContent = `Razão entre as RT (${comp} ÷ ${ref}): ` + linhas.filter((l) => l.r).map((l) => `${l.rotulo.toLowerCase()} ${f2(l.r.razao_rt)} (${fIC(l.r.razao_inf, l.r.razao_sup)}; ${fP(l.r.p_diferenca)})`).join("; ") + ". Valores perto de 1 indicam o mesmo efeito nos dois grupos.";
    const sexo = c.dimensao === "sexo";
    const campo = (c.desfecho === "Usuários dos CAPS" ? "caps_" : "f_") + (sexo ? "fem" : "negra");
    const quem = c.desfecho === "Usuários dos CAPS" ? "usuários dos CAPS" : "internações psiquiátricas";
    $("des-titulo-barras").textContent = sexo ? `Mulheres entre os ${quem}` : `Pessoas pretas ou pardas entre os ${quem}`;
    const barras = D.desigualdades.descritivo.map((d) => ({ rotulo: `${ROT_CAT[d.cat]} atingida`, valor: d[campo] }));
    graficoColunas($("des-barras"), barras, { aria: $("des-titulo-barras").textContent, cor: "var(--s1)", rotuloValor: sexo ? "mulheres" : "pretos ou pardos" });
    definirTabela("des-barras", [{ rot: "Categoria", txt: true }, { rot: "%" }], barras.map((b) => [b.rotulo, f1(b.valor)]));
  }

  // ------------------------------------------------------------------ navegação
  const ABAS = { visao: renderVisao, contrafactual: renderCf, dose: renderDr, municipios: renderMun, desigualdades: renderDes, sobre: () => {} };
  function renderizar() {
    esconderTip();
    try { ABAS[E.aba](); } catch (erro) { console.error(erro); }
  }
  function mudarAba() {
    const h = location.hash.replace("#", "");
    E.aba = ABAS[h] ? h : "visao";
    document.querySelectorAll("nav.abas button").forEach((b) => {
      const ativo = b.dataset.aba === E.aba;
      b.setAttribute("aria-selected", String(ativo));
      b.tabIndex = ativo ? 0 : -1;
    });
    document.querySelectorAll("main > section").forEach((s) => { s.hidden = s.id !== E.aba; });
    renderizar();
  }
  const botoesAba = [...document.querySelectorAll("nav.abas button")];
  botoesAba.forEach((b, i) => {
    b.addEventListener("click", () => { location.hash = b.dataset.aba; });
    b.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      const j = (i + (ev.key === "ArrowRight" ? 1 : botoesAba.length - 1)) % botoesAba.length;
      botoesAba[j].focus(); botoesAba[j].click();
    });
  });
  window.addEventListener("hashchange", mudarAba);

  $("cf-desfecho").addEventListener("change", (ev) => { E.cf.desfecho = ev.target.value; renderizar(); });
  $("cf-modelo").addEventListener("change", (ev) => { E.cf.modelo = ev.target.value; renderizar(); });
  $("dr-desfecho").addEventListener("change", (ev) => { E.dr.desfecho = ev.target.value; renderizar(); });
  $("dr-espec").addEventListener("change", (ev) => { E.dr.espec = ev.target.value; renderizar(); });
  $("mun-sel").addEventListener("change", (ev) => { E.mun.cod = ev.target.value; renderizar(); });
  $("mun-desfecho").addEventListener("change", (ev) => { E.mun.desfecho = ev.target.value; renderizar(); });
  $("mun-suavizar").addEventListener("change", (ev) => { E.mun.suavizar = ev.target.checked; renderizar(); });
  $("mun-busca").addEventListener("input", (ev) => { E.mun.busca = ev.target.value; if (SERIES_MUN) tabelaMunicipios(); });
  $("des-dimensao").addEventListener("change", (ev) => { E.des.dimensao = ev.target.value; renderizar(); });

  // tema: segue o sistema; o botão fixa claro ou escuro (lembrado neste navegador, se possível)
  const raiz = document.documentElement;
  const escuroAgora = () => raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const rotularTema = () => { $("tema").textContent = escuroAgora() ? "Tema claro" : "Tema escuro"; };
  try { const t = localStorage.getItem("painel-tema"); if (t === "dark" || t === "light") raiz.dataset.theme = t; } catch (e) { /* sem armazenamento */ }
  rotularTema();
  $("tema").addEventListener("click", () => {
    raiz.dataset.theme = escuroAgora() ? "light" : "dark";
    try { localStorage.setItem("painel-tema", raiz.dataset.theme); } catch (e) { /* sem armazenamento */ }
    rotularTema();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rotularTema);

  let espera;
  let larguraAnterior = document.querySelector("main").clientWidth;
  new ResizeObserver(() => {
    const w = document.querySelector("main").clientWidth;
    if (w === larguraAnterior) return;
    larguraAnterior = w;
    clearTimeout(espera);
    espera = setTimeout(renderizar, 150);
  }).observe(document.querySelector("main"));

  // ------------------------------------------------------------------ carga
  const json = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: ${r.status}`); return r.json(); });
  Promise.all([json("dados/painel.json"), json("dados/municipios.geojson")]).then(([dados, geo]) => {
    D = dados; GEO = geo;
    DATAS = D.meses.map(dataDe);
    D.municipios.forEach((m) => { MUN.set(m.cod, m); MUN7.set(m.cod7, m); });
    promessaSeries = json("dados/series_municipio.json").then((s) => { SERIES_MUN = s; });
    $("carregando").remove();
    $("sobre-gerado").textContent = `Painel gerado em ${D.gerado.split("-").reverse().join("/")} a partir dos arquivos de resultados.`;
    mudarAba();
  }).catch((erro) => {
    console.error(erro);
    $("carregando").textContent = "Não foi possível carregar os dados. Abra o painel por um endereço web (GitHub Pages) ou por um servidor local: python -m http.server, na pasta do painel.";
  });
})();
