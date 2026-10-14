# -*- coding: utf-8 -*-
"""
第 3 步：建模 —— 用短评文本预测"这条短评是不是力荐（5 星）"

为什么要做这个：
  豆瓣短评是"文本 + 星级"成对出现的。星级是用户显式给出的态度，文本是隐式表达。
  如果文本能较准地预测星级，说明"评论用词和打分是一致的"；如果不行，说明
  用户嘴上说的和手上打的分是两回事（样板项目作者的反思"浅薄"就是指这个）。

  本脚本把这个"文本 → 态度"问题做成一个可测量的监督学习任务：
    主任务  二分类：5 星（力荐）  vs  ≤4 星（一般/还行/推荐）        —— 57.5% : 42.5%，接近平衡
    副任务  三分类：好评(4-5星) / 中评(3星) / 差评(1-2星)            —— 严重不平衡，看 macro-F1
    副任务  多标签：短评 → 电影类型（剧情/喜剧/动画/…）              —— 文本和题材的相关性

  注意：不用样板项目的"star>=3 算喜欢"标签 —— 在我们的数据里那是 98.4% : 1.6%，
  完全不可用（模型只要全猜"喜欢"就有 98.4% 准确率）。这是本项目相对样板项目
  最重要的一处方法学修正。

怎么跑：
  .venv\\Scripts\\python.exe analysis\\03_train_model.py            # 全部任务
  .venv\\Scripts\\python.exe analysis\\03_train_model.py --task top # 只跑主任务

产出：
  analysis\\model_output\\metrics.json         所有指标（给报告引用）
  analysis\\model_output\\cv_<task>.csv       交叉验证每折明细
  analysis\\model_output\\features_<task>.csv 判别力最强的特征词
  analysis\\model_output\\predictions.csv     全量预测结果（含错例，便于人工看）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
OUT = os.path.join(HERE, "model_output")
COMMENTS_CSV = os.path.join(HERE, "analysis_comments.csv")
MOVIES_CSV = os.path.join(HERE, "analysis_movies.csv")

# ---------------------------------------------------------------------------
# 停用词：中文短评里高频但几乎不含"态度"信息的词
#   像"电影""剧情"这种词在好评差评里都出现 → 没有判别力，去掉能显著提高精度
#   也可以读项目根目录的 stopwords.txt，这里用内置的精简表，避免依赖文件
# ---------------------------------------------------------------------------
STOPWORDS = set("""
的 了 是 我 你 他 她 它 们 这 那 就 都 也 还 又 很 太 更 最 好 不 没 有 在 和 与
一个 一部 一些 什么 怎么 这样 那样 因为 所以 但是 而且 然后 如果 虽然 可是
电影 片子 影片 这部 这个 那个 觉得 感觉 真的 就是 还是 可以 应该 一部电影
看完 看了 看过 没有 自己 我们 你们 他们 知道 时候 现在 已经 一直 有点 特别
非常 十分 比较 确实 实在 其实 只是 不过 于是 终于 整个 各种 好多 很多
""".split())

# 中文里能表达"强烈态度"的标点，先单独抽成特征再进文本
PUNCT_FEATURES = {
    "excl": "!",       # 感叹号密度
    "ques": "?",       # 问号密度
}


# ===========================================================================
# 一、读数据
# ===========================================================================
def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_comments():
    """读短评表，丢掉没有星级的、文本为空的，把 rating 转成 float。"""
    rows = read_csv(COMMENTS_CSV)
    keep = []
    for r in rows:
        star = (r.get("rating") or "").strip()
        text = (r.get("content") or "").strip()      # 用原始文本分词，不用 content_clean
        if not star or star in ("0", "0.0"):
            continue                                  # 没有星级的 81 条不要
        if len(text) < 2:
            continue                                  # 空文本/纯表情的不要
        r["star"] = int(float(star))
        r["text"] = text
        keep.append(r)
    return keep


def load_movie_genres():
    """movie_id -> 类型列表，用于副任务（短评 → 题材）。"""
    m = {}
    for r in read_csv(MOVIES_CSV):
        gs = [x.strip() for x in (r.get("genres") or "").split("/") if x.strip()]
        m[r["id"]] = gs
    return m


# ===========================================================================
# 二、分词与向量化
# ===========================================================================
try:
    import jieba
    jieba.setLogLevel(60)                             # 关掉 jieba 的加载日志
except Exception:                                     # pragma: no cover
    jieba = None

_word_re = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+")


def _cut_fallback(text):
    """没有 jieba 时的兜底：中文按二元字组切，英文按单词切。

    二元字组（bigram）是把"好看"切成"好看"，把"不好看"切成"不好/好看"，
    虽不如词典分词准，但对情感分类其实够用。
    """
    out = []
    for seg in _word_re.findall(text):
        if seg.isascii():
            out.append(seg.lower())
        else:
            if len(seg) == 1:
                out.append(seg)
            else:
                out.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return out


def cut(text):
    """把一条短评切成词列表，过滤停用词和单字。"""
    if jieba is not None:
        toks = [t.strip() for t in jieba.lcut(text)]
    else:
        toks = _cut_fallback(text)
    return [t for t in toks if t and t not in STOPWORDS and len(t) > 1]


def tokenize_all(texts):
    t0 = time.time()
    toks = [cut(t) for t in texts]
    print(f"    分词完成：{len(toks)} 条，耗时 {time.time() - t0:.1f}s，"
          f"平均 {sum(len(x) for x in toks) / max(1, len(toks)):.1f} 词/条")
    return [" ".join(x) for x in toks]


class ViewPick:
    """从 (原文, 分词文本) 这一对里挑出某一列，喂给后面的向量器。

    idx=0 → 原文（给字向量器 / char_wb）
    idx=1 → 分词结果（给词向量器 / token_pattern）

    有了它，evaluate() 可以统一把 (raw, tokenized) 成对的样本喂进来，
    具体每个模型吃哪一列由它自己声明 —— 不用在 eval 里分支判断。
    """

    def __init__(self, idx, inner):
        self.idx = idx
        self.inner = inner

    def fit(self, X, y=None):
        self.inner.fit(self._column(X), y)
        return self

    def transform(self, X):
        return self.inner.transform(self._column(X))

    def fit_transform(self, X, y=None):
        return self.inner.fit_transform(self._column(X), y)

    def get_feature_names_out(self, *a, **k):
        return self.inner.get_feature_names_out(*a, **k)

    def _column(self, X):
        return [row[self.idx] for row in X]


def build_vectorizers(mode):
    """返回 {名字: (向量器, 分类器)} 的候选组合，逐个交叉验证比一比。

    mode='word'  : 只用分词后的词袋 / TF-IDF
    mode='char'  : 只用人话原文字级 n-gram（2~3 字），不需要分词
    mode='both'  : 两者拼接
    """
    from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
    from sklearn.pipeline import FeatureUnion
    from sklearn.svm import LinearSVC
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import MultinomialNB

    word = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_df=0.9,
                           sublinear_tf=True, token_pattern=r"(?u)\S+")
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=3,
                           sublinear_tf=True)
    count = CountVectorizer(ngram_range=(1, 2), min_df=3, max_features=20000,
                            token_pattern=r"(?u)\S+")

    W = lambda: ViewPick(1, word)          # 词视图
    C = lambda: ViewPick(0, char)          # 字视图
    K = lambda: ViewPick(1, count)
    LR = lambda: LogisticRegression(max_iter=2000, class_weight="balanced")
    SVM = lambda: LinearSVC(C=1.0, class_weight="balanced")

    cands = {}
    if mode in ("word", "both"):
        cands["TFIDF词(1,2)+线性SVM"] = (W(), SVM())
        cands["TFIDF词(1,2)+逻辑回归"] = (W(), LR())
        cands["词频(1,2)+朴素贝叶斯"] = (K(), MultinomialNB())
    if mode in ("char", "both"):
        cands["TFIDF字(2,3)+线性SVM"] = (C(), SVM())
        cands["TFIDF字(2,3)+逻辑回归"] = (C(), LR())
    if mode == "both":
        # FeatureUnion 直接吃 (原文, 分词文本) 成对的样本，两个 ViewPick 各取一列
        union = FeatureUnion([("w", ViewPick(1, word)),
                              ("c", ViewPick(0, char))])
        cands["词+字拼接+线性SVM"] = (union, SVM())
        cands["词+字拼接+逻辑回归"] = (union, LR())
    return cands


# ===========================================================================
# 三、交叉验证
# ===========================================================================
def evaluate(name, X_text, y, vec, clf, cv=5):
    """做分层 K 折交叉验证，返回每折指标与整体汇总。"""
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                                 recall_score, confusion_matrix)
    from sklearn.pipeline import Pipeline

    pipe = Pipeline([("vec", vec), ("clf", clf)])
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)

    folds = []
    for i, (tr, te) in enumerate(skf.split(X_text, y), 1):
        pipe.fit([X_text[j] for j in tr], [y[j] for j in tr])
        pred = pipe.predict([X_text[j] for j in te])
        truth = [y[j] for j in te]
        folds.append({
            "fold": i,
            "n_test": len(te),
            "accuracy": round(accuracy_score(truth, pred), 6),
            "macro_f1": round(f1_score(truth, pred, average="macro"), 6),
            "weighted_f1": round(f1_score(truth, pred, average="weighted"), 6),
        })

    # 用 out-of-fold 预测做整体评估（每条样本都被"没见过它"的模型预测过一次）
    oof = cross_val_predict(pipe, X_text, y, cv=skf, n_jobs=1)
    labels = sorted(set(y))
    cm = confusion_matrix(y, oof, labels=labels).tolist()

    # AUC：二分类时算"打分"，衡量排序能力（不受 0.5 阈值影响，是更本质的指标）
    #   逻辑回归 / 朴素贝叶斯有 predict_proba；线性 SVM 只有 decision_function。
    auc = None
    if len(labels) == 2:
        try:
            from sklearn.metrics import roc_auc_score
            for method in ("predict_proba", "decision_function"):
                if not hasattr(pipe, method):
                    continue
                scores = cross_val_predict(pipe, X_text, y, cv=skf, method=method,
                                           n_jobs=1)
                if getattr(scores, "ndim", 1) == 2:
                    scores = scores[:, 1]
                auc = round(float(roc_auc_score(y, scores)), 6)
                break
        except Exception:
            auc = None

    # 全量重训一次，供后续看特征词与预测
    pipe.fit(X_text, y)

    macro = [f["macro_f1"] for f in folds]
    mean = sum(macro) / len(macro)
    std = (sum((x - mean) ** 2 for x in macro) / len(macro)) ** 0.5

    return {
        "name": name,
        "cv": cv,
        "accuracy": round(accuracy_score(y, oof), 6),
        "macro_f1": round(f1_score(y, oof, average="macro"), 6),
        "weighted_f1": round(f1_score(y, oof, average="weighted"), 6),
        "macro_precision": round(precision_score(y, oof, average="macro",
                                                 zero_division=0), 6),
        "macro_recall": round(recall_score(y, oof, average="macro",
                                           zero_division=0), 6),
        "macro_f1_mean": round(mean, 6),
        "macro_f1_std": round(std, 6),
        "auc": auc,
        "labels": labels,
        "confusion_matrix": cm,
        "folds": folds,
        "oof": oof,
        "pipe": pipe,
    }


def top_features(pipe, k=25, n_classes=None):
    """把模型的权重翻译成"最像好评的词 / 最像差评的词"。

    只在向量器能报出特征名时才做（词 TF-IDF 可以；词+字拼接的 FeatureUnion 不行，
    所以主任务里额外单独训了一个"字(2,3)+逻辑回归"专门用来出特征词）。
    """
    vec = pipe.named_steps["vec"]
    clf = pipe.named_steps["clf"]
    try:
        names = vec.get_feature_names_out()
        coef = clf.coef_
    except Exception:
        return {}
    if coef.shape[-1] != len(names):
        return {}
    out = {}
    if coef.shape[0] == 1:                            # 二分类：一条权重轴
        w = coef[0]
        order = w.argsort()
        out["top_positive"] = [(str(names[i]), round(float(w[i]), 4))
                               for i in order[::-1][:k]]
        out["top_negative"] = [(str(names[i]), round(float(w[i]), 4))
                               for i in order[:k]]
    else:                                             # 多分类：每个类别一条
        classes = list(clf.classes_)
        for ci, cname in enumerate(classes):
            w = coef[ci]
            order = w.argsort()[::-1][:k]
            out[f"top_class_{cname}"] = [(str(names[i]), round(float(w[i]), 4))
                                         for i in order]
    return out


# ===========================================================================
# 四、三个任务
# ===========================================================================
def task_top(rows, mode="both"):
    """主任务：5 星（力荐） vs ≤4 星。"""
    data = [r for r in rows]
    y = [1 if r["star"] == 5 else 0 for r in data]
    texts = [r["text"] for r in data]
    print(f"\n【主任务】5星 vs ≤4星   样本 {len(y)}，"
          f"正例 {sum(y)}（{100 * sum(y) / len(y):.1f}%）")
    tok = tokenize_all(texts)

    # ★ 每个模型拿到的都是 (原文, 分词后文本) 这一对：
    #   字向量器取第 0 列（原文），词向量器取第 1 列（分词结果）
    pairs = list(zip(texts, tok))

    best = None
    for name, (vec, clf) in build_vectorizers(mode).items():
        print(f"  · {name} ...", end=" ", flush=True)
        m = evaluate(name, pairs, y, vec, clf)
        print(f"acc={m['accuracy']:.4f}  macroF1={m['macro_f1']:.4f}"
              f"  AUC={m['auc'] if m['auc'] is not None else float('nan'):.4f}"
              f"（±{m['macro_f1_std']:.4f}）")
        if best is None or m["macro_f1"] > best["macro_f1"]:
            best = m

    print(f"  → 最佳：{best['name']}  macroF1={best['macro_f1']:.4f}")
    best["features"] = top_features(best["pipe"], k=25)
    if not best["features"]:
        # 拼接模型出不了特征名 → 单独训一个纯字模型专门用来解释"哪些字组像好评"
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        expl = Pipeline([
            ("vec", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=3,
                                    sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ])
        expl.fit(texts, y)
        best["features"] = top_features(expl, k=25)
    best["task"] = "top"
    best["y"] = y
    best["texts"] = texts
    best["rows"] = data
    return best


def task_three(rows, mode="word"):
    """副任务：3 分类（差评 1-2 星 / 中评 3 星 / 好评 4-5 星）。"""
    data = [r for r in rows]
    def lab(s):
        return "差评" if s <= 2 else ("中评" if s == 3 else "好评")
    y = [lab(r["star"]) for r in data]
    texts = [r["text"] for r in data]
    print(f"\n【副任务】三分类   样本 {len(y)}，分布 {dict(Counter(y))}")
    tok = tokenize_all(texts)
    pairs = list(zip(texts, tok))

    best = None
    for name, (vec, clf) in build_vectorizers(mode).items():
        print(f"  · {name} ...", end=" ", flush=True)
        m = evaluate(name, pairs, y, vec, clf)
        print(f"acc={m['accuracy']:.4f}  macroF1={m['macro_f1']:.4f}")
        if best is None or m["macro_f1"] > best["macro_f1"]:
            best = m

    print(f"  → 最佳：{best['name']}  macroF1={best['macro_f1']:.4f}")
    best["features"] = top_features(best["pipe"], k=20)
    best["task"] = "three"
    best["y"] = y
    best["texts"] = texts
    best["rows"] = data
    return best


def task_genre(rows, genres_of, mode="word", top_k=8):
    """副任务：短评 → 电影类型。

    ★ 为什么不用"是不是剧情"这种一对多做法：
      我们的 1052 部作品里 90% 都带"剧情"标签，做"是否为剧情"的二分类，
      基线就有 0.90，模型准确率反而更低 —— 这个问法本身就是坏的。

    ★ 改成两两对比（pairwise）：只在**两部类型截然不同的电影**之间选，
      让模型回答"这条短评来自哪一部"。这是一个基线恰好 50% 的平衡二分类，
      得到的准确率才说明"文本里到底有没有题材信息"。

      对比组刻意挑互斥的：动画 vs 纪录片、喜剧 vs 犯罪 …
    """
    # 每个类型 → 该类型下的短评
    by_genre = {}
    for r in rows:
        for g in genres_of.get(r["movie_id"], []):
            by_genre.setdefault(g, []).append(r)

    pairs_list = [("动画", "纪录片"), ("喜剧", "犯罪"), ("爱情", "科幻"),
                  ("动画", "剧情"), ("纪录片", "喜剧"), ("爱情", "动画"),
                  ("犯罪", "动画"), ("纪录片", "爱情"), ("动画", "悬疑")]

    pairwise = []
    print("\n  两两对比（基线 50%，高于 50% 才说明文本里有题材信息）:")
    for a, b in pairs_list:
        res = _genre_pair(a, b, by_genre)
        if res:
            pairwise.append(res)
            print(f"    {a} vs {b:<5} n={res['n']:<5} 准确率={res['accuracy']:.3f}"
                  f"  AUC={res['auc']:.3f}  比基线 {res['accuracy'] - 0.5:+.3f}")

    return {"task": "genre",
            "name": "TFIDF字(2,3)+逻辑回归",
            "note": "一对多做法因「剧情」覆盖 90% 而基线过高、模型反而不如瞎猜；改报两两对比",
            "pairwise": sorted(pairwise, key=lambda x: -x["accuracy"]),
            "n_samples": len(rows)}


def _fit_eval(pairs, y, cv=5):
    """跑一次分层 5 折交叉验证，返回 (out-of-fold 预测, out-of-fold 分数)。"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import Pipeline
    pipe = Pipeline([
        ("vec", ViewPick(0, TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3),
                                            min_df=3, sublinear_tf=True))),
        ("clf", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ])
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)
    oof = cross_val_predict(pipe, pairs, y, cv=skf)
    score = cross_val_predict(pipe, pairs, y, cv=skf, method="predict_proba")[:, 1]
    return oof, score


