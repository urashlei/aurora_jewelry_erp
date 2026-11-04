# coding: utf-8
"""
AURORA JEWELRY ERP - ENTERPRISE BI & AI DECISION COPILOT
Grounded in Live Enterprise Data, Multi-Supplier Procurement, and Multi-Source Gold Price Benchmarks.
"""

import os
import re
import json
import unicodedata
from google import genai
import urllib.request
import urllib.error

import time
import random

import socket
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # handled below: _find_setting() reads the .env file itself

# ---------------------------------------------------------------------------
# Gemini connection: key / model lookup, error reporting, self-healing model choice
# ---------------------------------------------------------------------------
_KEY_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_PLACEHOLDERS = {"", "MY_GEMINI_API_KEY", "YOUR_API_KEY", "YOUR_GEMINI_API_KEY", "PASTE_YOUR_KEY_HERE"}
DEFAULT_MODELS = [
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]
_WORKING_MODEL = ""          # last model that answered, tried first next time
_LAST_STATUS = {}            # what the last call did (for /api/ai/status)


def _parse_env_file(path):
    """Tiny .env reader (KEY=VALUE, quotes, comments, 'export'). Used when python-dotenv is missing."""
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in ("\"", "'") and v.find(v[0], 1) > 0:
            v = v[1:v.find(v[0], 1)]                 # quoted: keep what is inside the quotes
        elif " #" in v:
            v = v.split(" #", 1)[0].strip()          # unquoted: drop a trailing comment
        values[k.strip()] = v.strip()
    return values


def _env_folders():
    here = Path(__file__).resolve().parent
    seen, out = set(), []
    for f in (here, here.parent, Path.cwd()):
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _find_setting(names, skip=()):
    """Returns (value, where) from the environment first, then from .env files. Re-read on every call."""
    for name in names:
        v = os.environ.get(name, "").strip()
        if v and v not in skip:
            return v, f"environment variable {name}"
    for folder in _env_folders():
        f = folder / ".env"
        if f.is_file():
            vals = _parse_env_file(f)
            for name in names:
                v = vals.get(name, "").strip()
                if v and v not in skip:
                    return v, f"{f} ({name})"
    return "", ""


def _find_api_key():
    return _find_setting(_KEY_NAMES, skip=_PLACEHOLDERS)


class GeminiError(Exception):
    """Gemini could not be used. `hint` explains how to fix it (in Vietnamese)."""
    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


def _generate_sdk(api_key, model, prompt):
    """
    Gọi Gemini qua SDK google-genai.
    Key AQ. phải được gửi đến endpoint AI Studio (generativelanguage.googleapis.com),
    KHÔNG phải Vertex AI (aiplatform.googleapis.com).
    """
    from google import genai
    from google.genai import types

    # Cách 1: Truyền api_key trực tiếp (khuyến nghị cho key AQ. từ AI Studio)
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            top_p=0.8,
            max_output_tokens=4096,
        ),
    )

    if not response.text:
        raise Exception("Empty Gemini response")

    return response.text

