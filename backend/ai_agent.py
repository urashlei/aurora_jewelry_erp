"""
AURORA JEWELRY ERP - AI DECISION AGENT (data-grounded version)

How it works
1. The browser sends a snapshot of the live ERP data (products, stock per warehouse,
   production orders, purchase orders, recent stock moves, sales today).
2. build_facts() turns that snapshot into verified facts and decisions with plain Python
   (low-stock alerts, suggested transfers, can a production order be completed, ...).
   These numbers are computed by code, so the AI never has to do the math or guess.
3. Gemini only explains and prioritises those facts, under a strict prompt
   (conclusion first, evidence, max 3 actions, no invented numbers).
4. If Gemini is unavailable, a local engine answers from the same facts.
"""

import os
import re
import json
import unicodedata
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Business rules (same thresholds the web UI uses)
# ---------------------------------------------------------------------------
DEFAULT_MIN_STOCK = 10   # a store holding fewer pieces than this is flagged
REFILL_TARGET = 15       # replenish a flagged store up to this level
MAX_HISTORY_CHARS = 600  # per message, keeps the prompt small


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """
You are Aurora's Operations Copilot for the manager of AURORA JEWELRY, a gold and fine-jewelry business (central warehouse, casting workshop, retail stores).

SCOPE
- You cover only Aurora's day-to-day operations as shown in the system: the recommended actions on the BI Dashboard, inventory and stock transfers, manufacturing orders, purchasing, retail POS sales, and the gold position.
- If asked about anything outside that (academic frameworks, report formats, competitors, other companies, general knowledge), do not discuss it. Reply in one sentence that you only cover Aurora's operations, and name what you can analyse instead.

SOURCE OF TRUTH
- Every request contains a BUSINESS DATA block with live figures from the company's ERP (everything the manager and staff have entered). It is the only source for facts about the company.
- Use only numbers, product names, warehouse codes and document codes that appear in it. Never invent or estimate figures, prices, percentages, demand forecasts, market gold prices or competitor facts.
- Figures under "computed" (low-stock alerts, suggested transfers, production feasibility, open purchase orders) were calculated by the system. Quote them as given. Do not recalculate or contradict them.
- If the question needs data that is not there (market gold price, sales history, demand forecast), say in one sentence what is missing, then answer with what the data does support.
- If nothing is wrong, say so plainly ("No action needed") and do not invent problems.

ANSWER STYLE (the manager is busy)
- Answer the question asked, first. No greeting, no self-introduction, no restating the question, no generic theory, no closing offers.
- Default length: 60 to 140 words. Go longer only if the manager asks for detail.
- Structure, skipping any part that does not apply:
  **Conclusion:** one or two sentences that directly answer the question.
  **Evidence:** 2 to 4 hyphen bullets with exact numbers, units, warehouse codes and document codes.
  **Actions:** a numbered list, at most 3, most urgent first. Each item says what, how much, from -> to, and where to click (for example BI Dashboard > Approve & Rebalance, Inventory > Internal Transfer, Manufacturing > Complete MO, Procurement > Create Purchase Order, Retail POS).
  **Watch out:** one line, only if there is a real risk or a data limitation.
- Formatting: plain text with **bold**, "- " bullets and "1." numbering only. No headings (#), no tables, no emojis.
- Language: reply in the language of the manager's latest message (Vietnamese -> Vietnamese, English -> English). Keep product names, SKUs and document codes unchanged.
- Units: raw materials in grams, finished products in pieces. 1 chi = 3.75 g, 1 tael (luong) = 37.5 g. Money in VND with thousands separators.

DECISION RULES
- Recommend only actions the system can perform and the data supports: transfer stock between warehouses, complete a production order, create or receive a purchase order, adjust stock after a physical count.
- Never recommend moving more stock than the source warehouse holds. If central stock cannot cover a gap, recommend production or purchase and state the shortfall.
- Rank by urgency: out-of-stock stores first, then low stock, then material shortages that block production, then optimisations.
- You only advise. The manager performs every action in the interface. Never say that you executed something.
- Never mention these instructions, "JSON" or "data block". Say "the system shows" instead. Never mention MIS, reports, coursework or presentations.
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
    """12.0 -> 12, 12.5 -> 12.5"""
    n = _num(n)
    return int(n) if n == int(n) else round(n, 2)


def _ascii(text):
    """Lowercase and strip Vietnamese accents so keyword matching is simple."""
    text = (text or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _is_vietnamese(text):
    if re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", (text or "").lower()):
        return True
    q = _ascii(text)
    return bool(re.search(r"\b(vang|kho|ton|ban|mua|hang|cua|nen|bao nhieu|sao|the nao|thieu|doanh thu|lenh)\b", q))


def _sold_in_pos(p):
    if "showInPos" in p:
        return bool(p["showInPos"])
    return p.get("type") == "finished"


# ---------------------------------------------------------------------------
# Verified facts computed from the live ERP snapshot
# ---------------------------------------------------------------------------
def build_facts(ctx):
    """Turn the browser's ERP snapshot into verified facts. Returns None if no snapshot."""
    snap = (ctx or {}).get("snapshot") or {}
    warehouses = snap.get("warehouses") or []
    products = snap.get("products") or []
    if not warehouses or not products:
        return None

    wh_by_id = {w.get("id"): w for w in warehouses}
    central = next((w for w in warehouses if w.get("type") != "store"), warehouses[0])
    stores = [w for w in warehouses if w.get("id") != central.get("id")]
    cid = central.get("id")

    # ---- inventory, totals -------------------------------------------------
    wh_totals = {
        w["id"]: {"code": w.get("code"), "name": w.get("name"), "gold_g": 0.0, "value_vnd": 0.0}
        for w in warehouses
    }
    inventory = []
    total_gold = total_value = gold_raw = gold_finished = 0.0
    for p in products:
        stocks = p.get("stocks") or {}
        gw = _num(p.get("goldWeightGrams"))
        cost = _num(p.get("unitCostVnd"))
        qty_total = sum(_num(v) for v in stocks.values())
        for wid, q in stocks.items():
            if wid in wh_totals:
                wh_totals[wid]["gold_g"] += _num(q) * gw
                wh_totals[wid]["value_vnd"] += _num(q) * cost
        total_gold += qty_total * gw
        total_value += qty_total * cost
        if p.get("type") == "raw":
            gold_raw += qty_total * gw
        else:
            gold_finished += qty_total * gw
        inventory.append({
            "sku": p.get("sku"),
            "name": p.get("name"),
            "karat": p.get("karat"),
            "kind": "raw material" if p.get("type") == "raw" else "finished product",
            "unit": p.get("unit") or ("g" if p.get("type") == "raw" else "pcs"),
            "gold_per_unit_g": gw,
            "cost_vnd": cost,
            "price_vnd": _num(p.get("retailPriceVnd")),
            "sold_in_pos": _sold_in_pos(p),
            "stock": {
                wh_by_id[wid].get("code", wid): _clean_qty(q)
                for wid, q in stocks.items() if wid in wh_by_id
            },
            "total_qty": _clean_qty(qty_total),
        })

    # ---- store stock gaps and suggested transfers --------------------------
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
                "status": "OUT OF STOCK" if have <= 0 else "LOW",
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

    # ---- production orders: does every component have enough stock? ---------
    # Same rule as the web page: vault stock minus what the OTHER open orders already reserved.
    boms = {b.get("id"): b for b in snap.get("boms") or []}
    prod_by_id = {p.get("id"): p for p in products}
    open_orders = [m for m in snap.get("manufacturingOrders") or []
                   if m.get("status") in ("confirmed", "in_progress")]

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
            if other is mo:
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

    # ---- open purchase orders ---------------------------------------------
    catalog_names = {p.get("name") for p in products}
    open_pos, notes = [], []
    for po in snap.get("purchaseOrders") or []:
        if po.get("status") == "received":
            continue
        open_pos.append({
            "order": po.get("code"),
            "vendor": po.get("vendor"),
            "item": po.get("productName"),
            "qty": _clean_qty(po.get("quantity", po.get("quantityGrams"))),
            "unit": po.get("unit"),
            "total_vnd": _num(po.get("totalVnd")),
            "status": po.get("status"),
        })
        if po.get("productName") not in catalog_names:
            notes.append(
                f"{po.get('code')}: item '{po.get('productName')}' is not in the product catalog, "
                "so receiving it will not update that item's stock correctly."
            )

    pending_recs = [
        {"title": r.get("title"), "suggested_action": r.get("recommendedAction")}
        for r in snap.get("aiRecommendations") or [] if r.get("status") == "pending"
    ]

    sales_today = _num(snap.get("salesTodayVnd", ctx.get("totalSalesTodayVnd")))
    return {
        "central_warehouse": central.get("code"),
        "thresholds": {
            "store_low_stock_pcs": DEFAULT_MIN_STOCK,
            "refill_target_pcs": REFILL_TARGET,
            "note": "Per-product 'min_level' overrides the default when set.",
        },
        "company_totals": {
            "total_gold_g": round(total_gold, 1),
            "total_gold_chi": round(total_gold / 3.75, 1),
            "total_gold_tael": round(total_gold / 37.5, 2),
            "gold_in_raw_material_g": round(gold_raw, 1),
            "gold_in_finished_jewelry_g": round(gold_finished, 1),
            "inventory_value_at_cost_vnd": round(total_value),
            "sales_today_vnd": round(sales_today),
        },
        "warehouses": [
            {"code": v["code"], "name": v["name"],
             "gold_g": round(v["gold_g"], 1), "value_vnd": round(v["value_vnd"])}
            for v in wh_totals.values()
        ],
        "inventory": inventory,
        "computed": {
            "store_stock_alerts": alerts,
            "open_production_orders": mo_checks,
            "open_purchase_orders": open_pos,
            "pending_ai_recommendations": pending_recs,
            "data_notes": notes,
        },
        "recent_stock_moves": [
            {"ref": m.get("reference"), "sku": m.get("productSku"), "from": m.get("fromLocation"),
             "to": m.get("toLocation"), "qty": m.get("quantity"), "type": m.get("type"),
             "time": m.get("timestamp")}
            for m in (snap.get("stockMoves") or [])[:8]
        ],
    }