def _genre_pair(a, b, by_genre, max_n=600):
    """把类型 a 和类型 b 的短评各取 max_n 条，做平衡二分类（基线 50%）。"""
    from sklearn.metrics import accuracy_score, roc_auc_score, f1_score
    ra, rb = by_genre.get(a, []), by_genre.get(b, [])
    if min(len(ra), len(rb)) < 40:
        return None
    n = min(len(ra), len(rb), max_n)
    data = ra[:n] + rb[:n]
    y = [1] * n + [0] * n
    pairs = [(r["text"], " ".join(cut(r["text"]))) for r in data]
    oof, score = _fit_eval(pairs, y)
    return {"a": a, "b": b, "n": len(y),
            "accuracy": round(accuracy_score(y, oof), 4),
            "auc": round(float(roc_auc_score(y, score)), 4),
            "f1": round(f1_score(y, oof, average="binary"), 4)}


def task_diag(rows, mode="char"):
    """诊断：换不同的"好坏分界线"，看文本的预测力怎么变。

    这是本报告最有价值的一组数字 —— 它回答"为什么模型这么弱"：
    如果 5星 vs 1-2星 也分不开，说明文本本身没信息；
    如果 5星 vs 4星 分不开、5星 vs 1星 能分开，说明"4 和 5"这条线是人为的。
    """
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    print("\n【诊断】不同分界线上的可分性（字数模型，基线=多数类）")

    cases = [
        ("5星 vs 1-2星（极端对立）", lambda r: 1 if r["star"] == 5 else 0,
         [r for r in rows if r["star"] in (5, 1, 2)]),
        ("5星 vs 3星", lambda r: 1 if r["star"] == 5 else 0,
         [r for r in rows if r["star"] in (5, 3)]),
        ("5星 vs 4星（相邻档）", lambda r: 1 if r["star"] == 5 else 0,
         [r for r in rows if r["star"] in (5, 4)]),
        ("3星 vs 1-2星", lambda r: 1 if r["star"] == 3 else 0,
         [r for r in rows if r["star"] in (3, 1, 2)]),
        ("4-5星 vs 1-3星（推荐与否）", lambda r: 1 if r["star"] >= 4 else 0,
         [r for r in rows if r["star"] >= 1]),
        ("5星 vs ≤4星（主任务）", lambda r: 1 if r["star"] == 5 else 0,
         [r for r in rows if r["star"] >= 1]),
    ]

    out = []
    for tag, lab, data in cases:
        y = [lab(r) for r in data]
        if min(sum(y), len(y) - sum(y)) < 30:
            continue
        pairs = [(r["text"], " ".join(cut(r["text"]))) for r in data]
        oof, score = _fit_eval(pairs, y)
        base = max(sum(y), len(y) - sum(y)) / len(y)
        row = {"case": tag, "n": len(y), "pos_rate": round(sum(y) / len(y), 4),
               "baseline": round(base, 4),
               "accuracy": round(accuracy_score(y, oof), 4),
               "macro_f1": round(f1_score(y, oof, average="macro"), 4),
               "auc": round(float(roc_auc_score(y, score)), 4),
               "lift_over_base": round(accuracy_score(y, oof) - base, 4)}
        out.append(row)
        print(f"  · {tag:<22} n={row['n']:<5} 基线={base:.3f}  "
              f"准确率={row['accuracy']:.3f}  macroF1={row['macro_f1']:.3f}  "
              f"AUC={row['auc']:.3f}  比基线={row['lift_over_base']:+.3f}")

    return {"task": "diag", "name": "TFIDF字(2,3)+逻辑回归", "cases": out}


