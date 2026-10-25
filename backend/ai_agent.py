"""
AURORA JEWELRY ERP - AI DECISION AGENT
Autonomous AI Copilot integrating Google Gemini API & Embedded Local Heuristic Reasoning Engine.
"""

import os
import json
import urllib.request
import urllib.error
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SYSTEM_INSTRUCTION = """
You are the AI Decision Copilot and Chief Information Officer (CIO) of AURORA JEWELRY - an enterprise fine jewelry manufacturing and retail corporation.
Aurora Jewelry was designed as an innovative upgrade over real enterprise PNJ (Phu Nhuan Jewelry), inheriting PNJ's integrated value chain while resolving operational latency through modular Odoo ERP architecture and autonomous AI Agents.

Your core expertise spans:
1. Management Information Systems (MIS) Academic Foundations:
   - Michael Porter's Five Forces (Chapter 3): Supplier Power (state-regulated gold quotas SJC/DOJI), Buyer Power (discerning luxury VIPs), Competitive Rivalry (PNJ, DOJI, SJC), Threat of Substitutes (Lab-grown diamonds, Moissanite), Barriers to Entry (capital reserves, bullion licenses).
   - Business Value Chain Model (Pages 129-138): Inbound Logistics (Gold Bullion Vault KT), Operations (Precision Vacuum Casting BOM with 1.87% loss factor), Outbound Logistics (Store Transfers), Marketing & Sales (POS Terminal with VIP Tiers), Service (Lifetime authenticity cleaning & trade-in guarantees).
   - Comparative Analysis of 3 ERP Solutions: SAP S/4HANA (PNJ's legacy system: multi-million dollar TCO, sluggish customization), Microsoft Dynamics 365 (good cloud BI integration but high per-seat fee), and Odoo ERP (Aurora's choice: modular, Python/FastAPI agile stack, unified database).
2. Precious Metal Risk Management:
   - Unit Conversions: 1 Chi of Gold = 3.75 grams; 1 Luong (Tael) = 10 Chi = 37.5 grams.
   - Natural Hedging: Store POS sales immediately offset central vault holdings in real time.
3. Response Standard:
   - Provide structured, professional English answers with Markdown bullet points and bold highlights.
   - Reference live ERP database numbers provided in the context whenever applicable.
"""


def _generate_local_heuristic_response(message: str, erp_context: dict = None) -> str:
    """Embedded Autonomous MIS Heuristic Engine for zero-downtime offline execution."""
    q = (message or "").lower()
    ctx = erp_context or {}

    total_gold_g = ctx.get("totalGoldGramsAll", 2320.0)
    total_gold_chi = ctx.get("totalGoldChiAll", total_gold_g / 3.75)
    total_val = ctx.get("totalInventoryValueVnd", 5475200000)
    today_sales = ctx.get("totalSalesTodayVnd", 31200000)

    if any(k in q for k in ["hedge", "hedging", "risk", "balance", "gold price", "fluctuat"]):
        return (
            f"### Autonomous Gold Position & Hedging Analysis\n\n"
            f"- **Live Total Gold Exposure**: **{total_gold_g:,.1f} grams** (~**{total_gold_chi:,.1f} Chi** / **{(total_gold_g/37.5):,.1f} Tael**).\n"
            f"- **Working Capital Valuation**: **{total_val:,.0f} VND**.\n"
            f"- **Hedging Strategy (Natural Hedging)**: Unlike financial derivatives, Aurora Jewelry hedges by matching daily raw bullion purchases (PO) with retail point-of-sale volume (POS: **{today_sales:,.0f} VND** today). This neutralizes intraday spot bullion fluctuations without costly futures contracts.\n"
            f"- **Prescriptive Recommendation**: Maintain a **35% safety buffer** in Main Warehouse WH-MW and execute daily rebalancing before 17:00 to lock in spot spreads."
        )

    if any(k in q for k in ["stockout", "out of stock", "shortage", "phu nhuan", "pn", "rebalance", "transfer"]):
        return (
            f"### Boutique Stockout Risk & Rebalance Directive\n\n"
            f"- **Vulnerable Location**: **Phu Nhuan Boutique (WH-PN)**.\n"
            f"- **Critical Item**: *Fortune Ring 24K* (Current on-hand: ~4 units, below the safety threshold of **15 units** ahead of the God of Wealth festival).\n"
            f"- **Prescriptive Action**: Dispatch an internal transfer of **15 units** from Main Warehouse (WH-MW) to WH-PN.\n"
            f"- **Automation Trigger**: Click the **'Approve & Rebalance'** button in the **AI Agent** tab or execute via **Inventory > Internal Transfer**."
        )

    if any(k in q for k in ["forecast", "demand", "god of wealth", "festival", "tet", "season"]):
        return (
            f"### Peak Season Demand Forecast (God of Wealth & Wedding Season)\n\n"
            f"- **Projected Demand Surge**: **+340%** for 24K small-denomination rings (0.5 Chi & 1 Chi) and bullion bars.\n"
            f"- **Boutique Target Inventory**: Ensure **WH-PN** and **WH-D1** hold at least **50 units** of Fortune Rings 48 hours prior to the festival.\n"
            f"- **Production Schedule**: Activate Go Vap Casting Cell #1 to process **150g of 24K Bullion** into 35 rings daily to prevent regional inventory exhaustion."
        )

    if any(k in q for k in ["pnj", "aurora", "compare", "heritage", "weakness", "drawback", "strength"]):
        return (
            f"### Architectural Comparison: PNJ vs. AURORA JEWELRY\n\n"
            f"1. **Inherited Strengths (from PNJ)**:\n"
            f"   - **Closed-Loop Value Chain**: In-house 3D design ➜ Bullion procurement ➜ Centralized casting ➜ Multi-boutique POS. Controlling casting preserves 9999 karat purity and saves 15% outsourced machining costs.\n"
            f"2. **Overcoming PNJ's Limitations (in Aurora)**:\n"
            f"   - **Eliminating the Bullwhip Effect**: PNJ's heavy SAP batch runs take hours for provincial reconciliation. Aurora's Odoo modular architecture reflects inventory deductions to the microsecond.\n"
            f"   - **Autonomous AI Decision Agent**: Replacing PNJ's 72-hour manual inter-store approval bureaucracy with real-time AI-prescribed 1-click rebalancing."
        )

    if any(k in q for k in ["porter", "5 force", "five forces", "competitive"]):
        return (
            f"### Michael Porter's Five Forces Analysis (Chapter 3)\n\n"
            f"1. **Supplier Power (High)**: State Bank regulates 24K bullion import quotas (SJC monopoly). Aurora mitigates this by maintaining long-term institutional vendor ties (SJC, DOJI, Heraeus).\n"
            f"2. **Buyer Power (Moderate)**: Discerning retail clients demand karat assay certificates and buyback guarantees. Aurora provides real-time digital e-Receipts with lifetime warranty.\n"
            f"3. **Threat of Substitutes (Moderate-High)**: Lab-grown diamonds (LGD) pressure natural stones. Aurora offers certified dual-track product lines.\n"
            f"4. **Competitive Rivalry (High)**: Intense competition with PNJ, DOJI, and traditional family shops. Aurora wins via agile modular ERP and AI-driven instant fulfillment."
        )

    if any(k in q for k in ["button", "flow", "step", "how to", "create po", "buy", "cast", "mo"]):
        return (
            f"### 4-Step Interactive Execution Flow & Button Guide\n\n"
            f"1. **Procurement**: Go to **Procurement (Purchase)** ➜ Click *'Create Purchase Order'* (150g 24K Gold) ➜ Click *'Receive Goods into Vault'* to increment WH-MW stock.\n"
            f"2. **Manufacturing**: Go to **Production (Manufacturing)** ➜ Confirm MO for 25 Fortune Rings ➜ Click *'Complete MO'* (ERP deducts gold with 1.87% casting loss).\n"
            f"3. **Inter-Store Transfer**: Go to **AI Agent** ➜ Click *'Approve & Rebalance'* to dispatch 15 rings to WH-PN.\n"
            f"4. **Retail POS**: Go to **Retail POS** ➜ Select Phu Nhuan boutique ➜ Add ring to cart ➜ Click *'Complete Checkout'* for instant inventory deduction and e-Receipt!"
        )

    return (
        f"### Aurora AI Decision Copilot\n\n"
        f"I am actively monitoring your live enterprise database:\n"
        f"- **Current Total Gold**: **{total_gold_g:,.1f} grams** (~**{total_gold_chi:,.1f} Chi**).\n"
        f"- **Working Capital**: **{total_val:,.0f} VND**.\n"
        f"- **Today's POS Sales**: **{today_sales:,.0f} VND**.\n\n"
        f"You can ask me about **hedging gold volatility**, **solving boutique stockouts**, **PNJ vs. Aurora comparison**, **Porter's 5 Forces**, or **step-by-step button flows**!"
    )


