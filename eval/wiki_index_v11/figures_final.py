#!/usr/bin/env python3
"""Final figures. Every number is traceable to a log in this directory; the source log is named
in each caption."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np
from PIL import Image
matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
O = "/home/happy/.codex/bench/wiki_forensics/figF_"

# --- 1. the token window -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 4.3), dpi=200)
langs = ["EN", "JA", "ZH"]; old = [3.1, 13.7, 18.5]; cpt = ["3.95", "2.01", "1.98"]
x = np.arange(3); w = 0.36
ax.bar(x-w/2, old, w, color="#c62828", label="published 2026-04/06 revision (1,536-character slices)")
ax.bar(x+w/2, [0,0,0], w, color="#1565c0", label="v11b (whole sentences, 256-token budget)")
for i,o in enumerate(old):
    ax.text(i-w/2, o+0.35, f"{o:.1f}%", ha="center", fontsize=9)
    ax.text(i+w/2, 0.35, "0.00%", ha="center", fontsize=9, color="#1565c0")
ax.set_xticks(x); ax.set_xticklabels([f"{l}\n({c} characters per token)" for l,c in zip(langs,cpt)])
ax.set_ylabel("chunks past the ME5 512-token window\n(the overflow never reaches the encoder)", fontsize=9)
ax.set_title("A character-length cap misses the token window, and misses it most in Chinese", fontsize=10.5)
ax.legend(fontsize=8.5, frameon=False, loc="upper left"); ax.spines[["top","right"]].set_visible(False); ax.set_ylim(0, 23)
fig.text(0.01, 0.028, "Uniform stride sample of 8,000 chunks per published store (ja 1.55M, zh 1.64M, en 5.46M chunks) — window_footer_uniform.log.", fontsize=6.3, color="#555")
fig.text(0.01, 0.008, "Truncated chunks lose 14.4% (en) / 21.7% (ja) / 27.0% (zh) of their tokens. v11b figures: verify_{en,ja,zh}.log, 4,000-chunk samples per shipped store.", fontsize=6.3, color="#555")
plt.tight_layout(rect=(0,0.06,1,1)); fig.savefig(O+"tokens.png"); Image.open(O+"tokens.png").save(O+"tokens.png")

# --- 2. index type and quantiser range ------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), dpi=200)
ax = axes[0]
pts = [("IVF,PQ64\n(previous revision)", 107, 61.4, 78.7, "#c62828"),
       ("OPQ256,IVF,PQ256", 327, 67.9, 87.5, "#ef6c00"),
       ("PCA256,IVF,SQ8", 306, 63.4, 82.2, "#9e9e9e"),
       ("IVF,SQ4  (v11b)", 548, 68.6, 88.6, "#1565c0"),
       ("IVF,SQ8", 1060, 68.7, 88.9, "#455a64")]
for name, b, ja, en, c in pts:
    ax.scatter(b, ja, s=110, color=c, zorder=3); ax.scatter(b, en, s=110, color=c, marker="^", zorder=3)
    ax.annotate(name, (b, ja), textcoords="offset points", xytext=(6, -15), fontsize=7.8, color=c)
ax.axhline(69.2, ls="--", lw=0.9, color="#333"); ax.text(1090, 69.6, "exact search, ja", fontsize=7.5, ha="right")
ax.axhline(89.4, ls="--", lw=0.9, color="#333"); ax.text(1090, 89.8, "exact search, en", fontsize=7.5, ha="right")
ax.set_xlabel("bytes per vector (measured on the index file)"); ax.set_ylabel("MRR on generated questions\n(● Japanese  ▲ English)", fontsize=9)
ax.set_title("Product quantisation is the wrong trade for these vectors", fontsize=10)
ax.set_xlim(0, 1150); ax.set_ylim(58, 93); ax.spines[["top","right"]].set_visible(False)

ax = axes[1]
names = ["FAISS min/max\n(default)", "FAISS RS_optim", "residual quantiles\n0.1–99.9% (v11b)"]
fid = [81.6, 84.5, 85.2]; mrr = [66.2, 66.9, 66.9]
xx = np.arange(3)
b1 = ax.bar(xx-0.2, fid, 0.4, color="#1565c0", label="top-10 agreement with exact search")
b2 = ax.bar(xx+0.2, mrr, 0.4, color="#9e9e9e", label="MRR")
for r,v in zip(b1, fid): ax.text(r.get_x()+r.get_width()/2, v+0.5, f"{v:.1f}%", ha="center", fontsize=8.5)
for r,v in zip(b2, mrr): ax.text(r.get_x()+r.get_width()/2, v+0.5, f"{v:.1f}", ha="center", fontsize=8.5)
ax.set_xticks(xx); ax.set_xticklabels(names, fontsize=8.5); ax.set_ylim(55, 92)
ax.set_title("Same 4 bits, same decode cost: only the range changes", fontsize=10)
ax.legend(fontsize=8, frameon=False, loc="upper left"); ax.spines[["top","right"]].set_visible(False)
fig.text(0.01, 0.028, "Left: 205,789 ja chunks / 303 questions and 158,200 en chunks / 400 questions, IVF with nlist≈4·√N, nprobe 128 — index_e2e.log, sizes.log.", fontsize=6.3, color="#555")
fig.text(0.01, 0.008, "Right: the same ja pool at the shipped nlist=4096, nprobe 128 — faiss_range_residual.log. Both are 1/50-scale probes used to choose the design, not measurements of the shipped index.", fontsize=6.3, color="#555")
plt.tight_layout(rect=(0,0.06,1,1)); fig.savefig(O+"index.png"); Image.open(O+"index.png").save(O+"index.png")
print("figures written")
