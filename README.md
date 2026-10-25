# AURORA JEWELRY ERP & AI COPILOT (MIS FINAL PROJECT)

> **Enterprise Fine Jewelry Management Information System (MIS)** simulating a vertically integrated luxury jewelry enterprise (**AURORA JEWELRY**), benchmarked against empirical analysis of Vietnam's jewelry market leader (**PNJ**).
>
> The system features a **modular enterprise architecture** integrating Procurement, Manufacturing, Inventory, Retail POS, Gold Flow BI Dashboard, and an AI Decision Agent for precious metal risk management and store stock rebalancing.

---

## Repository Directory Structure

```text
aurora_jewelry_erp/
│
├── backend/
│   ├── __init__.py
│   ├── app.py              # Main server script (Python Flask / built-in HTTP server)
│   ├── ai_agent.py         # AI Decision Copilot (Google Gemini API & Local Heuristic Engine)
│   └── requirements.txt    # Python dependencies
│
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   └── input.css   # Tailwind CSS configuration & custom typography
│   │   └── images/
│   │       └── aurora-logo.jpg  # Aurora Jewelry brand logo
│   └── templates/
│       └── index.html      # Main ERP interface & AI Copilot client
│
├── .env.example            # Template for environment variables
├── .gitignore              # Ignores sensitive keys, and Python caches
└── README.md               # Project documentation & setup guide
```

---

## How to Run the Application

### Run with Python

**1. Install Python dependencies**

Open a terminal in the project root directory and run:

```bash
pip install -r backend/requirements.txt
```

**2. Configure environment variables**

Create a `.env` file in the project root directory using `.env.example` as a template. Add your Google Gemini API key if you want to enable AI responses through Gemini.

```env
GEMINI_API_KEY=your_gemini_api_key_here
APP_URL=http://127.0.0.1
PORT=5000
```

**3. Start the server**

```bash
python -m backend.app
```

**4. Open the application**

Visit either URL in your browser.

*Note: If Flask is unavailable, `backend/app.py` may fall back to Python's built-in HTTP server, depending on the application's implementation.*

---

## 6 Integrated Enterprise Modules

### 1. Inventory

- Tracks inventory across multiple warehouses and stores:
  - Main Warehouse (`WH-MW`)
  - Phu Nhuan Store (`WH-PN`)
  - District 1 Store (`WH-D1`)
- Supports internal stock transfers and inventory adjustments.
- Maintains a stock movement ledger for inventory tracking and auditing.

### 2. Manufacturing

- Manages Bills of Materials (BOM).
- Applies a **1.87% casting loss factor** to 24K and 18K precious metals.

### 3. Procurement (PO)

- Manages raw gold purchase orders from suppliers such as SJC, DOJI, and Heraeus.
- Supports workflows for receiving purchased gold into the central vault.

### 4. Retail POS

- Supports cashier shift sessions and store selection.
- Includes VIP loyalty tiers:
  - Diamond: 5% discount
  - Gold: 3% discount
- Generates electronic receipts with gold purity and warranty information.

### 5. Gold Flow BI Dashboard

- Displays gold distribution across warehouses and stores.
- Includes an interactive Michael Porter Business Value Chain diagram.
- Provides a Porter's Five Forces competitive analysis dashboard.

### 6. AI Decision Agent

- Tracks sales velocity and identifies potential stockout risks.
- Analyzes inventory distribution and precious metal exposure.
- Provides an **"Approve & Rebalance"** action to support stock reallocation between stores.

---

## 4-Step Presentation Demo

### Step 1: Procurement

In **Procurement (PO)**, create a purchase order for 150 g of 24K pure gold from SJC and click **"Receive Goods into Vault"**. The main warehouse (`WH-MW`) inventory increases.

### Step 2: Manufacturing

In **Manufacturing**, click **"Create & Confirm MO"** to produce 20 Fortune Rings, then click **"Complete MO"**. The system consumes the required gold, accounting for the 1.87% casting loss factor, and adds 20 finished rings to inventory.

### Step 3: Internal Transfer

In **AI Agent**, identify the stockout risk at Phu Nhuan (`WH-PN`) and click **"Approve & Rebalance"**. The system transfers 15 rings from `WH-MW` to `WH-PN`.

### Step 4: Retail POS

In **Retail POS**, select the Phu Nhuan store, add 2 Fortune Rings to the cart, select a VIP member, and click **"Complete Checkout"**. The system deducts the sold items from `WH-PN` inventory and generates an electronic receipt.

*Alternatively, use **"Guided MIS Demo"** in the top navigation bar and select **"Run Full 4-Step Pipeline in 1 Click"** to execute the demonstration.*

---

## AI Copilot Capabilities

- **Real-Time Data Grounding:** Uses available warehouse balances, store inventory, daily sales, and active recommendation states to inform responses.
- **Precious Metal Risk Management:** Analyzes gold exposure and provides recommendations for managing precious metal price risks.
- **Dual-Layer Execution:** Uses the Google Gemini API when a valid API key is configured and falls back to the local heuristic reasoning engine when Gemini is unavailable.

---

## License

**Apache-2.0 License**

Academic final project for Management Information Systems (MIS).