def ask_gemini_or_local(message: str, history: list = None, erp_context: dict = None) -> dict:
    """
    Dual-layer AI query handler:
    1. Attempts Google Gemini 3.6 Flash via REST API (if GEMINI_API_KEY is configured).
    2. Gracefully falls back to the local Autonomous MIS Heuristic Engine.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # If no key or placeholder key, use local heuristic engine
    if not api_key or api_key == "MY_GEMINI_API_KEY":
        print("[AI Agent] Source: LOCAL_FALLBACK - No API key")
        reply = _generate_local_heuristic_response(message, erp_context)
        return {
            "source": "local_fallback",
            "reply": reply
        }

    # Prepare prompt with live context
    ctx = erp_context or {}
    context_telemetry = (
        f"\nLIVE REAL-TIME DATABASE TELEMETRY:\n"
        f"- Total Gold Position: {ctx.get('totalGoldGramsAll', 0):.1f} grams (~{ctx.get('totalGoldChiAll', 0):.1f} Chi)\n"
        f"- Total Inventory Valuation: {ctx.get('totalInventoryValueVnd', 0):,.0f} VND\n"
        f"- Retail POS Sales Today: {ctx.get('totalSalesTodayVnd', 0):,.0f} VND\n"
        f"- Active Recommendations: {ctx.get('activeWarnings', 'None')}\n"
    )

    history_text = "\n".join(
        [f"{'User' if h.get('role') == 'user' else 'AI'}: {h.get('text', '')}" for h in (history or [])[-6:]]
    )

    full_prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"{context_telemetry}\n\n"
        f"CONVERSATION HISTORY:\n{history_text}\n\n"
        f"USER QUESTION: {message}"
    )

    # Call Gemini REST API directly using standard urllib (no complex external SDK required)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-3.6-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [{"text": full_prompt}]
            }
        ]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            reply = (
                result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if reply:
                print("[AI Agent] Source: GEMINI")
                return {
                    "source": "gemini",
                    "reply": reply
                }
    except Exception as e:
        print(f"[AI Agent] Gemini API call failed or timed out: {e}. Switching to Local MIS Engine.")

    # Fallback if Gemini fails or times out
    print("[AI Agent] Source: LOCAL_FALLBACK - API error")
    reply = _generate_local_heuristic_response(message, erp_context)
    return {
        "source": "local_fallback",
        "reply": reply
    }
