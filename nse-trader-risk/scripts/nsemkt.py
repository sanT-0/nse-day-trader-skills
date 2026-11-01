"""nsemkt - shared NSE / broker-neutral utilities for nse-trader-* skills.

Standard library only. Windows-safe: IST is computed as a fixed +05:30 offset
(no zoneinfo / tzdata dependency). Every network call is best-effort with a
clear error message; callers decide whether to degrade.

Conventions
-----------
- Symbols are NSE tickers ("RELIANCE", "TATAMOTORS"); Yahoo needs ".NS".
- Money is INR. The default price step is a conservative Rs 0.05; callers
  must verify the instrument's current exchange tick with their broker/NSE.
- Session times are IST: pre-open auction 09:00, trading 09:15-15:30,
  MIS square-off 15:15, no new entries after 15:00.
- State lives in ./nse-trader/ relative to the working directory.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
# Conservative/common NSE order-price step. Some lower-priced cash instruments
# can have a Rs 0.01 tick under NSE's monthly tick-size regime; Rs 0.05 remains
# valid but coarser. Always verify the instrument's current tick.
TICK = 0.05

PREOPEN_START = (9, 0)      # pre-open auction begins
OPEN = (9, 15)              # continuous trading begins
ENTRY_CUTOFF = (15, 0)      # no new entries after this
MIS_SQUAREOFF = (15, 15)    # brokers start squaring off MIS near here
CLOSE = (15, 30)            # continuous trading ends

STATE_DIR = os.environ.get("NSE_TRADER_STATE_DIR", "nse-trader")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Bundled fallback for offline operation. The live NSE holiday master is cached
# by nse_holidays(); this table prevents a network outage from misclassifying
# known 2026 holidays.
HOLIDAYS = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-15": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-21": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan*",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}

HOLIDAY_SOURCE_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
HOLIDAY_CACHE_HOURS = 24 * 7
CHARGE_SCHEDULE_DATE = "2026-11-01"
# Backward compatibility for callers from the initial Groww-specific release.
GROWW_CHARGE_SCHEDULE_DATE = CHARGE_SCHEDULE_DATE

# --------------------------------------------------------------------------
# Time / session helpers
# --------------------------------------------------------------------------


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def today_ist() -> dt.date:
    return now_ist().date()


def _parse_nse_holiday_date(value: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(value, "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return None


def nse_holidays(refresh: bool = False, allow_network: bool = False) -> dict[str, str]:
    """Return known NSE capital-market holidays, optionally refreshing cache.

    The bundled fallback is always included. The cache is stored under
    ``./nse-trader/cache``. Network refresh is explicit except when
    ``holiday_name`` encounters a year absent from both fallback and cache.
    Set ``NSE_TRADER_OFFLINE=1`` to suppress every refresh attempt.
    """
    merged = dict(HOLIDAYS)
    path = os.path.join(STATE_DIR, "cache", "nse_holidays.json")
    cached = load_json(path, {}) or {}
    cached_holidays = cached.get("holidays", {}) if isinstance(cached, dict) else {}
    if isinstance(cached_holidays, dict):
        merged.update({str(k): str(v) for k, v in cached_holidays.items()})

    offline = os.environ.get("NSE_TRADER_OFFLINE", "").strip().lower() in (
        "1", "true", "yes", "on"
    )
    should_fetch = allow_network and not offline and (
        refresh or not _cache_fresh(path, HOLIDAY_CACHE_HOURS)
    )
    if not should_fetch:
        return merged

    official: dict[str, str] = {}
    error = None
    try:
        payload = http_json(HOLIDAY_SOURCE_URL, timeout=20, retries=1)
        rows = payload.get("CM", []) if isinstance(payload, dict) else []
        for row in rows:
            day = _parse_nse_holiday_date(row.get("tradingDate"))
            name = str(row.get("description") or "NSE holiday").strip()
            if day:
                official[day.isoformat()] = name
        if not official:
            raise ValueError("NSE holiday response contained no CM dates")
    except Exception as exc:  # retain fallback and record why refresh failed
        error = str(exc)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_json(path, {
        "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": HOLIDAY_SOURCE_URL,
        "holidays": official,
        "error": error,
    })
    merged.update(official)
    return merged


def holiday_name(d: dt.date | None = None, refresh: bool = False) -> str | None:
    d = d or today_ist()
    initial = nse_holidays(refresh=False, allow_network=False)
    known_years = {int(value[:4]) for value in initial if len(value) >= 4 and value[:4].isdigit()}
    holidays = initial
    if refresh or d.year not in known_years:
        holidays = nse_holidays(refresh=refresh, allow_network=True)
    return holidays.get(d.isoformat())


def holiday_calendar_verified(year: int) -> bool:
    """Whether fallback/cache contains at least one holiday for ``year``."""
    holidays = nse_holidays()
    if not any(key.startswith(f"{year:04d}-") for key in holidays):
        holidays = nse_holidays(allow_network=True)
    return any(key.startswith(f"{year:04d}-") for key in holidays)


def is_trading_day(d: dt.date | None = None) -> bool:
    d = d or today_ist()
    return d.weekday() < 5 and holiday_name(d) is None


def next_trading_day(d: dt.date | None = None, include_today: bool = False) -> dt.date:
    d = d or today_ist()
    if not include_today:
        d = d + dt.timedelta(days=1)
    while not is_trading_day(d):
        d = d + dt.timedelta(days=1)
    return d


def _at(d: dt.date, hm: tuple[int, int]) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=IST)


def session_state(now: dt.datetime | None = None) -> dict:
    """Return a dict describing the NSE session right now (all IST)."""
    now = now or now_ist()
    d = now.date()
    base = {
        "now_ist": now.isoformat(timespec="seconds"),
        "date": d.isoformat(),
        "flat_by": _at(d, MIS_SQUAREOFF).isoformat(timespec="minutes"),
        "entry_cutoff": _at(d, ENTRY_CUTOFF).isoformat(timespec="minutes"),
        "holiday_calendar_verified": holiday_calendar_verified(d.year),
    }
    if d.weekday() >= 5:
        return {**base, "state": "WEEKEND", "is_trading_day": False,
                "next_open": _at(next_trading_day(d), OPEN).isoformat(timespec="minutes")}
    hol = holiday_name(d)
    if hol:
        return {**base, "state": "HOLIDAY", "is_trading_day": False, "holiday": hol,
                "next_open": _at(next_trading_day(d), OPEN).isoformat(timespec="minutes")}

    t = now.time()
    if t < dt.time(*PREOPEN_START):
        state = "PRE_MARKET"
    elif t < dt.time(*OPEN):
        state = "PRE_OPEN"
    elif t < dt.time(*MIS_SQUAREOFF):
        state = "OPEN"
    elif t < dt.time(*CLOSE):
        state = "SQUAREOFF"
    else:
        state = "POST_CLOSE"

    close_dt = _at(d, CLOSE)
    return {
        **base,
        "state": state,
        "is_trading_day": True,
        "minutes_to_close": int((close_dt - now).total_seconds() // 60),
        "next_open": _at(next_trading_day(d), OPEN).isoformat(timespec="minutes"),
    }


def can_enter_now(now: dt.datetime | None = None) -> tuple[bool, str]:
    """Whether a new entry is allowed right now, with a one-line reason."""
    now = now or now_ist()
    ss = session_state(now)
    if ss["state"] == "WEEKEND":
        return False, "weekend - market closed"
    if ss["state"] == "HOLIDAY":
        return False, f"NSE holiday: {ss['holiday']}"
    if ss["state"] in ("PRE_MARKET", "PRE_OPEN"):
        return False, f"market not open yet ({ss['state'].lower()})"
    if ss["state"] == "SQUAREOFF":
        return False, "past 15:00 entry cutoff - squaring-off window only"
    if ss["state"] == "POST_CLOSE":
        return False, "market closed for the day"
    if now.time() >= dt.time(*ENTRY_CUTOFF):
        return False, "past 15:00 entry cutoff"
    return True, "open for entries"


# --------------------------------------------------------------------------
# HTTP + JSON
# --------------------------------------------------------------------------


def http_get(url: str, timeout: int = 25, retries: int = 2) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url} ({last})")


def http_json(url: str, timeout: int = 25, retries: int = 2):
    return json.loads(http_get(url, timeout=timeout, retries=retries))


# --------------------------------------------------------------------------
# Yahoo Finance (NSE data, no key)
# --------------------------------------------------------------------------


def yahoo_symbol(symbol: str) -> str:
    s = str(symbol).strip().upper()
    if "." not in s:
        s += ".NS"
    return s


def yahoo_chart(symbol: str, interval: str = "1d", range_: str = "6mo") -> dict:
    """Fetch OHLCV bars. Returns {'symbol', 'meta', 'bars': [{t,o,h,l,c,v}]} with t in IST."""
    sym = yahoo_symbol(symbol)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(sym)}?interval={interval}&range={range_}"
        "&includePrePost=false&events=div%2Csplits"
    )
    data = http_json(url)
    res = ((data or {}).get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError(f"no chart data for {sym}")
    r = res[0]
    ts = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    bars = []
    for i, t in enumerate(ts):
        try:
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        except IndexError:
            continue
        if None in (o, h, l, c):
            continue
        bars.append({
            "t": dt.datetime.fromtimestamp(t, IST),
            "o": float(o), "h": float(h), "l": float(l), "c": float(c),
            "v": float(vols[i] or 0) if i < len(vols) else 0.0,
        })
    return {"symbol": sym, "meta": r.get("meta") or {}, "bars": bars}


def yahoo_quote(symbol: str) -> dict:
    """Last price and previous close, with timestamp. Raises on failure."""
    sym = yahoo_symbol(symbol)
    q = yahoo_chart(sym, interval="1d", range_="5d")
    bars = q["bars"]
    meta = q["meta"]
    if not bars:
        raise RuntimeError(f"no quote for {sym}")
    last = bars[-1]
    ltp = float(meta.get("regularMarketPrice") or last["c"])
    fallback_prev = bars[-2]["c"] if len(bars) > 1 else last["o"]
    prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or fallback_prev)
    ts_ms = meta.get("regularMarketTime")
    ts = dt.datetime.fromtimestamp(ts_ms, IST) if ts_ms else last["t"]
    chg = ltp - prev
    return {
        "symbol": sym.replace(".NS", ""),
        "ltp": ltp,
        "prev_close": prev,
        "change": chg,
        "pct": (chg / prev * 100.0) if prev else 0.0,
        "ts_ist": ts.isoformat(timespec="seconds"),
        "currency": meta.get("currency", "INR"),
        "exchange": meta.get("fullExchangeName", "NSE"),
    }


def atr_daily(symbol: str, period: int = 14) -> float:
    """ATR(period) from daily bars (Wilder). Returns 0.0 if not enough data."""
    bars = yahoo_chart(symbol, "1d", "6mo")["bars"]
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return 0.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


# --------------------------------------------------------------------------
# NSE reference data
# --------------------------------------------------------------------------


def _cache_path(name: str) -> str:
    return os.path.join(STATE_DIR, "cache", name)


def _cache_fresh(path: str, hours: int = 12) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < hours * 3600
    except OSError:
        return False


def nse_symbols(refresh: bool = False) -> list[dict]:
    """NSE equity master (EQUITY_L.csv). Cached 12h under nse-trader/cache/."""
    path = _cache_path("equity_master.json")
    if not refresh and _cache_fresh(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    text = http_get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        sym = (row.get("SYMBOL") or "").strip()
        if not sym:
            continue
        rows.append({
            "symbol": sym,
            "name": (row.get("NAME OF COMPANY") or "").strip(),
            "series": (row.get("SERIES") or "").strip(),
            "isin": (row.get("ISIN NUMBER") or "").strip(),
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return rows


def fo_lots(refresh: bool = False) -> dict:
    """Current-month F&O lot sizes from NSE fo_mktlots.csv -> {symbol: lot}."""
    path = _cache_path("fo_mktlots.json")
    if not refresh and _cache_fresh(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    text = http_get("https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    # header: UNDERLYING, SYMBOL, NOV-26, DEC-26, ...
    try:
        lot_col = 2
        _ = header[2]
    except IndexError:
        raise RuntimeError("unexpected fo_mktlots.csv header")
    lots: dict[str, int] = {}
    for row in reader:
        if not row or len(row) <= lot_col:
            continue
        sym = (row[1] or "").strip().upper()
        raw = (row[lot_col] or "").strip()
        if not sym or not raw:
            continue
        try:
            lots[sym] = int(float(raw))
        except ValueError:
            continue
        und = (row[0] or "").strip().upper()
        if und and und not in lots:
            lots[und] = lots[sym]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lots, f)
    return lots


# --------------------------------------------------------------------------
# Broker/statutory charge model (estimates; verify against the contract note)
# --------------------------------------------------------------------------


BROKER_PROFILES = {
    # Portable placeholder, not guaranteed conservative for every broker.
    # Users should provide their actual brokerage rule.
    "generic": {
        "name": "generic-flat-20",
        "cash_intraday": {"flat": 20.0},
        "cash_delivery": {"flat": 20.0},
        "futures": {"flat": 20.0},
        "options": {"flat": 20.0},
    },
    "groww": {
        "name": "groww-2026-11-01",
        "cash_intraday": {"rate": 0.001, "minimum": 5.0, "maximum": 20.0},
        "cash_delivery": {"rate": 0.001, "minimum": 5.0, "maximum": 20.0},
        "futures": {"flat": 20.0},
        "options": {"flat": 20.0},
    },
}


def resolve_broker_profile(broker: str = "generic", custom: dict | None = None) -> dict:
    """Resolve and validate a built-in or custom brokerage profile.

    A custom profile may override any of ``cash_intraday``, ``cash_delivery``,
    ``futures`` and ``options``. Each rule uses either ``flat`` or ``rate``
    with optional ``minimum`` / ``maximum`` values.
    """
    key = str(broker or "generic").strip().lower()
    if key not in BROKER_PROFILES:
        raise ValueError(f"unknown broker profile {broker!r}; use generic, groww, or a custom file")
    base = BROKER_PROFILES[key]
    profile = {
        "name": base["name"],
        **{name: dict(base[name]) for name in (
            "cash_intraday", "cash_delivery", "futures", "options"
        )},
    }
    if custom:
        if not isinstance(custom, dict):
            raise ValueError("custom broker profile must be a JSON object")
        profile["name"] = str(custom.get("name") or "custom")
        for name in ("cash_intraday", "cash_delivery", "futures", "options"):
            if name in custom:
                if not isinstance(custom[name], dict):
                    raise ValueError(f"broker rule {name} must be an object")
                profile[name] = dict(custom[name])
    for name in ("cash_intraday", "cash_delivery", "futures", "options"):
        rule = profile[name]
        if "flat" not in rule and "rate" not in rule:
            raise ValueError(f"broker rule {name} needs flat or rate")
        for field in ("flat", "rate", "minimum", "maximum"):
            if field in rule and float(rule[field]) < 0:
                raise ValueError(f"broker rule {name}.{field} cannot be negative")
    return profile


def load_broker_profile(path: str | None) -> dict | None:
    if not path:
        return None
    profile = load_json(path)
    if profile is None:
        raise ValueError(f"could not read broker profile: {path}")
    return profile


def _brokerage(turnover: float, rule: dict) -> float:
    if "flat" in rule:
        return float(rule["flat"])
    amount = float(rule.get("rate", 0.0)) * turnover
    if "minimum" in rule:
        amount = max(float(rule["minimum"]), amount)
    if "maximum" in rule:
        amount = min(float(rule["maximum"]), amount)
    return amount


def broker_charges(segment: str, side: str, qty: float, price: float,
                   product: str = "MIS", exchange: str = "NSE",
                   broker: str = "generic", broker_profile: dict | None = None) -> dict:
    """Estimate one-leg Indian broker/statutory charges in INR.

    The default generic profile assumes Rs 20 brokerage per executed order.
    The optional ``groww`` profile uses Groww's published 2026 schedule.
    A custom JSON profile can model another broker's brokerage while retaining
    the exchange/statutory estimate below.

    Equity regulatory estimate: intraday STT 0.025% sell, stamp 0.003% buy,
    NSE transaction charge 0.00297%, SEBI 0.0001%, IPFT 0.0001%, and GST 18%
    on brokerage + transaction + SEBI + IPFT.
    F&O regulatory estimate (retrieved 2026-11-01):
    futures STT 0.05% sell, options STT 0.15% of premium sell, futures NSE
    transaction charge 0.00173%, options 0.03503% of premium, stamp 0.002%
    futures / 0.003% options buy, and GST 18%.
    DP charges on delivery sells are excluded (billed separately).
    """
    seg = str(segment).upper()
    side = str(side).upper()
    prod = str(product).upper()
    turnover = float(qty) * float(price)
    profile = resolve_broker_profile(broker, broker_profile)
    if seg not in ("CASH", "FNO"):
        raise ValueError(f"unknown segment {segment!r}")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"unknown transaction side {side!r}")

    if seg == "CASH":
        if prod == "MIS":
            brokerage = _brokerage(turnover, profile["cash_intraday"])
            stt = 0.00025 * turnover if side == "SELL" else 0.0
            stamp = 0.00003 * turnover if side == "BUY" else 0.0
        else:  # CNC / delivery
            brokerage = _brokerage(turnover, profile["cash_delivery"])
            stt = 0.001 * turnover
            stamp = 0.00015 * turnover if side == "BUY" else 0.0
        exch = (0.0000297 if exchange == "NSE" else 0.0000345) * turnover
        sebi = 0.000001 * turnover
        ipft = 0.000001 * turnover
    else:  # FNO (futures/options), turnover = contract value or premium value
        is_opt = "OPT" in prod
        if is_opt:
            brokerage = _brokerage(turnover, profile["options"])
            stt = 0.0015 * turnover if side == "SELL" else 0.0
            stamp = 0.00003 * turnover if side == "BUY" else 0.0
            exch = 0.0003503 * turnover
            ipft = 0.000005 * turnover
        else:
            brokerage = _brokerage(turnover, profile["futures"])
            stt = 0.0005 * turnover if side == "SELL" else 0.0
            stamp = 0.00002 * turnover if side == "BUY" else 0.0
            exch = 0.0000173 * turnover
            ipft = 0.000001 * turnover
        sebi = 0.000001 * turnover

    gst = 0.18 * (brokerage + exch + sebi + ipft)
    total = brokerage + stt + stamp + exch + sebi + ipft + gst
    return {
        "broker_profile": profile["name"],
        "schedule_date": CHARGE_SCHEDULE_DATE,
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "stamp": round(stamp, 2),
        "exchange": round(exch, 2),
        "sebi": round(sebi, 2),
        "ipft": round(ipft, 2),
        "gst": round(gst, 2),
        "total": round(total, 2),
    }


def groww_charges(segment: str, side: str, qty: float, price: float,
                  product: str = "MIS", exchange: str = "NSE") -> dict:
    """Backward-compatible wrapper for the optional Groww profile."""
    return broker_charges(
        segment, side, qty, price, product, exchange, broker="groww"
    )


def round_trip_charges(segment: str, qty: float, entry: float, exit_price: float,
                       product: str = "MIS", broker: str = "generic",
                       broker_profile: dict | None = None) -> dict:
    """Buy at entry + sell at exit_price; returns summed charges."""
    buy = broker_charges(
        segment, "BUY", qty, entry, product, broker=broker,
        broker_profile=broker_profile,
    )
    sell = broker_charges(
        segment, "SELL", qty, exit_price, product, broker=broker,
        broker_profile=broker_profile,
    )
    return {
        "broker_profile": buy["broker_profile"],
        "schedule_date": CHARGE_SCHEDULE_DATE,
        "buy": buy,
        "sell": sell,
        "total": round(buy["total"] + sell["total"], 2),
    }


# --------------------------------------------------------------------------
# Misc helpers
# --------------------------------------------------------------------------


def round_tick(price: float, mode: str = "nearest") -> float:
    """Round to the conservative Rs 0.05 step. mode: nearest|down|up."""
    if not price:
        return 0.0
    x = float(price) / TICK
    if mode == "down":
        return math.floor(x + 1e-9) * TICK
    if mode == "up":
        return math.ceil(x - 1e-9) * TICK
    return round(x) * TICK


def state_path(name: str) -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, name)


def load_json(path: str, default=None):
    try:
        # utf-8-sig accepts ordinary UTF-8 plus the BOM Windows PowerShell can
        # add when users create a rules file with Set-Content.
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path: str, obj) -> str:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    return path


def append_event(kind: str, payload: dict) -> None:
    rec = {"ts_ist": now_ist().isoformat(timespec="seconds"), "kind": kind, **payload}
    with open(state_path("events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def fmt_inr(x: float) -> str:
    return f"Rs {x:,.2f}"


def pct(x: float, digits: int = 1) -> str:
    return f"{x:+.{digits}f}%"


def json_cli_dump(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))
