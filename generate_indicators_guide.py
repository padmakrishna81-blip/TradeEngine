"""Generate a comprehensive PDF guide for all health score parameters."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "data", "SQE_Indicators_Guide.pdf")
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

# ── Colours ──────────────────────────────────────────────────────────────────
C_DARK   = HexColor("#1e2a3a")
C_BLUE   = HexColor("#2979FF")
C_GREEN  = HexColor("#00C853")
C_ORANGE = HexColor("#FF6D00")
C_RED    = HexColor("#D50000")
C_TEAL   = HexColor("#00897B")
C_LIGHT  = HexColor("#f4f6f9")
C_MID    = HexColor("#dde3ed")

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def s(name, **kw):
    return ParagraphStyle(name, **kw)

TITLE   = s("MyTitle",   fontName="Helvetica-Bold",  fontSize=28, textColor=C_DARK,  spaceAfter=6,  alignment=TA_CENTER)
SUBTITLE= s("MySub",     fontName="Helvetica",        fontSize=13, textColor=C_BLUE,  spaceAfter=20, alignment=TA_CENTER)
H1      = s("MyH1",      fontName="Helvetica-Bold",  fontSize=16, textColor=white,   spaceAfter=4,  spaceBefore=16)
H2      = s("MyH2",      fontName="Helvetica-Bold",  fontSize=12, textColor=C_DARK,  spaceAfter=4,  spaceBefore=8)
BODY    = s("MyBody",    fontName="Helvetica",        fontSize=9.5,textColor=C_DARK,  spaceAfter=4,  leading=14, alignment=TA_JUSTIFY)
SMALL   = s("MySmall",   fontName="Helvetica",        fontSize=8.5,textColor=HexColor("#555"), spaceAfter=3, leading=12)
BOLD    = s("MyBold",    fontName="Helvetica-Bold",  fontSize=9.5,textColor=C_DARK,  spaceAfter=4)
TH      = s("MyTH",      fontName="Helvetica-Bold",  fontSize=8.5,textColor=white,   alignment=TA_CENTER)
TD      = s("MyTD",      fontName="Helvetica",        fontSize=8.5,textColor=C_DARK,  leading=12, alignment=TA_CENTER)
TDL     = s("MyTDL",     fontName="Helvetica",        fontSize=8.5,textColor=C_DARK,  leading=12, alignment=TA_LEFT)

def section_header(title, color=C_BLUE):
    tbl = Table([[Paragraph(title, H1)]], colWidths=[17*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    return tbl

def bucket_table(rows, colw=None):
    """rows = list of (label, description) or (label, col2, col3...)"""
    if colw is None:
        colw = [4*cm, 13*cm]
    data = [[Paragraph(c, TH) if i == 0 else Paragraph(c, TH)
             for i, c in enumerate(rows[0])]]
    for row in rows[1:]:
        data.append([Paragraph(str(c), TDL if j == len(row)-1 else TD)
                     for j, c in enumerate(row)])
    t = Table(data, colWidths=colw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  C_DARK),
        ("BACKGROUND",    (0,1),(-1,-1), C_LIGHT),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_LIGHT, white]),
        ("GRID",          (0,0),(-1,-1), 0.4, C_MID),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    return t

def signal_badge(text, color):
    cell = Table([[Paragraph(f"<b>{text}</b>", s("", fontName="Helvetica-Bold",
                  fontSize=9, textColor=white, alignment=TA_CENTER))]],
                 colWidths=[3*cm])
    cell.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1), color),
                               ("TOPPADDING",(0,0),(-1,-1),3),
                               ("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    return cell

# ═══════════════════════════════════════════════════════════════════════════
# INDICATOR DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

INDICATORS = [

  dict(
    num="01", name="200 DMA (200-Day Moving Average)",
    color=C_BLUE,
    what="The average closing price of a stock over the last 200 trading days (~10 months). "
         "It is the single most-watched long-term trend indicator in equity markets.",
    formula="200 DMA = Sum of last 200 closing prices ÷ 200",
    example="RELIANCE closes at ₹1,304. Its 200 DMA is ₹1,210. "
            "The stock is +7.8% above the 200 DMA → clear uptrend.",
    buy_rows=[
        ["Distance from 200 DMA", "Entry Score", "Interpretation"],
        ["≥ +8% above",  "1.00 (Full)",  "Strong uptrend — ideal entry"],
        ["+4% to +8%",   "0.85",         "Healthy uptrend — good entry"],
        ["0% to +4%",    "0.65",         "Barely above — marginal entry"],
        ["-3% to 0%",    "0.25",         "Just below — wait"],
        ["< -3%",        "0.00",         "Downtrend — no entry"],
    ],
    hold_rows=[
        ["Distance from 200 DMA", "Hold Score", "Interpretation"],
        ["≥ +5% above",  "1.00 (Full)",  "Healthy uptrend — hold comfortably"],
        ["0% to +5%",    "0.85",         "Still above — hold"],
        ["-3% to 0%",    "0.55",         "Just below — watch carefully"],
        ["-5% to -3%",   "0.25",         "Weakening — consider exit"],
        ["< -5%",        "0.00",         "Broken trend — exit"],
    ],
    buy_thresh="0 (bucket rules apply — no fixed threshold needed)",
    hold_thresh="0 (bucket rules apply)",
    note="For ENTRY, we are stricter (need ≥ +4% for a good score). "
         "For HOLD, we are more forgiving (0% is enough for 0.85 score) — "
         "a position opened at +8% may dip to +2% without triggering a sell."
  ),

  dict(
    num="02", name="50 DMA (50-Day Moving Average)",
    color=C_BLUE,
    what="The average of the last 50 closing prices (~2.5 months). "
         "A medium-term trend indicator, faster to react than the 200 DMA. "
         "When price crosses above the 50 DMA, it signals medium-term momentum.",
    formula="50 DMA = Sum of last 50 closing prices ÷ 50",
    example="INFY at ₹1,800. Its 50 DMA is ₹1,750. "
            "Stock is +2.9% above 50 DMA → moderate medium-term momentum.",
    buy_rows=[
        ["Condition",                    "Score", "Meaning"],
        ["Price > 50 DMA",               "1.00",  "Bullish medium-term trend"],
        ["Price < 50 DMA",               "0.00",  "Bearish medium-term trend"],
    ],
    hold_rows=[
        ["Condition",                    "Score", "Meaning"],
        ["Price > 50 DMA",               "1.00",  "Medium-term support intact"],
        ["Price < 50 DMA",               "0.00",  "Medium-term support broken"],
    ],
    buy_thresh="0 (binary: above or below 50 DMA)",
    hold_thresh="0 (binary)",
    note="Simple binary check. Used as a secondary trend confirmation alongside the 200 DMA. "
         "Not in the default stock_hold profile — more relevant for entry timing than holding decisions."
  ),

  dict(
    num="03", name="RSI — Relative Strength Index",
    color=C_TEAL,
    what="RSI measures the speed and magnitude of recent price moves on a 0–100 scale. "
         "Values above 70 indicate overbought (extended), below 30 indicate oversold. "
         "The sweet spot for a new BUY entry is 48–60 — a 'controlled recovery', "
         "not a panic bottom and not an exhausted top.",
    formula="RSI = 100 − [100 ÷ (1 + Average Gain ÷ Average Loss)], over 14 periods",
    example="HDFC Bank RSI = 54. This is in the ideal entry zone (48-60) → score 1.0. "
            "If RSI = 78, the stock is overbought → score 0.35 (risky entry).",
    buy_rows=[
        ["RSI Range",   "Entry Score", "Interpretation"],
        ["48 to 60",    "1.00",        "Ideal — controlled bullish recovery"],
        ["40 to 48",    "0.85",        "Recovering from weakness — good entry"],
        ["60 to 68",    "0.70",        "Bullish but slightly extended"],
        ["35 to 40",    "0.55",        "Oversold — watch for reversal signal"],
        ["68 to 75",    "0.35",        "Overbought zone — risky entry"],
        ["< 35",        "0.15",        "Deep oversold — potential but risky"],
        ["> 75",        "0.10",        "Extreme overbought — very risky entry"],
    ],
    hold_rows=[
        ["RSI Range",   "Hold Score", "Interpretation"],
        ["45 to 70",    "1.00",       "Healthy hold zone — momentum intact"],
        ["40 to 45",    "0.75",       "Weakening — watch"],
        ["35 to 40",    "0.50",       "Oversold territory — caution"],
        ["30 to 35",    "0.20",       "Deeply oversold — consider exit"],
        ["< 30",        "0.00",       "Extreme weakness — exit signal"],
    ],
    buy_thresh="50 (midpoint of healthy zone; can be adjusted in Scoring Profiles → Threshold)",
    hold_thresh="45 (wider zone for holding vs entering)",
    note="For ENTRY: ideal zone is 48–60 (a stock that pulled back but is recovering). "
         "For HOLD: the zone is 45–70 (healthy momentum). Threshold in the DB = lower bound of the zone."
  ),

  dict(
    num="04", name="MACD — Moving Average Convergence Divergence",
    color=C_TEAL,
    what="MACD measures the difference between a 12-day EMA and 26-day EMA. "
         "It has three components: the MACD line, the signal line (9-day EMA of MACD), "
         "and the histogram (MACD − signal). When MACD crosses above signal, it is bullish. "
         "The histogram slope tells us whether momentum is accelerating or fading.",
    formula="MACD Line = EMA(12) − EMA(26)  |  Signal = EMA(9) of MACD  |  Histogram = MACD − Signal",
    example="NTPC: MACD = 0.45, Signal = 0.30, Histogram rising → MACD bullish + accelerating = score 1.0. "
            "BHARTIARTL: MACD = −0.20, Signal = −0.10, Histogram falling → bearish and weakening = score 0.0.",
    buy_rows=[
        ["MACD State",                              "Entry Score", "Condition"],
        ["MACD > Signal + Histogram rising",        "1.00",        "Bullish and accelerating"],
        ["MACD > Signal, Histogram flat/neutral",   "0.75",        "Bullish but slowing"],
        ["Near bullish crossover (MACD ≈ Signal)",  "0.55",        "About to turn bullish"],
        ["MACD < Signal but improving",             "0.25",        "Bearish but recovering"],
        ["MACD < Signal + Histogram falling",       "0.00",        "Bearish and worsening"],
    ],
    hold_rows=[
        ["MACD State",                              "Hold Score", "Condition"],
        ["MACD > Signal + Histogram stable/rising", "1.00",       "Momentum intact — hold"],
        ["MACD > Signal but histogram weakening",   "0.75",       "Bullish but fading — watch"],
        ["Near crossover (either direction)",       "0.50",       "Neutral — monitor"],
        ["MACD < Signal, mild weakness",            "0.25",       "Bearish — consider partial exit"],
        ["MACD < Signal + Histogram falling",       "0.00",       "Exit signal"],
    ],
    buy_thresh="0 (state-based logic — the histogram slope comparison does the work)",
    hold_thresh="0 (state-based)",
    note="MACD is a hard gate for BUY in the default config: if MACD is strong bearish "
         "(line < signal AND histogram falling), a BUY signal is blocked regardless of other scores. "
         "Configure this in Scoring Profiles → Profile Settings → Hard Gates."
  ),

  dict(
    num="05", name="ADX — Average Directional Index",
    color=HexColor("#7B1FA2"),
    what="ADX measures the STRENGTH of a trend, not its direction. "
         "A rising ADX means the trend (up or down) is strengthening. "
         "A high ADX means strong trend. A low ADX means range-bound/sideways market. "
         "ADX does NOT tell you whether the trend is up or down — use 200 DMA for direction.",
    formula="ADX = 14-period smoothed average of |+DI − −DI| ÷ (|+DI + −DI|)",
    example="BEL: ADX = 32 → strong uptrend in progress, good for entry. "
            "HDFCBANK: ADX = 14 → market is ranging, no clear trend — risky entry.",
    buy_rows=[
        ["ADX Value", "Entry Score", "Interpretation"],
        ["≥ 25",      "1.00",        "Strong trending market — ideal entry"],
        ["20 to 25",  "0.75",        "Moderate trend — good entry"],
        ["15 to 20",  "0.40",        "Weak trend — entry timing uncertain"],
        ["< 15",      "0.00",        "Sideways/range-bound — avoid entry"],
    ],
    hold_rows=[
        ["ADX Value", "Hold Score", "Interpretation"],
        ["≥ 20",      "1.00",       "Trend intact — hold"],
        ["15 to 20",  "0.60",       "Trend weakening — watch"],
        ["< 15",      "0.25",       "No trend — reassess position"],
    ],
    buy_thresh="20 (minimum ADX to confirm a trending market for entry)",
    hold_thresh="15 (lower bar — we allow weaker trends for holding vs entering)",
    note="ADX is useful as a 'trend quality filter'. A stock with RSI 55 and ADX 28 "
         "is a much better entry than RSI 55 and ADX 12 (which might just be noise). "
         "Not in the default 6-parameter stock_entry profile — but available for custom strategies."
  ),

  dict(
    num="06", name="ATR — Average True Range",
    color=HexColor("#7B1FA2"),
    what="ATR measures daily price volatility in absolute rupee terms. "
         "It shows the average range of movement per day (high to low). "
         "High ATR = volatile stock (bigger daily swings). Low ATR = calm stock. "
         "Used as a risk and stop-loss sizing tool, not a directional indicator.",
    formula="True Range = Max(High-Low, |High-PrevClose|, |Low-PrevClose|)  |  ATR = 14-period EMA of TR",
    example="RELIANCE ATR = ₹18 on a ₹1,300 stock = 1.4% daily range (calm). "
            "A small-cap at ₹200 with ATR ₹12 = 6% daily range (volatile — higher risk).",
    buy_rows=[
        ["ATR % of Price",  "Entry Score", "Interpretation"],
        ["< 1.5%",          "1.00",        "Low volatility — stable entry"],
        ["1.5% to 2.5%",    "0.75",        "Normal volatility — acceptable"],
        ["2.5% to 3.5%",    "0.50",        "Higher volatility — risk management needed"],
        ["> 3.5%",          "0.00",        "Very volatile — high risk entry"],
    ],
    hold_rows=[
        ["ATR % of Price",  "Hold Score", "Interpretation"],
        ["< 2%",            "1.00",       "Calm — comfortable hold"],
        ["2% to 3%",        "0.75",       "Normal — hold with stops"],
        ["3% to 4%",        "0.40",       "Elevated — tighten stops"],
        ["> 4%",            "0.00",       "Dangerous volatility — exit risk"],
    ],
    buy_thresh="0 (percentage is computed internally; adjust weights to control impact)",
    hold_thresh="0 (internal calculation)",
    note="ATR is particularly important for portfolio risk management and stop-loss sizing. "
         "Rule of thumb: stop-loss = entry price − 1.5× ATR. "
         "Also used as a risk exit signal: if VIX > 25 AND ATR% > 2.5%, consider exiting."
  ),

  dict(
    num="07", name="Volume Spike (Volume Ratio)",
    color=C_GREEN,
    what="Compares today's trading volume to the 20-day average volume. "
         "High volume on an up day = institutional buying (confirmation). "
         "Low volume on an up day = weak/unconfirmed rally. "
         "Volume spike at support = strong buying interest at that price level.",
    formula="Volume Ratio = Today's Volume ÷ 20-Day Average Volume",
    example="SUNPHARMA trades 8M shares today vs average 5M = ratio 1.6x. "
            "This is above the 1.5 threshold → score 0.85 (above-average participation). "
            "If only 3M traded = ratio 0.6x → score 0.00 (no institutional interest).",
    buy_rows=[
        ["Volume Ratio", "Entry Score", "Interpretation"],
        ["≥ 2.0×",       "1.00",        "Heavy volume — strong institutional interest"],
        ["1.5× to 2.0×", "0.85",        "Above average — good confirmation"],
        ["1.2× to 1.5×", "0.65",        "Moderate volume — partial confirmation"],
        ["1.0× to 1.2×", "0.35",        "Barely above avg — weak entry signal"],
        ["< 1.0×",        "0.00",        "Below average — no confirmation"],
    ],
    hold_rows=[
        ["Volume Ratio", "Hold Score", "Interpretation"],
        ["≥ 1.2×",       "1.00",        "Active interest — hold confirmed"],
        ["1.0× to 1.2×", "0.75",        "Normal — hold"],
        ["0.8× to 1.0×", "0.50",        "Slightly below — watch"],
        ["0.6× to 0.8×", "0.25",        "Low interest — caution"],
        ["< 0.6×",        "0.00",        "Very thin — exit risk"],
    ],
    buy_thresh="1.5 (minimum ratio for a meaningful volume spike at entry)",
    hold_thresh="1.0 (lower threshold for holding — normal volume is acceptable)",
    note="Entry threshold = 1.5 (require volume 50% above average). "
         "Hold threshold = 1.0 (just normal volume is fine for holding). "
         "The threshold field in the DB is used as the minimum ratio below which score = 0."
  ),

  dict(
    num="08", name="Relative Strength vs NIFTY",
    color=C_GREEN,
    what="Compares the stock's 20-day return to the NIFTY 50's 20-day return. "
         "Positive RS diff = stock is OUTPERFORMING the benchmark. "
         "Negative RS diff = stock is UNDERPERFORMING (money flowing into other stocks). "
         "The best entries are in stocks leading the market, not lagging it.",
    formula="RS Diff (20-day) = Stock 20-day return % − NIFTY 20-day return %",
    example="INFY gained +9% in 20 days. Nifty gained +3% in the same period. "
            "RS Diff = +6% → outperforming by 6% → score 1.0 for entry.",
    buy_rows=[
        ["RS Diff (20-day)", "Entry Score", "Interpretation"],
        ["≥ +5%",            "1.00",        "Strong outperformer — lead the index"],
        ["+2% to +5%",       "0.80",        "Outperforming — good entry"],
        ["0% to +2%",        "0.60",        "In-line with index — neutral"],
        ["-2% to 0%",        "0.25",        "Lagging — weak entry"],
        ["< -2%",            "0.00",        "Underperformer — avoid entry"],
    ],
    hold_rows=[
        ["RS Diff (20-day)", "Hold Score", "Interpretation"],
        ["≥ +3%",            "1.00",       "Outperforming — strong hold"],
        ["0% to +3%",        "0.75",       "In-line — hold"],
        ["-2% to 0%",        "0.50",       "Slight lag — watch"],
        ["-5% to -2%",       "0.20",       "Lagging — consider reducing"],
        ["< -5%",            "0.00",       "Underperforming badly — exit"],
    ],
    buy_thresh="0 (RS diff is computed from OHLCV data; threshold controls scoring bucket)",
    hold_thresh="0 (same)",
    note="RS is a powerful filter. A stock with good fundamentals but poor RS means "
         "capital is flowing elsewhere — better to wait. "
         "For ENTRY: demand ≥ +2% outperformance. "
         "For HOLD: 0% (in-line) is acceptable — the position is already open."
  ),

  dict(
    num="09", name="Drawdown from N-Day High",
    color=C_ORANGE,
    what="Measures how far the stock has pulled back from its recent high. "
         "A 0% drawdown means the stock is AT its recent high (extended, risky entry). "
         "A 5-8% pullback from the high is the 'sweet spot' — healthy correction in an uptrend. "
         "A >15% drawdown may indicate the trend is broken. "
         "Uses a BELL-CURVE scoring model — both too extended and too broken score low.",
    formula="Drawdown % = (Current Price − N-Day High) ÷ N-Day High × 100  [always negative or zero]",
    example="RELIANCE 60-day high = ₹1,380. Current = ₹1,295. "
            "Drawdown = (1295−1380) ÷ 1380 × 100 = −6.2% → ideal zone → score 1.0.",
    buy_rows=[
        ["Drawdown from N-day High", "Entry Score", "Interpretation"],
        ["0% to -2%",                "0.20",        "Near highs — likely extended, wait for pullback"],
        ["-2% to -5%",               "0.70",        "Mild pullback — decent entry"],
        ["-5% to -8%",               "1.00",        "IDEAL — healthy correction in uptrend"],
        ["-8% to -12%",              "0.75",        "Moderate pullback — still ok"],
        ["-12% to -15%",             "0.35",        "Deep pullback — caution"],
        ["< -15%",                   "0.00",        "Excessive — possible trend damage"],
    ],
    hold_rows=[
        ["Drawdown from N-day High", "Hold Score", "Interpretation"],
        ["0% to -4%",                "1.00",        "Near highs — position healthy"],
        ["-4% to -8%",               "0.80",        "Normal pullback — hold"],
        ["-8% to -12%",              "0.55",        "Deeper decline — watch"],
        ["-12% to -15%",             "0.25",        "Significant decline — danger zone"],
        ["< -15%",                   "0.00",        "Critical — exit signal"],
    ],
    buy_thresh="0 (bell-curve: both 0% and >15% score low; 5-8% scores highest)",
    hold_thresh="0 (same bell-curve logic, but more forgiving)",
    note="The N-day window is configurable (default 60 trading days). "
         "Change it in Settings → Data → Default Drawdown Window, or per-scan in Strategy Lab. "
         "For HOLD: no bell curve — drawdown 0 to -4% is GOOD (position is profitable/near high). "
         "The hold model rewards small drawdowns (position doing well), not specific pullbacks."
  ),

  dict(
    num="10", name="VIX — India Volatility Index",
    color=C_RED,
    what="India VIX measures the FEAR level in the market — how much uncertainty traders "
         "are pricing into options. It is computed from Nifty options prices. "
         "LOW VIX (< 15) = calm market, risk-on environment — good for buying. "
         "HIGH VIX (> 25) = fear/panic — markets can fall sharply, risky to buy. "
         "VIX is a MARKET-WIDE indicator, same for all stocks.",
    formula="India VIX = Implied Volatility computed from NIFTY 50 Options (NSE formula)",
    example="VIX = 12.5 → very calm market → score 1.0 (full marks). "
            "VIX = 28 → elevated fear → score 0.25. "
            "VIX = 35 → panic → score 0.0 (no new buying).",
    buy_rows=[
        ["VIX Level",  "Score",  "Market Environment"],
        ["≤ 13",       "1.00",   "Very low fear — ideal risk-on environment"],
        ["13 to 16",   "0.85",   "Calm — good conditions"],
        ["16 to 20",   "0.65",   "Mild anxiety — acceptable but cautious"],
        ["20 to 25",   "0.35",   "Elevated fear — risky to add positions"],
        ["> 25",       "0.00",   "High fear/panic — avoid new entries"],
    ],
    hold_rows=[
        ["VIX Level",  "Score",  "Interpretation for Holdings"],
        ["≤ 20",       "1.00",   "VIX under control — hold comfortably"],
        ["20 to 25",   "0.65",   "Rising anxiety — watch trailing stops"],
        ["25 to 30",   "0.30",   "Fear elevated — tighten stops"],
        ["> 30",       "0.00",   "Panic — review all positions"],
    ],
    buy_thresh="20 (VIX must be below 20 for any positive entry score in default setup)",
    hold_thresh="20 (same)",
    note="VIX > 25 is also a HARD EXIT trigger when combined with high ATR. "
         "VIX is used in the MARKET HEALTH score (weight 40%) — higher weight there "
         "because it is a better signal for deployment decisions than individual stock scoring. "
         "In stock_entry profile it has lower weight (10%) as it is one of 6 factors."
  ),

  dict(
    num="11", name="Market Breadth",
    color=C_RED,
    what="Market Breadth = the fraction of stocks in the universe that are trading "
         "ABOVE their 200-day EMA. If 70% of NIFTY 50 stocks are above their 200 DMA, "
         "the rally is broad and healthy. If only 30% are above, only a few large-caps "
         "are holding up the index — dangerous narrow market.",
    formula="Breadth = Number of stocks above 200 EMA ÷ Total stocks in universe",
    example="35 out of 50 Nifty stocks above 200 EMA → Breadth = 0.70 → score 1.0. "
            "18 out of 50 above 200 EMA → Breadth = 0.36 → score 0.0 (very narrow market).",
    buy_rows=[
        ["Breadth Ratio", "Score", "Market Interpretation"],
        ["≥ 0.70 (70%+)", "1.00",  "Broad participation — healthy bull market"],
        ["0.55 to 0.70",  "0.75",  "Good breadth — decent conditions"],
        ["0.40 to 0.55",  "0.40",  "Narrow market — caution"],
        ["< 0.40 (40%−)", "0.00",  "Very narrow — few stocks leading"],
    ],
    hold_rows=[
        ["Breadth Ratio", "Score", "Market Interpretation for Holdings"],
        ["≥ 0.50 (50%+)", "1.00",  "More than half above 200 EMA — hold"],
        ["0.35 to 0.50",  "0.60",  "Below majority — watch"],
        ["< 0.35",        "0.00",  "Very narrow — exit risk higher"],
    ],
    buy_thresh="0.5 (at least 50% of stocks above 200 EMA for a positive entry environment)",
    hold_thresh="0.35 (more lenient for holding vs entering)",
    note="Breadth is COMPUTED from your watchlist or the top-20 most liquid stocks. "
         "It is primarily a MARKET HEALTH parameter (weight 40% in Market Health score). "
         "In stock_entry profile it carries less weight (10%). "
         "A narrow market can still have individual strong stocks — use breadth as context."
  ),

]

# ═══════════════════════════════════════════════════════════════════════════
# BUILD DOCUMENT
# ═══════════════════════════════════════════════════════════════════════════

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm,
    topMargin=2*cm,  bottomMargin=2*cm,
    title="SQE Indicators Reference Guide",
    author="STATE Quant Engine",
)

story = []

# ── Cover page ────────────────────────────────────────────────────────────────
story.append(Spacer(1, 3*cm))
story.append(Paragraph("📈 STATE Quant Engine", TITLE))
story.append(Paragraph("Technical Indicators Reference Guide", SUBTITLE))
story.append(Spacer(1, 0.5*cm))
story.append(HRFlowable(width="100%", thickness=2, color=C_BLUE))
story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "Complete reference for all 11 health score parameters — "
    "their meaning, BUY (Entry) scoring rules, EXIT/HOLD scoring rules, "
    "threshold settings, and practical examples.",
    s("sub2", fontName="Helvetica", fontSize=11, textColor=HexColor("#555"),
      alignment=TA_CENTER, spaceAfter=6)
))
story.append(Spacer(1, 0.5*cm))

# Quick summary table
summary_data = [
    [Paragraph("Parameter", TH), Paragraph("Entry Weight", TH),
     Paragraph("Hold Weight", TH), Paragraph("Market Health", TH), Paragraph("Type", TH)],
    ["200 DMA",           "25%", "25%", "—",   "Trend"],
    ["50 DMA",            "10%", "—",   "—",   "Trend"],
    ["RSI(14)",           "15%", "15%", "—",   "Momentum"],
    ["MACD",              "10%", "10%", "—",   "Momentum"],
    ["ADX(14)",           "10%", "—",   "—",   "Trend Strength"],
    ["ATR(14)",           "5%",  "—",   "—",   "Volatility"],
    ["Volume Spike",      "10%", "10%", "—",   "Volume"],
    ["Relative Strength", "20%", "20%", "—",   "Relative"],
    ["Drawdown",          "20%", "20%", "—",   "Pullback"],
    ["VIX",               "—",   "—",   "40%", "Fear Index"],
    ["Market Breadth",    "—",   "—",   "40%", "Breadth"],
    ["Nifty 200 DMA",     "—",   "—",   "20%", "Market Trend"],
    ["Profit %",          "—",   "20%", "—",   "Position P&L"],
]
st = []
for i, row in enumerate(summary_data):
    is_header = i == 0
    cols = [Paragraph(str(c), TH if is_header else TD) for c in row]
    st.append(cols)

stbl = Table(st, colWidths=[4.5*cm, 2.5*cm, 2.5*cm, 3*cm, 3.5*cm], repeatRows=1)
stbl.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,0),  C_DARK),
    ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_LIGHT, white]),
    ("GRID",          (0,0), (-1,-1), 0.4, C_MID),
    ("TOPPADDING",    (0,0), (-1,-1), 4),
    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ("LEFTPADDING",   (0,0), (-1,-1), 5),
]))
story.append(stbl)
story.append(Spacer(1, 0.5*cm))

story.append(Paragraph(
    "<b>Note:</b> Entry score and Hold score use the same 6 parameters but with different bucket thresholds. "
    "Market Health uses VIX + Breadth + Nifty 200 DMA to compute the capital deployment multiplier.",
    SMALL
))
story.append(PageBreak())

# ── One page per indicator ────────────────────────────────────────────────────
for ind in INDICATORS:
    story.append(section_header(f"  {ind['num']}. {ind['name']}", ind["color"]))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph("<b>What it measures</b>", H2))
    story.append(Paragraph(ind["what"], BODY))

    story.append(Paragraph("<b>Formula</b>", H2))
    story.append(Paragraph(ind["formula"],
                            s("form", fontName="Courier", fontSize=8.5,
                              textColor=HexColor("#333"), spaceAfter=4, leading=13)))

    story.append(Paragraph("<b>Real example</b>", H2))
    story.append(Paragraph(ind["example"], BODY))

    # BUY table
    story.append(Paragraph("<b>Entry Health scoring (Scanner → BUY/WAIT)</b>", H2))
    story.append(bucket_table(ind["buy_rows"],
                               colw=[3.5*cm, 2.5*cm, 10*cm]))
    story.append(Spacer(1, 0.15*cm))

    # HOLD table
    story.append(Paragraph("<b>Hold Health scoring (Portfolio → HOLD/AVG/EXIT)</b>", H2))
    story.append(bucket_table(ind["hold_rows"],
                               colw=[3.5*cm, 2.5*cm, 10*cm]))
    story.append(Spacer(1, 0.15*cm))

    # Threshold box
    thr_data = [
        [Paragraph("Setting", TH), Paragraph("Value", TH), Paragraph("Where to configure", TH)],
        [Paragraph("Entry threshold", TDL),
         Paragraph(ind["buy_thresh"][:40], TDL),
         Paragraph("Scoring Profiles → stock_entry → Parameters tab", TDL)],
        [Paragraph("Hold threshold",  TDL),
         Paragraph(ind["hold_thresh"][:40], TDL),
         Paragraph("Scoring Profiles → stock_hold → Parameters tab", TDL)],
    ]
    ttbl = Table(thr_data, colWidths=[3*cm, 6*cm, 8*cm])
    ttbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), HexColor("#3a4a5a")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [HexColor("#fff8e1"), white]),
        ("GRID",          (0,0),(-1,-1), 0.4, C_MID),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(ttbl)
    story.append(Spacer(1, 0.15*cm))

    story.append(Paragraph("<b>💡 Practical note</b>", H2))
    story.append(Paragraph(ind["note"], BODY))

    story.append(PageBreak())

# ── Final summary page ────────────────────────────────────────────────────────
story.append(section_header("  Quick Setup Guide — Recommended Thresholds", C_TEAL))
story.append(Spacer(1, 0.3*cm))

story.append(Paragraph("stock_entry profile (Scanner)", H2))
setup_entry = [
    ["Parameter", "Weight", "Threshold", "Notes"],
    ["200 DMA",           "25", "0",    "Bucket rules — no threshold needed"],
    ["Drawdown",          "20", "0",    "Bell-curve: 5-8% ideal"],
    ["Relative Strength", "20", "0",    "Bucket rules"],
    ["Volume Spike",      "10", "1.5",  "Require 50% above avg volume"],
    ["RSI",               "15", "50",   "Ideal zone 48-60"],
    ["MACD",              "10", "0",    "State-based (histogram slope)"],
]
story.append(bucket_table(setup_entry, colw=[4*cm,2*cm,2.5*cm,8.5*cm]))
story.append(Paragraph("BUY threshold: 75% (in Scoring Profiles → Profile Settings)", SMALL))
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("stock_hold profile (Portfolio)", H2))
setup_hold = [
    ["Parameter", "Weight", "Threshold", "Notes"],
    ["200 DMA",           "25", "0",    "More forgiving than entry buckets"],
    ["Drawdown",          "20", "0",    "0 to -4% = full marks (near high = good)"],
    ["Relative Strength", "20", "0",    "Broader hold zone"],
    ["Volume Spike",      "10", "1.0",  "Normal volume acceptable for holding"],
    ["RSI",               "15", "45",   "Wide zone 45-70"],
    ["MACD",              "10", "0",    "State-based"],
    ["Profit %",          "20", "10",   "At 10% profit → full contribution"],
]
story.append(bucket_table(setup_hold, colw=[4*cm,2*cm,2.5*cm,8.5*cm]))
story.append(Paragraph("EXIT threshold: 45% | AVG threshold: 60% (in Scoring Profiles → Profile Settings)", SMALL))
story.append(Spacer(1, 0.4*cm))

story.append(Paragraph("Market Health profile (Capital Deployment)", H2))
setup_mkt = [
    ["Parameter",        "Weight", "Notes"],
    ["India VIX",        "40",     "< 13 = fear-free · > 25 = high fear = 0 score"],
    ["Market Breadth",   "40",     "≥ 70% stocks above 200 EMA = full score"],
    ["Nifty 200 DMA",    "20",     "Nifty above its own 200 EMA"],
]
story.append(bucket_table(setup_mkt, colw=[4.5*cm,2*cm,10.5*cm]))
deploy_rows = [
    ["Market Health Score", "Capital Deployed", "Label"],
    ["80 – 100%", "100%", "Full Deploy"],
    ["60 – 79%",  "75%",  "75% Deploy"],
    ["40 – 59%",  "50%",  "50% Deploy"],
    ["< 40%",     "25%",  "25% / Hold Cash"],
]
story.append(Spacer(1, 0.2*cm))
story.append(bucket_table(deploy_rows, colw=[5*cm,3*cm,9*cm]))

story.append(Spacer(1, 0.5*cm))
story.append(HRFlowable(width="100%", thickness=1, color=C_MID))
story.append(Spacer(1, 0.2*cm))
story.append(Paragraph(
    "Configure all parameters in the app: Scoring Profiles → select a profile → Parameters tab. "
    "Load weights from Strategy Lab strategies using the 'Copy parameters from strategy' dropdown.",
    SMALL
))

doc.build(story)
print(f"PDF generated: {OUTPUT}")
