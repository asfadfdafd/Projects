# -*- coding: utf-8 -*-
"""
Обучение модели вероятности удовлетворения иска.

Обучаются две модели:
  1) Логистическая регрессия с L2 (IRLS) — ОСНОВНАЯ модель демо.
  2) Градиентный бустинг на деревьях — контрольная модель для сравнения.

Почему основная — логистическая регрессия. Требование объяснимости здесь
не «желательное», а профильное: система работает в судебной сфере, где
непрозрачный вывод неприемлем. У логистической регрессии вклад каждого
признака в итоговую вероятность считается ТОЧНО (coef * value), а не
аппроксимируется, как SHAP для ансамблей. Бустинг обучается, чтобы
честно показать разницу в качестве: если она мала, выбор в пользу
объяснимой модели обоснован; метрики обеих моделей сохраняются в
models/metrics.json.

Модель выгружается в models/model.json (обычный JSON), поэтому рантайму
не нужны ни numpy, ни scikit-learn.

Запуск:  python3 scripts/train_model.py
"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.features import build_feature_vector, humanize  # noqa: E402
from core.schema import TARGET  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "cases.csv")
MODEL_DIR = os.path.join(ROOT, "models")
SEED = 7
TEST_SHARE = 0.2
RIDGE = 1.0

NUMERIC_CSV = {"claim_amount_kzt", "months_since_breach", "witness_count",
               "evidence_count", "doc_completeness", "outcome_win",
               "satisfied_share", "true_probability"}


# ---------------------------------------------------------------------------
# Данные
# ---------------------------------------------------------------------------
def load_dataset(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            case = {}
            for k, v in row.items():
                if k in NUMERIC_CSV:
                    case[k] = float(v)
                elif v in ("0", "1"):
                    case[k] = int(v)
                else:
                    case[k] = v
            rows.append(case)
    return rows


def build_matrix(rows):
    names, _ = build_feature_vector(rows[0])
    X = np.array([build_feature_vector(r)[1] for r in rows], dtype=float)
    y = np.array([r[TARGET] for r in rows], dtype=float)
    p_true = np.array([r["true_probability"] for r in rows], dtype=float)
    return names, X, y, p_true


# ---------------------------------------------------------------------------
# Логистическая регрессия (IRLS с гребневой регуляризацией)
# ---------------------------------------------------------------------------
def sigmoid(z):
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35))),
                    np.exp(np.clip(z, -35, 35)) / (1.0 + np.exp(np.clip(z, -35, 35))))


def fit_logistic(X, y, ridge=RIDGE, iters=60, tol=1e-8):
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    penalty = np.eye(d + 1) * ridge
    penalty[0, 0] = 0.0                      # свободный член не штрафуем
    for _ in range(iters):
        p = sigmoid(Xb @ w)
        s = np.clip(p * (1 - p), 1e-8, None)
        grad = Xb.T @ (y - p) - penalty @ w
        hess = -(Xb.T * s) @ Xb - penalty
        try:
            step = np.linalg.solve(hess, -grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hess, -grad, rcond=None)[0]
        w_new = w + step
        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            break
        w = w_new
    return w[0], w[1:]


# ---------------------------------------------------------------------------
# Вторая модель: какая доля требований будет удовлетворена
# ---------------------------------------------------------------------------
# «Выиграете или нет» — не тот вопрос, который на самом деле волнует истца.
# Ему важно, сколько он получит. Поэтому на выигранных делах отдельно
# обучается гребневая регрессия доли удовлетворённых требований, и
# ожидаемое взыскание считается как
#     P(иск удовлетворён) × E[доля | удовлетворён] × сумма требований.
# Обучение только на выигранных делах — не упрощение: у проигранных дел
# доля тождественно равна нулю, и их включение смешало бы два разных
# вопроса в одной модели.
def fit_ridge(X, y, ridge=5.0):
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    penalty = np.eye(d + 1) * ridge
    penalty[0, 0] = 0.0
    w = np.linalg.solve(Xb.T @ Xb + penalty, Xb.T @ y)
    return w[0], w[1:]


def evaluate_share(y, pred):
    resid = y - pred
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(len(y)),
        "mae": round(float(np.mean(np.abs(resid))), 4),
        "rmse": round(float(np.sqrt(np.mean(resid ** 2))), 4),
        "r2": round(1 - ss_res / ss_tot if ss_tot else 0.0, 4),
        "baseline_mae_if_always_mean": round(
            float(np.mean(np.abs(y - y.mean()))), 4),
    }


# ---------------------------------------------------------------------------
# Градиентный бустинг на деревьях (контрольная модель)
# ---------------------------------------------------------------------------
def _bin_matrix(X, n_bins=32):
    edges, Xb = [], np.zeros(X.shape, dtype=np.int16)
    for j in range(X.shape[1]):
        qs = np.unique(np.quantile(X[:, j], np.linspace(0, 1, n_bins + 1)[1:-1]))
        edges.append(qs)
        Xb[:, j] = np.searchsorted(qs, X[:, j], side="left")
    return Xb, edges


class _Node(object):
    __slots__ = ("feature", "threshold_bin", "left", "right", "value")

    def __init__(self):
        self.feature = None
        self.threshold_bin = None
        self.left = None
        self.right = None
        self.value = 0.0


def _grow(Xb, g, h, idx, depth, max_depth, min_samples, lam, n_bins):
    node = _Node()
    G, H = g[idx].sum(), h[idx].sum()
    node.value = -G / (H + lam)
    if depth >= max_depth or len(idx) < 2 * min_samples:
        return node

    parent_gain = G * G / (H + lam)
    best = (0.0, None, None)
    for j in range(Xb.shape[1]):
        bins = Xb[idx, j]
        gs = np.bincount(bins, weights=g[idx], minlength=n_bins)
        hs = np.bincount(bins, weights=h[idx], minlength=n_bins)
        cnt = np.bincount(bins, minlength=n_bins)
        cg, ch, cc = np.cumsum(gs), np.cumsum(hs), np.cumsum(cnt)
        valid = (cc >= min_samples) & ((len(idx) - cc) >= min_samples)
        if not valid.any():
            continue
        gain = (cg ** 2 / (ch + lam)
                + (G - cg) ** 2 / (H - ch + lam) - parent_gain)
        gain = np.where(valid, gain, -np.inf)
        b = int(np.argmax(gain))
        if gain[b] > best[0]:
            best = (float(gain[b]), j, b)

    if best[1] is None or best[0] <= 1e-6:
        return node

    _, j, b = best
    mask = Xb[idx, j] <= b
    node.feature, node.threshold_bin = j, b
    node.left = _grow(Xb, g, h, idx[mask], depth + 1, max_depth, min_samples, lam, n_bins)
    node.right = _grow(Xb, g, h, idx[~mask], depth + 1, max_depth, min_samples, lam, n_bins)
    return node


def _predict_tree(node, Xb):
    out = np.zeros(Xb.shape[0])
    stack = [(node, np.arange(Xb.shape[0]))]
    while stack:
        nd, idx = stack.pop()
        if nd.feature is None or len(idx) == 0:
            out[idx] = nd.value
            continue
        mask = Xb[idx, nd.feature] <= nd.threshold_bin
        stack.append((nd.left, idx[mask]))
        stack.append((nd.right, idx[~mask]))
    return out


def fit_gbdt(X, y, n_rounds=250, lr=0.06, max_depth=3, min_samples=25, lam=1.0):
    n_bins = 32
    Xb, edges = _bin_matrix(X, n_bins)
    base = np.log(max(y.mean(), 1e-6) / max(1 - y.mean(), 1e-6))
    f = np.full(len(y), base)
    trees = []
    for _ in range(n_rounds):
        p = sigmoid(f)
        g, h = p - y, np.clip(p * (1 - p), 1e-6, None)
        tree = _grow(Xb, g, h, np.arange(len(y)), 0, max_depth, min_samples, lam, n_bins)
        f += lr * _predict_tree(tree, Xb)
        trees.append(tree)
    return dict(base=base, trees=trees, lr=lr, edges=edges, n_bins=n_bins)


def predict_gbdt(model, X):
    Xb = np.zeros(X.shape, dtype=np.int16)
    for j, qs in enumerate(model["edges"]):
        Xb[:, j] = np.searchsorted(qs, X[:, j], side="left")
    f = np.full(X.shape[0], model["base"])
    for tree in model["trees"]:
        f += model["lr"] * _predict_tree(tree, Xb)
    return sigmoid(f)


# ---------------------------------------------------------------------------
# Метрики
# ---------------------------------------------------------------------------
def roc_auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p), dtype=float)
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    pos, neg = y.sum(), len(y) - y.sum()
    if pos == 0 or neg == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2.0) / (pos * neg))


def calibration_table(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if m.sum() == 0:
            continue
        out.append({
            "bin": "%.0f–%.0f%%" % (lo * 100, hi * 100),
            "n": int(m.sum()),
            "predicted": round(float(p[m].mean()), 4),
            "actual": round(float(y[m].mean()), 4),
        })
    return out


def evaluate(y, p, name):
    pred = (p >= 0.5).astype(float)
    tp = float(((pred == 1) & (y == 1)).sum())
    fp = float(((pred == 1) & (y == 0)).sum())
    fn = float(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    eps = 1e-12
    return {
        "model": name,
        "roc_auc": round(roc_auc(y, p), 4),
        "accuracy": round(float((pred == y).mean()), 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "brier_score": round(float(np.mean((p - y) ** 2)), 4),
        "log_loss": round(float(-np.mean(y * np.log(p + eps)
                                         + (1 - y) * np.log(1 - p + eps))), 4),
        "expected_calibration_error": round(float(np.mean([
            abs(b["predicted"] - b["actual"]) * b["n"]
            for b in calibration_table(y, p)]) / max(len(y), 1) * 10), 4),
    }


def permutation_importance(X, y, predict_fn, names, rng, repeats=3):
    base = roc_auc(y, predict_fn(X))
    result = []
    for j in range(X.shape[1]):
        drops = []
        for _ in range(repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            drops.append(base - roc_auc(y, predict_fn(Xp)))
        result.append({"feature": names[j], "label": humanize(names[j]),
                       "auc_drop": round(float(np.mean(drops)), 4)})
    result.sort(key=lambda r: -r["auc_drop"])
    return result


# ---------------------------------------------------------------------------
def main():
    rows = load_dataset(DATA)
    names, X, y, p_true = build_matrix(rows)
    share = np.array([r["satisfied_share"] for r in rows], dtype=float)

    rng = np.random.default_rng(SEED)
    idx = rng.permutation(len(y))
    n_test = int(len(y) * TEST_SHARE)
    test_idx, train_idx = idx[:n_test], idx[n_test:]
    Xtr, ytr = X[train_idx], y[train_idx]
    Xte, yte = X[test_idx], y[test_idx]

    # стандартизация по обучающей выборке
    mean = Xtr.mean(axis=0)
    std = Xtr.std(axis=0)
    std[std < 1e-9] = 1.0
    Ztr, Zte = (Xtr - mean) / std, (Xte - mean) / std

    # --- логистическая регрессия ------------------------------------------
    intercept, coef = fit_logistic(Ztr, ytr)
    p_lr_te = sigmoid(Zte @ coef + intercept)
    p_lr_tr = sigmoid(Ztr @ coef + intercept)

    # --- доля удовлетворённых требований (только по выигранным делам) ------
    won_tr = ytr > 0.5
    won_te = yte > 0.5
    share_intercept, share_coef = fit_ridge(Ztr[won_tr], share[train_idx][won_tr])
    share_pred_te = np.clip(Zte[won_te] @ share_coef + share_intercept, 0.15, 1.0)
    share_metrics = evaluate_share(share[test_idx][won_te], share_pred_te)

    # --- градиентный бустинг ----------------------------------------------
    gbdt = fit_gbdt(Xtr, ytr)
    p_gb_te = predict_gbdt(gbdt, Xte)

    metrics = {
        "dataset": {"n_total": len(y), "n_train": len(ytr), "n_test": len(yte),
                    "win_rate": round(float(y.mean()), 4)},
        "test": [evaluate(yte, p_lr_te, "logistic_regression"),
                 evaluate(yte, p_gb_te, "gradient_boosting")],
        "share_model_test": share_metrics,
        "train": [evaluate(ytr, p_lr_tr, "logistic_regression (train)")],
        "calibration_logistic_test": calibration_table(yte, p_lr_te),
        # Проверка, что модель восстановила заложенную причинную структуру:
        # сравнение с «истинной» вероятностью генератора (в обучении не участвует).
        "recovery_check": {
            "corr_pred_vs_true_probability": round(
                float(np.corrcoef(p_lr_te, p_true[test_idx])[0, 1]), 4),
            "mean_abs_error_vs_true_probability": round(
                float(np.mean(np.abs(p_lr_te - p_true[test_idx]))), 4),
        },
    }

    # Ширина диапазона неопределённости, которую честно показывать пользователю:
    # среднеквадратичное отклонение факта от прогноза внутри калибровочных корзин.
    cal = metrics["calibration_logistic_test"]
    band = float(np.sqrt(np.average(
        [(b["predicted"] - b["actual"]) ** 2 for b in cal],
        weights=[b["n"] for b in cal])))
    metrics["uncertainty_band_pp"] = round(band * 100, 1)

    metrics["permutation_importance_top15"] = permutation_importance(
        Xte, yte, lambda M: sigmoid(((M - mean) / std) @ coef + intercept),
        names, np.random.default_rng(SEED))[:15]

    os.makedirs(MODEL_DIR, exist_ok=True)
    model = {
        "model_type": "logistic_regression_l2",
        "model_version": "demo-1.0.0",
        "trained_on": os.path.basename(DATA),
        "n_train": int(len(ytr)),
        "target": TARGET,
        "feature_names": names,
        "mean": [float(v) for v in mean],
        "std": [float(v) for v in std],
        "coef": [float(v) for v in coef],
        "intercept": float(intercept),
        "metrics_summary": metrics["test"][0],
        "uncertainty_band_pp": metrics["uncertainty_band_pp"],
        "share_model": {
            "intercept": float(share_intercept),
            "coef": [float(v) for v in share_coef],
            "clip": [0.15, 1.0],
            "trained_on": "выигранные дела обучающей выборки",
            "n_train": int(won_tr.sum()),
            "metrics": share_metrics,
        },
        "disclaimer": ("Модель обучена на синтетическом демонстрационном "
                       "датасете и не пригодна для практического применения."),
    }
    with open(os.path.join(MODEL_DIR, "model.json"), "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)

    lr_m, gb_m = metrics["test"][0], metrics["test"][1]
    print("Тестовая выборка: %d дел" % len(yte))
    print("  Логистическая регрессия: ROC-AUC %.3f | F1 %.3f | Brier %.3f"
          % (lr_m["roc_auc"], lr_m["f1"], lr_m["brier_score"]))
    print("  Градиентный бустинг:     ROC-AUC %.3f | F1 %.3f | Brier %.3f"
          % (gb_m["roc_auc"], gb_m["f1"], gb_m["brier_score"]))
    print("  Корреляция с истинной вероятностью: %.3f"
          % metrics["recovery_check"]["corr_pred_vs_true_probability"])
    print("  Доля удовлетворённых требований: MAE %.3f (базовый уровень %.3f), R² %.3f"
          % (share_metrics["mae"], share_metrics["baseline_mae_if_always_mean"],
             share_metrics["r2"]))
    print("\nТоп факторов (падение ROC-AUC при перемешивании признака):")
    for r in metrics["permutation_importance_top15"][:8]:
        print("  %-52s %.4f" % (r["label"][:52], r["auc_drop"]))
    print("\nСохранено: models/model.json, models/metrics.json")


if __name__ == "__main__":
    main()
