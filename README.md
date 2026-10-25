# AURORA JEWELRY ERP & AI COPILOT (MIS FINAL PROJECT)

> **Enterprise Fine Jewelry Management Information System (MIS)** simulating a vertically integrated luxury jewelry enterprise (**AURORA JEWELRY**), benchmarked against empirical analysis of Vietnam's jewelry market leader (**PNJ**).
> Engineered with a **Modular Odoo Architecture** (Procurement, Manufacturing, Multi-Vault Inventory, Retail POS, Gold Flow BI Dashboard) coupled with an **Autonomous Prescriptive AI Agent** for precious metal hedging and store stock rebalancing.

---

## Repository Directory Structure

```
aurora_jewelry_erp/
│
├── backend/
│   ├── __init__.py
│   ├── app.py              # Main server script (Python Flask / zero-dependency HTTP server)
│   ├── ai_agent.py         # AI Decision Copilot (Google Gemini API & Local Heuristic Engine)
│   └── requirements.txt    # Python dependencies (flask, requests, python-dotenv, google-genai)
│
├── frontend/
│   ├── static/
│   │   └── css/
│   │       └── input.css   # Tailwind CSS configuration & custom typography
│   └── templates/
│       └── index.html      # Main ERP interface & AI Copilot client (7 modules + 4-step demo)
│
├── .env                    # Environment variables (GEMINI_API_KEY, APP_URL, PORT)
├── .env.example            # Environment variables template for GitHub
├── .gitignore              # Ignores sensitive keys, node_modules, and Python caches
└── README.md               # Complete project documentation & academic defense guide
```

---

## How to Run the Application

### Method 1: Run with Python (Recommended for Local / GitHub Clones)
```bash
# 1. Install Python dependencies
pip install -r backend/requirements.txt

# 2. Start the server
python backend/app.py

# 3. Open your browser at:
# http://localhost:3000 (or http://127.0.0.1:3000)
```
*(Note: If Flask is not yet installed, `backend/app.py` automatically falls back to Python's high-performance built-in HTTP server, so it runs on any standard Python installation without errors).*

---

### Method 2: 1-Click Launchers (Windows / macOS / Linux)
- **Windows**: Double-click `chay_he_thong.bat` or `run_app.bat`.
- **macOS / Linux**: Run `./run_app.sh` in your terminal.

---

### Method 3: Run with Node.js & Vite (Active in AI Studio)
```bash
npm install
npm run dev
```

---

## 7 Integrated Enterprise Modules

1. **Inventory**: Multi-vault tracking across Central Vault & Plant (`WH-KT`), Phu Nhuan Boutique (`WH-PN`), and District 1 Flagship (`WH-Q1`). Includes internal transfers, audit adjustments, and immutable stock moves ledger.
2. **Manufacturing (MO)**: Bill of Materials (BOM) management with automatic **1.87% casting loss factor compensation** for 24K and 18K precious metals.
3. **Procurement (PO)**: Raw bullion purchase orders from SJC, DOJI, and Heraeus, with instant vault deposit workflows.
4. **Retail POS**: Cashier shift session management, boutique selector, VIP loyalty tiers (Diamond 5%, Gold 3%), and e-Receipts with authentic gold purity assay guarantees.
5. **Gold Flow BI**: Live gold distribution matrix, interactive Michael Porter Business Value Chain diagram, and Porter's Five Forces scorecard.
6. **AI Decision Agent**: Continuous sell-through tracking, stockout velocity warning, and 1-click **"Approve & Rebalance"** action.
7. **MIS Academic Report**: Complete coursework defense documentation covering the PNJ empirical case study, the Aurora simulated venture, and a 3-way ERP comparison (*SAP S/4HANA vs. Microsoft Dynamics 365 vs. Odoo ERP*).

---

## 4-Step Presentation Demo Script

To demonstrate the closed-loop system during class or final exam defense:
1. **Procurement**: In **Procurement (PO)**, create a PO for 150g 24K pure gold from SJC ➜ Click *"Receive Goods into Vault"*. Central Vault (`WH-KT`) stock increments.
2. **Manufacturing**: In **Manufacturing (MO)**, click *"Create & Confirm MO"* for 20 Fortune Rings ➜ Click *"Complete MO"*. ERP automatically consumes 76.4g gold (with 1.87% casting loss) and deposits 20 finished rings.
3. **Internal Transfer**: In **AI Agent**, identify the stockout vulnerability at Phu Nhuan (`WH-PN`) ➜ Click *"Approve & Rebalance"*. 15 rings are instantly transferred from `WH-KT` to `WH-PN`.
4. **Retail POS**: In **Retail POS**, select Phu Nhuan store ➜ Add 2 Fortune Rings to cart ➜ Select VIP member ➜ Click *"Complete Checkout"*. Stock decrements in real time at `WH-PN` and generates an authenticated gold warranty e-Receipt!

*(Or click **"Guided MIS Demo"** in the top navigation bar and choose **"Run Full 4-Step Pipeline in 1 Click"**!)*

---

## AI Copilot Capabilities
- **Real-Time Data Grounding**: Ingests live vault balances, store inventory, daily sales, and active recommendation states.
- **Precious Metal Risk Management**: Analyzes spot gold exposure and prescribes hedging tactics.
- **Dual-Layer Execution**: Automatically routes to **Google Gemini 3.8 Flash** when an API key is available, and falls back to an **Autonomous MIS Heuristic Reasoning Engine** offline with zero downtime.

---

## License
Apache-2.0 License. Academic final project for Management Information Systems (MIS).