class _HTTPFail(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class _EmptyReply(Exception):
    pass


def _error_message(body):
    try:
        err = json.loads(body).get("error", {})
        return f"{err.get('status', '')} {err.get('message', '')}".strip() or body[:200]
    except Exception:
        return (body or "")[:200]

def _hint_for(code, message):
    m = (message or "").lower()
    if "api key not valid" in m or "api_key_invalid" in m or "api key expired" in m:
        return "API key sai, hết hạn hoặc đã bị thu hồi. Tạo key mới tại aistudio.google.com/apikey rồi dán vào .env: GEMINI_API_KEY=..."
    if "location is not supported" in m or "user location" in m:
        return "Khu vực/mạng hiện tại chưa được hỗ trợ cho Gemini API (hoặc gói miễn phí). Bật thanh toán cho project hoặc dùng mạng ở khu vực được hỗ trợ."
    if code in (401, 403):
        return "Key bị từ chối. Kiểm tra key còn hiệu lực và project đã bật Generative Language API (tạo key mới trong AI Studio là cách nhanh nhất)."
    if code == 404:
        return "Tên model không tồn tại với key này. Hệ thống đã tự thử model khác; nếu vẫn lỗi hãy đặt GEMINI_MODEL trong .env (xem /api/ai/status để biết model khả dụng)."
    if code == 429:
        return "Hết hạn mức (quota) hoặc gọi quá nhanh. Đợi 1 phút rồi thử lại, hoặc bật thanh toán cho project."
    if code and code >= 500:
        return "Máy chủ Google đang lỗi tạm thời. Thử lại sau."
    return "Xem chi tiết lỗi ở cửa sổ chạy server."

def gemini_status():
    """Quick self-test for /api/ai/status: is a key found, and does a tiny request work?"""
    key, where = _find_api_key()
    info = {"key_found": bool(key), "key_source": where or "not found",
            "key_preview": ("..." + key[-4:]) if key else "",
            "searched_env_folders": [str(f) for f in _env_folders()],
            "model_setting": _find_setting(("GEMINI_MODEL",))[0] or "(default list: " + ", ".join(DEFAULT_MODELS) + ")"}
    if not key:
        info.update(ok=False, error="No API key found.", hint="Tạo file .env cạnh thư mục backend (hoặc cùng thư mục với ai_agent.py) với dòng GEMINI_API_KEY=... rồi chạy lại server.")
        return info
    try:
        text, model = _call_gemini(key, {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word OK."}]}],
                                          "generationConfig": {"maxOutputTokens": 64, "temperature": 0}})
        info.update(ok=True, model=model, reply=text[:60])
    except GeminiError as e:
        info.update(ok=False, error=str(e)[:500], hint=e.hint)
    return info

# ---------------------------------------------------------------------------
# Business Constants & Conversion Standards
# ---------------------------------------------------------------------------
DEFAULT_MIN_STOCK = 10     # Low stock threshold
REFILL_TARGET = 15         # Normal refill target
MAX_HISTORY_CHARS = 800    # Per message history budget
GOLD_TAEL_GRAMS = 37.5     # 1 Tael (Lượng) = 37.5g
GOLD_CHI_GRAMS = 3.75      # 1 Mace (Chỉ) = 3.75g
DEFAULT_BENCHMARK_PRICE = 88500000  # Default SJC 9999 (VND/Tael)

# ---------------------------------------------------------------------------
# System Instruction (Executive BI Decision Support)
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
RESPONSE PRINCIPLES (MANDATORY):
1. FOCUSED — CONCISE — DECISION-READY:
   - Answer the question directly. Do NOT ramble, do NOT list everything you know.
   - Ideal length: 3-8 lines for simple lookups; 15 lines max for complex analysis.
   - Every reply must cover: (a) current state, (b) the actual numbers, (c) the recommended next action.
   - Do NOT repeat the user's question back, do NOT re-greet, do NOT open with filler.

2. CONSISTENT FORMATTING (MANDATORY):
   - Simple markdown only: **bold** for key figures, `-` for bullets, numbered list for steps.
   - Do NOT use `#` or `##` headings inside chat replies — reserve them only for very long multi-section answers.
   - Do NOT use markdown tables unless >=3 columns of data genuinely need comparison.
   - Currency: comma thousands (e.g. 88,500,000 VND), no "88.5M" unless asked for an overview.
   - Gold weight: 2 decimals for tael/luong (e.g. 61.87 tael), 1 decimal for grams (e.g. 2,320.0 g).
   - Max 3 sections per reply. No more.

3. GROUNDED IN LIVE DATA:
   - Only use the BUSINESS DATA provided. Never invent figures.
   - If the requested data is empty, say "No data available for X in the system" — do NOT speculate.

4. OUT-OF-SCOPE QUERIES:
   - If the question is entirely unrelated to Aurora Jewelry ERP (weather, cooking, social news, schoolwork, etc.): refuse in 1-2 sentences, then suggest one relevant ERP topic they could ask instead. Do NOT give a long explanation of "I am an AI that only supports...".

5. LANGUAGE:
   - User asks in Vietnamese → answer in Vietnamese (professional tone, "tôi" — "anh/chị").
   - User asks in English → answer in English (executive tone, no academic phrasing).

6. GOOD EXAMPLE (focused, decision-ready):
   Q: "What is our current net gold position?"
   A: "**Net gold position: 61.87 tael (2,320.0 g)** — 2,200 g sits in WH-MW vault, the rest across two boutiques.
   - ±1% price sensitivity: **±547,800 VND**.
   - Main risk: SJC benchmark near its peak (88.5M/tael) → consider partial bullion liquidation.
   Want me to run the ±5% stress test?"

7. BAD EXAMPLE (verbose — DO NOT do this):
   "Hello! Thank you for asking about net gold position. This is a very important topic in risk management..."
   → Wrong because: it re-greets, opens with filler, and does not answer directly.

8. SELF-CHECK BEFORE SENDING:
   - Is the reply > 15 lines? If yes, CUT — keep only the 3 most important facts.
   - Any unnecessary greeting or intro line? If yes, DELETE it.
   - Does it contain concrete numbers from BUSINESS DATA? If not, ADD them.
   - Does it end with a clear next action or follow-up question? If not, ADD one.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt(n, digits=0):
    return f"{_num(n):,.{digits}f}"


def _clean_qty(n):
    n = _num(n)
    return int(n) if n == int(n) else round(n, 2)


def _ascii(text):
    text = (text or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _is_vietnamese(text):
    if re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", (text or "").lower()):
        return True
    q = _ascii(text)
    return bool(re.search(r"\b(vang|kho|ton|ban|mua|hang|cua|nen|bao nhieu|sao|the nao|thieu|doanh thu|lenh|du bao|phe duyet|sai lech|kiem ke|gia|nha cung cap|ncc)\b", q))


def _sold_in_pos(p):
    if "showInPos" in p:
        return bool(p["showInPos"])
    return p.get("type") == "finished"


# ---------------------------------------------------------------------------
# Domain Extraction & Fact Builder
# ---------------------------------------------------------------------------
def build_facts(ctx):
    snap = (ctx or {}).get("snapshot") or {}
    warehouses = snap.get("warehouses") or []
    products = snap.get("products") or []
    if not warehouses or not products:
        return None

    wh_by_id = {w.get("id"): w for w in warehouses}
    central = next((w for w in warehouses if w.get("type") != "store"), warehouses[0])
    stores = [w for w in warehouses if w.get("id") != central.get("id")]
    cid = central.get("id")

    # ---- 1. Inventory & Net Gold Exposure ----------------------------------
    wh_totals = {
        w["id"]: {"code": w.get("code"), "name": w.get("name"), "gold_g": 0.0, "value_vnd": 0.0}
        for w in warehouses
    }
    inventory = []
    total_gold = total_value = gold_raw = gold_finished = 0.0
    gold_by_karat = {"24K": 0.0, "18K": 0.0, "14K": 0.0, "Other": 0.0}

    for p in products:
        stocks = p.get("stocks") or {}
        gw = _num(p.get("goldWeightGrams"))
        cost = _num(p.get("unitCostVnd"))
        qty_total = sum(_num(v) for v in stocks.values())
        karat = p.get("karat", "Other")

        for wid, q in stocks.items():
            if wid in wh_totals:
                wh_totals[wid]["gold_g"] += _num(q) * gw
                wh_totals[wid]["value_vnd"] += _num(q) * cost

        item_gold = qty_total * gw
        total_gold += item_gold
        total_value += qty_total * cost

        if karat in gold_by_karat:
            gold_by_karat[karat] += item_gold
        else:
            gold_by_karat["Other"] += item_gold

        if p.get("type") == "raw":
            gold_raw += item_gold
        else:
            gold_finished += item_gold

        inventory.append({
            "sku": p.get("sku"),
            "name": p.get("name"),
            "karat": karat,
            "kind": "raw material" if p.get("type") == "raw" else "finished product",
            "unit": p.get("unit") or ("g" if p.get("type") == "raw" else "pcs"),
            "gold_per_unit_g": gw,
            "cost_vnd": cost,
            "price_vnd": _num(p.get("retailPriceVnd")),
            "stock": {
                wh_by_id[wid].get("code", wid): _clean_qty(q)
                for wid, q in stocks.items() if wid in wh_by_id
            },
            "total_qty": _clean_qty(qty_total),
        })

    # Gold on pending Purchase Orders (incoming exposure)
    pending_po_gold = 0.0
    for po in snap.get("purchaseOrders") or []:
        if po.get("status") != "received":
            prod_match = next((p for p in products if p.get("id") == po.get("productId") or p.get("name") == po.get("productName")), None)
            if prod_match:
                pending_po_gold += _num(po.get("quantity", po.get("quantityGrams"))) * _num(prod_match.get("goldWeightGrams", 1.0))

    net_gold_exposure_g = total_gold + pending_po_gold
    net_exposure_tael = net_gold_exposure_g / GOLD_TAEL_GRAMS

    # Benchmark Gold Prices
    benchmarks = snap.get("benchmarks") or {
        "sjc": {"code": "SJC", "name": "SJC 9999 National Benchmark", "priceTael": 88500000, "priceGram": 2360000, "note": "State-licensed benchmark bar"},
        "doji": {"code": "DOJI", "name": "DOJI 9999 Wholesale Bullion", "priceTael": 88200000, "priceGram": 2352000, "note": "Primary jewelry trade reference"},
        "pnj": {"code": "PNJ", "name": "PNJ 9999 Retail Benchmark", "priceTael": 88600000, "priceGram": 2362667, "note": "Nationwide retail jewelry benchmark"},
        "kitco": {"code": "KITCO", "name": "World Spot (Kitco Converted)", "priceTael": 63200000, "priceGram": 1685333, "note": "London / COMEX conversion (USD 2,740/oz)"},
        "sbv": {"code": "SBV", "name": "State Bank Reference Rate", "priceTael": 87800000, "priceGram": 2341333, "note": "Customs & central bank valuation rate"}
    }
    active_bm_key = snap.get("activeBenchmark") or "sjc"
    active_bm = benchmarks.get(active_bm_key, benchmarks["sjc"])
    active_price_tael = _num(active_bm.get("priceTael", active_bm.get("price_tael")), DEFAULT_BENCHMARK_PRICE)
    active_price_gram = _num(active_bm.get("priceGram", active_bm.get("price_g")), active_price_tael / GOLD_TAEL_GRAMS)

    sensitivity_1pct_vnd = round(net_exposure_tael * active_price_tael * 0.01)
    sensitivity_5pct_vnd = round(net_exposure_tael * active_price_tael * 0.05)
    valuation_at_benchmark_vnd = round(net_exposure_tael * active_price_tael)

    # Multi-benchmark comparison valuations
    benchmark_valuations = {}
    for k, bm in benchmarks.items():
        p_tael = _num(bm.get("priceTael", bm.get("price_tael")), DEFAULT_BENCHMARK_PRICE)
        benchmark_valuations[k] = {
            "name": bm.get("name"),
            "price_tael": p_tael,
            "valuation_vnd": round(net_exposure_tael * p_tael),
            "sens_1pct": round(net_exposure_tael * p_tael * 0.01)
        }

    # ---- 2. Multi-Supplier Sourcing Catalog --------------------------------
    suppliers = snap.get("suppliers") or [
        {
            "id": "sup_sjc",
            "code": "SJC",
            "name": "SJC Gold Corporation",
            "contact": "028-3929-6016",
            "priceList": {"prod_g24k": 2360000, "prod_g18k": 1690000, "prod_silver_ingot": 29000},
            "note": "Official national bullion standard. Strict verification."
        },
        {
            "id": "sup_doji",
            "code": "DOJI",
            "name": "DOJI Gold & Gems Group",
            "contact": "024-2220-6688",
            "priceList": {"prod_g24k": 2352000, "prod_g18k": 1675000, "prod_silver_ingot": 28200},
            "note": "Wholesale casting grain granules. Volume discount: -8,000 đ/g on 24K."
        },
        {
            "id": "sup_phuquy",
            "code": "PHUQUY",
            "name": "Phu Quy Precious Metals",
            "contact": "024-3573-5959",
            "priceList": {"prod_g24k": 2356000, "prod_g18k": 1680000, "prod_silver_ingot": 28000},
            "note": "Competitive fine silver 999 and investment bullion."
        },
        {
            "id": "sup_pnj",
            "code": "PNJ",
            "name": "PNJ Material Supply",
            "contact": "028-3995-1703",
            "priceList": {"prod_g24k": 2365000, "prod_g18k": 1685000, "prod_silver_ingot": 28500},
            "note": "European master alloys and high-purity casting metals."
        },
        {
            "id": "sup_heraeus",
            "code": "HERAEUS",
            "name": "Heraeus Precious Metals Vietnam",
            "contact": "028-3827-0100",
            "priceList": {"prod_g24k": 2358000, "prod_g18k": 1678000, "prod_silver_ingot": 27800},
            "note": "LBMA-certified international bullion grains."
        },
        {
            "id": "sup_viettin",
            "code": "VIETTIN",
            "name": "Viet Tin GIA Diamond Importers",
            "contact": "028-3822-1234",
            "priceList": {"prod_ring_18k_dia": 28000000},
            "note": "Certified loose natural diamonds & luxury settings."
        }
    ]

    # ---- 3. Store Stock Gaps & Days of Inventory (DOI) ---------------------
    alerts = []
    for p in products:
        if not _sold_in_pos(p):
            continue
        stocks = p.get("stocks") or {}
        central_left = _num(stocks.get(cid))
        min_level = _num(p.get("minStock"), DEFAULT_MIN_STOCK)
        target = max(REFILL_TARGET, min_level)
        for st in stores:
            have = _num(stocks.get(st["id"]))
            if have >= min_level:
                continue
            need = target - have
            move = int(min(need, central_left))
            alerts.append({
                "product": p.get("name"),
                "sku": p.get("sku"),
                "store": st.get("code"),
                "status": "OUT OF STOCK" if have <= 0 else "LOW STOCK",
                "stock_now": _clean_qty(have),
                "min_level": _clean_qty(min_level),
                "refill_to": _clean_qty(target),
                "central_available": _clean_qty(central_left),
                "suggested_transfer_qty": move,
                "from": central.get("code"),
                "to": st.get("code"),
                "gap_not_covered_by_central": _clean_qty(max(0, need - move)),
            })
            central_left -= move
    alerts.sort(key=lambda a: (a["stock_now"] / a["min_level"]) if a["min_level"] else 1)

    # ---- 4. Multi-tier Approval Pipeline -----------------------------------
    approvals = snap.get("approvals") or []
    pending_approvals = [a for a in approvals if a.get("status") in ("pending", "PENDING_COO", "PENDING_CFO", "PENDING_MGR")]
    total_pending_approval_vnd = sum(_num(a.get("estimatedValueVnd", a.get("amountVnd"))) for a in pending_approvals)

    # ---- 5. Forecasting & Accuracy Metrics ---------------------------------
    forecast_data = snap.get("forecastData") or {
        "activeScenario": "god_of_wealth",
        "scenarioName": "God of Wealth Festival Peak (+240%)",
        "mape": 7.4,
        "wape": 6.8,
        "trackingSignal": 1.1,
        "biasPercent": 2.3
    }

    # ---- 6. Data Anomalies & Audit Discrepancies ---------------------------
    discrepancies = snap.get("discrepancies") or []
    open_discrepancies = [d for d in discrepancies if d.get("status") in ("open", "investigating")]

    # ---- 7. Production Readiness (MO Check) --------------------------------
    boms = {b.get("id"): b for b in snap.get("boms") or []}
    prod_by_id = {p.get("id"): p for p in products}
    open_orders = [m for m in snap.get("manufacturingOrders") or []
                   if m.get("status") in ("confirmed", "in_progress", "not_available")]

    def _required(c):
        if c.get("required") is not None:
            return _num(c.get("required"))
        return _num(c.get("quantity", c.get("qty"))) * (1 + _num(c.get("lossPct")) / 100)

    mo_checks = []
    for mo in open_orders:
        bom = boms.get(mo.get("bomId"))
        if not bom:
            continue
        reserved = {}
        for other in open_orders:
            if other is mo or other.get("status") == "completed":
                continue
            ob = boms.get(other.get("bomId"))
            for c in (ob or {}).get("components") or []:
                reserved[c.get("productId")] = reserved.get(c.get("productId"), 0.0) + _num(other.get("quantity")) * _required(c)
        lines = []
        for c in bom.get("components") or []:
            comp = prod_by_id.get(c.get("productId"))
            if not comp:
                continue
            in_vault = _num((comp.get("stocks") or {}).get(cid))
            available = max(0.0, in_vault - reserved.get(comp["id"], 0.0))
            need = _num(mo.get("quantity")) * _required(c)
            lines.append({
                "material": comp.get("name"),
                "unit": comp.get("unit") or ("g" if comp.get("type") == "raw" else "pcs"),
                "needed": round(need, 3),
                "available": round(available, 3),
                "short": round(max(0.0, need - available), 3),
            })
        mo_checks.append({
            "order": mo.get("code"),
            "product": mo.get("productName"),
            "qty": _clean_qty(mo.get("quantity")),
            "status": mo.get("status"),
            "materials": lines,
            "available": bool(lines) and all(l["short"] <= 1e-9 for l in lines),
        })

    # ---- 8. Open Purchase Orders -------------------------------------------
    open_pos = []
    for po in snap.get("purchaseOrders") or []:
        if po.get("status") != "received":
            open_pos.append({
                "order": po.get("code"),
                "vendor": po.get("vendor"),
                "item": po.get("productName"),
                "qty": _clean_qty(po.get("quantity", po.get("quantityGrams"))),
                "unit": po.get("unit") or "g",
                "unit_price_vnd": _num(po.get("unitPriceVnd")),
                "total_vnd": _num(po.get("totalVnd")),
                "status": po.get("status"),
            })

    sales_today = _num(snap.get("salesTodayVnd", ctx.get("totalSalesTodayVnd")))

    return {
        "central_warehouse": central.get("code"),
        "net_gold_position": {
            "physical_gold_vault_g": round(wh_totals.get(cid, {}).get("gold_g", 0.0), 1),
            "physical_gold_stores_g": round(sum(wh_totals[w["id"]]["gold_g"] for w in stores if w["id"] in wh_totals), 1),
            "total_physical_gold_g": round(total_gold, 1),
            "total_physical_gold_tael": round(total_gold / GOLD_TAEL_GRAMS, 2),
            "pending_po_gold_g": round(pending_po_gold, 1),
            "net_gold_exposure_g": round(net_gold_exposure_g, 1),
            "net_gold_exposure_tael": round(net_exposure_tael, 2),
            "active_benchmark": {
                "key": active_bm_key,
                "name": active_bm.get("name"),
                "price_tael": active_price_tael,
                "price_gram": active_price_gram,
            },
            "valuation_at_benchmark_vnd": valuation_at_benchmark_vnd,
            "sensitivity_plus_minus_1pct_vnd": sensitivity_1pct_vnd,
            "sensitivity_plus_minus_5pct_vnd": sensitivity_5pct_vnd,
            "benchmark_valuations": benchmark_valuations,
            "gold_by_karat": {k: round(v, 1) for k, v in gold_by_karat.items()},
            "gold_raw_g": round(gold_raw, 1),
            "gold_finished_g": round(gold_finished, 1),
            "casting_loss_benchmark_pct": 1.87
        },
        "company_totals": {
            "total_gold_g": round(total_gold, 1),
            "total_gold_chi": round(total_gold / GOLD_CHI_GRAMS, 1),
            "total_gold_tael": round(total_gold / GOLD_TAEL_GRAMS, 2),
            "inventory_value_at_cost_vnd": round(total_value),
            "sales_today_vnd": round(sales_today),
        },
        "suppliers": suppliers,
        "warehouses": [
            {"code": v["code"], "name": v["name"],
             "gold_g": round(v["gold_g"], 1), "value_vnd": round(v["value_vnd"])}
            for v in wh_totals.values()
        ],
        "inventory": inventory,
        "governance": {
            "pending_approvals": pending_approvals,
            "total_pending_approval_vnd": round(total_pending_approval_vnd),
            "discrepancies": open_discrepancies,
            "forecast": forecast_data,
        },
        "computed": {
            "store_stock_alerts": alerts,
            "open_production_orders": mo_checks,
            "open_purchase_orders": open_pos,
        },
        "recent_stock_moves": [
            {"ref": m.get("reference"), "sku": m.get("productSku"), "from": m.get("fromLocation"),
             "to": m.get("toLocation"), "qty": m.get("quantity"), "type": m.get("type"),
             "time": m.get("timestamp")}
            for m in (snap.get("stockMoves") or [])[:8]
        ],
    }


def _legacy_facts(ctx):
    g = _num(ctx.get("totalGoldGramsAll"))
    return {
        "company_totals": {
            "total_gold_g": round(g, 1),
            "total_gold_chi": round(g / GOLD_CHI_GRAMS, 1),
            "total_gold_tael": round(g / GOLD_TAEL_GRAMS, 2),
            "inventory_value_at_cost_vnd": round(_num(ctx.get("totalInventoryValueVnd"))),
            "sales_today_vnd": round(_num(ctx.get("totalSalesTodayVnd"))),
        },
        "net_gold_position": {
            "total_physical_gold_g": round(g, 1),
            "net_gold_exposure_g": round(g, 1),
            "net_gold_exposure_tael": round(g / GOLD_TAEL_GRAMS, 2),
            "sensitivity_plus_minus_1pct_vnd": round(g / GOLD_TAEL_GRAMS * DEFAULT_BENCHMARK_PRICE * 0.01),
        },
        "computed": {"store_stock_alerts": [], "open_production_orders": [], "open_purchase_orders": []},
        "governance": {"pending_approvals": [], "total_pending_approval_vnd": 0, "discrepancies": [], "forecast": {}},
        "suppliers": [],
        "warehouses": [],
        "inventory": [],
    }


# ---------------------------------------------------------------------------
# Gemini Payload Builder
# ---------------------------------------------------------------------------
def _history_to_contents(history, message, facts):
    contents = []
    for h in (history or []):
        if not isinstance(h, dict) or not h.get("text"):
            continue
        role = "user" if h.get("role") == "user" else "model"
        text = h["text"].strip()[:MAX_HISTORY_CHARS]
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    data_block = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    lang_instruction = (
        "LANGUAGE INSTRUCTION: The user question is in Vietnamese. Answer strictly in Vietnamese."
        if _is_vietnamese(message)
        else "LANGUAGE INSTRUCTION: The user question is in English. Answer strictly in English."
    )
    final = f"BUSINESS DATA (Live Telemetry from ERP & BI Core):\n{data_block}\n\n{lang_instruction}\n\nEXECUTIVE QUESTION:\n{message}"
    if contents and contents[-1]["role"] == "user":
        contents[-1]["parts"][0]["text"] += "\n\n" + final
    else:
        contents.append({"role": "user", "parts": [{"text": final}]})
    return contents


def _build_gemini_payload(message, history, facts):
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION.strip()}]},
        "contents": _history_to_contents(history, message, facts),
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 4096,
        },
    }


