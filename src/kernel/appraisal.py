"""
appraisal.py — Möbius v7.5 Phase A appraisal module

Changes from v2.1:
  - AppraisalState gains kvs field (KVSResult | None)
  - stable_fact flag retained for backward compatibility
  - KVS computation integrated when model_name provided
  - stable_fact is now KVS-gated: stable_fact=True only when
    STABLE_FACT_PATTERNS match AND KVS says eligible
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import List, Optional
import re

from .kvs import KVSResult, compute_kvs

# ── ISMProfile (optional, graceful fallback) ─────────────────────────────────
try:
    from ..adapters.raf.profile import ISMProfile as _ISMProfile
    from ..adapters.raf.schema import ISMState as _ISMState
    _ism_profile = _ISMProfile()
    _ism_available = _ism_profile.load()
    if _ism_available:
        import logging as _log
        _log.getLogger(__name__).info(
            "[Appraiser] ISMProfile loaded — intent classification active"
        )
except Exception:
    _ism_available = False
    _ism_profile = None


@dataclass
class AppraisalState:
    completeness:      float
    uncertainty:       float
    freshness_sensitive: bool
    safety_relevant:   bool
    intent_clarity:    float
    stable_fact:       bool = False
    kvs:               Optional[KVSResult] = None
    self_referential:  bool = False
    user_correction:   bool = False
    ism:               Optional[object] = None
    notes:             List[str] = field(default_factory=list)
    # Phase E hook: meta-recall intent (summarize / coverage / continue / same format).
    # Consumed by Box W calibration (G1 guard) and synthesis routing.
    meta_recall_intent: bool = False
    # Phase E hook: context_dependent surface flag (derived elsewhere in appraiser).
    context_dependent: bool = False
    # Phase F v2+ narrow exception: same-format continuation with a clear prior
    # format anchor. When True, the query is treated as a bounded continuation
    # rather than a generic under-specified ask. Safety and truly ambiguous
    # queries still route to ask. See appraisal evaluate() for detection.
    format_anchored_continuation: bool = False
    # Phase G.8 — definitional-query flag.
    # True when the query has the shape of a bare definition request
    # ("what is X?" / "Xとは？" / "X是什么？") and is NOT already covered
    # by the structural STABLE_FACT_PATTERNS, NOT self-referential, NOT
    # freshness-sensitive, and NOT under-specified. Consumed by
    # route_decision to produce a grounded-definition reason code.
    definitional_query: bool = False
    # Phase G.9 — continuity / save intent.
    # True when the user says something like "save this conversation" /
    # "今までの話を保存したい". Consumed by the UI post-response hook to
    # trigger the existing trigger_manual_checkpoint path; also drops a
    # reason code on the route decision for inspectability.
    continuity_save_intent: bool = False


class Appraiser:
    FRESHNESS_TERMS = {
        "current", "currently", "today", "latest", "recent", "recently", "now",
        "up to date", "as of today", "this week", "this month", "new",
        "last month", "yesterday", "just", "update", "changed", "changes",
        "tomorrow", "next week", "next month", "next year",
        "today's", "upcoming",
        # Stage 4 additions — commonly used real-world freshness phrasings
        # missed by Stage 3 eval (107 route_mismatch_freshness_answered).
        # Keep each addition narrow enough to avoid broad false positives.
        "lately", "these days", "nowadays", "right now", "at the moment",
        "trending", "as of", "at present", "presently",
        # Japanese freshness terms
        "今の", "現在の", "最新の", "最近の", "今日の", "いまの",
        "明日", "あした", "来週", "らいしゅう", "今週", "こんしゅう",
        "今月", "こんげつ", "来月", "らいげつ", "今年", "ことし",
        "来年", "らいねん", "最新", "さいしん", "直近", "じっきん",
        "現在", "げんざい", "現時点", "今現在", "最近",
        # Stage 4 additions — past-relative and time-of-day phrasings
        "先週", "せんしゅう", "先月", "せんげつ", "去年", "きょねん",
        "昨年", "さくねん", "昨日", "きのう", "今朝", "けさ",
        "今夜", "こんや", "今晩", "こんばん",
        "このところ", "このごろ", "足元",
        # Stage 5 — additional natural freshness markers
        "これから", "先ほど", "ここ数日", "ここ最近", "ここ数週間",
        "直前", "さっき",
        # Chinese freshness terms
        "现在的", "最新的", "最近的", "今天的", "当前的",
        "明天", "下周", "下週", "下个月", "下個月",
        "今年", "最新", "最近", "当前", "當前", "目前",
        # Stage 4 additions — past-relative
        "上周", "上週", "上个月", "上個月", "昨天", "昨日",
        # ZH Phase 2 — bare "现在" (without 的) and other common standalone
        # freshness markers. Phase 2 baseline missed queries like
        # "btc 现在多少钱" / "现在什么样的概率分布" because "现在" alone
        # was not in this set, leaving freshness_sensitive=False.
        "现在", "現在", "這幾年", "这几年", "這些天", "这些天", "近来", "近來",
        "这段时间", "這段時間", "这一阵", "這一陣", "眼下", "如今",
        "当下", "當下",
    }
    HIGH_STAKES_TERMS = {
        "medical", "medicine", "dose", "law", "legal", "rights", "contract",
        "invest", "investment", "stock", "crypto", "tax",
    }
    SAFETY_TERMS = {
        "harm", "illegal", "explosive", "malware", "weapon",
        "synthesise", "synthesize", "controlled substance",
        "exploit", "vulnerability", "hack", "poison", "kill", "murder", "attack",
    }

    UNDER_SPEC_PATTERNS = re.compile(
        r"\b(compare|summarize|summarise)\b"
        r"(?!.*\b(for|between|vs|versus|of|in|across)\b)"
        # Japanese bare/deictic action commands with no object. Whole-query
        # anchored (low false-positive risk): optional leading deictic
        # (それ/これ…) and trailing punctuation tolerated. (ERO Infinity v0.13 —
        # fixes the prior `^(...)$` anchor that rejected a trailing "。" and
        # widens the verb set.)
        r"|^(?:(?:それ|これ|その|あの|あれ)[でをにのは、,]?\s*)?"
        r"(?:比較して|まとめて|要約して|説明して|教えて|改善して|選んで|やって"
        r"|直して|なおして|進めて|対応して|処理して|やり直して)[。.!?！？\s]*$"
        # English bare/deictic imperatives with no object (whole-query anchored).
        r"|^(?:do it|do this|do that|fix it|fix this|fix that|redo it|continue"
        r"|sort (?:it|this|that|these|those) out|handle (?:it|this|that)"
        r"|take care of it|optimi[sz]e it|improve (?:it|this|that)"
        r"|what should i (?:choose|pick|select|do)|which (?:one|to (?:choose|pick))"
        r"|pick (?:one|the best one?))[\s.!?]*$"
        # Chinese: bare action verbs without object
        r"|^(比较一下|总结|解释一下|告诉我|介绍)$",
        re.IGNORECASE,
    )
    VAGUE_BEST_PATTERN = re.compile(
        r"\bbest\b(?!.*\b(for|between|of|in|option|way|approach|method|practice|system)\b)",
        re.IGNORECASE,
    )
    PRONOUN_REF_PATTERN = re.compile(
        r"\b(this policy|that policy|it|them|those|these|the changes|the situation"
        r"|the meeting|the summit|the announcement|the decision|the update"
        r"|the status|the number|the rate|the result|the outcome)\b",
        re.IGNORECASE,
    )

    # Context-dependent subject patterns: "the government/company/court/team did X"
    # without specifying WHICH government/company/etc.
    CONTEXT_DEPENDENT_SUBJECT = re.compile(
        r"\bwhat did (the government|the company|the court|the team|the committee"
        r"|the board|the president|the minister|the agency|the authority"
        r"|the organization|the institution|they|he|she|it)\b",
        re.IGNORECASE,
    )

    # Bare action queries: "what happened at the X" without specifying which X
    BARE_ACTION_PATTERN = re.compile(
        r"\b(what happened|what changed|what was decided|what was announced"
        r"|what did .{0,20} decide|what did .{0,20} announce"
        r"|what did .{0,20} approve|what did .{0,20} pass"
        r"|what was the outcome|what was the result|what was the decision)\b",
        re.IGNORECASE,
    )
    REFERENT_ANCHORS = re.compile(
        r"\b("
        r"prime minister of|president of|secretary of|chancellor of"
        r"|minister of|governor of|head of|chief of|ceo of|director of|leader of"
        r"|inflation rate|unemployment rate|treasury yield|interest rate|jobless rate"
        r"|federal funds|funds rate|base rate|policy rate|policy interest"
        r"|brent crude|crude oil|gdp|exchange rate|stock market|stock price|weather"
        r"|united kingdom|united states|eurozone|european union|euro area"
        r"|france|germany|canada|australia|japan|china|brazil|india"
        r"|nato|fed |federal reserve|bank of england|bank of japan"
        r"|imf|world bank|un security|european commission"
        r"|california|texas|new york|congress|parliament"
        r"|regulation|regulations|policy on|policy for|law on|law for"
        r"|permitting|compliance|governing|rules for|rules on"
        r"|version of|release of|python|openai|microsoft|google|apple|amazon"
        # Stage 5 — news/update anchors + select software/network
        # standards that are often the subject of freshness queries.
        r"|\bnews\b|\bheadlines?\b|\bupdate on\b"
        r"|\b(llvm|gcc|clang|kubernetes|docker|node\.?js|rust\s+compiler)\b"
        r"|\bwifi\s?6?\b|\b5g\b|\b6g\b"
        r")\b"
        # Japanese referent anchors (no \b needed — CJK has no word boundaries)
        r"|首相|大統領|総理|内閣|国会|議会"
        r"|日本|アメリカ|中国|韓国|イギリス|フランス|ドイツ"
        r"|インフレ率|失業率|為替|GDP|金利|株価|株式|天気|気温"
        # Chinese referent anchors
        r"|首相|总理|总统|国家主席|内阁|国会"
        r"|中国|美国|日本|英国|法国|德国"
        r"|通货膨胀率|失业率|汇率|GDP|利率|股价|股票|天气|气温"
        # Financial realtime anchors
        r"|\bbitcoin\b|\bbtc\b|\bethereum\b|\beth\b|\bcrypto\b"
        r"|\bnasdaq\b|\bs&p\b|\bdow\s?jones\b|\bnikkei\b|\bftse\b"
        r"|\bgold\s+price\b|\boil\s+price\b|\bcrude\s+price\b"
        r"|\btreasury\s+yield\b|\bbond\s+yield\b|\bforex\b"
        r"|ビットコイン|イーサリアム|仮想通貨|暗号資産"
        r"|原油価格|金価格|先物|日経平均"
        # Stage 5 — JP/ZH news anchors for freshness gating
        r"|ニュース|経済ニュース|見出し|速報"
        r"|新闻|经济新闻|头条|新聞|頭條"
        # ZH Phase 2 — Chinese financial / crypto / market / tech anchors.
        # Phase 2 baseline (rl_zh_post_20260422) flagged 55 ret_financial
        # + 46 ret_freshness misses where `比特币 / 纳斯达克 / 加密货币`
        # were absent from REFERENT_ANCHORS, leaving freshness_sensitive=False
        # because `freshness_with_ref = freshness AND has_referent`.
        r"|比特币|比特幣|以太坊|以太币|以太幣"
        r"|加密货币|加密貨幣|虚拟货币|虛擬貨幣|数字货币|數字貨幣"
        r"|区块链|區塊鏈"
        r"|纳斯达克|納斯達克|标准普尔|標準普爾|道琼斯|道瓊斯|恒生指数|恆生指數"
        r"|原油|黄金价格|黃金價格"
        r"|美元|日元|人民币|人民幣|美金|欧元|歐元|英镑|英鎊"
        r"|央行|联储|聯儲|日本銀行|日本银行|美联储|美聯儲"
        r"|股市|股價|市場|市场|大盘|大盤"
        # Current-state ZH news/update markers
        r"|最新情况|最新情況|最新动态|最新動態|最新进展|最新進展"
        r"|最新消息|最新资讯|最新資訊|最新研究"
        r"|最新发布|最新發佈|最新(?:版本|版)"
        r"|近况|近況|近期(?:进展|进展|发展|發展|研究|趋势|趨勢)"
        r"|目前(?:最|的)|当前(?:最|的)|當前(?:最|的)"
        # Public figures / institutions common in ZH news
        r"|国务院|國務院|主席|总理|總理|总统|總統"
        # Stage 4 — non-word-boundary variants for CJK-mixed contexts
        # where \b fails (の+nasdaq, 、+btc, etc.). Narrow set covering
        # the highest-volatility tickers. Harmless in pure EN contexts
        # (the \b version already matched above).
        r"|(?<![a-z])nasdaq(?![a-z])"
        r"|(?<![a-z])bitcoin(?![a-z])"
        r"|(?<![a-z])btc(?![a-z])"
        r"|(?<![a-z])ethereum(?![a-z])"
        r"|(?<![a-z])nikkei(?![a-z])"
        # Stage 5 — non-boundary variants for tech tooling inside CJK
        # contexts (e.g. "の llvm の更新" or "最近のkubernetes").
        r"|(?<![a-z])llvm(?![a-z])"
        r"|(?<![a-z])gcc(?![a-z])"
        r"|(?<![a-z])clang(?![a-z])"
        r"|(?<![a-z])kubernetes(?![a-z])"
        r"|(?<![a-z])docker(?![a-z])"
        r"|(?<![a-z])python(?![a-z])"
        r"|(?<![a-z])news(?![a-z])",
        re.IGNORECASE,
    )

    # Stage 7 — STRONG_FRESHNESS_PATTERN. Narrow patterns that denote an
    # unambiguous request for current/latest information even when the
    # query lacks an explicit REFERENT_ANCHOR. Matching this pattern
    # sets freshness_sensitive=True directly, bypassing the anchor
    # requirement. Kept narrow to avoid false positives on stable
    # definition queries.
    #
    # Design: each alternative requires BOTH a freshness lexeme
    # (current/latest/recent/最新/現在/最近/etc.) AND an adjacent
    # concrete-state noun (price/version/state/trend/etc.), or a
    # clearly time-bound phrasing ("at the moment with X"). This
    # two-term conjunction protects against bare freshness-term
    # matches on stable queries.
    STRONG_FRESHNESS_PATTERN = re.compile(
        # English: "current/latest/recent/today's/nowadays + <concrete-state noun>"
        r"\b(current|latest|recent|today'?s|nowadays?)\s+"
        r"(price|prices|state|status|version|versions|rate|rates"
        r"|value|values|trend|trends|development|developments"
        r"|release|releases|standard|standards|cost|costs|market\b"
        r"|situation|news|headline|headlines)\b"
        # English: "whats going on with / whats the latest/current on /
        # whats the deal with X these days"
        r"|\bwhat'?s\s+(going\s+on\s+with|the\s+current|the\s+latest\s+on"
        r"|the\s+latest\s+in|trending\s+in|new\s+in|the\s+deal\s+with)\b"
        # English: "X these days", "X nowadays", "X at the moment"
        r"|\b(these\s+days|nowadays|at\s+the\s+moment|right\s+now)\b(?=.{0,40}\?|$)"
        # English: "at the moment/right now/these days with/on/for X"
        r"|\bat\s+the\s+moment\b.{0,40}\b(with|on|for|in)\b"
        r"|\bhow\s+has\s+\w+\s+(changed|evolved|moved)\s+(recently|lately)\b"
        # JP compound: <freshness>の<25 chars>(concrete-state noun)
        r"|最近の[^、。]{0,40}(状況|動向|トレンド|研究状況|研究|進展|進捗|発展|バージョン|版|価格|レート|動き)"
        r"|最新の[^、。]{0,40}(状況|動向|トレンド|研究|研究状況|進展|進捗|バージョン|版|モデル|人気|情報|ニュース)"
        r"|現在の[^、。]{0,40}(状況|動向|研究状況|バージョン|版|レート|値|状態|価格|進捗|進展|トレンド|為替)"
        r"|今の[^、。]{0,25}(価格|レート|状況|状態|動向|バージョン|相場)"
        # JP: "Xの最新バージョン / Xの現在のバージョン / Xの最新版"
        r"|\S{1,25}の最新(バージョン|版|モデル|トレンド|情報|研究|状況|動向|版本)"
        r"|\S{1,25}の現在の?(バージョン|版|状態|状況|価格|レート|値|為替)"
        # JP: "現在どの...が一番人気/主流/標準"
        r"|現在どの[^、。]{0,30}(人気|主流|標準|流行|トレンド)"
        # JP: "最近...一番人気" / "最近...注目"
        r"|最近[^、。]{0,25}(一番人気|注目|話題|主流|流行)"
        # ZH
        r"|现在的[^。]{0,30}(价格|状态|趋势|版本|利率|动向)"
        r"|最近的[^。]{0,30}(价格|动向|趋势|版本|进展|状态)"
        r"|最新的[^。]{0,30}(价格|版本|趋势|进展|动向|状态)"
        # ZH Phase 2 — "现在/目前 + 最 + concrete-state noun" compounds
        r"|(?:现在|目前|當前|当前|最近|如今)\s*最\s*"
        r"(?:好|佳|流行|火|火热|熱門|热门|新|先进|先進|主流|受欢迎|受歡迎|"
        r"便宜|便宜|稳定|穩定|快|常用)"
        r"[^。]{0,25}(?:的|是)"
        # ZH compact: 现在/目前/当前 + Xが一番人気 analogue
        r"|(?:现在|目前|當前|当前)[^。]{0,6}(?:最|哪个|哪個|什么|什麼)"
        r"[^。]{0,15}(?:人气|人氣|流行|主流|受欢迎|受歡迎|最好|最佳|好用|实用|實用)"
        # ZH: "X 现在多少钱" / "X 现在多少" (price/quantity query with bare noun)
        r"|(?:btc|比特币|比特幣|以太坊|以太币|以太幣|[一-鿿]{1,8})"
        r"\s*(?:现在|現在|目前|當前|当前|如今)\s*(?:多少|几|幾|怎么|怎樣|怎么样|怎麼樣|價格|价格)"
        # ZH Phase 3 — extended concrete-state nouns for tech/research
        # domain freshness queries. Phase 2 caught price/trend/version; these
        # add research/algo/system/architecture/model/experiment/result/
        # performance/development/tech — the nouns that dominate the 20
        # substantive freshness misses post-Phase-2.
        # 的 is optional so that "最新发展" (compound) matches as well as
        # "最新的发展" (adjectival form).
        r"|(?:现在的?|目前的?|當前的?|当前的?|最近的?|最新的?|現在的?|如今的?)[^。]{0,30}"
        r"(?:研究|进展|進展|发展|發展|技术|技術|算法|方法|系统|系統|"
        r"架构|架構|模型|实验|實驗|结果|結果|性能|收敛速度|收斂速度|动态|動態|"
        r"研究进展|研究進展|行情|市场|市場|走势|走勢|消息|资讯|資訊|新闻|新聞)"
        # ZH Phase 3 — "最近 + 有(什么|哪些|有没有|沒有) + (新|先进|流行|主流)
        # + (X|的X)" form. "最近有什么新的分布式文件系统" style.
        r"|最近\s*(?:有|出[了來来])\s*(?:什么|什麼|哪些|沒有|没有|啥|)?[^。]{0,18}"
        r"(?:新|先进|先進|流行|主流|热门|熱門|值得|有趣)"
        # ZH Phase 3 — "当前/目前 + X + 的 + (最高|最新|最佳|最快|最常用) +
        # (版本|算法|方法|工具|系统|架构|软件|...)". "当前 mysql 的最高版本"
        # and "現在全球最常用的統計軟體" form. Intervening chars permitted
        # up to 15 chars so that adjectival "的" + short noun can appear
        # between the "most-X" marker and the concrete noun.
        r"|(?:当前|目前|當前|最近|现在|現在|如今)"
        r"[^。]{0,20}(?:的)?\s*(?:最高|最新|最佳|最好|最快|最常用|最常见|最常見|主流|主要)"
        r"[^。]{0,15}"
        r"(?:版本|算法|方法|工具|系统|系統|架构|架構|模型|技术|技術|实现|實現|软件|軟體|软体|软件包|工具链|工具鏈|框架)"
        # ZH Phase 3 — "目前/当前 + X + (平均|平均收敛|收敛) + 速度/效率".
        # "目前梯度下降法的平均收敛速度" form.
        r"|(?:目前|当前|當前|现在|現在|最近|如今)[^。]{0,20}"
        r"(?:平均|收敛|收斂|运行|運行|执行|執行)?\s*(?:速度|效率|性能|表现|表現)"
        # ZH Phase 3 — "最近 + 的 + X + (研究|进展|动态|情况) + 怎么样/
        # 如何/有啥". "最近的量子纠缠实验结果怎么样" form.
        r"|最近(?:的)?[^。]{0,25}"
        r"(?:实验结果|實驗結果|研究结果|研究結果|实验|實驗|"
        r"研究动态|研究動態|研究进展|研究進展|新进展|新進展|新研究)",
        re.IGNORECASE,
    )

    # Structural stability patterns — necessary but NOT sufficient for
    # LOW_STAKES_STABLE. KVS must also pass (MKR_eff >= threshold).
    STABLE_FACT_PATTERNS = re.compile(
        r"\b("
        r"capital of|capital city of"
        r"|speed of light|chemical symbol|atomic number|atomic mass"
        r"|boiling point|melting point|molecular weight"
        r"|established in|founded in|when was .* established|when was .* founded"
        r"|in what year was .* established|in what year was .* founded"
        r"|in what year was .* invented|in what year was .* created"
        r"|in what year did .* join|in what year did .* sign"
        r"|when did .* join|when did .* sign"
        r"|how many amendments|how many articles"
        r"|number of amendments|number of articles"
        r"|permanent members|founding members|founding treaty"
        r"|how many permanent|how many founding"
        r"|official language of|official currency of"
        r"|established by the tax cuts|established by tcja"
        r"|standard vat rate|standard corporate tax"
        r"|pythagorean|speed of sound|gravitational constant"
        r")\b",
        re.IGNORECASE,
    )

    # Short but fully-specified definition queries (en/ja/zh).
    DEFINITION_QUERY_PATTERN = re.compile(
        # English: "what is/are <topic>"
        r"^what\s+(is|are)\s+\S"
        # Japanese: "<topic>は？" / "<topic>とは？" / "<topic>って何？"
        r"|.+は[？?]$"
        r"|.+とは[？?]?$"
        r"|.+って(何|なに)[？?]?$"
        # Chinese: "<topic>是什么？" / "什么是<topic>？"
        r"|.+是什么[？?]?$"
        r"|^什么是.+"
        r"|.+是啥[？?]?$",
        re.IGNORECASE,
    )

    # Phase G.8 — supplemental pattern for natural-language Japanese
    # definitional asks that trail with copula/honorific tails. The core
    # DEFINITION_QUERY_PATTERN above is deliberately terse (punctuation-
    # anchored). Real users write "Xって何ですか？" / "Xとは何ですか？".
    #
    # Intentionally restrictive on English side: only a bare "define X"
    # is added, because "explain X in ..." / "tell me about X and Y" are
    # typically comparison or contextual requests, not bare definitions.
    # Length gating below prevents long multi-concept queries from
    # matching even when the surface form is superficially definitional.
    DEFINITION_QUERY_EXTENDED = re.compile(
        # Japanese with copula: "って何ですか(？)", "とは何ですか(？)",
        # "はどういう (意味|こと|もの)" and variants.
        r".+って(何|なに)(です)?[かの]?[？?]?$"
        r"|.+とは(何|なに)(です)?[かの]?[？?]?$"
        r"|.+はどういう(意味|こと|もの|ものですか)[？?]?$"
        # English extended: only "define X" (narrowest safe pattern).
        r"|^define\s+\S",
        re.IGNORECASE,
    )

    # Phase G.8 — exclusion patterns. Query shape matches definitional
    # surface but is actually comparison / contextualized / multi-concept
    # and should remain on the ordinary answer path.
    DEFINITION_QUERY_EXCLUSION = re.compile(
        r"\b(difference between|compared to|versus|vs\.?|relate[ds]? to|"
        r"contrast|pros and cons|advantages|disadvantages|"
        r"the concept of|the idea of|the basic idea)\b"
        r"|と(違い|の違い|の比較|を比較)"
        r"|のメリット|のデメリット",
        re.IGNORECASE,
    )

    # Phase G.8 — definitional queries must be short. Long queries are
    # typically multi-concept / contextualized and not bare definitions.
    DEFINITION_QUERY_MAX_CHARS = 60

    # Phase 3 (ZH) — prose-embedded technical-definition anchor.
    # When a ZH query wraps a concrete technical term in long prose AND
    # attaches a definitional intent marker ("X这个概念/X是什么意思/X的定义/
    # 术语叫做X/缩写是X/怎么理解X"), the query is a bounded definitional
    # request and its deictic tails ("这个东西") are self-contained
    # within-utterance anaphora — not cross-turn context references.
    # Matching this pattern suppresses the has_context_dep_subj and
    # _needs_context contributors to under_specified (narrow; does NOT
    # suppress vague-verb, bare-action, or pronoun-question triggers,
    # so genuinely ambiguous prose still routes to ask).
    #
    # Each alternative requires BOTH a concrete term-anchor noun AND a
    # definitional-intent word, to avoid over-firing on general prose.
    ZH_PROSE_TECH_DEF_PATTERN = re.compile(
        # A: 术语|缩写|概念|名词|名字 + 叫|叫做|是|就是
        r"(?:术语|術語|缩写|縮寫|名词|名詞|名称|名稱)\s*(?:叫做|叫|是|就是)"
        # B: <termish> + 这个 + 词|概念|术语|名词
        r"|(?:[A-Za-z][A-Za-z0-9_\-]{1,30}|[一-鿿]{2,10})"
        r"\s*(?:这个|這個|此)\s*(?:词|詞|概念|术语|術語|名词|名詞)"
        # C: <termish> + 是什么意思|到底是什么|具体是什么|是啥
        r"|(?:[A-Za-z][A-Za-z0-9_\-]{1,30}|[一-鿿]{2,10})"
        r"\s*(?:是\s*什么\s*意思|是\s*什麼\s*意思"
        r"|到底\s*是\s*什么|到底\s*是\s*什麼"
        r"|具体\s*是\s*什么|具體\s*是\s*什麼"
        r"|具体\s*是\s*啥|具體\s*是\s*啥"
        r"|到底\s*是\s*啥)"
        # D: <termish> + 的? + 定义|定義 (definitional noun anchor)
        r"|(?:[A-Za-z][A-Za-z0-9_\-]{1,30}|[一-鿿]{2,10})"
        r"\s*(?:的\s*)?(?:定义|定義)(?!\s*是\s*否)"
        # E: 怎么?理解 + <termish>
        r"|(?:怎么|怎麼)\s*理解\s*(?:[A-Za-z][A-Za-z0-9_\-]|[一-鿿]{2,})",
        re.IGNORECASE,
    )

    SELF_REF_PATTERNS = re.compile(
        r"\b(you|your|yourself|mobius|möbius|this system|this ai|this assistant"
        r"|what are you|who are you|what can you do|how do you work"
        r"|what is mobius|tell me about yourself|describe yourself"
        r"|what do you do|how do you|what is your)\b"
        # System component names (Box 0/A/B/C/M, EAL, KVS, etc.)
        # Use (?<![a-zA-Z])...(?![a-zA-Z]) instead of \b to handle
        # ASCII terms adjacent to CJK characters (e.g. "EALとは")
        r"|(?<![a-zA-Z])box\s?[0abcm](?![a-zA-Z])|box0|box[abcm]"
        r"|(?<![a-zA-Z])(eal|kvs|tvs|mkr|kiwix|faiss)(?![a-zA-Z])"
        r"|(?<![a-zA-Z])(routing|appraisal|retrieval|wiki.?adapter)(?![a-zA-Z])"
        r"|(?<![a-zA-Z])(qk|ism|half.?step|answer.?entitlement|chain.?type)(?![a-zA-Z])"
        r"|(?<![a-zA-Z])(premise.?validity|premise.?audit|corpus.?harvest)(?![a-zA-Z])"
        r"|(?<![a-zA-Z])(knowledge.?source|query.?reform|v7\.?7)(?![a-zA-Z])"
        r"|あなた|きみ|おまえ|自己紹介|あなた自身|このシステム|このAI"
        # 2026-04-23 critical fix (cyc_20260423_critical_self_ref_kanji_fix):
        # kanji / polite / formal forms of the second-person pronoun, missing
        # pre-fix. Real-world UI symptom: "貴方の特徴を教えてください" was
        # routed to answer without Box 0 consultation because the hiragana-only
        # `あなた` pattern did not match. The eval datasets never exercised the
        # kanji form (0/6838 occurrences in full_20260421 + zh_focus_20260422),
        # masking the gap through pytest and judge-based eval. Additions are
        # strictly additive; existing patterns above unchanged.
        r"|貴方|貴女|貴殿|そなた|そちら"
        r"|あなた様|貴方様|貴殿様"
        r"|このシステム自身|当該システム|このシステム自体"
        r"|メビウス|モビウス"
        r"|ボックス[0abcmABCM０]"
        # Chinese self-referential terms
        # ZH Phase 2 — "你" / "您" alone is ubiquitous in polite Chinese
        # address ("请你...", "您好", "你能帮我..."), so bare pronouns are
        # NOT sufficient to flag self-ref. Require either a self-ref anchor
        # noun (你自己 / 这个系统 / 这个AI / 莫比乌斯 / 莫比烏斯) or one of the
        # explicit "what/who are you" interrogative forms below.
        r"|你自己|您自己|这个系统|這個系統|这个AI|這個AI|莫比乌斯|莫比烏斯"
        r"|你是(谁|誰|什么|什麼|哪)"
        r"|您是(谁|誰|什么|什麼|哪)"
        r"|你(?:能|会|會)做什么|你(?:能|会|會)做什麼"
        r"|你的(功能|能力|名字|名稱|作用)"
        r"|您的(功能|能力|名字|名稱|作用)"
        r"|(介绍|介紹|描述)(一下)?(你|您)(自己)?"
        r"|(你|您)(是一个|是一個)什么(样|樣)"
        r"|告诉我你|告訴我你"
        # cyc_20260424_zh_residual_cleanup — C-1a additive ZH self-ref:
        # bare "你叫什么名字" (what are you called) and "你使用什么架构"
        # (what architecture do you use) and their possessive
        # counterparts "你的特征" / "你的架构" were not matched by the
        # existing ZH alternations above, so identity_stability_zh
        # failed → Box 0 skipped → qwen3.5 base-model identity leaked
        # ("我叫 Qwen3.5"). Strictly additive; no existing pattern is
        # modified. Anchor-noun required (名字 / 特征 / 架构 / 模型 /
        # 系统 / 技术) so bare pronoun questions ("你使用这个软件吗")
        # do NOT false-positive to self-ref.
        r"|你叫什么(名字|名稱)?|您叫什么(名字|名稱)?"
        r"|你叫甚麼(名字|名稱)?|您叫甚麼(名字|名稱)?"
        r"|你的(特征|特点|特點|架构|架構)"
        r"|您的(特征|特点|特點|架构|架構)"
        r"|(你|您)(使用|运行|運行|基于|基於)(什么|什麼|甚么|甚麼)?(架构|架構|模型|系统|系統|技术|技術)",
        re.IGNORECASE,
    )

    # ── Referential ambiguity: deictic expressions without prior context ────
    # Loaded from config/referential_patterns.json at module init.
    _REF_AMBIG_PATTERNS: Optional[re.Pattern] = None

    _CONTEXT_DEP_PATTERNS: Optional[re.Pattern] = None

    @classmethod
    def _load_referential_patterns(cls) -> re.Pattern:
        """Build a compiled regex from config/referential_patterns.json (deictic)."""
        import json as _json
        _cfg_path = _Path(__file__).parent.parent.parent / "config" / "referential_patterns.json"
        fragments: list[str] = []
        if _cfg_path.exists():
            with open(_cfg_path, encoding="utf-8") as f:
                cfg = _json.load(f)
            for lang, pats in cfg.get("patterns", {}).items():
                fragments.extend(pats)
        if not fragments:
            fragments = [
                "あれ", "これ", "それ", "例の", "さっきの",
                r"\bthat thing\b", r"\bthis thing\b", r"\bthe thing\b",
                "那个", "这个",
            ]
        return re.compile("|".join(fragments), re.IGNORECASE)

    @classmethod
    def _load_context_dependent_patterns(cls) -> re.Pattern:
        """Build regex for context-dependent patterns (bare commands, continuations)."""
        import json as _json
        _cfg_path = _Path(__file__).parent.parent.parent / "config" / "referential_patterns.json"
        fragments: list[str] = []
        if _cfg_path.exists():
            with open(_cfg_path, encoding="utf-8") as f:
                cfg = _json.load(f)
            for group, pats in cfg.get("context_dependent", {}).items():
                fragments.extend(pats)
        if not fragments:
            fragments = [r"^やって$", r"^直して$", "続き", "もっと"]
        return re.compile("|".join(fragments), re.IGNORECASE)

    # ── Confirmatory / evaluative statement guard ──────────────────────────
    # Short feedback or evaluative statements that are NOT information requests.
    CONFIRMATORY_PATTERN = re.compile(
        # English
        r"^(this is|that'?s|that is|it'?s|it is)\s+"
        r"(great|good|fine|correct|right|wrong|amazing|excellent|perfect|bad|nice"
        r"|interesting|helpful|useful|clear|true|false|awesome|cool|ok|okay)\b"
        r"|\b(sounds good|i agree|i disagree|well done|thank you|thanks"
        r"|got it|understood|makes sense|i see|i like|i love|i prefer"
        r"|no problem|of course|sure|exactly|indeed|absolutely)\b"
        # Japanese
        r"|^(これは|それは|あれは)(素晴らし|すごい|いい|良い|正しい|間違い|面白い|便利|最高)"
        r"|^(それで|これで)(合って|OK|いい|良い|大丈夫|問題ない)"
        r"|^(了解|分かりました|わかりました|なるほど|ありがとう|承知)"
        r"|進めましょう|やりましょう|お願いします",
        re.IGNORECASE,
    )

    # ── Information request markers (for deictic ambiguity gating) ────────
    # Deictic ambiguity only triggers when the query seeks information.
    INFO_REQUEST_PATTERN = re.compile(
        r"[？?]$"                         # Ends with question mark
        r"|\b(tell|explain|describe|show|what|how|why|when|where|who)\b"
        r"|教えて|説明して|どう|何|なぜ|いつ|どこ|誰"
        r"|怎么|什么|为什么|哪里|谁",
        re.IGNORECASE,
    )

    # ── Reasoning / hypothetical query guard ──────────────────────────────
    REASONING_GUARD_PATTERN = re.compile(
        r"\bif\s+(?:it\s+takes|all|every|each|a\s+\w+\s+and\s+a\s+\w+)"
        r"|\bif\b.{5,60}\bhow\s+(?:long|many|much)\b"
        r"|\bif\b.{5,60}\bcan\b"
        r"|もし.{2,30}(?:なら|たら|とき|場合)"
        r"|如果.{2,20}(?:那么|会|能)",
        re.IGNORECASE,
    )

    CORRECTION_PATTERNS = re.compile(
        # English correction patterns
        r"\b(no,|that'?s wrong|that'?s incorrect|actually,|you'?re wrong"
        r"|incorrect|not correct|wrong answer|you said .+ but)"
        # Japanese correction patterns
        r"|違います|間違い|正しくは|ではなく|誤りです|訂正"
        # Chinese correction patterns
        r"|不对|错了|不正确|应该是|纠正",
        re.IGNORECASE,
    )

    # cyc_20260426_c2_context_aware_self_ref:
    # Bare aspect-question patterns that are *only* meaningful as
    # self-reference if the conversation context supplies the subject.
    # Used by the C-2 path in `evaluate()` together with a self-ref
    # check on `metadata["recent_user_queries"]` / `metadata["prev_user"]`.
    # Each alternation is a generic interrogative + system-aspect noun:
    # we INTENTIONALLY do not include proper nouns or domain-specific
    # entities here — those would short-circuit topic-shift detection
    # (e.g. "Krillin's wife?" must remain non-self-ref even after a
    # self-ref turn).
    CONTEXT_DEPENDENT_SELF_REF_PATTERNS = re.compile(
        # JA: bare aspect questions (どんな X / X は何 / X について / etc.)
        r"(どんな|どう(いう)?|どのよう(な|に))"
        r"(構造|構成|アーキテクチャ|仕組み|機能|能力|特徴|デザイン"
        r"|目的|意味|思想|哲学|名前|役割)"
        r"|(構造|アーキテクチャ|仕組み|機能|能力|特徴|デザイン"
        r"|目的|意味|思想|哲学|名前|役割)"
        r"(は(何|どう)|について|を教えて)"
        # EN: aspect words in interrogative form
        r"|\b(what|how|why)\s+(?:is|are|about)\s+"
        r"(your|its|the)?\s*"
        r"(architecture|structure|design|purpose|nature|"
        r"capability|capabilities|feature|features|"
        r"name|role|function)"
        # ZH: aspect questions
        r"|(架构|架構|结构|結構|功能|能力|设计|設計|本质|本質"
        r"|名字|目的|哲学|哲學|角色)"
        r"(是什么|是什麼|呢|怎么样|怎麼樣|如何)",
        re.IGNORECASE,
    )

    def evaluate(
        self,
        query: str,
        model_name: str = "phi4-mini:latest",
        metadata: dict | None = None,
    ) -> AppraisalState:
        q = query.lower().strip()
        notes: List[str] = []

        # ── Freshness ─────────────────────────────────────────────────────────
        freshness = any(term in q for term in self.FRESHNESS_TERMS)
        # Stage 7 — strong-freshness pattern catches "current price of X",
        # "whats the latest on X", "現在のXの状況", "Xの最新バージョン",
        # etc. — phrasings that denote freshness intent even when the
        # query lacks a REFERENT_ANCHOR match. When the pattern fires,
        # freshness_sensitive is forced True downstream.
        strong_freshness = bool(self.STRONG_FRESHNESS_PATTERN.search(query))
        if strong_freshness:
            notes.append("strong-freshness-pattern")
            # Ensure the base freshness flag is also set so downstream
            # consumers that look at it directly see the signal.
            freshness = True
        if freshness:
            notes.append("freshness-sensitive")

        # ── Safety ────────────────────────────────────────────────────────────
        safety = (
            "controlled substance" in q
            or any(term in q for term in self.SAFETY_TERMS)
        )
        if safety:
            notes.append("safety-relevant")

        # ── Referent detection ────────────────────────────────────────────────
        has_referent = bool(self.REFERENT_ANCHORS.search(q))

        # ── Under-specification ───────────────────────────────────────────────
        # CJK text has no spaces; count CJK characters as individual tokens.
        _cjk = sum(1 for c in q if '\u3000' <= c <= '\u9fff' or '\uf900' <= c <= '\ufaff')
        word_count      = len(q.split()) + _cjk if _cjk else len(q.split())
        has_pronoun_ref      = bool(self.PRONOUN_REF_PATTERN.search(q))
        has_vague_verb       = bool(self.UNDER_SPEC_PATTERNS.search(query))
        has_vague_best       = bool(self.VAGUE_BEST_PATTERN.search(query))
        has_context_dep_subj = bool(self.CONTEXT_DEPENDENT_SUBJECT.search(query))
        has_bare_action      = bool(self.BARE_ACTION_PATTERN.search(query))
        bare_freshness       = freshness and not has_referent and word_count <= 8
        is_definition_query  = bool(self.DEFINITION_QUERY_PATTERN.search(q))
        is_confirmatory      = bool(self.CONFIRMATORY_PATTERN.search(query))
        is_info_request      = bool(self.INFO_REQUEST_PATTERN.search(query))

        # ── Referential ambiguity (deictic without context) ───────────
        # Only applies when the query is an information request, not an
        # evaluative or confirmatory statement.
        if self._REF_AMBIG_PATTERNS is None:
            Appraiser._REF_AMBIG_PATTERNS = self._load_referential_patterns()
        has_deictic = (
            bool(self._REF_AMBIG_PATTERNS.search(query))
            and is_info_request
            and not is_confirmatory
        )

        # ── Context-dependent patterns (bare commands, continuations) ──
        if self._CONTEXT_DEP_PATTERNS is None:
            Appraiser._CONTEXT_DEP_PATTERNS = self._load_context_dependent_patterns()
        has_context_dep = (
            bool(self._CONTEXT_DEP_PATTERNS.search(query))
            and not is_confirmatory
        )

        # ── Combined context resolution (deictic OR context-dependent) ──
        _needs_context = has_deictic or has_context_dep
        _context_resolved = False
        if _needs_context:
            _has_session_prior = False
            if metadata:
                prev_user = metadata.get("prev_user", "") or ""
                prev_assistant = metadata.get("prev_assistant", "") or ""
                # Any non-empty prior turn counts as "this session has
                # history"; the 10-char minimum still gates whether the
                # prior is substantive enough to fully resolve on its own.
                _has_session_prior = bool(prev_user or prev_assistant)
                prev = prev_assistant + prev_user
                if prev and len(prev) > 10:
                    _context_resolved = True
            # ZH Phase 2 — Box M context resolution is the "cross-session
            # continuity" path, but requires at least some in-session
            # prior turn to avoid test-harness and fresh-session
            # contamination. Without a session prior, the shared Box M
            # index returns semantically-close but unrelated capsules
            # (observed on 167 ZH turn-0 ambiguity samples where Box M
            # top-3 score was ~0.86 against a JP or EN capsule), which
            # wrongly suppresses the `ask` route. Requiring a session
            # prior preserves the legitimate within-session use case.
            if (
                not _context_resolved
                and metadata
                and _has_session_prior
            ):
                box_m_ctx = metadata.get("box_m_context")
                if box_m_ctx and len(box_m_ctx) > 0:
                    _context_resolved = True
        if _needs_context and not _context_resolved:
            if has_deictic:
                notes.append("referential-ambiguity")
            if has_context_dep:
                notes.append("context-dependent")

        # ── Reasoning / hypothetical guard ────────────────────────────
        is_reasoning_query = bool(self.REASONING_GUARD_PATTERN.search(query))

        # ── Conversational / game context override ─────────────────────
        _conv_override = False
        if metadata:
            prev_assistant = metadata.get("prev_assistant", "")
            if prev_assistant:
                prev_lower = prev_assistant.lower()
                _GAME_MARKERS = [
                    "しりとり", "ゲーム", "遊び", "次は", "では次",
                    "いきます", "どうぞ", "あなたの番",
                    "shiritori", "game", "let's play", "your turn",
                    "次の言葉", "続けて",
                ]
                if any(m in prev_lower for m in _GAME_MARKERS):
                    _conv_override = True
                    notes.append("CONV_OVERRIDE")

        # Phase 3 (ZH) — prose-embedded tech-def anchor suppresses
        # context-dep / needs-context contributors only. Vague-verb,
        # bare-action, pronoun-question, freshness, and short-word triggers
        # remain active, so genuinely ambiguous ZH prose still routes to ask.
        _zh_prose_tech_def = bool(
            self.ZH_PROSE_TECH_DEF_PATTERN.search(query or "")
        )
        if _zh_prose_tech_def:
            notes.append("zh_prose_tech_def_anchor")

        under_specified = (
            (word_count < 4 and not is_definition_query and not _conv_override
             and not is_reasoning_query and not is_confirmatory)
            or (q.endswith("?") and has_pronoun_ref and not is_reasoning_query)
            or has_vague_verb
            or has_vague_best
            or (has_context_dep_subj and not _zh_prose_tech_def)
            or has_bare_action
            or bare_freshness
            or (_needs_context and not _context_resolved and not _zh_prose_tech_def)
        )
        if under_specified:
            notes.append("under-specified")
        if bare_freshness:
            notes.append("bare-freshness-no-referent")

        # ── Phase F v2+ format-anchored continuation exception ─────────
        # Narrow refinement of ambiguity typing:
        # A same-format continuation request ("Same format", "同じ形式で", etc.)
        # is treated as a BOUNDED CONTINUATION — not a fully under-specified
        # ask — when ALL of the following are true:
        #   (1) query carries a same-format / same-style / continue-in-same
        #       cue (is_same_format_request)
        #   (2) a prior assistant turn is available in metadata
        #   (3) the prior assistant turn yields a non-UNKNOWN format descriptor
        #   (4) safety is not relevant (structural safety still wins)
        #   (5) routing_engine is calling through the normal path with metadata
        #
        # When True, we suppress two specific false-positive under_specified
        # contributors:
        #   - bare_freshness (caused by a discourse-marker "now")
        #   - _needs_context when context is already resolved via prev_assistant
        # We do NOT broadly disable under_specified; other triggers (vague verbs,
        # vague best, bare actions, context-dep subjects, pronoun-refs) stay in
        # force. So genuinely ambiguous continuations still route to ask.
        _format_anchored_continuation = False
        _format_anchor_kind = ""
        _format_anchor_prev_assistant = ""
        if metadata:
            _format_anchor_prev_assistant = (metadata.get("prev_assistant") or "")
        if (not safety) and _format_anchor_prev_assistant:
            try:
                from .format_descriptor import (
                    is_same_format_request as _is_same_fmt_req,
                    describe_format as _describe_fmt,
                    FMT_UNKNOWN as _FMT_UNKNOWN,
                )
                if _is_same_fmt_req(query):
                    _fmt_desc = _describe_fmt(_format_anchor_prev_assistant)
                    if _fmt_desc is not None and _fmt_desc.kind != _FMT_UNKNOWN:
                        _format_anchored_continuation = True
                        _format_anchor_kind = _fmt_desc.kind
                        notes.append("format-anchored-continuation")
                        notes.append(f"format-anchor={_format_anchor_kind}")
                    else:
                        # Same-format requested but prior format unrecognized.
                        # Do NOT rescue; remain honest and keep under_specified.
                        notes.append("format-anchor-insufficient")
            except Exception:
                # Defensive: any failure in the helper leaves the ordinary
                # under_specified path intact.
                _format_anchored_continuation = False

        # Apply the narrow override. Safety is already excluded above; we also
        # preserve freshness when the query contains an explicit referent
        # (e.g. "current price of X, same format as before" — has_referent=True
        # → bare_freshness was False anyway; and freshness_with_ref below still
        # fires via has_referent).
        if _format_anchored_continuation:
            # Suppress only the specific false-positive contributors. Keep
            # explicit pronoun-with-question, vague-verb, vague-best, context-
            # dependent-subject and bare-action triggers intact so genuinely
            # ambiguous language still routes to ask.
            #
            # Suppressed contributors (narrow, justified):
            #   - bare_freshness          (discourse-marker "now" with short q)
            #   - _needs_context          (context IS anchored by prev_assistant)
            #   - word_count < 4          (e.g. "Same format." — the format-
            #                              anchor cue IS the bounded intent)
            if bare_freshness:
                freshness = False
            under_specified_after_exception = (
                (q.endswith("?") and has_pronoun_ref and not is_reasoning_query)
                or has_vague_verb
                or has_vague_best
                or has_context_dep_subj
                or has_bare_action
            )
            if under_specified and not under_specified_after_exception:
                # Only relax when the exception is solely responsible. If other
                # triggers are still active, keep under_specified=True.
                under_specified = False

        # ── Self-referential detection ────────────────────────────────────────
        # Suppress self_ref when the query is context-dependent and unresolved
        # (e.g. "Can you elaborate?" matches "you" but is actually a
        # continuation request, not a question about the system itself).
        _self_ref_raw = bool(self.SELF_REF_PATTERNS.search(query))

        # cyc_20260426_c2_context_aware_self_ref (Phase 2 Commit 12):
        # If the current query lacks a SELF_REF anchor but the last
        # user turn (or any of last-3 if metadata supplies them) DID
        # have one, AND the current query is a bare aspect-question
        # ("どんなアーキテクチャですか" / "what about its design") —
        # treat as context-dependent self-ref. Pure-additive: Fix 1's
        # SELF_REF_PATTERNS path is unchanged; the C-2 path only fires
        # when metadata is supplied and the bare-aspect pattern matches.
        if not _self_ref_raw and metadata:
            recent_q = metadata.get("recent_user_queries") or []
            if not recent_q and metadata.get("prev_user"):
                recent_q = [metadata["prev_user"]]
            _prior_was_self_ref = any(
                self.SELF_REF_PATTERNS.search(q or "")
                for q in recent_q
            )
            if _prior_was_self_ref and self.CONTEXT_DEPENDENT_SELF_REF_PATTERNS.search(query):
                _self_ref_raw = True
                notes.append("context-dependent-self-ref-c2")

        self_referential = _self_ref_raw and not (_needs_context and not _context_resolved)
        if self_referential:
            notes.append("self-referential")

        # ── User correction detection ────────────────────────────────────────
        user_correction = bool(self.CORRECTION_PATTERNS.search(query))
        if user_correction:
            notes.append("user-correction")
            freshness = True  # Force verify route via freshness_sensitive

        # ── High-stakes ───────────────────────────────────────────────────────
        high_stakes = any(term in q for term in self.HIGH_STAKES_TERMS)
        if high_stakes:
            notes.append("high-stakes-domain")

        # ── Structural stability check ────────────────────────────────────────
        is_structurally_stable = bool(self.STABLE_FACT_PATTERNS.search(q))

        # ── KVS computation (Phase A) ─────────────────────────────────────────
        kvs_result = compute_kvs(query, model_name)
        notes.append(
            f"kvs:tvs={kvs_result.tvs:.2f}"
            f",mkr_eff={kvs_result.mkr_eff:.2f}"
            f",class={kvs_result.model_class}"
        )
        if kvs_result.low_stakes_eligible:
            notes.append("KVS_PASS")
        else:
            notes.append(f"KVS_FAIL:{kvs_result.kvs_fail_reason}")

        # ── stable_fact: structural match AND KVS pass ────────────────────────
        # This is the key v7.5 gate:
        #   v3 only checked STABLE_FACT_PATTERNS (structural)
        #   v7.5 also requires KVS eligibility (model knowledge reliability)
        is_stable_fact = is_structurally_stable and kvs_result.low_stakes_eligible
        if is_structurally_stable and not kvs_result.low_stakes_eligible:
            notes.append("stable-structure-kvs-blocked")
        elif is_stable_fact:
            notes.append("low-stakes-stable")

        # ── Score computation ─────────────────────────────────────────────────
        # Stage 7 — strong_freshness fires freshness_with_ref semantics
        # directly (bypasses has_referent gate) when the query matches
        # STRONG_FRESHNESS_PATTERN and is not already scored as a
        # stable fact.
        freshness_with_ref = (
            freshness and has_referent and not is_stable_fact
        ) or (strong_freshness and not is_stable_fact)

        completeness   = 0.35 if (under_specified and not self_referential) else 0.8
        intent_clarity = 0.4  if (under_specified and not self_referential) else 0.85
        uncertainty    = 0.8  if freshness_with_ref else (0.55 if freshness else 0.25)
        if under_specified:
            uncertainty = max(uncertainty, 0.55)
        if is_stable_fact:
            uncertainty = 0.1

        # ── ISM intent classification (optional) ─────────────────────────────
        ism_state = None
        if _ism_available and _ism_profile is not None:
            try:
                ism_state = _ism_profile.retrieve(query)
                if ism_state and ism_state.confidence >= _ism_profile.CONFIDENCE_THRESHOLD:
                    notes.append(f"ism:intent={ism_state.intent_type}"
                                 f",conf={ism_state.confidence:.2f}")
                else:
                    notes.append("ism:low-confidence")
                    ism_state = None
            except Exception:
                notes.append("ism:error")

        # Phase E hook: detect meta-recall intent (summarize / coverage / continue / same format).
        # Deliberately local & lightweight; does not alter route taxonomy.
        try:
            from src.memory.meta_recall import detect_meta_recall_mode as _detect_meta
            _meta_recall_intent = bool(_detect_meta(query or ""))
        except Exception:
            _meta_recall_intent = False

        # Phase E hook: context_dependent surface flag. Derived from existing
        # under-specified / pronoun-reference signals without adding new rules.
        _q_raw = query or ""
        _context_dependent = bool(
            _q_raw and (
                bool(self.PRONOUN_REF_PATTERN.search(_q_raw))
                or bool(self.UNDER_SPEC_PATTERNS.search(_q_raw))
            )
        )

        # Phase G.8 — definitional-query detection. Compact, pattern-only.
        # Gated by: not self-ref, not freshness-sensitive, not user_correction,
        # not safety-relevant, not under-specified, and the query looks like
        # a bare definitional ask. Does NOT override stable_fact: a query
        # that is both is simply the stable-fact case (already handled).
        _q_stripped = (query or "").strip()
        _def_query_surface = bool(
            self.DEFINITION_QUERY_PATTERN.search(_q_stripped)
            or self.DEFINITION_QUERY_EXTENDED.search(_q_stripped)
        )
        _def_query_excluded = bool(
            _q_stripped
            and self.DEFINITION_QUERY_EXCLUSION.search(_q_stripped)
        )
        _def_query_length_ok = (
            0 < len(_q_stripped) <= self.DEFINITION_QUERY_MAX_CHARS
        )
        _definitional_query = bool(
            _q_stripped
            and _def_query_surface
            and _def_query_length_ok
            and not _def_query_excluded
            and not self_referential
            and not (freshness_with_ref or user_correction)
            and not safety
            and not under_specified
            and not is_stable_fact
        )
        if _definitional_query:
            notes.append("definitional_query")

        # Phase G.9 — continuity / save intent detection (pattern-only).
        try:
            from src.memory.meta_recall import detect_save_intent as _detect_save
            _continuity_save_intent = bool(_detect_save(query or ""))
        except Exception:
            _continuity_save_intent = False
        if _continuity_save_intent:
            notes.append("continuity_save_intent")

        return AppraisalState(
            completeness=completeness,
            uncertainty=uncertainty,
            freshness_sensitive=freshness_with_ref or user_correction,
            safety_relevant=safety,
            intent_clarity=intent_clarity,
            stable_fact=is_stable_fact,
            self_referential=self_referential,
            user_correction=user_correction,
            kvs=kvs_result,
            ism=ism_state,
            notes=notes,
            meta_recall_intent=_meta_recall_intent,
            context_dependent=_context_dependent,
            format_anchored_continuation=_format_anchored_continuation,
            definitional_query=_definitional_query,
            continuity_save_intent=_continuity_save_intent,
        )
