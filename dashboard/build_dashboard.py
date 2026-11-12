"""สร้าง Stable Income Dashboard (หุ้นไทยปันผลสม่ำเสมอ) จากข้อมูล Yahoo Finance

ใช้แค่ standard library ของ Python ไม่ต้องติดตั้งอะไรเพิ่ม
รัน:  python3 dashboard/build_dashboard.py   (หรือรัน serve.py แล้วกดปุ่ม Update ในหน้าเว็บ)
ผลลัพธ์: dashboard/index.html และ dashboard/data/dividends.json (ข้อมูลดิบไว้ตรวจย้อน)
รายชื่อหุ้น = tickers.txt (มีกลุ่มธุรกิจ) + ทุกตัวใน data/universe.json (รายชื่อ SET/mai จาก SETSMART)
เกณฑ์ผ่าน/ไม่ผ่านคำนวณในหน้าเว็บ (ปรับได้) สคริปต์นี้คำนวณเฉพาะตัวชี้วัดดิบ
"""

import json
import os
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TICKERS_FILE = HERE / "tickers.txt"
DATA_FILE = HERE / "data" / "dividends.json"
HTML_FILE = HERE / "index.html"
BOND_FILE = HERE.parent / "data" / "th10y.json"
UNIVERSE_FILE = HERE.parent / "data" / "universe.json"
SETHD_FILE = HERE.parent / "data" / "sethd.json"

TH = timezone(timedelta(hours=7))
YEARS = 10
WORKERS = 6
DEFAULT_SECTOR = "ไม่ระบุกลุ่ม"
CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={years}y&interval=1mo&events=div"
FIN_API = (
    "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
    "?type=annualTotalRevenue,annualNetIncome,annualOperatingCashFlow,annualCashDividendsPaid"
    ",annualFreeCashFlow,annualOrdinarySharesNumber"
    ",annualTotalDebt,annualTotalEquityGrossMinorityInterest,annualStockholdersEquity"
    "&merge=false&period1=1420070400&period2={now}"
)
QUOTE_PAGE = "https://finance.yahoo.com/quote/{sym}/history?filter=div"
FIN_PAGE = "https://finance.yahoo.com/quote/{sym}/financials"
UA = "Mozilla/5.0 (AI Investor Alpha stable income dashboard)"
FIN_KEYS = {
    "annualTotalRevenue": "revenue",
    "annualNetIncome": "net_income",
    "annualOperatingCashFlow": "ocf",
    "annualCashDividendsPaid": "div_paid",
    "annualFreeCashFlow": "fcf",
    "annualOrdinarySharesNumber": "shares",
    "annualTotalDebt": "debt",
    "annualTotalEquityGrossMinorityInterest": "equity",
    "annualStockholdersEquity": "equity_parent",
}
NETWORK_ERRORS = (urllib.error.URLError, KeyError, IndexError, TypeError, ValueError, TimeoutError, OSError)


def read_tickers():
    """tickers.txt ก่อน (มีกลุ่มธุรกิจ) แล้วตามด้วยหุ้นที่เหลือใน universe.json"""
    out, seen, disabled = [], set(), set()
    for line in TICKERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") and "|" in line:  # บรรทัดที่ปิดไว้ด้วย # ไม่ถูกดึงกลับมาจาก universe
            disabled.add(line.lstrip("# ").partition("|")[0].strip())
            continue
        if not line or line.startswith("#"):
            continue
        sym, _, sector = line.partition("|")
        sym = sym.strip()
        out.append((sym, sector.strip() or DEFAULT_SECTOR))
        seen.add(sym)
    try:
        universe = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))["kept"]
    except (OSError, KeyError, ValueError):
        universe = []
    out += [(sym, DEFAULT_SECTOR) for sym in universe if sym not in seen and sym not in disabled]
    return out


def get_json(url, tries=3):
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503) or i == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def fetch_financials(sym):
    """งบรายปีจาก Yahoo (ย้อนหลังได้ประมาณ 4 ปี) คืน {ปี: {revenue, net_income, ocf, ...}}"""
    data = get_json(FIN_API.format(sym=sym, now=int(time.time())))
    by_year = {}
    for res in data["timeseries"]["result"]:
        for yk, field in FIN_KEYS.items():
            for item in res.get(yk) or []:
                if not item or not item.get("reportedValue"):
                    continue
                year = int(item["asOfDate"][:4])
                by_year.setdefault(year, {})[field] = item["reportedValue"]["raw"]
    return by_year