# ---------------------------------------------------------------------------
# Local Engine (Domain-Driven Fallback for Enterprise BI)
# ---------------------------------------------------------------------------
ERP_DOMAIN_KEYWORDS = [
    "gold", "vang", "sjc", "doji", "pnj", "kitco", "sbv", "gia", "price",
    "ton", "kho", "stock", "inventory", "vault", "warehouse", "showroom", "boutique",
    "mua", "ban", "po", "purchase", "procure", "supplier", "vendor", "ncc", "nha cung cap",
    "san xuat", "mo", "bom", "duc", "casting", "hao hut", "loss",
    "du bao", "forecast", "wape", "mape", "tracking signal", "bias", "than tai", "scenario",
    "phe duyet", "approval", "coo", "cfo", "tham quyen", "ticket",
    "sai lech", "discrepancy", "kiem ke", "audit", "variance", "doi soat",
    "vi the", "exposure", "hedging", "nhay", "sensitivity", "tael", "luong", "chi",
    "pos", "cashier", "doanh thu", "sales", "revenue", "khach", "customer",
    "dieu chuyen", "transfer", "rebalance", "doi", "stockout", "het hang", "thieu",
    "aurora", "erp", "he thong", "dashboard", "bi", "help", "giup", "huong dan", "quy trinh",
    "overview", "tong quan", "bao cao", "tinh hinh", "chi tiet", "nguyen lieu"
]

