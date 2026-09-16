#!/usr/bin/env python3
"""The paper claimed 'differences under ~2.4 MRR points are inside the standard error' with no log
behind it. Per-question reciprocal ranks were not retained, so bound the standard error from the
reported recall@1 / recall@5 / MRR instead. RR takes values in {1, 1/2, ..., 1/10, 0}."""
import numpy as np
out=[]
def p(s):
    print(s, flush=True); out.append(s)
# (lang, n, recall@1, recall@5, MRR) from final_eval_{lang}.log, nprobe 128
R=[("en",400,53.5,71.8,60.9),("ja",303,50.8,63.0,56.3),("zh",310,49.4,64.2,55.5)]
p("standard error of MRR, reconstructed from the reported rates (per-question ranks not retained)")
for lang,n,r1,r5,m in R:
    p1,m_=r1/100,m/100
    # upper bound: RR in [0,1] so E[RR^2] <= E[RR]
    var_hi=m_-m_**2
    # point estimate: mass p1 at RR=1, the rest spread over 1/2..1/10 with mean (m-p1)/(1-p1)
    rest_mean=(m_-p1)/(1-p1) if p1<1 else 0.0
    # those non-top-1 items have RR <= 1/2, so E[RR^2 | not top1] <= 0.5 * rest_mean
    var_pt=(p1*1.0+(1-p1)*0.5*rest_mean)-m_**2
    p(f"  {lang}: n={n}  MRR={m}  recall@1={r1}")
    p(f"     SD upper bound {np.sqrt(var_hi):.3f} -> SE {100*np.sqrt(var_hi/n):.2f} MRR points")
    p(f"     SD estimate    {np.sqrt(var_pt):.3f} -> SE {100*np.sqrt(var_pt/n):.2f} MRR points")
p("")
p("Unpaired 95% interval for the difference of two such means is about 2*sqrt(2)*SE,")
p("i.e. 6.5-7.8 MRR points. Our comparisons reuse the same questions, so the paired standard error")
p("is smaller than this, but we did not retain the per-question ranks needed to compute it.")
p("Conclusion: the '~2.4 points' figure used in the draft is roughly one unpaired standard error")
p("for English and understates it for Japanese and Chinese. It is a rough noise scale, not a test.")
open("noise_floor.log","w").write("\n".join(out)+"\n")