# ===========================================================================
# 五、写文件
# ===========================================================================
def write_cv_csv(m, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fold", "n_test", "accuracy",
                                          "macro_f1", "weighted_f1"])
        w.writeheader()
        w.writerows(m["folds"])


def write_feature_csv(m, path):
    feats = m.get("features") or {}
    if not feats:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["方向", "排名", "特征", "权重"])
        for key, items in feats.items():
            for i, (tok, wgt) in enumerate(items, 1):
                w.writerow([key, i, tok, wgt])


def write_predictions(all_results, path):
    """把每条短评的真实标签和模型预测写出来，重点标出判错的。"""
    from sklearn.metrics import confusion_matrix
    rows = []
    for m in all_results:
        if "oof" not in m:
            continue
        labels = m["labels"]
        for r, truth, pred in zip(m["rows"], m["y"], m["oof"]):
            rows.append({
                "task": m["task"],
                "model": m["name"],
                "comment_id": r["comment_id"],
                "movie_title": r["movie_title"],
                "star": r["star"],
                "truth": truth,
                "pred": pred,
                "correct": int(truth == pred),
                "n_chars": len(r["text"]),
                "text": r["text"].replace("\n", " ")[:120],
            })
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def save_metrics(metrics, path):
    def clean(m):
        return {k: v for k, v in m.items()
                if k not in ("pipe", "oof", "rows", "texts", "y")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


# ===========================================================================
# 六、主流程
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="all",
                    choices=["all", "top", "three", "genre", "diag"])
    ap.add_argument("--mode", default="both",
                    help="word / char / both")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    t_start = time.time()

    print("=" * 72)
    print("豆瓣短评建模 —— 文本 → 态度")
    print("=" * 72)
    print(f"jieba：{'已启用' if jieba else '未安装，改用二元字组兜底'}")

    rows = load_comments()
    print(f"可用短评：{len(rows)} 条（已剔除无星级/空文本）")
    star_dist = Counter(r["star"] for r in rows)
    print(f"星级分布：{dict(sorted(star_dist.items()))}")

    metrics = {"n_samples": len(rows),
               "star_distribution": {str(k): v for k, v in sorted(star_dist.items())},
               "jieba": bool(jieba),
               "tasks": {}}
    all_results = []

    if args.task in ("all", "top"):
        m = task_top(rows, args.mode)
        metrics["tasks"]["top"] = {k: v for k, v in m.items()
                                   if k not in ("pipe", "oof", "rows", "texts", "y")}
        write_cv_csv(m, os.path.join(OUT, "cv_top.csv"))
        write_feature_csv(m, os.path.join(OUT, "features_top.csv"))
        all_results.append(m)

    if args.task in ("all", "three"):
        m = task_three(rows, "word" if args.mode == "char" else args.mode)
        metrics["tasks"]["three"] = {k: v for k, v in m.items()
                                     if k not in ("pipe", "oof", "rows", "texts", "y")}
        write_cv_csv(m, os.path.join(OUT, "cv_three.csv"))
        write_feature_csv(m, os.path.join(OUT, "features_three.csv"))
        all_results.append(m)

    if args.task in ("all", "genre"):
        g = task_genre(rows, load_movie_genres(),
                       "word" if args.mode == "char" else args.mode)
        metrics["tasks"]["genre"] = g

    if args.task in ("all", "diag"):
        d = task_diag(rows)
        metrics["tasks"]["diag"] = d

    # 顺带记下几条"没有文本也能达到的"基线，报告里要用它们做参照
    from collections import defaultdict
    byt = defaultdict(list)
    for r in rows:
        byt[r["movie_id"]].append(1 if r["star"] == 5 else 0)
    y_all = [1 if r["star"] == 5 else 0 for r in rows]
    ok = n = 0
    for r, yy in zip(rows, y_all):
        lst = byt[r["movie_id"]]
        idx = lst.index(yy)
        others = lst[:idx] + lst[idx + 1:]        # 严格留一：不看自己
        if not others:
            continue
        maj = 1 if sum(others) * 2 >= len(others) else 0
        ok += (maj == yy)
        n += 1
    metrics["baselines"] = {
        "majority_class": round(sum(y_all) / len(y_all), 4),
        "movie_loo_majority": round(ok / n, 4) if n else None,
        "n_evaluable": n,
        "note": "movie_loo_majority = 严格留一：猜「同一部电影其他短评的多数星级」",
    }
    print(f"\n参照基线：恒猜多数类 {metrics['baselines']['majority_class']:.4f}；"
          f"同片其他短评多数票（严格留一）{metrics['baselines']['movie_loo_majority']:.4f}")

    if all_results:
        n = write_predictions(all_results, os.path.join(OUT, "predictions.csv"))
        print(f"\n已写 predictions.csv（{n} 行）")

    save_metrics(metrics, os.path.join(OUT, "metrics.json"))
    print(f"\n全部完成，耗时 {time.time() - t_start:.1f}s")
    print(f"产出目录：{OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