INTENTS = [
    ("supplier_pricing", ["nha cung cap", "supplier", "vendor", "ncc", "doji", "phu quy", "heraeus", "viettin", "so sanh gia", "bang gia", "gia mua", "gia ncc", "gia si", "quote"]),
    ("benchmarks", ["gia tham chieu", "benchmark", "sjc", "kitco", "spot", "ty gia", "nguon gia", "nhnn", "lech gia", "spread", "tham chieu"]),
    ("forecast", ["du bao", "forecast", "mape", "wape", "tracking signal", "bias", "sai so", "than tai", "chinh xac", "mua cuoi", "kich ban"]),
    ("approval", ["phe duyet", "approval", "ma tran", "tham quyen", "coo", "cfo", "ai duyet", "quy trinh", "ky duyet", "ticket"]),
    ("discrepancy", ["sai lech", "kiem ke", "du lieu khong chinh xac", "bat thuong", "lech kho", "doi soat", "hao hut", "blind audit", "variance", "dung sai"]),
    ("exposure", ["vi the", "net gold", "hedging", "phong ngua", "rui ro gia", "do nhay", "sensitivity", "luong vang", "exposure"]),
    ("howto", ["huong dan", "button", "nut", "quy trinh", "cach dung", "flow", "demo"]),
    ("stock", ["stockout", "out of stock", "shortage", "low stock", "rebalanc", "transfer", "replenish", "boutique", "store", "het hang", "thieu hang", "chuyen kho", "ton kho", "cua hang", "bo sung", "doi"]),
    ("production", ["production", "manufactur", "casting", "cast", "mo", "bom", "san xuat", "duc", "lenh"]),
    ("purchase", ["purchase", "procure", "po", "buy", "don mua", "nhap kho"]),
    ("sales", ["sales", "revenue", "pos", "doanh thu", "ban hang", "ban"]),
]