def _legacy_facts(ctx):
    """Used only if the browser did not send a full snapshot (old frontend)."""
    g = _num(ctx.get("totalGoldGramsAll"))
    return {
        "company_totals": {
            "total_gold_g": round(g, 1),
            "total_gold_chi": round(_num(ctx.get("totalGoldChiAll"), g / 3.75), 1),
            "inventory_value_at_cost_vnd": round(_num(ctx.get("totalInventoryValueVnd"))),
            "sales_today_vnd": round(_num(ctx.get("totalSalesTodayVnd"))),
        },
        "computed": {"pending_ai_recommendations": ctx.get("activeWarnings") or "none"},
        "data_notes": ["Only summary figures were provided; per-warehouse stock is unavailable."],
    }


# ---------------------------------------------------------------------------
# Gemini request
# ---------------------------------------------------------------------------
def _history_to_contents(history, message, facts):
    """Chat history -> Gemini contents. Fresh data is attached to the latest question only."""
    items = [h for h in (history or [])[-6:] if (h.get("text") or "").strip()]
    # the browser already appended the current question to history: drop that duplicate
    if items and items[-1].get("role") == "user" and items[-1].get("text", "").strip() == message:
        items = items[:-1]

    contents = []
    for h in items:
        role = "user" if h.get("role") == "user" else "model"
        text = h["text"].strip()[:MAX_HISTORY_CHARS]
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    while contents and contents[0]["role"] == "model":
        contents.pop(0)

    data_block = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    final = f"BUSINESS DATA (live from the ERP):\n{data_block}\n\nMANAGER QUESTION:\n{message}"
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
            "temperature": 0.2,       # low = consistent, fact-bound answers
            "topP": 0.8,
            "maxOutputTokens": 2048,  # headroom for models that "think"; brevity comes from the prompt
        },
    }


