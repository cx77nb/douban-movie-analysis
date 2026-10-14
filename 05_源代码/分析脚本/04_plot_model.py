# -*- coding: utf-8 -*-
"""
第 3 步（配图）：把建模结果画成 6 张图，供报告引用

产出在 analysis\\model_output\\ 下：
  fig1_boundary.png    不同"好评分界线"上的 AUC / 准确率对比  ← 报告核心图
  fig2_confusion.png   主任务与三分类的混淆矩阵
  fig3_features.png    最有判别力的字组（好评侧 / 差评侧）
  fig4_length.png      文本长度与星级的关系（为什么长短评更好打分）
  fig5_genre.png       类型两两对比准确率
  fig6_roc.png         主任务 ROC 曲线

中文字体用样板项目里的 simhei.ttf（D:\\App\\study_data\\_repos\\...）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "model_output")
SAMPLE = r"D:\App\study_data\_repos\TOP250movie_douban-master\simhei.ttf"

# ---- 中文字体：找不到 simhei 就退回系统里任何一个中文字体 ----
if os.path.exists(SAMPLE):
    font_manager.fontManager.addfont(SAMPLE)
    plt.rcParams["font.sans-serif"] = ["SimHei"]
else:
    for name in ("Microsoft YaHei", "SimHei", "SimSun"):
        try:
            plt.rcParams["font.sans-serif"] = [name]
            break
        except Exception:
            continue
plt.rcParams["axes.unicode_minus"] = False   # SimHei 没有 U+2212 负号字形，用 '-' 代替

# 大屏同款配色，报告和网站看着是一套
CYAN, PINK, GOLD, GRAY = "#22d3ee", "#f472b6", "#fbbf24", "#64748b"
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#f8fafc",
    "axes.edgecolor": "#cbd5e1",
    "axes.grid": True,
    "grid.color": "#e2e8f0",
    "grid.linewidth": 0.8,
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
})


def load_json(name):
    with io.open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  已出图 {name}")


# ---------------------------------------------------------------- 图 1
def fig_boundary(m):
    cases = m["tasks"]["diag"]["cases"]
    labels = [c["case"] for c in cases]
    auc = [c["auc"] for c in cases]
    acc = [c["accuracy"] for c in cases]
    base = [c["baseline"] for c in cases]
    lift = [c["lift_over_base"] for c in cases]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.6))

    y = range(len(labels))
    ax1.barh([i + 0.2 for i in y], auc, height=0.38, color=CYAN, label="AUC（排序能力）")
    ax1.barh([i - 0.2 for i in y], acc, height=0.38, color=GOLD,
             label="准确率 accuracy")
    ax1.axvline(0.5, color=GRAY, ls="--", lw=1.2)
    ax1.text(0.505, len(labels) - 0.5, "0.5 = 瞎猜", color=GRAY, fontsize=9)
    ax1.set_yticks(list(y))
    ax1.set_yticklabels(labels, fontsize=10)
    ax1.set_xlim(0.4, 1.0)
    ax1.invert_yaxis()
    ax1.set_title("换个分界线，文本的预测力就不一样")
    ax1.legend(loc="lower right", fontsize=10)

    colors = [PINK if v > 0 else GRAY for v in lift]
    ax2.barh(list(y), lift, color=colors)
    ax2.axvline(0, color="#334155", lw=1.2)
    ax2.set_yticks(list(y))
    ax2.set_yticklabels(["" for _ in y])
    ax2.set_xlabel("准确率 - 多数类基线")
    ax2.set_title("只有「5星 vs ≤4星」这条线跑赢基线")

    save(fig, "fig1_boundary.png")


# ---------------------------------------------------------------- 图 2
def fig_confusion(m):
    from sklearn.metrics import confusion_matrix  # noqa: F401  (仅示意，数据已在 json 里)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2))

    top = m["tasks"]["top"]
    cm = top["confusion_matrix"]
    names = ["≤4星", "5星（力荐）"]
    _heat(axes[0], cm, names, "主任务：5星 vs ≤4星")

    three = m["tasks"]["three"]
    cm2 = three["confusion_matrix"]
    _heat(axes[1], cm2, three["labels"], "副任务：三分类")
    save(fig, "fig2_confusion.png")


def _heat(ax, cm, names, title):
    import numpy as np
    a = np.array(cm, dtype=float)
    row = a / a.sum(axis=1, keepdims=True)          # 按行归一化，看召回
    im = ax.imshow(row, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=10)
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlabel("模型预测")
    ax.set_ylabel("真实标签")
    ax.set_title(title)
    ax.grid(False)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{int(a[i, j])}\n{row[i, j] * 100:.0f}%",
                    ha="center", va="center", fontsize=10,
                    color="white" if row[i, j] > 0.55 else "#0f172a")
    fig = ax.figure
    fig.colorbar(im, ax=ax, fraction=0.045, label="行内占比（召回率）")


# ---------------------------------------------------------------- 图 3
def fig_features():
    rows = list(csv.DictReader(io.open(os.path.join(OUT, "features_top.csv"),
                                       encoding="utf-8-sig")))
    pos = [(r["特征"], float(r["权重"])) for r in rows
           if r["方向"] == "top_positive"][:18]
    neg = [(r["特征"], float(r["权重"])) for r in rows
           if r["方向"] == "top_negative"][:18]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 7))

    def clean(t):
        return t.replace("w__", "").replace("c__", "")

    p = pos[::-1]
    ax1.barh([clean(t) for t, _ in p], [w for _, w in p], color=CYAN)
    ax1.set_title("最像「5 星」的 18 个特征")
    ax1.set_xlabel("逻辑回归权重")
    ax1.tick_params(axis="y", labelsize=11)

    q = neg[::-1]
    ax2.barh([clean(t) for t, _ in q], [w for _, w in q], color=PINK)
    ax2.set_title("最像「≤4 星」的 18 个特征")
    ax2.set_xlabel("逻辑回归权重")
    ax2.tick_params(axis="y", labelsize=11)

    save(fig, "fig3_features.png")


# ---------------------------------------------------------------- 图 4
def fig_length(m):
    data = m["_length_data"]
    stars = sorted(data)
    stays = [data[str(s)]["median"] for s in stars]
    means = [data[str(s)]["mean"] for s in stars]
    ns = [data[str(s)]["n"] for s in stars]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    x = range(len(stars))
    ax.bar(x, means, color=CYAN, alpha=0.85, label="平均字数")
    ax.plot(x, stays, "o-", color=PINK, lw=2.5, ms=9, label="中位字数")
    for i, (n, mu) in enumerate(zip(ns, means)):
        ax.text(i, mu + 2, f"n={n}", ha="center", fontsize=9, color="#334155")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{s} 星" for s in stars])
    ax.set_ylabel("短评字数")
    ax.set_title("星级越低，写得越长（差评更愿意展开说）")
    ax.legend()
    save(fig, "fig4_length.png")


# ---------------------------------------------------------------- 图 5
def fig_genre(m):
    items = m["tasks"]["genre"]["pairwise"]
    labels = [f"{i['a']} vs {i['b']}" for i in items]
    acc = [i["accuracy"] for i in items]
    auc = [i["auc"] for i in items]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    y = range(len(labels))
    ax.barh([i + 0.2 for i in y], acc, height=0.38, color=CYAN, label="准确率")
    ax.barh([i - 0.2 for i in y], auc, height=0.38, color=GOLD, label="AUC")
    ax.axvline(0.5, color=PINK, ls="--", lw=1.8)
    ax.text(0.505, len(labels) - 0.4, "0.5 = 瞎猜", color=PINK, fontsize=10)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0.4, 0.95)
    ax.set_title("文本判别「题材」明显强于判别「态度」")
    ax.legend(loc="lower right")
    save(fig, "fig5_genre.png")


# ---------------------------------------------------------------- 图 6
def fig_roc(m):
    d = m["_roc"]
    fig, ax = plt.subplots(figsize=(6.4, 6))
    ax.plot(d["fpr"], d["tpr"], color=CYAN, lw=2.5,
            label=f"字(2,3)+逻辑回归  AUC={d['auc']:.3f}")
    ax.plot([0, 1], [0, 1], "--", color=GRAY, lw=1.5, label="随机猜 AUC=0.5")
    ax.set_xlabel("假正率 FPR")
    ax.set_ylabel("真正率 TPR")
    ax.set_title("主任务 ROC：比随机好，但离好用还很远")
    ax.legend(loc="lower right")
    save(fig, "fig6_roc.png")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    m = load_json("metrics.json")
    # 把两张图需要的原始数据也从 csv 现算一遍（保持脚本自洽）
    m["_length_data"] = length_stats()
    m["_roc"] = roc_points()
    print("开始出图 ...")
    fig_boundary(m)
    fig_confusion(m)
    fig_features()
    fig_length(m)
    fig_genre(m)
    fig_roc(m)
    print("全部完成")


def length_stats():
    import statistics
    p = os.path.join(HERE, "analysis_comments.csv")
    rows = list(csv.DictReader(io.open(p, encoding="utf-8-sig", newline="")))
    by = {}
    for r in rows:
        s = (r.get("rating") or "").strip()
        if not s or s in ("0", "0.0"):
            continue
        t = (r.get("content") or "").strip()
        if len(t) < 2:
            continue
        by.setdefault(int(float(s)), []).append(len(t))
    return {str(s): {"n": len(v), "mean": round(sum(v) / len(v), 1),
                     "median": statistics.median(v)}
            for s, v in sorted(by.items())}


def roc_points():
    """重算一次主任务的 ROC 曲线点（只为了画图）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m3", os.path.join(HERE, "03_train_model.py"))
    m3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m3)
    from sklearn.metrics import roc_curve, roc_auc_score
    rows = m3.load_comments()
    y = [1 if r["star"] == 5 else 0 for r in rows]
    pairs = [(r["text"], " ".join(m3.cut(r["text"]))) for r in rows]
    _, score = m3._fit_eval(pairs, y)
    fpr, tpr, _ = roc_curve(y, score)
    idx = list(range(0, len(fpr), max(1, len(fpr) // 300)))
    return {"fpr": [float(fpr[i]) for i in idx],
            "tpr": [float(tpr[i]) for i in idx],
            "auc": float(roc_auc_score(y, score))}


if __name__ == "__main__":
    main()