def _detect_intent(message):
    q = _ascii(message)
    # Check if the query is in domain
    in_domain = any(k in q for k in ERP_DOMAIN_KEYWORDS)
    if not in_domain:
        return "out_of_scope"

    best, best_score = "overview", 0
    for name, keys in INTENTS:
        score = 0
        for k in keys:
            pattern = rf"\b{re.escape(k)}\b" if len(k) <= 3 else rf"\b{re.escape(k)}"
            if re.search(pattern, q):
                score += 1
        if score > best_score:
            best, best_score = name, score
    return best


def _local_reply(message, facts):
    vi = _is_vietnamese(message)

    def t(vn, en):
        return vn if vi else en

    ct = facts["company_totals"]
    pos_data = facts.get("net_gold_position") or {}
    gov = facts.get("governance") or {}
    comp = facts.get("computed", {})
    suppliers = facts.get("suppliers", [])
    alerts = comp.get("store_stock_alerts", [])
    mos = comp.get("open_production_orders", [])
    purchase_pos = comp.get("open_purchase_orders", [])
    approvals = gov.get("pending_approvals", [])
    discrepancies = gov.get("discrepancies", [])
    forecast = gov.get("forecast", {})
    active_bm = pos_data.get("active_benchmark", {})
    intent = _detect_intent(message)

    # ----- 0. OUT OF SCOPE --------------------------------------------------
    if intent == "out_of_scope":
        return t(
            "Tôi là Trợ lý Điều hành AI của hệ thống **Aurora Jewelry ERP**.\n\n"
            "Hiện tại tôi chỉ hỗ trợ các thông tin nghiệp vụ, dữ liệu vận hành và quyết định quản trị trong hệ thống "
            "(Quản trị tồn kho vàng, Phân hệ Mua sắm & Bảng giá riêng theo từng NCC, Sản xuất đúc & Hao hụt BOM 1.87%, "
            "Bán lẻ POS, Đề xuất duyệt 1-Click và BI Dashboard).\n\n"
            "Quý quản trị có thể hỏi tôi về: **Vị thế vàng ròng**, **So sánh giá mua các nhà cung cấp**, **Phiếu chờ duyệt**, "
            "hoặc **Cảnh báo đứt hàng tại các showroom**!",
            "I am the AI Executive Decision Copilot for **Aurora Jewelry ERP**.\n\n"
            "I am dedicated exclusively to supporting business operations, data analytics, and executive decisions within the Aurora ERP system "
            "(Net Gold Exposure, Multi-Supplier Procurement Quotes, Casting BOM & Loss, Retail POS, Multi-tier Approvals, and BI Decision Analytics).\n\n"
            "Please feel free to ask about our **Net Gold Position**, **Supplier Quote Comparisons**, **Pending Approvals**, "
            "or **Store Stockout Vulnerabilities**!"
        )

    # ----- 1. SUPPLIER PRICING & PROCUREMENT SOURCING -----------------------
    if intent == "supplier_pricing":
        sup_rows = []
        for s in suppliers:
            pl = s.get("priceList") or {}
            p24k = pl.get("prod_g24k")
            p18k = pl.get("prod_g18k")
            p24k_txt = f"{_fmt(p24k)} đ/g" if p24k else "N/A"
            p18k_txt = f"{_fmt(p18k)} đ/g" if p18k else "N/A"
            sup_rows.append(f"- **{s.get('name')} ({s.get('code', 'NCC')})**: 24K: {p24k_txt} · 18K: {p18k_txt} ({s.get('note', '')})")

        return (t(
            "**Cơ chế Giá mua theo từng Nhà cung cấp (Procurement Pricing):**\n"
            "Doanh nghiệp không áp dụng một mức giá cố định mà thiết lập hợp đồng và đàm phán riêng với từng NCC:\n\n"
            + "\n".join(sup_rows) + "\n\n"
            "**Đánh giá & Khuyến nghị Nhà quản trị:**\n"
            "1. **Đúc trang sức 24K khối lượng lớn:** Nên ưu tiên đặt hàng qua **DOJI** (2,352,000 đ/g) nhờ chiết khấu hạt đúc sỉ (-8,000 đ/g so với SJC chuẩn), giúp tiết kiệm đáng kể chi phí vốn.\n"
            "2. **Dự trữ vàng miếng chuẩn quốc gia:** Mua từ **SJC Gold Corporation** (2,360,000 đ/g) khi cần tài sản thanh khoản cao bảo chứng thanh toán.\n"
            "3. **Hợp kim Master Alloy Ý:** Nhập từ **PNJ Material Supply** (1,685,000 đ/g) để đảm bảo độ bóng và chống oxy hóa cho nhẫn 18K.",
            "**Supplier-Specific Sourcing & Procurement Pricing:**\n"
            "Aurora maintains tailored contracts and distinct price quotes with each vendor, avoiding rigid fixed pricing:\n\n"
            + "\n".join(sup_rows) + "\n\n"
            "**Executive Recommendations:**\n"
            "1. **Bulk 24K Casting Production:** Prioritize **DOJI Group** (2,352,000 VND/g) for casting grain batches due to their volume discount (-8,000 VND/g vs SJC), directly optimizing material COGS.\n"
            "2. **National Bullion Standard:** Source from **SJC Gold Corporation** (2,360,000 VND/g) when certified state-licensed bar liquidity is required.\n"
            "3. **Italian Master Alloys (18K):** Order from **PNJ Material Supply** (1,685,000 VND/g) to maintain casting ductility and anti-tarnish standards."
        ))

    # ----- 2. BENCHMARKS & REFERENCE PRICES ---------------------------------
    if intent == "benchmarks":
        bm_name = active_bm.get("name", "SJC 9999")
        bm_price = _fmt(active_bm.get("price_tael", DEFAULT_BENCHMARK_PRICE))
        return (t(
            f"**Quản trị Nguồn Giá Tham Chiếu (Reference Price Benchmarks):**\n"
            f"- Nguồn tham chiếu đang kích hoạt trên Dashboard: **{bm_name}** ({bm_price} đ/lượng).\n"
            "- **Nguyên tắc cốt lõi:** SJC chỉ là một nguồn giá tham chiếu tài chính của thị trường, KHÔNG phải là nhà cung cấp mặc định của doanh nghiệp.\n"
            "- Các nguồn tham chiếu tích hợp trên BI Dashboard:\n"
            "  * **SJC 9999:** 88,500,000 đ/lượng (Chuẩn thương hiệu quốc gia)\n"
            "  * **DOJI 9999:** 88,200,000 đ/lượng (Giá sỉ vàng đúc thị trường)\n"
            "  * **PNJ 9999:** 88,600,000 đ/lượng (Mặt bằng bán lẻ kim hoàn)\n"
            "  * **World Spot Kitco:** 63,200,000 đ/lượng (Chênh lệch vàng trong nước ~25.3M đ/lượng)\n"
            "  * **State Bank Reference:** 87,800,000 đ/lượng (Tỷ giá tham chiếu hải quan / liên ngân hàng)\n\n"
            "**Ý nghĩa đối với nhà quản trị:** Giá tham chiếu dùng để tính Định giá Tồn kho Vàng Ròng và Ma trận Độ nhạy rủi ro (Sensitivity ±1% và ±5%). Việc chuyển đổi nguồn tham chiếu trên Dashboard giúp kiểm tra kịch bản phòng ngừa rủi ro (Hedging) trong các bối cảnh biên độ thị trường khác nhau.",
            f"**Reference Gold Price Benchmarks & Valuation:**\n"
            f"- Currently active benchmark on BI Dashboard: **{bm_name}** ({bm_price} VND/Tael).\n"
            "- **Core Governance Principle:** SJC is merely one external financial benchmark index, NOT Aurora's default or sole supplier.\n"
            "- Available benchmark feeds supported on the BI Dashboard:\n"
            "  * **SJC 9999:** 88,500,000 VND/Tael (National standard)\n"
            "  * **DOJI 9999:** 88,200,000 VND/Tael (Wholesale jewelry trade benchmark)\n"
            "  * **PNJ 9999:** 88,600,000 VND/Tael (Nationwide retail reference)\n"
            "  * **World Spot (Kitco Converted):** 63,200,000 VND/Tael (Domestic premium ~25.3M VND/Tael)\n"
            "  * **State Bank Interbank:** 87,800,000 VND/Tael (Customs & interbank reference)\n\n"
            "**Executive Utility:** Benchmarks drive Net Gold Exposure valuation and ±1% sensitivity matrices. Switching benchmark sources allows managers to evaluate portfolio resilience under varying spread environments."
        ))

    # ----- 3. FORECAST & ACCURACY ------------------------------------------
    if intent == "forecast":
        mape = forecast.get("mape", 7.4)
        wape = forecast.get("wape", 6.8)
        ts = forecast.get("trackingSignal", 1.1)
        bias = forecast.get("biasPercent", 2.3)
        scenario = forecast.get("scenarioName", "Vía Thần Tài")

        return (t(
            f"**Dự báo Nhu cầu & Đánh giá Độ tin cậy Mô hình:**\n"
            f"- Kịch bản hoạt động: **{scenario}**\n"
            f"- Sai số có trọng số WAPE: **{wape}%** (Chuẩn xuất sắc < 10%)\n"
            f"- Sai số trung bình MAPE: **{mape}%**\n"
            f"- Tracking Signal: **{ts}** (nằm an toàn trong dải kiểm soát [-4, +4], không bị lệch xu hướng)\n"
            f"- Forecast Bias: **+{bias}%** (chủ động duy trì lượng đệm dương nhẹ để chống đứt hàng cao điểm)\n\n"
            "**Khuyến nghị điều hành:**\n"
            "1. Chọn kịch bản **Vía Thần Tài** trên BI Dashboard để kích hoạt hệ số dự phòng x3 cho Nhẫn Kim Tiền 24K.\n"
            "2. Khởi tạo Lệnh sản xuất (MO) đúc trước 50 chiếc Nhẫn 24K tại nhà máy Gò Vấp để kịp hoàn thiện trước đợt cao điểm.",
            f"**Demand Forecasting & Model Reliability:**\n"
            f"- Active Scenario: **{scenario}**\n"
            f"- Weighted Absolute Percentage Error (WAPE): **{wape}%** (Outstanding benchmark < 10%)\n"
            f"- Mean Absolute Percentage Error (MAPE): **{mape}%**\n"
            f"- Tracking Signal: **{ts}** (well within statistical control boundary [-4, +4])\n"
            f"- Forecast Bias: **+{bias}%** (conservative positive buffer to prevent stockouts during peak retail windows)\n\n"
            "**Actionable Decisions:**\n"
            "1. Toggle the **God of Wealth** scenario in the BI Dashboard to scale safety buffers x3 for 24K Fortune Rings.\n"
            "2. Trigger an advance Casting MO for 50 units at Go Vap Plant at least 7 days before seasonal demand peaks."
        ))

    # ----- 4. APPROVAL MATRIX & WORKFLOWS -----------------------------------
    if intent == "approval":
        if not approvals:
            return t(
                "**Phân quyền & Phê duyệt:** Hiện không có phiếu đề xuất nào đang chờ ký duyệt. Toàn bộ chuỗi vận hành thông suốt.",
                "**Governance & Approvals:** No pending approval requests in the pipeline. All operations are clear."
            )
        lines = [
            f"- **{a.get('id', 'REQ')}** ({a.get('type', 'Đề xuất')}): {_fmt(a.get('estimatedValueVnd', a.get('amountVnd')))} đ · Thẩm quyền: **{a.get('approverRole', a.get('assignedRole', 'COO'))}** · {a.get('title', a.get('detail', ''))}"
            for a in approvals[:4]
        ]
        return (t(
            f"**Danh sách Phiếu Chờ Phê duyệt ({len(approvals)} phiếu - Tổng giá trị: {_fmt(gov.get('total_pending_approval_vnd'))} đ):**\n"
            + "\n".join(lines) + "\n\n"
            "**Quy tắc Thẩm quyền:**\n"
            "- Cửa hàng trưởng: Điều chuyển tồn kho ≤ 50 triệu đ.\n"
            "- COO: Điều chuyển chiến lược và lệnh đúc 50 - 300 triệu đ.\n"
            "- CFO: Mua sắm vàng thô và lô đúc giá trị lớn > 300 triệu đ.\n"
            "Quý quản trị có thể thực hiện **[Duyệt 1-Click]** hoặc **[Từ chối]** trực tiếp tại Tab 'Đề xuất & Phê duyệt' trên BI Dashboard.",
            f"**Pending Governance Approvals ({len(approvals)} ticket(s) - Total Value: {_fmt(gov.get('total_pending_approval_vnd'))} VND):**\n"
            + "\n".join(lines) + "\n\n"
            "**Authority Governance Rules:**\n"
            "- Store Manager: Operational store rebalancing ≤ 50M VND.\n"
            "- COO: Strategic transfers & casting batches 50M - 300M VND.\n"
            "- CFO: High-value bullion procurement & large casting MOs > 300M VND.\n"
            "Executives can execute **[1-Click Approve]** or **[Reject]** directly in the BI Dashboard 'Prescriptive & Approvals' tab."
        ))

    # ----- 5. DATA DISCREPANCY & AUDIT RECONCILIATION -----------------------
    if intent == "discrepancy":
        if not discrepancies:
            return t(
                "**Kiểm soát Dữ liệu & Kiểm kê:** Toàn bộ dữ liệu kiểm kê khớp 100% với cân phân tích. Không phát hiện sai lệch hoặc hao hụt bất thường.",
                "**Data Governance & Audit:** Physical stock matches analytical scale records 100%. No anomalies or casting loss spikes detected."
            )
        lines = [
            f"- **{d.get('id', d.get('ticketId'))}** ({d.get('sku', '')}): Lệch {_fmt(d.get('varianceGrams', d.get('goldWeightLossGrams')), 2)}g vàng · Trạng thái: **{d.get('status')}** · Kho: {d.get('warehouseCode', 'WH')}"
            for d in discrepancies[:3]
        ]
        return (t(
            f"**Cảnh báo Sai lệch Kiểm kê ({len(discrepancies)} phiếu bất thường):**\n"
            + "\n".join(lines) + "\n\n"
            "**Quy trình Đối soát 3 Cấp chuẩn:**\n"
            "1. Lệch ≤ ±0.005g: Dung sai cân phân tích tự động bỏ qua.\n"
            "2. Lệch 0.005g - 0.5g: Cửa hàng trưởng cân lại lần 2 trong 2 giờ.\n"
            "3. Lệch > 0.5g: Kích hoạt đối soát kép (Cửa hàng trưởng + Kiểm soát nội bộ) và rà soát camera tủ trưng bày.\n"
            "Thao tác giải quyết: Nhấn **[Ký Biên bản & Đóng phiếu]** trên BI Dashboard sau khi hoàn tất đối soát.",
            f"**Physical Audit Discrepancies ({len(discrepancies)} active ticket(s)):**\n"
            + "\n".join(lines) + "\n\n"
            "**3-Tier Blind Audit Protocol:**\n"
            "1. Variance ≤ ±0.005g: Analytical balance tolerance (auto-cleared).\n"
            "2. Variance 0.005g - 0.5g: Secondary re-weighing by Store Manager within 2 hours.\n"
            "3. Variance > 0.5g: Critical alert requiring dual sign-off (Store Manager + Internal Auditor) and CCTV audit.\n"
            "Action: Click **[Sign Protocol & Close]** on the BI Dashboard once reconciled."
        ))

    # ----- 6. NET GOLD EXPOSURE & RISK SENSITIVITY --------------------------
    if intent == "exposure":
        net_g = pos_data.get("net_gold_exposure_g", ct["total_gold_g"])
        net_tael = pos_data.get("net_gold_exposure_tael", ct["total_gold_tael"])
        vault_g = pos_data.get("physical_gold_vault_g", 0)
        stores_g = pos_data.get("physical_gold_stores_g", 0)
        sens1 = pos_data.get("sensitivity_plus_minus_1pct_vnd", 0)
        bm_name = active_bm.get("name", "SJC 9999")

        return (t(
            f"**Vị thế Vàng Ròng & Phân tích Độ nhạy Rủi ro:**\n"
            f"- Tổng vị thế vàng ròng (Net Gold Exposure): **{_fmt(net_tael, 2)} lượng** ({_fmt(net_g, 1)} g vàng nguyên chất)\n"
            f"  * Tại két trung tâm Gò Vấp (WH-MW): {_fmt(vault_g, 1)} g\n"
            f"  * Tại hệ thống cửa hàng (WH-PN, WH-Q1): {_fmt(stores_g, 1)} g\n"
            f"- Nguồn giá tham chiếu: **{bm_name}** ({_fmt(active_bm.get('price_tael', DEFAULT_BENCHMARK_PRICE))} đ/lượng)\n"
            f"- Độ nhạy danh mục (±1% giá vàng): **±{_fmt(sens1)} đ**\n"
            f"- Hệ số hao hụt đúc định mức (BOM): **1.87%**\n\n"
            "**Khuyến nghị:** Với vị thế ròng hiện tại, biến động 1% của giá vàng sẽ tác động danh mục xấp xỉ "
            f"±{_fmt(sens1)} đ. Doanh nghiệp có thể chủ động chuyển đổi nguồn tham chiếu trên Dashboard để đánh giá phòng ngừa rủi ro giá.",
            f"**Net Gold Position & Price Sensitivity Analysis:**\n"
            f"- Net Gold Exposure: **{_fmt(net_tael, 2)} Tael** ({_fmt(net_g, 1)} grams of fine gold)\n"
            f"  * Central Vault (WH-MW): {_fmt(vault_g, 1)} g\n"
            f"  * Boutique Displays (WH-PN, WH-Q1): {_fmt(stores_g, 1)} g\n"
            f"- Active Reference Benchmark: **{bm_name}** ({_fmt(active_bm.get('price_tael', DEFAULT_BENCHMARK_PRICE))} VND/Tael)\n"
            f"- Price Sensitivity (±1% shift): **±{_fmt(sens1)} VND**\n"
            f"- Standard Casting Loss Benchmark: **1.87%**\n\n"
            "**Executive Insight:** A 1% market move shifts balance sheet equity by approximately "
            f"±{_fmt(sens1)} VND. Executives can test alternative benchmark scenarios on the BI Dashboard to evaluate hedging strategies."
        ))

    # ----- 7. STORE STOCK & DOI REBALANCING ---------------------------------
    if intent == "stock":
        if not alerts:
            return t(
                "**Tồn kho Cửa hàng:** Tất cả các cửa hàng đều đang đảm bảo mức tồn an toàn (DOI > 7 ngày). Không có rủi ro đứt hàng.",
                "**Store Stock Health:** All retail boutiques maintain healthy safety stock (DOI > 7 days). No stockout vulnerability detected."
            )
        lines = [
            f"- **{a['product']}** tại **{a['store']}**: Tồn hiện tại {a['stock_now']} (Tối thiểu: {a['min_level']}) ➜ Đề xuất chuyển **{a['suggested_transfer_qty']} pcs** từ {a['from']}."
            for a in alerts[:3]
        ]
        return (t(
            f"**Cảnh báo Nguy cơ Đứt hàng tại Showroom ({len(alerts)} sản phẩm):**\n"
            + "\n".join(lines) + "\n\n"
            "**Hành động:** Chuyển sang Tab 'Ma trận Tồn kho Cửa hàng' hoặc 'Đề xuất & Phê duyệt' trên BI Dashboard để ký duyệt lệnh điều chuyển bổ sung.",
            f"**Store Stockout Alerts ({len(alerts)} SKU(s) below threshold):**\n"
            + "\n".join(lines) + "\n\n"
            "**Action:** Switch to the 'Store Matrix' or 'Prescriptive & Approvals' tab on the BI Dashboard to approve stock replenishment."
        ))

    # ----- 8. MANUFACTURING & CASTING BOM -----------------------------------
    if intent == "production":
        short = [m for m in mos if not m["available"]]
        return (t(
            f"**Sản xuất & Lệnh đúc Gò Vấp:** Có {len(mos)} lệnh sản xuất ({len(short)} lệnh đang thiếu nguyên liệu cần xử lý).\n"
            "- Hao hụt đúc tiêu chuẩn: 1.87% theo BOM.\n"
            "- Để kiểm tra chi tiết, mở phân hệ Manufacturing trên menu chính.",
            f"**Manufacturing & Casting Operations:** {len(mos)} MO(s) in pipeline ({len(short)} blocked by material shortages).\n"
            "- Standard casting loss factor: 1.87% per BOM.\n"
            "- Review component allocations under the Manufacturing tab."
        ))

    # ----- 9. PURCHASE & INTAKE ---------------------------------------------
    if intent == "purchase":
        if not purchase_pos:
            return t(
                "**Mua sắm (Procurement):** Hiện không có đơn PO nào đang chờ nhận hàng vào két.",
                "**Procurement:** No pending purchase orders awaiting vault receipt."
            )
        lines = [f"- {p['order']} ({p['vendor']}): {p['qty']} {p['unit']} ({_fmt(p['total_vnd'])} đ)" for p in purchase_pos[:3]]
        return (t(
            f"**Đơn Mua Hàng Đang Chờ Nhập Kho ({len(purchase_pos)} đơn):**\n"
            + "\n".join(lines) + "\n\n"
            "**Thao tác:** Vào phân hệ Procurement, nhấn 'Receive Goods into Vault' để hoàn tất cân đo và nhập két WH-MW.",
            f"**Pending Purchase Orders Awaiting Vault Intake ({len(purchase_pos)} PO(s)):**\n"
            + "\n".join(lines) + "\n\n"
            "**Action:** Navigate to Procurement and click 'Receive Goods into Vault' to verify weights and ingest into WH-MW."
        ))

    # ----- 10. SALES & POS --------------------------------------------------
    if intent == "sales":
        return t(
            f"**Doanh thu POS Hôm nay:** {_fmt(ct['sales_today_vnd'])} đ.\n"
            "Doanh số bán lẻ được cập nhật theo thời gian thực từ các quầy thu ngân tại Phú Nhuận và Quận 1.",
            f"**Today's POS Sales:** {_fmt(ct['sales_today_vnd'])} VND.\n"
            "Retail transactions synchronize in real time from boutique registers at Phu Nhuan and District 1."
        )

    # ----- 11. HOWTO --------------------------------------------------------
    if intent == "howto":
        return t(
            "**Quy trình Vận hành Vàng 4 bước chuẩn BI của Aurora Jewelry:**\n"
            "1. **Procurement:** Mua nguyên liệu theo báo giá riêng của NCC (DOJI, SJC, Phu Quy, PNJ) và nhập két WH-MW.\n"
            "2. **Manufacturing:** Đúc trang sức theo BOM với tỷ lệ hao hụt định mức 1.87%.\n"
            "3. **BI Dashboard:** Theo dõi Vị thế Vàng Ròng, đối chiếu các nguồn giá tham chiếu, duyệt lệnh điều chuyển liên kho theo DOI.\n"
            "4. **Retail POS & Audit:** Bán hàng tại showroom và định kỳ kiểm kê mù theo chuẩn dung sai 3 cấp.",
            "**Aurora 4-Step Gold Enterprise Workflow:**\n"
            "1. **Procurement:** Source raw gold using supplier-specific quotes (DOJI, SJC, Phu Quy, PNJ) into WH-MW vault.\n"
            "2. **Manufacturing:** Cast jewelry using BOM specifications with 1.87% casting loss control.\n"
            "3. **BI Dashboard:** Monitor Net Gold Exposure across reference benchmarks and approve transfers.\n"
            "4. **Retail POS & Audit:** Retail sales at boutiques and blind physical audits with 3-tier tolerance protocol."
        )

    # ----- 12. DEFAULT OVERVIEW ---------------------------------------------
    net_g = pos_data.get("net_gold_exposure_g", ct["total_gold_g"])
    net_tael = pos_data.get("net_gold_exposure_tael", ct["total_gold_tael"])
    sens1 = pos_data.get("sensitivity_plus_minus_1pct_vnd", 0)

    return t(
        f"**Tổng quan Điều hành Doanh nghiệp Aurora Jewelry:**\n"
        f"- **Vị thế Vàng Ròng:** {_fmt(net_tael, 2)} lượng ({_fmt(net_g, 1)} g vàng) · Độ nhạy ±1%: ±{_fmt(sens1)} đ.\n"
        f"- **Giá trị Tồn kho (giá vốn):** {_fmt(ct['inventory_value_at_cost_vnd'])} đ · Doanh số hôm nay: {_fmt(ct['sales_today_vnd'])} đ.\n"
        f"- **Phiếu chờ duyệt:** {len(approvals)} phiếu ({_fmt(gov.get('total_pending_approval_vnd', 0))} đ).\n"
        f"- **Độ chính xác dự báo (WAPE):** {forecast.get('wape', 6.8)}% (Kịch bản: {forecast.get('scenarioName', 'Vía Thần Tài')}).\n"
        f"- **Đối tác cung ứng:** {len(suppliers)} nhà cung cấp ký hợp đồng với cơ chế báo giá riêng biệt.\n\n"
        "Quý quản trị có thể yêu cầu tôi phân tích sâu hơn về bất kỳ phân hệ nào!",
        f"**Aurora Jewelry Executive Operations Overview:**\n"
        f"- **Net Gold Exposure:** {_fmt(net_tael, 2)} Tael ({_fmt(net_g, 1)} g gold) · ±1% Sensitivity: ±{_fmt(sens1)} VND.\n"
        f"- **Inventory Valuation (at cost):** {_fmt(ct['inventory_value_at_cost_vnd'])} VND · Sales Today: {_fmt(ct['sales_today_vnd'])} VND.\n"
        f"- **Pending Governance Approvals:** {len(approvals)} ticket(s) ({_fmt(gov.get('total_pending_approval_vnd', 0))} VND).\n"
        f"- **Forecast Accuracy (WAPE):** {forecast.get('wape', 6.8)}% (Scenario: {forecast.get('scenarioName', 'God of Wealth')}).\n"
        f"- **Sourcing Partners:** {len(suppliers)} contracted suppliers with distinct negotiated quotes.\n\n"
        "Feel free to ask for deeper analysis on any operational module!"
    )


