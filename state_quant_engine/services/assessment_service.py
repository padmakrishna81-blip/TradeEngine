"""Trend and Risk assessment using free public web data — no API key required."""
from __future__ import annotations
from typing import List, Dict, TYPE_CHECKING
import re
import time
from loguru import logger

if TYPE_CHECKING:
    from state_quant_engine.services.scanner_service import ScanResult


# ---------------------------------------------------------------------------
# Helpers — lightweight web fetches
# ---------------------------------------------------------------------------

def _fetch(url: str, timeout: int = 8) -> str:
    """GET a URL and return the text, silently empty on failure."""
    try:
        import requests
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


def _google_news_headlines(query: str) -> List[str]:
    """Fetch headline snippets from Google News RSS for a query."""
    q = query.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={q}+site:moneycontrol.com+OR+site:economictimes.com&hl=en-IN&gl=IN&ceid=IN:en"
    text = _fetch(url)
    titles = re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", text)
    # skip the first (feed title)
    return [t.strip() for t in titles[1:6] if t.strip()]


def _yahoo_finance_summary(ticker: str) -> str:
    """Fetch the short summary from Yahoo Finance for a ticker."""
    url = f"https://finance.yahoo.com/quote/{ticker}"
    text = _fetch(url)
    # Extract analyst recommendation if present
    m = re.search(r'"recommendationKey":"([^"]+)"', text)
    rec = m.group(1) if m else ""
    m2 = re.search(r'"recommendationMean":\{"raw":([\d.]+)', text)
    mean = m2.group(1) if m2 else ""
    m3 = re.search(r'"shortName":"([^"]+)"', text)
    name = m3.group(1) if m3 else ticker
    return f"{name} | analyst_rec={rec} mean={mean}"


def _moneycontrol_news(symbol_bare: str) -> List[str]:
    """Try to get recent news from Moneycontrol search."""
    q = symbol_bare.replace(".", "+")
    url = f"https://www.moneycontrol.com/news/tags/{q}.html"
    text = _fetch(url)
    titles = re.findall(r'<h2[^>]*class="[^"]*article[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', text)
    if not titles:
        titles = re.findall(r'<a[^>]+title="([^"]+)"[^>]*class="[^"]*news[^"]*"', text)
    return [t.strip() for t in titles[:5] if t.strip()]


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def _score_trend(headlines: List[str], yahoo_summary: str, symbol: str) -> tuple[str, str]:
    """
    Simple keyword scoring to classify Bullish / Bearish / Neutral.
    Returns (trend, reason).
    """
    positive_kw = [
        "upgrade", "buy", "outperform", "strong", "beat", "surpass", "record",
        "high", "growth", "profit", "positive", "optimistic", "bullish",
        "rally", "surge", "gain", "boost", "expansion", "target raised",
        "strong buy", "overweight", "accumulate",
    ]
    negative_kw = [
        "downgrade", "sell", "underperform", "weak", "miss", "below", "fall",
        "loss", "negative", "bearish", "drop", "decline", "cut", "downside",
        "concern", "risk", "debt", "fraud", "penalty", "suspension",
        "underweight", "reduce", "avoid",
    ]

    all_text = " ".join(headlines + [yahoo_summary]).lower()

    pos = sum(1 for k in positive_kw if k in all_text)
    neg = sum(1 for k in negative_kw if k in all_text)

    # Yahoo analyst recommendation carries more weight
    rec = re.search(r"analyst_rec=(\w+)", yahoo_summary)
    if rec:
        r = rec.group(1).lower()
        if r in ("buy", "strong_buy", "outperform", "overweight"):
            pos += 3
        elif r in ("sell", "underperform", "underweight"):
            neg += 3

    if pos > neg + 1:
        trend = "Bullish"
        reason = _top_phrase(headlines, positive_kw) or "Positive analyst outlook and news flow"
    elif neg > pos + 1:
        trend = "Bearish"
        reason = _top_phrase(headlines, negative_kw) or "Negative news flow or analyst downgrades"
    else:
        trend = "Neutral"
        reason = "Mixed signals; no strong directional catalyst"

    return trend, reason[:80]


