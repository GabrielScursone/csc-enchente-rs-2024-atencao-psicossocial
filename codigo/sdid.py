"""Synthetic difference-in-differences (Arkhangelsky et al., 2021, AER 111(12):4088-4118).

Tradução direta da implementação de referência em R (pacote synthdid: sc.weight.fw,
fw.step, sparsify_function, synthdid_estimate e jackknife_se), sem covariáveis.
Y: matriz N × T com as N0 primeiras linhas de controles e as T0 primeiras colunas pré.
"""
from __future__ import annotations

import numpy as np


def _fw_step(A, x, b, eta):
    Ax = A @ x
    half_grad = (Ax - b) @ A + eta * x
    i = int(np.argmin(half_grad))
    dx = -x.copy()
    dx[i] = 1 - x[i]
    if np.all(dx == 0):
        return x
    derr = A[:, i] - Ax
    step = -(half_grad @ dx) / (derr @ derr + eta * (dx @ dx))
    return x + min(1.0, max(0.0, step)) * dx


def _sc_weight_fw(Y, zeta, intercept=True, lam=None, min_decrease=1e-3, max_iter=1000):
    """Ajusta Y[:, -1] ≈ Y[:, :-1] @ lam, lam no simplex, com penalidade ridge zeta²."""
    N0, T0 = Y.shape[0], Y.shape[1] - 1
    lam = np.full(T0, 1 / T0) if lam is None else lam.copy()
    if intercept:
        Y = Y - Y.mean(axis=0)
    A, b = Y[:, :T0], Y[:, T0]
    eta = N0 * zeta ** 2
    vals = []
    t = 0
    while t < max_iter and (t < 2 or vals[-2] - vals[-1] > min_decrease ** 2):
        lam = _fw_step(A, lam, b, eta)
        err = Y @ np.append(lam, -1)
        vals.append(zeta ** 2 * (lam @ lam) + (err @ err) / N0)
        t += 1
    return lam


def _esparsificar(w):
    w = np.where(w <= w.max() / 4, 0.0, w)
    return w / w.sum()


def _pesos(Y, N0, T0, eta_lambda=1e-6, max_iter=10000):
    N, T = Y.shape
    N1, T1 = N - N0, T - T0
    noise = np.std(np.diff(Y[:N0, :T0], axis=1), ddof=1)
    zeta_omega = ((N1 * T1) ** 0.25) * noise
    zeta_lambda = eta_lambda * noise
    min_dec = 1e-5 * noise
    Yc = np.vstack([np.column_stack([Y[:N0, :T0], Y[:N0, T0:].mean(axis=1)]),
                    np.append(Y[N0:, :T0].mean(axis=0), Y[N0:, T0:].mean())])
    lam = _sc_weight_fw(Yc[:N0, :], zeta_lambda, True, None, min_dec, 100)
    lam = _sc_weight_fw(Yc[:N0, :], zeta_lambda, True, _esparsificar(lam), min_dec, max_iter)
    om = _sc_weight_fw(Yc[:, :T0].T, zeta_omega, True, None, min_dec, 100)
    om = _sc_weight_fw(Yc[:, :T0].T, zeta_omega, True, _esparsificar(om), min_dec, max_iter)
    return om, lam


def estimar(Y: np.ndarray, N0: int, T0: int) -> dict:
    """Efeito médio nos tratados (ATT), pesos, erro-padrão jackknife e contrafactual dos tratados."""
    N, T = Y.shape
    N1, T1 = N - N0, T - T0
    om, lam = _pesos(Y, N0, T0)
    w_unid = np.append(-om, np.full(N1, 1 / N1))
    w_tempo = np.append(-lam, np.full(T1, 1 / T1))
    tau = float(w_unid @ Y @ w_tempo)
    # Jackknife com pesos fixos (synthdid::jackknife_se): retira uma unidade e renormaliza ω.
    est = []
    for i in range(N):
        manter = np.ones(N, bool)
        manter[i] = False
        n0 = N0 - (i < N0)
        n1 = N1 - (i >= N0)
        if n0 == 0 or n1 == 0:
            continue
        o = om[manter[:N0]]
        o = o / o.sum() if o.sum() > 0 else np.full(n0, 1 / n0)  # sum_normalize do synthdid
        wu = np.append(-o, np.full(n1, 1 / n1))
        est.append(float(wu @ Y[manter] @ w_tempo))
    est = np.asarray(est)
    n = len(est)
    ep = float(np.sqrt((n - 1) / n * ((est - est.mean()) ** 2).sum()))
    trat_post = Y[N0:, T0:].mean()
    return {"att": tau, "ep": ep, "omega": om, "lambda": lam,
            "media_tratados_pos": trat_post, "contrafactual_tratados_pos": trat_post - tau}