def ask_gemini_or_local(message: str, history: list = None, erp_context: dict = None) -> dict:
    ctx = erp_context or {}
    message = (message or "").strip()
    facts = build_facts(ctx) or _legacy_facts(ctx)

    intent = _detect_intent(message)
    print("MESSAGE =", message)
    print("INTENT =", intent)
    print("HISTORY SIZE =", len(history or []))

    api_key, key_source = _find_api_key()
    reason = ""

    if api_key:
        try:
            payload = _build_gemini_payload(message, history, facts)
            prompt = f"{SYSTEM_INSTRUCTION}\n\nBUSINESS DATA:\n{json.dumps(facts, ensure_ascii=False)}\n\nQUESTION:\n{message}"

            env_model = _find_setting(("GEMINI_MODEL",))[0]
            models_to_try = []
            if env_model:
                models_to_try.append(env_model)
            for m in DEFAULT_MODELS:
                if m not in models_to_try:
                    models_to_try.append(m)

            last_error = None
            for model in models_to_try:
                for attempt in range(2):
                    try:
                        print(f"[AI Agent] Trying model = {model} (attempt {attempt + 1}) ...")
                        reply = _generate_sdk(api_key, model, prompt)
                        _LAST_STATUS.update(ok=True, model=model, error="")
                        print(f"[AI Agent] ✅ Gemini OK (model={model})")
                        return {"source": "gemini", "model": model, "reply": reply}
                    except Exception as e:
                        err_str = str(e)
                        is_503 = "503" in err_str or "UNAVAILABLE" in err_str
                        print(f"[AI Agent] ❌ {model} attempt {attempt + 1} failed -> {e}")
                        last_error = e
                        if is_503 and attempt == 0:
                            wait = 2 + random.uniform(0, 1)
                            print(f"[AI Agent] 503 detected, retrying in {wait:.1f}s ...")
                            time.sleep(wait)
                        else:
                            break

            reason = f"All models failed after retries. Last error: {last_error}"
            _LAST_STATUS.update(ok=False, error=reason)
            print(f"[AI Agent] {reason}")

        except Exception as e:
            reason = f"unexpected error: {type(e).__name__}: {e}"
            _LAST_STATUS.update(ok=False, error=reason)
            print(f"[AI Agent] {reason}")
    else:
        reason = (
            "No API key found (looked for GEMINI_API_KEY / GOOGLE_API_KEY in environment "
            f"and .env files in: {[str(f) for f in _env_folders()]})."
        )
        print(f"[AI Agent] {reason}")

    # 🔴 QUAN TRỌNG: LUÔN trả về fallback local khi Gemini không dùng được
    print(f"[AI Agent] RETURNING LOCAL FALLBACK. Reason: {reason}")
    return {
        "source": "local_fallback",
        "reply": _local_reply(message, facts),
        "gemini_error": reason
    }