def _score_risk(ind_data: Dict, trend: str, asset_type: str) -> tuple[str, str]:
    """
    Classify SAFE / VOLATILE / RISKY from technical indicator data + trend.
    Returns (risk, reason).
    """
    score = 0  # higher = riskier

    rsi   = ind_data.get("rsi", 50)
    adx   = ind_data.get("adx", 20)
    atr_pct = ind_data.get("atr_pct", 2)
    dd    = ind_data.get("drawdown_pct", 0)
    rs    = ind_data.get("relative_strength", 1.0)
    above_200 = ind_data.get("above_200ema", True)

    reasons = []

    # Drawdown risk
    if dd < -20:
        score += 3
        reasons.append(f"deep drawdown {dd:.0f}%")
    elif dd < -10:
        score += 1
        reasons.append(f"moderate drawdown {dd:.0f}%")

    # Volatility (ATR)
    if atr_pct > 3.5:
        score += 2
        reasons.append("high volatility")
    elif atr_pct > 2.0:
        score += 1

    # Trend alignment
    if not above_200:
        score += 2
        reasons.append("below 200 EMA")

    # Relative strength
    if rs < 0.85:
        score += 2
        reasons.append("underperforming market")

    # Bearish trend adds risk
    if trend == "Bearish":
        score += 2
    elif trend == "Bullish":
        score = max(0, score - 1)

    # ETFs are generally safer
    if asset_type == "ETF":
        score = max(0, score - 1)

    if score <= 2:
        risk = "SAFE"
        reason = "Strong fundamentals; within normal range" if not reasons else f"Minor concerns: {', '.join(reasons[:2])}"
    elif score <= 5:
        risk = "VOLATILE"
        reason = ", ".join(reasons[:2]) if reasons else "Sector or technical headwinds"
    else:
        risk = "RISKY"
        reason = ", ".join(reasons[:3]) if reasons else "Multiple risk factors present"

    return risk, reason[:80]


def _top_phrase(headlines: List[str], keywords: List[str]) -> str:
    """Return the most relevant headline snippet (≤12 words)."""
    for h in headlines:
        for kw in keywords:
            if kw in h.lower():
                words = h.split()
                return " ".join(words[:12]) + ("…" if len(words) > 12 else "")
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess_trend_and_risk(results: List["ScanResult"]) -> List["ScanResult"]:
    """
    Enrich each ScanResult with Trend and Risk using free public web data.
    No API key required — uses Google News RSS, Yahoo Finance, Moneycontrol.
    """
    for r in results:
        if r.error:
            r.trend = "N/A"
            r.risk  = "N/A"
            r.trend_reason = "Scan error"
            r.risk_reason  = "Scan error"
            continue

        try:
            # Strip exchange suffix for news search (e.g. RELIANCE.NS → RELIANCE)
            bare = r.symbol.split(".")[0]

            # 1. Fetch headlines
            headlines = _google_news_headlines(f"{bare} NSE stock")
            if not headlines:
                headlines = _moneycontrol_news(bare)
            time.sleep(0.3)  # polite delay

            # 2. Yahoo Finance analyst summary
            yahoo = _yahoo_finance_summary(r.symbol)
            time.sleep(0.2)

            # 3. Trend scoring
            trend, trend_reason = _score_trend(headlines, yahoo, r.symbol)

            # 4. Risk scoring from indicators
            ind = r.indicator
            ind_data = {}
            if ind:
                ind_data = {
                    "rsi":           ind.rsi14,
                    "adx":           ind.adx14,
                    "atr_pct":       (ind.atr14 / ind.price * 100) if ind.price > 0 else 2,
                    "drawdown_pct":  ind.drawdown_pct,
                    "relative_strength": ind.relative_strength,
                    "above_200ema":  ind.price > ind.ema200,
                }
            risk, risk_reason = _score_risk(ind_data, trend, r.asset_type)

            r.trend        = trend
            r.trend_reason = trend_reason
            r.risk         = risk
            r.risk_reason  = risk_reason

        except Exception as e:
            logger.error(f"Assessment error for {r.symbol}: {e}")
            r.trend = "Neutral"
            r.risk  = "VOLATILE"
            r.trend_reason = "Assessment unavailable"
            r.risk_reason  = "Assessment unavailable"

    return results
