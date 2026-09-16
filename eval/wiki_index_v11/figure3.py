import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as _p; matplotlib.rcParams["font.family"]="Noto Sans CJK JP"
import matplotlib.pyplot as plt
from PIL import Image
fig, axes = plt.subplots(2, 1, figsize=(9, 4.4), dpi=200)
old = ("(16736) トンガリヤマ (16736) トンガリヤマ トンガリヤマ 16736 Tongariyama 仮符号 ・別名 1996 JW 2 分類 小惑星 …\n"
       "… (16736) トンガリヤマ（英語: Tongariyama）は、小惑星帯（メインベルト）に位置する小惑星の一つ。\n"
       "This article is issued from Wikipedia . The text is available under Creative Commons Attribution-Share Alike 4.0 …")
new = ("トンガリヤマ16736 Tongariyama / 仮符号・別名: 1996 JW2 / 分類: 小惑星 / 発見者: 大国富丸 …\n"
       "(16736) トンガリヤマ（英語: Tongariyama）は、小惑星帯（メインベルト）に位置する小惑星の一つ。\n"
       "山形県南陽市のアマチュア天文家、大国富丸により発見された。")
for ax, (title, body, colour) in zip(axes, [("before — 671 characters, 73.5% of sampled chunks carried CSS or the licence footer", old, "#ffebee"),
                                            ("after — 421 characters, same facts: title once, entities decoded, no injected spaces, no footer", new, "#e3f2fd")]):
    ax.axis("off"); ax.set_title(title, fontsize=9, loc="left")
    ax.text(0.005, 0.5, body, fontsize=7.6, va="center", family="Noto Sans CJK JP",
            bbox=dict(facecolor=colour, edgecolor="none", pad=6), wrap=True)
fig.suptitle("Extraction, v11: the footer appeared in 96.1% of published Japanese chunks and 89.9% of Chinese ones", fontsize=10)
fig.text(0.005, 0.01, "Article (16736) トンガリヤマ, ja Wikipedia mini ZIM. 'JW 2' → 'JW2' and '仮符号 ・別名' → '仮符号・別名': inline tags used to be replaced by a space, splitting words.", fontsize=6.5, color="#555")
plt.tight_layout(rect=(0,0.04,1,0.94)); fig.savefig("fig_v11_extraction.png"); Image.open("fig_v11_extraction.png").save("fig_v11_extraction.png")
print("figure 3 written")