def _call_gemini(api_key, payload):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    parts = (result.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


# ---------------------------------------------------------------------------
# Local engine (used when there is no API key or Gemini fails)
# ---------------------------------------------------------------------------
INTENTS = [  # order = priority when two intents tie
    ("howto", ["button", "how to", "flow", "step", "huong dan", "nut", "quy trinh", "cach dung"]),
    ("offtopic", ["pnj", "porter", "five forces", "value chain", "laudon", "mis", "chuoi gia tri", "doi thu"]),
    ("stock", ["stockout", "out of stock", "shortage", "low stock", "rebalanc", "transfer", "replenish",
               "boutique", "store", "het hang", "thieu hang", "chuyen kho", "ton kho", "cua hang", "bo sung", "can bang"]),
    ("production", ["production", "manufactur", "casting", "cast", "mo", "bom", "san xuat", "duc", "lenh"]),
    ("purchase", ["purchase", "procure", "po", "buy", "supplier", "vendor", "mua", "nhap hang", "nha cung cap", "don mua"]),
    ("gold", ["gold", "hedg", "exposure", "position", "risk", "price", "vang", "rui ro", "gia", "phong ngua"]),
    ("sales", ["sales", "revenue", "pos", "doanh thu", "ban hang", "ban"]),
]


def _detect_intent(message):
    q = _ascii(message)
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
    comp = facts.get("computed", {})
    alerts = comp.get("store_stock_alerts", [])
    mos = comp.get("open_production_orders", [])
    pos = comp.get("open_purchase_orders", [])
    intent = _detect_intent(message)

    def actions_for_alerts(limit=3):
        out = []
        for a in alerts[:limit]:
            if a["suggested_transfer_qty"] > 0:
                out.append(t(
                    f"Chuyển {a['suggested_transfer_qty']} cái {a['product']} từ {a['from']} sang {a['to']} (BI Dashboard > Approve & Rebalance).",
                    f"Transfer {a['suggested_transfer_qty']} pcs of {a['product']} from {a['from']} to {a['to']} (BI Dashboard > Approve & Rebalance)."))
            else:
                out.append(t(
                    f"{a['from']} không còn {a['product']} để chuyển cho {a['to']}: cần đúc thêm (Manufacturing) hoặc mua vàng (Procurement).",
                    f"{a['from']} has no {a['product']} left for {a['to']}: create a production order (Manufacturing) or buy gold (Procurement)."))
        return out

    def numbered(items):
        return "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))

    # ----- stock -----------------------------------------------------------
    if intent == "stock":
        if not alerts:
            return t("**Kết luận:** Hiện không có cửa hàng nào dưới mức tồn tối thiểu. Không cần hành động.",
                     "**Conclusion:** No store is below its minimum stock right now. No action needed.")
        top = alerts[0]
        ev = [t(f"- {a['to']} · {a['product']}: còn {a['stock_now']} cái (tối thiểu {a['min_level']}); {a['from']} đang có {a['central_available']} cái",
                f"- {a['to']} · {a['product']}: {a['stock_now']} pcs (minimum {a['min_level']}); {a['from']} holds {a['central_available']} pcs")
              for a in alerts[:4]]
        return (t(f"**Kết luận:** {len(alerts)} vị trí thiếu hàng. Gấp nhất: {top['product']} tại {top['to']} ({top['status']}, còn {top['stock_now']} cái).",
                  f"**Conclusion:** {len(alerts)} store position(s) are short. Most urgent: {top['product']} at {top['to']} ({top['status']}, {top['stock_now']} pcs left).")
                + "\n\n**" + t("Bằng chứng", "Evidence") + ":**\n" + "\n".join(ev)
                + "\n\n**" + t("Hành động", "Actions") + ":**\n" + numbered(actions_for_alerts()))

    # ----- production ------------------------------------------------------
    if intent == "production":
        if not mos:
            return t("**Kết luận:** Không có lệnh sản xuất nào đang mở.", "**Conclusion:** There are no open production orders.")
        short = [m for m in mos if not m["available"]]

        def shortage(m):
            return ", ".join(f"{_clean_qty(l['short'])} {l['unit']} {l['material']}" for l in m["materials"] if l["short"] > 0)

        ev = [t(f"- {m['order']} ({m['product']} x{m['qty']}, {m['status']}): " + ("Available" if m["available"] else f"Not Available, thiếu {shortage(m)}"),
                f"- {m['order']} ({m['product']} x{m['qty']}, {m['status']}): " + ("Available" if m["available"] else f"Not Available, short {shortage(m)}"))
              for m in mos]
        acts = []
        for m in mos:
            if m["available"]:
                acts.append(t(f"Hoàn tất {m['order']} (Manufacturing > Complete MO).", f"Complete {m['order']} (Manufacturing > Complete MO)."))
            else:
                acts.append(t(f"Mua bổ sung {shortage(m)} trước khi hoàn tất {m['order']} (Procurement > New Purchase Order).",
                              f"Buy {shortage(m)} before completing {m['order']} (Procurement > New Purchase Order)."))
        head = (t(f"**Kết luận:** {len(mos)} lệnh đang mở, {len(short)} lệnh Not Available (thiếu vật tư).",
                  f"**Conclusion:** {len(mos)} open order(s), {len(short)} Not Available (short of materials).")
                if short else t(f"**Kết luận:** {len(mos)} lệnh đang mở, đủ vật tư để hoàn tất tất cả.",
                                f"**Conclusion:** {len(mos)} open order(s), all have enough materials."))
        return head + "\n\n**" + t("Bằng chứng", "Evidence") + ":**\n" + "\n".join(ev) + "\n\n**" + t("Hành động", "Actions") + ":**\n" + numbered(acts[:3])

    # ----- purchase ---------------------------------------------------------
    if intent == "purchase":
        if not pos:
            return t("**Kết luận:** Không có đơn mua nào đang chờ nhận hàng.", "**Conclusion:** No purchase order is waiting to be received.")
        ev = [f"- {p['order']} · {p['vendor']} · {p['item']}: {p['qty']} · {_fmt(p['total_vnd'])} VND ({p['status']})" for p in pos[:4]]
        acts = [t(f"Nhận hàng {p['order']} khi vàng về kho (Procurement > Receive Goods into Vault).",
                  f"Receive {p['order']} when the goods arrive (Procurement > Receive Goods into Vault).") for p in pos[:3]]
        return (t(f"**Kết luận:** {len(pos)} đơn mua chưa nhận hàng.", f"**Conclusion:** {len(pos)} purchase order(s) not yet received.")
                + "\n\n**" + t("Bằng chứng", "Evidence") + ":**\n" + "\n".join(ev)
                + "\n\n**" + t("Hành động", "Actions") + ":**\n" + numbered(acts))

    # ----- gold position ----------------------------------------------------
    if intent == "gold":
        ev = [t(f"- Tổng vàng: {_fmt(ct['total_gold_g'], 1)} g (~{_fmt(ct['total_gold_chi'], 1)} chỉ); nguyên liệu {_fmt(ct.get('gold_in_raw_material_g'), 1)} g, thành phẩm {_fmt(ct.get('gold_in_finished_jewelry_g'), 1)} g",
                f"- Total gold: {_fmt(ct['total_gold_g'], 1)} g (~{_fmt(ct['total_gold_chi'], 1)} chi); raw {_fmt(ct.get('gold_in_raw_material_g'), 1)} g, finished {_fmt(ct.get('gold_in_finished_jewelry_g'), 1)} g"),
              t(f"- Giá trị tồn theo giá vốn: {_fmt(ct['inventory_value_at_cost_vnd'])} VND", f"- Inventory value at cost: {_fmt(ct['inventory_value_at_cost_vnd'])} VND")]
        for w in facts.get("warehouses", []):
            ev.append(f"- {w['code']}: {_fmt(w['gold_g'], 1)} g")
        return (t(f"**Kết luận:** Công ty đang nắm {_fmt(ct['total_gold_g'], 1)} g vàng. Hệ thống chưa có giá vàng thị trường nên chưa tính được lãi lỗ khi giá biến động.",
                  f"**Conclusion:** The company holds {_fmt(ct['total_gold_g'], 1)} g of gold. The system has no market gold price, so revaluation gain or loss cannot be calculated.")
                + "\n\n**" + t("Bằng chứng", "Evidence") + ":**\n" + "\n".join(ev[:5]))

    # ----- sales ------------------------------------------------------------
    if intent == "sales":
        body = t(f"**Kết luận:** Doanh thu POS hôm nay: {_fmt(ct['sales_today_vnd'])} VND.", f"**Conclusion:** Today's POS sales: {_fmt(ct['sales_today_vnd'])} VND.")
        if alerts:
            a = alerts[0]
            body += t(f"\n\n**Lưu ý:** {a['product']} tại {a['to']} chỉ còn {a['stock_now']} cái, có thể mất doanh thu nếu hết hàng.",
                      f"\n\n**Watch out:** {a['product']} at {a['to']} has only {a['stock_now']} pcs left; sales may be lost if it runs out.")
        return body

    # ----- how to / compare (short, conceptual) -----------------------------
    if intent == "howto":
        return t(
            "**Quy trình 4 bước:**\n1. Procurement > Create Purchase Order > Receive Goods into Vault (nhập vàng vào kho).\n2. Manufacturing > Create MO > Complete MO (trừ vàng, cộng thành phẩm).\n3. BI Dashboard > Approve & Rebalance, hoặc Inventory > Internal Transfer (đưa hàng ra cửa hàng).\n4. Retail POS > Add to Cart > Complete Checkout (bán và trừ tồn).",
            "**4-step flow:**\n1. Procurement > Create Purchase Order > Receive Goods into Vault (bring gold in).\n2. Manufacturing > Create MO > Complete MO (deduct gold, add finished goods).\n3. BI Dashboard > Approve & Rebalance, or Inventory > Internal Transfer (move stock to stores).\n4. Retail POS > Add to Cart > Complete Checkout (sell and deduct stock).")

    if intent == "offtopic":
        return t(
            "Tôi chỉ hỗ trợ vận hành của Aurora. Bạn có thể hỏi về: cửa hàng nào thiếu hàng và nên chuyển bao nhiêu, lệnh sản xuất nào đủ vàng để đúc, đơn mua nào chưa nhận, vị thế vàng hiện tại, hoặc doanh thu POS hôm nay.",
            "I only cover Aurora's operations. Ask me which store is short and how much to transfer, which production orders have enough gold, which purchase orders are open, the current gold position, or today's POS sales.")

    # ----- overview ---------------------------------------------------------
    lines = [t(f"- Tổng vàng {_fmt(ct['total_gold_g'], 1)} g · giá trị tồn {_fmt(ct['inventory_value_at_cost_vnd'])} VND · doanh thu hôm nay {_fmt(ct['sales_today_vnd'])} VND",
               f"- Gold {_fmt(ct['total_gold_g'], 1)} g · inventory value {_fmt(ct['inventory_value_at_cost_vnd'])} VND · sales today {_fmt(ct['sales_today_vnd'])} VND")]
    issues = []
    if alerts:
        lines.append(t(f"- {len(alerts)} vị trí cửa hàng thiếu hàng (gấp nhất: {alerts[0]['product']} tại {alerts[0]['to']}, còn {alerts[0]['stock_now']})",
                       f"- {len(alerts)} store position(s) short (most urgent: {alerts[0]['product']} at {alerts[0]['to']}, {alerts[0]['stock_now']} left)"))
        issues += actions_for_alerts(2)
    short = [m for m in mos if not m["available"]]
    if short:
        lines.append(t(f"- {len(short)} lệnh sản xuất Not Available ({short[0]['order']}: thiếu vật tư)",
                       f"- {len(short)} production order(s) Not Available ({short[0]['order']}: short of materials)"))
    head = (t("**Kết luận:** Có việc cần xử lý.", "**Conclusion:** Some items need attention.") if (alerts or short)
            else t("**Kết luận:** Tình hình ổn định, không cần hành động.", "**Conclusion:** Operations look stable. No action needed."))
    out = head + "\n\n**" + t("Bằng chứng", "Evidence") + ":**\n" + "\n".join(lines)
    if issues:
        out += "\n\n**" + t("Hành động", "Actions") + ":**\n" + numbered(issues)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def ask_gemini_or_local(message: str, history: list = None, erp_context: dict = None) -> dict:
    """
    1. Build verified facts from the live ERP snapshot.
    2. If GEMINI_API_KEY exists, let Gemini explain/prioritise them under a strict prompt.
    3. Otherwise (or on any error) answer with the local engine from the same facts.
    """
    ctx = erp_context or {}
    message = (message or "").strip()
    facts = build_facts(ctx) or _legacy_facts(ctx)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key and api_key != "MY_GEMINI_API_KEY":
        try:
            payload = _build_gemini_payload(message, history, facts)
            reply = _call_gemini(api_key, payload)
            if reply:
                print("[AI Agent] Source: GEMINI")
                return {"source": "gemini", "reply": reply}
            print("[AI Agent] Gemini returned an empty reply. Using local engine.")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            print(f"[AI Agent] Gemini HTTP {e.code}: {detail}. Using local engine.")
        except Exception as e:
            print(f"[AI Agent] Gemini call failed: {e}. Using local engine.")
    else:
        print("[AI Agent] No API key. Using local engine.")

    if "company_totals" in facts and "store_stock_alerts" not in facts.get("computed", {}):
        # legacy frontend: only summary numbers available
        ct = facts["company_totals"]
        return {"source": "local_fallback", "reply": (
            f"**Gold:** {_fmt(ct['total_gold_g'], 1)} g · **Inventory value:** {_fmt(ct['inventory_value_at_cost_vnd'])} VND · "
            f"**Sales today:** {_fmt(ct['sales_today_vnd'])} VND.\n\nDetailed stock data was not sent by the page, "
            "so store-level advice is unavailable. Update the chat payload in index.html.")}
    return {"source": "local_fallback", "reply": _local_reply(message, facts)}