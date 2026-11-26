"""Keep only headlines likely to move markets, using weighted keywords (Vietnamese + English).

shortcut: keyword scoring, not real understanding; tune KEYWORDS if junk gets through or big news is missed.
"""
import re

STRONG, MEDIUM = 3, 2
MIN_SCORE = STRONG  # one strong keyword, or two medium ones

KEYWORDS = {
    # Vietnam
    "lãi suất": STRONG, "tỷ giá": STRONG, "ngân hàng nhà nước": STRONG, "nhnn": STRONG, "vn-index": STRONG,
    "vnindex": STRONG, "lạm phát": STRONG, "gdp": STRONG, "khối ngoại": STRONG, "nâng hạng": STRONG,
    "trái phiếu": STRONG, "bán tháo": STRONG, "chứng khoán": STRONG, "thuế đối ứng": STRONG, "fdi": STRONG,
    "thuế": MEDIUM, "cổ phiếu": MEDIUM, "tín dụng": MEDIUM, "giá vàng": MEDIUM, "xuất khẩu": MEDIUM,
    "ngân hàng": MEDIUM, "vốn hóa": MEDIUM, "giá xăng": MEDIUM, "giá dầu": MEDIUM, "margin": MEDIUM,
    # world
    "fed": STRONG, "fomc": STRONG, "powell": STRONG, "interest rate": STRONG, "rate cut": STRONG,
    "rate hike": STRONG, "inflation": STRONG, "cpi": STRONG, "payrolls": STRONG, "jobs report": STRONG,
    "recession": STRONG, "tariff": STRONG, "tariffs": STRONG, "treasury": STRONG, "yields": STRONG,
    "s&p 500": STRONG, "nasdaq": STRONG, "dow": STRONG, "sell-off": STRONG, "selloff": STRONG, "opec": STRONG,
    "earnings": MEDIUM, "stocks": MEDIUM, "oil": MEDIUM, "dollar": MEDIUM, "bitcoin": MEDIUM, "crypto": MEDIUM,
    "nvidia": MEDIUM, "chips": MEDIUM, "china": MEDIUM, "trade": MEDIUM, "gold": MEDIUM, "bank": MEDIUM,
    "credit rating": MEDIUM, "downgrade": MEDIUM,
}
_PATTERNS = [(re.compile(rf"(?<!\w){re.escape(k)}(?!\w)", re.IGNORECASE), w) for k, w in KEYWORDS.items()]


def impact_score(headline: str) -> int:
    """Sum of keyword weights; whole-word matches so 'dow' doesn't hit 'down'."""
    return sum(w for pattern, w in _PATTERNS if pattern.search(headline))


def market_headlines(news: dict[str, list[str]] | None, counts: dict[str, int]) -> list[tuple[str, str]]:
    """Up to sum(counts) (tag, headline) pairs scoring >= MIN_SCORE.

    Each feed gets its quota of highest-scoring headlines (ties keep feed order, i.e. newest first);
    leftover slots go to the next best from any feed.
    """
    scored = {tag: sorted(((impact_score(h), i, h) for i, h in enumerate(heads) if impact_score(h) >= MIN_SCORE),
                          key=lambda t: (-t[0], t[1]))
              for tag, heads in (news or {}).items()}
    picked = [(tag, h) for tag, count in counts.items() for _, _, h in scored.get(tag, [])[:count]]
    spare = sorted(((s, i, tag, h) for tag, items in scored.items() for s, i, h in items if (tag, h) not in picked),
                   key=lambda t: (-t[0], t[1]))
    picked += [(tag, h) for _, _, tag, h in spare[:sum(counts.values()) - len(picked)]]
    order = list(counts)
    return sorted(picked, key=lambda p: order.index(p[0]) if p[0] in order else len(order))