def fetch(sym, sector):
    url = CHART_API.format(sym=sym, years=YEARS)
    result = get_json(url)["chart"]["result"][0]
    meta = result["meta"]
    divs = sorted(result.get("events", {}).get("dividends", {}).values(), key=lambda d: d["date"])
    stock = {
        "symbol": sym,
        "sector": sector,
        "name": meta.get("longName") or meta.get("shortName") or sym,
        "currency": meta.get("currency", ""),
        "price": meta.get("regularMarketPrice"),
        "dividends": [
            {"date": datetime.fromtimestamp(d["date"], TH).strftime("%Y-%m-%d"), "amount": d["amount"]}
            for d in divs
        ],
        "page_url": QUOTE_PAGE.format(sym=sym),
        "fin_url": FIN_PAGE.format(sym=sym),
        "financials": {},
        "fin_error": None,
    }
    try:
        stock["financials"] = fetch_financials(sym)
    except NETWORK_ERRORS as e:
        stock["fin_error"] = str(e)[:80]
    return stock


def cv(values):
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return None
    mean = statistics.mean(values)
    return statistics.pstdev(values) / abs(mean) if mean else None


def summarize(stock, today):
    divs = stock["dividends"]
    cutoff = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    ttm = sum(d["amount"] for d in divs if d["date"] > cutoff)
    price = stock["price"]
    by_year = {}
    for d in divs:
        y = int(d["date"][:4])
        by_year[y] = by_year.get(y, 0) + d["amount"]
    full_years = list(range(today.year - YEARS, today.year))  # ปีเต็มล่าสุด 10 ปี (ไม่รวมปีปัจจุบัน)
    paid = [by_year.get(y, 0.0) for y in full_years]
    streak = 0
    for v in reversed(paid):
        if not v:
            break
        streak += 1
    # ปีที่ปันผลรายปีลดลงเกิน 10% จากปีก่อน (เฉพาะคู่ปีที่ทั้งสองปีมีการจ่าย)
    cuts = sum(1 for a, b in zip(paid, paid[1:]) if a and b and b < a * 0.9)
    first = next((v for v in paid if v), None)
    nyears_between = len(paid) - 1 - paid.index(first) if first else 0
    last_full = paid[-1] if paid else 0
    cagr = ((last_full / first) ** (1 / nyears_between) - 1) * 100 if first and last_full and nyears_between >= 1 else None
    # ปันผล 12 เดือนที่สูงกว่า 1.8 เท่าของฐาน อาจเป็นปันผลพิเศษหรือข้อมูลผิด
    past = sorted(v for v in paid if v)
    median = past[len(past) // 2] if past else None
    if median is not None:
        median = max(median, paid[-1])
    unusual = (ttm / median) if median and ttm > 1.8 * median else None

    fin = stock["financials"]
    fin_years = sorted(fin)
    ni = [fin[y].get("net_income") for y in fin_years]
    rev = [fin[y].get("revenue") for y in fin_years]
    payout = fcf_yield = fcf_cover = mcap = ibd_de = None
    if fin_years:
        last = fin[fin_years[-1]]
        if last.get("net_income") and last["net_income"] > 0 and last.get("div_paid"):
            payout = abs(last["div_paid"]) / last["net_income"] * 100
        # มูลค่าตลาดโดยประมาณ = ราคาล่าสุด × จำนวนหุ้นสามัญจากงบปีล่าสุด (อาจคลาดเคลื่อนถ้าจำนวนหุ้นเพิ่งเปลี่ยน)
        if price and last.get("shares"):
            mcap = price * last["shares"]
        if mcap and last.get("fcf") is not None:
            fcf_yield = last["fcf"] / mcap * 100
        # IBD/Equity = หนี้ที่มีดอกเบี้ย (Yahoo TotalDebt รวมภาระเช่า) ÷ ส่วนของผู้ถือหุ้นรวมส่วนได้เสียที่ไม่มีอำนาจควบคุม
        eq = last.get("equity") or last.get("equity_parent")
        if last.get("debt") is not None and eq and eq > 0:
            ibd_de = last["debt"] / eq
        if last.get("fcf") is not None and last.get("div_paid"):
            fcf_cover = last["fcf"] / abs(last["div_paid"])
    return {
        "ttm_dps": ttm,
        "ttm_yield": (ttm / price * 100) if price and ttm else None,
        "annual": [[y, by_year.get(y, 0.0)] for y in full_years + [today.year]],
        "streak": streak,
        "years_paid": sum(1 for v in paid if v),
        "years_total": len(paid),
        "cuts": cuts,
        "div_cagr": cagr,
        "unusual_ratio": unusual,
        "median_annual": median,
        "last": divs[-1] if divs else None,
        "fin_years": fin_years,
        "ni_cv": cv(ni),
        "rev_cv": cv(rev),
        "loss_years": sum(1 for v in ni if v is not None and v < 0),
        "payout": payout,
        "mcap": mcap,
        "fcf_yield": fcf_yield,
        "fcf_cover": fcf_cover,
        "ibd_de": ibd_de,
    }


def bond_ref():
    try:
        b = json.loads(BOND_FILE.read_text(encoding="utf-8"))
        return {"value": b["value_percent_per_year"], "asof": b["asof"], "source": b["source"]}
    except (OSError, KeyError, ValueError):
        return None


def sethd_ref():
    """สมาชิกดัชนี SETHD พร้อม P/E, P/BV, yield ตามที่ SET แสดง (data/sethd.json ดึงผ่านเบราว์เซอร์)"""
    try:
        return json.loads(SETHD_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_html(payload):
    # หน้าเว็บไม่ใช้รายการปันผลดิบ (ใช้ summary) ตัดออกเพื่อให้ไฟล์เล็ก; ข้อมูลดิบยังอยู่ใน dividends.json
    # อ่าน SETHD ตอนสร้างหน้าเว็บ ไม่ใช่ตอนดึงข้อมูล จึงใช้กับ --html-only ได้
    slim = dict(payload, sethd=sethd_ref(), update_url=os.environ.get("UPDATE_URL"), stocks=[{k: v for k, v in s.items() if k != "dividends"} for s in payload["stocks"]])
    # ป้องกัน </script> ในข้อมูลปิด tag ก่อนเวลา
    blob = json.dumps(slim, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    HTML_FILE.write_text((HERE / "template.html").read_text(encoding="utf-8").replace("__DATA__", blob), encoding="utf-8")


def build(log=print, progress=None):
    """ดึงข้อมูลทุกตัวพร้อมกัน WORKERS เธรด progress(done, total) ถูกเรียกทุกครั้งที่เสร็จหนึ่งตัว"""
    now = datetime.now(TH)
    accessed = now.strftime("%Y-%m-%d %H:%M")
    tickers = read_tickers()
    stocks, errors, done = [], {}, 0

    def work(item):
        sym, sector = item
        try:
            s = fetch(sym, sector)
            s["summary"] = summarize(s, now)
            return sym, s, None
        except NETWORK_ERRORS as e:
            return sym, None, str(e)[:80]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for sym, s, err in pool.map(work, tickers):
            done += 1
            if s:
                stocks.append(s)
            else:
                errors[sym] = err
                log(f"FAIL {sym:12} {err}")
            if progress:
                progress(done, len(tickers))
            elif done % 50 == 0:
                log(f"... {done}/{len(tickers)}")
    payload = {"accessed": accessed, "bond": bond_ref(), "stocks": stocks, "errors": errors}
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    write_html(payload)
    log(f"wrote {HTML_FILE.name} and {DATA_FILE.name} ({len(stocks)} ok, {len(errors)} failed)")
    return payload


if __name__ == "__main__":
    import sys

    if "--html-only" in sys.argv:  # สร้างหน้าเว็บใหม่จากข้อมูลที่ดึงไว้แล้ว (หลังแก้ template.html)
        write_html(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    else:
        build()
