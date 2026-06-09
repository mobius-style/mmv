"""
kvs.py — Knowledge Volatility Score (KVS) for Möbius v7.5 Phase A

Implements Dynamic KVS Guard (Minimum Viable version):
  MKR_eff = clip(MKR_base - R_fresh - E_hist, 0, 1)

Phase A (this module):
  - TVS estimation from query structure
  - MKR_base from model-class priors
  - R_fresh (freshness/recency penalty)
  - E_hist (optional, domain-pair failure history)

Phase B (future):
  - H_pred (entropy-like instability proxy — requires logprobs)
  - V_regen (regeneration variance — requires multiple inference passes)
  - C_conflict (answer-justification conflict — requires extra inference)
  - RGC phi_t dynamic update

References:
  Paper II: Toward Knowledge Volatility-Aware Routing (Toeda, 2026)
  Paper II-derivative: Beyond Stable Fact Detection (Toeda, 2026)
  Volume IV: Answer Entitlement Architecture (Toeda, 2026)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ── Model class definitions ────────────────────────────────────────────────────

MODEL_CLASS_MICRO    = "micro"     # <= 7B
MODEL_CLASS_SMALL    = "small"     # 8B-13B
MODEL_CLASS_MID      = "mid"       # 14B-34B
MODEL_CLASS_FRONTIER = "frontier"  # hosted frontier

# MKR_base priors (Appendix A of Paper II-derivative)
# These are disciplined initialization points, NOT empirical truths.
# Domain-indexed calibration is Phase B work.
MKR_BASE_PRIORS: dict[str, float] = {
    MODEL_CLASS_MICRO:    0.50,   # < 7B — prefer verify outside textbook facts
    MODEL_CLASS_SMALL:    0.63,   # 8B-13B — allow stable-route candidacy w/ strong guard
    MODEL_CLASS_MID:      0.76,   # 14B-34B — eligible for more frequent LOW_STAKES_STABLE
    MODEL_CLASS_FRONTIER: 0.85,   # hosted — high prior, still subject to downward revision
}

# MKR threshold: MKR_eff must be >= this to remain LOW_STAKES_STABLE eligible
MKR_THRESHOLD = 0.52

# TVS threshold: TVS must be < this for LOW_STAKES_STABLE eligibility
TVS_THRESHOLD = 0.30


# ── Known model → class mapping ────────────────────────────────────────────────
# Add entries as new models are tested.
# Format: lowercase model name substring → class

MODEL_CLASS_MAP: list[tuple[str, str]] = [
    # Micro / small local open models (<= 7B)
    ("phi4-mini",        MODEL_CLASS_MICRO),
    ("phi-4-mini",       MODEL_CLASS_MICRO),
    ("phi4mini",         MODEL_CLASS_MICRO),
    ("llama3.2:1b",      MODEL_CLASS_MICRO),
    ("llama3.2:3b",      MODEL_CLASS_MICRO),
    ("gemma:2b",         MODEL_CLASS_MICRO),
    ("gemma2:2b",        MODEL_CLASS_MICRO),
    ("mistral:7b",       MODEL_CLASS_MICRO),
    ("qwen2.5:3b",       MODEL_CLASS_MICRO),
    # Small-to-mid (8B-13B)
    ("llama3:8b",        MODEL_CLASS_SMALL),
    ("llama3.1:8b",      MODEL_CLASS_SMALL),
    ("llama3.3:8b",      MODEL_CLASS_SMALL),
    ("mistral:8b",       MODEL_CLASS_SMALL),
    ("phi4:14b",         MODEL_CLASS_SMALL),
    ("phi4:latest",      MODEL_CLASS_SMALL),
    ("qwen2.5:14b",      MODEL_CLASS_SMALL),
    # Mid-to-large (14B-34B)
    ("llama3:70b",       MODEL_CLASS_MID),
    ("llama3.1:70b",     MODEL_CLASS_MID),
    ("mixtral",          MODEL_CLASS_MID),
    ("gpt-oss",          MODEL_CLASS_MID),   # gpt-oss-20b
    ("qwen2.5:32b",      MODEL_CLASS_MID),
    # Frontier hosted
    ("gpt-4",            MODEL_CLASS_FRONTIER),
    ("claude",           MODEL_CLASS_FRONTIER),
    ("gemini",           MODEL_CLASS_FRONTIER),
]

def get_model_class(model_name: str) -> str:
    """Map a model name to its size class."""
    mn = model_name.lower()
    for pattern, cls in MODEL_CLASS_MAP:
        if pattern in mn:
            return cls
    # Fallback: try to detect B-count from name
    m = re.search(r"(\d+)b", mn)
    if m:
        b = int(m.group(1))
        if b <= 7:    return MODEL_CLASS_MICRO
        if b <= 13:   return MODEL_CLASS_SMALL
        if b <= 34:   return MODEL_CLASS_MID
        return MODEL_CLASS_FRONTIER
    # Unknown — conservative fallback
    return MODEL_CLASS_MICRO


# ── TVS estimation ─────────────────────────────────────────────────────────────
# TVS = Temporal Volatility Score for query q
# Approximates delta_E_obj (object-level decay rate of the fact)

# High-volatility anchors (TVS → high)
TVS_HIGH_PATTERNS = re.compile(
    r"\b("
    r"current|currently|today|latest|recent|recently|now|as of|this week"
    r"|this month|last month|yesterday|just|new|updated|changed|live"
    # Stage 4 — keep aligned with FRESHNESS_TERMS in appraisal.py
    r"|lately|these days|nowadays|trending"
    r"|real.?time|price|rate|yield|inflation|unemployment|market"
    r"|prime minister|president of|secretary of|chancellor of"
    r"|ceo of|director of|speaker of|secretary.general"
    r"|federal reserve|bank of england|bank of japan"
    r"|brent crude|crude oil|exchange rate|stock"
    r")\b"
    # ── JA: Corpus-derived high-volatility signals (Sprint 2) ─────
    r"|現在の|最新の|最近の|今日の|今の|いまの"
    # Stage 4 — past-relative + time-of-day freshness
    r"|先週|先月|去年|昨年|昨日|今朝|今夜|今晩|このところ|このごろ"
    r"|為替|株価|金利|物価|相場|時価"
    r"|推移|変動|上昇|下落|急騰|急落"
    r"|改正|改定|更新|増減|転換"
    r"|首相|大統領|総裁|議長|知事"
    # ── ZH: High-volatility signals ───────────────────────────────
    r"|现在的|最新的|最近的|今天的"
    # Stage 4 — past-relative
    r"|上周|上週|上个月|上個月|昨天"
    r"|汇率|股价|利率|物价"
    # ── Financial realtime patterns (force HIGH TVS) ─────────────
    r"|\b(bitcoin|btc|ethereum|eth|crypto|cryptocurrency"
    r"|nasdaq|s&p|dow jones|nikkei|日経|ftse|dax"
    r"|usd/?jpy|eur/?usd|gbp/?usd|forex"
    r"|gold price|oil price|crude price"
    r"|market cap|futures|options price"
    r"|bond yield|treasury yield"
    # Stage 5 — news/tech-version anchors kept in sync with REFERENT_ANCHORS
    r"|news|headlines?|llvm|gcc|clang|kubernetes|docker"
    r")\b"
    r"|ビットコイン|イーサリアム|仮想通貨|暗号資産"
    r"|原油価格|金価格|先物"
    # Stage 5 — JP/ZH news anchors
    r"|ニュース|経済ニュース|見出し|速報|新闻|头条",
    re.IGNORECASE,
)

# Mid-volatility anchors — conventional wisdom signals (TVS mid)
# Sprint 2 corpus-derived: not used in scoring (Phase B integration).
# Kept as structured data for future SudachiPy-based TVS estimator.
TVS_MID_PATTERNS = re.compile(
    r"と言われている|とされている|とされる"
    r"|一般に|広く知られている|考えられている"
    r"|見なされている|思われている"
    r"|と言われて|とされて|と考えられて"
    r"|一般的に|通常|一般的には",
    re.IGNORECASE,
)

# Low-volatility anchors — structural stability markers (TVS → low)
TVS_LOW_PATTERNS = re.compile(
    r"\b("
    r"capital of|chemical symbol|speed of light|speed of sound"
    r"|atomic number|atomic mass|boiling point|melting point|molecular weight"
    r"|gravitational constant|gravitational|avogadro|planck|circumference"
    r"|established in|founded in|invented in|invented by|created in"
    r"|independence|treaty|world war|civil war"
    r"|in what year was|in what year did|when was .* established"
    r"|when was .* founded|when was .* invented"
    r"|how many amendments|how many articles"
    r"|permanent members|founding members|founding treaty"
    r"|official language of|official currency of"
    r"|established by the tax cuts|standard vat rate"
    r"|standard corporate tax|pythagorean"
    r"|theorem|formula|equation|prime number"
    r"|pi "
    r")\b"
    # ── JA: 科学定数・物理 ──────────────────────────────────────
    r"|沸点|融点|蒸発点|凝固点|昇華点"
    r"|光の速度|光速度|音速|音の速さ"
    r"|重力加速度|万有引力定数|プランク定数"
    r"|アボガドロ定数|ボルツマン定数|気体定数"
    r"|原子番号|原子量|分子量|元素記号"
    r"|密度|比重|屈折率|比熱"
    r"|電気抵抗|電磁気|静電気"
    r"|の化学式|の分子式|の元素"
    # ── JA: 数学 ──────────────────────────────────────────────
    r"|円周率|黄金比|フィボナッチ"
    r"|ピタゴラスの定理|三平方の定理"
    r"|二次方程式の解の公式|微分積分の公式"
    r"|素数|偶数|奇数|公約数|公倍数"
    r"|対数|指数|べき乗|平方根"
    r"|の面積の求め方|の体積の求め方|の公式"
    # ── JA: 歴史的事実 ────────────────────────────────────────
    r"|が建国されたのは|が独立したのは|が設立されたのは"
    r"|が始まったのは|が終わったのは|が起きたのは"
    r"|が発明されたのは|が発見されたのは|が創設されたのは"
    r"|第一次世界大戦|第二次世界大戦|太平洋戦争|日露戦争"
    r"|明治維新|大政奉還|江戸幕府|徳川|織田信長|豊臣秀吉"
    r"|ルネサンス|産業革命|フランス革命|アメリカ独立"
    r"|は何年に|は西暦何年|は何世紀"
    # ── JA: 地理・地名 ────────────────────────────────────────
    r"|の首都は|の首都はどこ"
    r"|の最高峰|の最長河川|の最大湖"
    r"|富士山|エベレスト|アルプス|ヒマラヤ|アンデス"
    r"|アマゾン川|ナイル川|ミシシッピ川|長江|黄河"
    r"|太平洋|大西洋|インド洋|北極海|南極海"
    r"|の面積は|の広さは|の国土面積"
    r"|県庁所在地|都道府県庁|行政区画"
    # ── JA: フィクション・キャラクター ─────────────────────────
    r"|の妻は|の夫は|の配偶者は"
    r"|の必殺技は|の能力は|の特技は"
    r"|の悪魔の実|の斬魄刀|の卍解|の卍解は"
    r"|の声優は|の中の人は"
    r"|の師匠は|の弟子は|の仲間は"
    r"|は何話で|は何巻で|は何話に登場"
    r"|ドラゴンボール|ワンピース|ナルト|鬼滅の刃"
    r"|進撃の巨人|呪術廻戦|ハンターハンター"
    r"|エヴァンゲリオン|ガンダム|マクロス"
    r"|ジョジョの奇妙な冒険|幽遊白書|るろうに剣心"
    r"|ハリーポッター|指輪物語|ナルニア国"
    r"|スターウォーズ|マーベル|DCコミックス"
    r"|クリリン|悟空|ルフィ|ナミ|サスケ|サクラ|炭治郎|禰豆子"
    r"|キリト|アスナ|レム|エミリア|リゼロ|このすば|転スラ"
    r"|ポケモン|ピカチュウ|マリオ|ゼルダ|リンク|ソニック"
    r"|セーラームーン|コナン|ジョジョ"
    # ── JA: 生物・医学常識 ────────────────────────────────────
    r"|人間の体温|平熱|正常体温"
    r"|人体の骨の数|骨格|関節の数"
    r"|血液型は|ABO式血液型|Rh式血液型"
    r"|心拍数|脈拍|血圧の正常値"
    r"|DNA|染色体|遺伝子|ゲノム"
    r"|の学名は|の分類は|の生息地は"
    r"|哺乳類|爬虫類|両生類|甲殻類"
    r"|光合成|呼吸|代謝|消化"
    # ── JA: 日常知識・料理 ────────────────────────────────────
    r"|の作り方|の調理法|の料理法|のレシピ"
    r"|の保存方法|の賞味期限|の消費期限"
    r"|に合う調味料|に合うソース|をかけると"
    r"|の栄養素|のカロリー|の成分"
    r"|茹で時間|焼き時間|蒸し時間"
    r"|の洗い方|の干し方|の手入れ方法|のメンテナンス"
    r"|電池の交換|の取り付け方|の使い方"
    # ── JA: 言語・文化 ────────────────────────────────────────
    r"|の語源は|の由来は|の意味は"
    r"|の漢字は|の書き方は|の読み方は"
    r"|の英語は|の日本語は|の中国語は"
    r"|ことわざ|慣用句|四字熟語"
    r"|の発祥は|の起源は|の歴史は"
    # ── JA: スポーツ・競技ルール ──────────────────────────────
    r"|のルールは|のルール説明|競技ルール"
    r"|野球の|サッカーの|バスケットボールの"
    r"|オリンピック種目|パラリンピック種目"
    r"|の距離は|のコースは|の制限時間は"
    # ── JA: 法律・制度（安定的なもの） ───────────────────────
    r"|の定義は|法律上の定義|法的な意味"
    r"|著作権の|特許の|商標の"
    r"|憲法の|民法の|刑法の"
    # ── JA: 単位・計量 ────────────────────────────────────────
    r"|何キロメートル|何メートル|何センチ"
    r"|何キログラム|何グラム|何ミリグラム"
    r"|何リットル|何ミリリットル|何cc"
    r"|摂氏|華氏|ケルビン"
    r"|光年|天文単位|パーセク"
    # ── EN: Fiction / anime / manga / game ────────────────────
    r"|\b(anime|manga|light novel|visual novel|isekai"
    r"|dragon ball|one piece|naruto|attack on titan|demon slayer"
    r"|bleach|fullmetal|studio ghibli|pokemon|sailor moon"
    r"|goku|luffy|eren|piccolo|vegeta|sasuke|hinata"
    r"|wife of|husband of|devil fruit|jutsu|quirk)\b"
    # ── EN: Everyday knowledge ────────────────────────────────
    r"|\b(cooking|recipe|ingredient|seasoning|how to cook|how to make)\b"
    # ── ZH: Fiction ───────────────────────────────────────────
    r"|动漫|漫画|火影|海贼王|龙珠|鬼灭|进击"
    r"|的妻子|的必杀技",
    re.IGNORECASE,
)

def estimate_tvs(query: str) -> float:
    """
    Estimate Temporal Volatility Score for query.
    Returns a float in [0, 1]:
      0.0 = structurally stable (physical constant, historical date)
      1.0 = high temporal volatility (current officeholder, live price)

    Sprint 2: TVS_MID_PATTERNS are detected but do not yet affect the score.
    They are logged via the `_last_tvs_mid` module-level flag for tracing.
    """
    q = query.lower()

    has_high = bool(TVS_HIGH_PATTERNS.search(q))
    has_low  = bool(TVS_LOW_PATTERNS.search(q))

    # Sprint 2: detect MID for logging (no score effect yet)
    global _last_tvs_mid
    _last_tvs_mid = bool(TVS_MID_PATTERNS.search(q))

    if has_low and not has_high:
        return 0.10   # Structurally stable, no freshness terms
    if has_low and has_high:
        return 0.25   # Stable structure but freshness term present
    if has_high and not has_low:
        return 0.85   # Clear freshness marker, no stability anchor
    # Neither: default moderate
    return 0.45

# Module-level flag for MID detection tracing (Sprint 2)
_last_tvs_mid: bool = False


# ── R_fresh: recency/freshness penalty ───────────────────────────────────────
# Increases when query contains direct recency pressure.
# Applied as downward revision to MKR_base.

RECENCY_PRESSURE_PATTERNS = re.compile(
    r"\b("
    r"current|currently|today|right now|as of|latest|live"
    r"|real.?time|this week|this month|yesterday|just announced"
    r")\b"
    # ── JA/ZH recency pressure (Sprint 2) ─────────────────────────
    r"|現在の|今の|今日の|最新の|最近の|いまの"
    r"|现在的|今天的|最新的|最近的",
    re.IGNORECASE,
)

# Patterns that immunize against R_fresh penalty
# Queries matching these are structurally frozen — freshness terms are
# incidental ("currently have" in constitutional fact questions, etc.)
R_FRESH_EXEMPT_PATTERNS = re.compile(
    r"\b("
    r"how many amendments|how many justices|how many articles"
    r"|speed of light|chemical symbol|atomic number|atomic mass"
    r"|capital of|official language of|official currency of"
    r"|in what year was .* invented|in what year was .* established"
    r"|in what year did .* join"
    r")\b",
    re.IGNORECASE,
)


def estimate_r_fresh(query: str) -> float:
    """
    Estimate freshness/recency penalty.
    Returns a value in [0, 0.30] to be subtracted from MKR_base.
    Queries matching R_FRESH_EXEMPT_PATTERNS are immune.
    """
    q = query.lower()
    # Structurally frozen facts: freshness terms are incidental
    if R_FRESH_EXEMPT_PATTERNS.search(q):
        return 0.0
    matches = len(RECENCY_PRESSURE_PATTERNS.findall(q))
    if matches == 0:
        return 0.0
    if matches == 1:
        return 0.10
    return min(0.30, matches * 0.10)


# ── E_hist: historical failure penalty (optional) ─────────────────────────────
# Tracks model-domain pair verification failures.
# Simple in-memory dict — not persisted across sessions (Phase B extension).

_failure_history: dict[tuple[str, str], int] = {}

def record_verification_failure(model_class: str, domain: str) -> None:
    """Record a verification failure for a model-domain pair."""
    key = (model_class, domain)
    _failure_history[key] = _failure_history.get(key, 0) + 1

def estimate_e_hist(model_class: str, domain: str) -> float:
    """
    Estimate historical failure penalty for model-domain pair.
    Returns a value in [0, 0.20].
    """
    key = (model_class, domain)
    failures = _failure_history.get(key, 0)
    return min(0.20, failures * 0.05)


# ── Domain classification ──────────────────────────────────────────────────────

DOMAIN_PATTERNS: list[tuple[str, str]] = [
    (r"\b(capital|country|continent|ocean|river|mountain)\b", "geography"),
    (r"\b(speed of light|atomic|chemical symbol|element|molecule|boiling|melting)\b", "physical_science"),
    (r"\b(amendment|constitution|founding|treaty|established|founded|invented|joined|join the|signed|in what year did)\b", "historical_institutional"),
    (r"\b(prime minister|president|secretary|chancellor|speaker|ceo|director)\b", "political_officeholder"),
    (r"\b(inflation|unemployment|gdp|yield|rate|price|market|stock|crude)\b", "economic_indicator"),
    (r"\b(official language|official currency|capital city)\b", "stable_institutional"),
]

def classify_domain(query: str) -> str:
    q = query.lower()
    for pattern, domain in DOMAIN_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            return domain
    return "general"


# ── KVS computation ────────────────────────────────────────────────────────────

@dataclass
class KVSResult:
    tvs:            float           # Temporal Volatility Score [0,1]
    mkr_base:       float           # Base MKR prior [0,1]
    r_fresh:        float           # Freshness penalty
    e_hist:         float           # Historical failure penalty
    mkr_eff:        float           # Effective MKR after downward revision [0,1]
    model_class:    str             # Model class string
    domain:         str             # Estimated domain
    low_stakes_eligible: bool       # True if LOW_STAKES_STABLE is eligible
    reason_codes:   list[str] = field(default_factory=list)

    @property
    def kvs_fail_reason(self) -> str:
        """Primary reason for KVS failure, if any."""
        if self.tvs >= TVS_THRESHOLD:
            return "KVS_FAIL_TVS"
        if self.mkr_eff < MKR_THRESHOLD:
            if self.r_fresh > 0.05:
                return "KVS_DOWNREV_FRESH"
            if self.e_hist > 0.0:
                return "KVS_DOWNREV_HIST"
            return "KVS_FAIL_MKR_PRIOR"
        return ""


# Domain-level MKR adjustment
# Applied on top of model-class prior.
# Positive = easier to know reliably; negative = higher confusion risk.
DOMAIN_MKR_ADJUSTMENT: dict[str, float] = {
    "physical_science":      +0.20,  # speed of light, chemical symbols — near-universal
    "geography":             +0.15,  # capitals, oceans — well-trained
    "historical_institutional": +0.12,  # founding dates / accession years
    "stable_institutional":  +0.10,  # official language/currency
    "political_officeholder": -0.10,  # high staleness risk
    "economic_indicator":    -0.15,  # live data, high staleness
    "general":               +0.00,  # neutral
}

# Numerically confusable fact classes get extra penalty
# (e.g., "how many X" where current vs historical counts differ)
NUMERICAL_CONFUSION_PATTERN = re.compile(
    r"\b(how many|number of|count of)\b.*\b(members|seats|states|countries|nations"
    r"|amendments|justices|permanent|founding|original)\b",
    re.IGNORECASE,
)

def estimate_domain_adjustment(query: str, domain: str) -> float:
    base_adj = DOMAIN_MKR_ADJUSTMENT.get(domain, 0.0)
    # Extra penalty for numerical confusion risk
    if re.search(NUMERICAL_CONFUSION_PATTERN, query):
        base_adj -= 0.10
    return base_adj


def compute_kvs(query: str, model_name: str) -> KVSResult:
    """
    Compute KVS for (query, model) pair.

    Phase A implementation:
      MKR_eff = clip(MKR_base + domain_adj - R_fresh - E_hist, 0, 1)
      LOW_STAKES_STABLE eligible iff TVS < TVS_THRESHOLD AND MKR_eff >= MKR_THRESHOLD

    Domain adjustment is positive for well-trained stable domains (geography,
    physical science) and negative for confusion-prone domains (political,
    numerical membership counts).

    Returns KVSResult with all intermediate values for tracing.
    """
    model_class = get_model_class(model_name)
    domain      = classify_domain(query)

    tvs         = estimate_tvs(query)
    mkr_base    = MKR_BASE_PRIORS[model_class]
    domain_adj  = estimate_domain_adjustment(query, domain)
    r_fresh     = estimate_r_fresh(query)
    e_hist      = estimate_e_hist(model_class, domain)

    mkr_eff = max(0.0, min(1.0, mkr_base + domain_adj - r_fresh - e_hist))

    tvs_ok  = tvs < TVS_THRESHOLD
    mkr_ok  = mkr_eff >= MKR_THRESHOLD
    eligible = tvs_ok and mkr_ok

    # Reason codes
    codes = []
    if eligible:
        codes.append("KVS_PASS_LOW_TVS_HIGH_MKR")
    else:
        if not tvs_ok:
            codes.append("KVS_FAIL_TVS")
        if not mkr_ok:
            if r_fresh > 0.05:
                codes.append("KVS_DOWNREV_FRESH")
            elif e_hist > 0.0:
                codes.append("KVS_DOWNREV_HIST")
            else:
                codes.append("KVS_FAIL_MKR_PRIOR")

    return KVSResult(
        tvs=round(tvs, 3),
        mkr_base=round(mkr_base, 3),
        r_fresh=round(r_fresh, 3),
        e_hist=round(e_hist, 3),
        mkr_eff=round(mkr_eff, 3),
        model_class=model_class,
        domain=domain,
        low_stakes_eligible=eligible,
        reason_codes=codes,
    )
