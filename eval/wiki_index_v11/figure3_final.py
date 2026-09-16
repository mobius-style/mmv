import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.family"]="Noto Sans CJK JP"
from PIL import Image
fig, axes = plt.subplots(2, 1, figsize=(9.5, 4.6), dpi=200)
old = ("(16736) トンガリヤマ (16736) トンガリヤマ トンガリヤマ 16736 Tongariyama 仮符号 ・別名 1996 JW 2 分類 小惑星 …\n"
       "… (16736) トンガリヤマ（英語: Tongariyama）は、小惑星帯（メインベルト）に位置する小惑星の一つ。\n"
       "This article is issued from Wikipedia . The text is available under Creative Commons Attribution-Share Alike 4.0 …")
new = ("トンガリヤマ16736 Tongariyama / 仮符号・別名: 1996 JW2 / 分類: 小惑星 / 発見者: 大国富丸 …\n"
       "(16736) トンガリヤマ（英語: Tongariyama）は、小惑星帯（メインベルト）に位置する小惑星の一つ。\n"
       "山形県南陽市のアマチュア天文家、大国富丸により発見された。")
for ax,(title,body,colour) in zip(axes,[("previous revision — 671 characters for this article",old,"#ffebee"),
                                        ("v11b — 421 characters, same facts",new,"#e3f2fd")]):
    ax.axis("off"); ax.set_title(title, fontsize=9.5, loc="left")
    ax.text(0.005,0.5, body, fontsize=7.6, va="center",
            bbox=dict(facecolor=colour, edgecolor="none", pad=6))
fig.suptitle("The licence footer was inside 97.1% of the published Japanese chunks and 92.9% of the Chinese ones", fontsize=10.5)
fig.text(0.005,0.030,"Footer rate: full-file count over every chunk of the published stores (ja 1,505,103/1,550,503; zh 1,521,419/1,638,042; en 0/5,458,524) — window_footer_uniform.log.", fontsize=6.3, color="#555")
fig.text(0.005,0.008,"Example: article (16736) トンガリヤマ, ja mini ZIM. 'JW 2'→'JW2' and '仮符号 ・別名'→'仮符号・別名': inline tags used to be replaced by a space, which split words.", fontsize=6.3, color="#555")
plt.tight_layout(rect=(0,0.055,1,0.93)); fig.savefig("figF_extraction.png"); Image.open("figF_extraction.png").save("figF_extraction.png")
print("figure 3 written")
