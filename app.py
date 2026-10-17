import streamlit as st
import sqlite3
import os
import shutil
from PIL import Image
import pytesseract
import requests
import json
import logging
from datetime import datetime, date, timedelta
import csv
import io
import babel.numbers

# Diagnostic logger (operation-level only; never logs receipt or expense contents)
logger = logging.getLogger("receiptpocket")

# Consistent Absolute Configuration Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
DB_PATH = os.path.join(DATA_DIR, "receiptpocket.db")

# Sensible SQLite connection timeout: concurrent access waits instead of
# immediately failing with "database is locked".
DB_CONNECT_TIMEOUT = 30.0
BUSY_TIMEOUT_MS = 30000


def get_db_connection(timeout=DB_CONNECT_TIMEOUT):
    """Open a SQLite connection with a sensible busy timeout.

    Every connection is closed by the caller in a ``finally`` block. The
    busy timeout makes SQLite wait (up to the timeout) when the database is
    locked by another connection instead of failing immediately.
    """
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:1.5b-instruct"
CATEGORIES = ["Food", "Travel", "Software", "Office Supplies", "Utilities", "Medical", "Shopping", "Other"]

# Supported ISO 4217 Currencies
SUPPORTED_CURRENCIES = [
    "INR", "USD", "EUR", "GBP", "CAD", "AUD", "AED", "JPY", "CNY", "PKR", "SGD", "NZD", "CHF", "BDT", "NPR", "LKR"
]

DEFAULT_HOME_CURRENCY = "INR"

CURRENCY_INFO = {
    "INR": {"name": "Indian Rupee", "symbol": "₹", "locale": "en_IN", "precision": 2},
    "USD": {"name": "US Dollar", "symbol": "$", "locale": "en_US", "precision": 2},
    "EUR": {"name": "Euro", "symbol": "€", "locale": "de_DE", "precision": 2},
    "GBP": {"name": "British Pound", "symbol": "£", "locale": "en_GB", "precision": 2},
    "CAD": {"name": "Canadian Dollar", "symbol": "CA$", "locale": "en_CA", "precision": 2},
    "AUD": {"name": "Australian Dollar", "symbol": "A$", "locale": "en_AU", "precision": 2},
    "AED": {"name": "UAE Dirham", "symbol": "AED", "locale": "ar_AE", "precision": 2},
    "JPY": {"name": "Japanese Yen", "symbol": "¥", "locale": "ja_JP", "precision": 0},
    "CNY": {"name": "Chinese Yuan", "symbol": "CN¥", "locale": "zh_CN", "precision": 2},
    "PKR": {"name": "Pakistani Rupee", "symbol": "PKR", "locale": "ur_PK", "precision": 2},
    "SGD": {"name": "Singapore Dollar", "symbol": "S$", "locale": "en_SG", "precision": 2},
    "NZD": {"name": "New Zealand Dollar", "symbol": "NZ$", "locale": "en_NZ", "precision": 2},
    "CHF": {"name": "Swiss Franc", "symbol": "CHF", "locale": "de_CH", "precision": 2},
    "BDT": {"name": "Bangladeshi Taka", "symbol": "৳", "locale": "bn_BD", "precision": 2},
    "NPR": {"name": "Nepalese Rupee", "symbol": "NPR", "locale": "ne_NP", "precision": 2},
    "LKR": {"name": "Sri Lankan Rupee", "symbol": "LKR", "locale": "si_LK", "precision": 2},
}

# Ensure data directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

def inject_custom_styles():
    """Inject centralized, scoped CSS styles for a modern, structured finance layout."""
    st.markdown("""
    <style>
    /* Clean typography & theme foundation */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #0f172a;
    }
    
    /* Main block container padding */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }
    
    /* Page header styling */
    .page-header {
        margin-bottom: 1.25rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .page-header h1 {
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        margin: 0 0 0.25rem 0 !important;
        letter-spacing: -0.02em;
    }
    .page-subtitle {
        font-size: 0.9rem;
        color: #64748b;
        margin: 0;
        line-height: 1.45;
    }

    /* Sidebar Branding */
    .sidebar-brand-box {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
        padding-top: 2px;
    }
    .brand-logo-icon {
        width: 36px;
        height: 36px;
        border-radius: 9px;
        background: #4f46e5;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        flex-shrink: 0;
        box-shadow: 0 2px 5px rgba(79, 70, 229, 0.25);
    }
    .brand-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.02em;
        line-height: 1.2;
    }
    .brand-pill {
        font-size: 0.65rem;
        color: #4f46e5;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .brand-desc {
        font-size: 0.8rem;
        color: #64748b;
        margin-bottom: 1.25rem;
        line-height: 1.35;
    }
    .nav-label {
        font-size: 0.68rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.4rem;
    }

    /* Sidebar Privacy Card */
    .sidebar-privacy-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 1.5rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
    }
    .privacy-title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.78rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 4px;
    }
    .privacy-note {
        font-size: 0.72rem;
        color: #64748b;
        line-height: 1.35;
        margin-bottom: 8px;
    }
    .engine-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
    }
    .engine-tag {
        font-size: 0.65rem;
        background: #f1f5f9;
        color: #475569;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 500;
    }

    /* Metric Cards */
    .rp-metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .rp-metric-card:hover {
        box-shadow: 0 3px 6px rgba(15, 23, 42, 0.06);
    }
    .rp-metric-label {
        font-size: 0.72rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .rp-metric-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.2;
        margin-bottom: 2px;
    }
    .rp-metric-sub {
        font-size: 0.75rem;
        color: #94a3b8;
    }

    /* Stage Steps Indicator */
    .stage-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 10px 16px;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
    }
    .stage-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.82rem;
        font-weight: 500;
        color: #64748b;
    }
    .stage-active {
        color: #4f46e5;
        font-weight: 600;
    }
    .stage-badge {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: #e2e8f0;
        color: #475569;
        font-size: 0.72rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .stage-active .stage-badge {
        background: #4f46e5;
        color: #ffffff;
    }
    .stage-arrow {
        color: #cbd5e1;
        font-size: 0.85rem;
    }

    /* Extraction & Currency Alert Cards */
    .extract-alert {
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 14px;
        font-size: 0.84rem;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .extract-alert-success {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        color: #166534;
    }
    .extract-alert-warning {
        background: #fffbeb;
        border: 1px solid #fde68a;
        color: #92400e;
    }
    .extract-alert-info {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #1e40af;
    }

    /* Currency Conversion Card */
    .fx-card {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 12px 14px;
        margin-top: 10px;
        margin-bottom: 12px;
    }
    .fx-header {
        font-size: 0.78rem;
        font-weight: 700;
        color: #334155;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 6px;
    }
    .fx-rate-text {
        font-size: 0.86rem;
        color: #1e293b;
        font-weight: 600;
        margin-bottom: 2px;
    }
    .fx-subtext {
        font-size: 0.73rem;
        color: #64748b;
    }

    /* Status Badges */
    .status-badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .status-badge-verified {
        background: #dcfce7;
        color: #166534;
    }
    .status-badge-unverified {
        background: #fef3c7;
        color: #92400e;
    }
    .status-badge-unconverted {
        background: #e0f2fe;
        color: #0369a1;
    }

    /* Empty State Card */
    .empty-state-card {
        background: #ffffff;
        border: 1px dashed #cbd5e1;
        border-radius: 12px;
        padding: 2.5rem 1.5rem;
        text-align: center;
        margin: 1.25rem 0;
    }
    .empty-icon {
        font-size: 2.2rem;
        margin-bottom: 0.75rem;
    }
    .empty-state-card h3 {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        color: #0f172a !important;
        margin: 0 0 0.4rem 0 !important;
    }
    .empty-state-card p {
        font-size: 0.88rem;
        color: #64748b;
        max-width: 440px;
        margin: 0 auto 1.25rem auto;
        line-height: 1.45;
    }

    /* Success Confirmation Card */
    .success-card {
        background: #ffffff;
        border: 1px solid #86efac;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 1.25rem;
        box-shadow: 0 2px 4px rgba(34, 197, 94, 0.08);
    }
    .success-card-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 14px;
    }
    .success-card-title {
        font-size: 1.12rem;
        font-weight: 700;
        color: #166534;
    }
    .success-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 12px;
        background: #f0fdf4;
        border: 1px solid #dcfce7;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
    }
    .success-grid-label {
        font-size: 0.7rem;
        color: #15803d;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    .success-grid-val {
        font-size: 1.05rem;
        font-weight: 700;
        color: #14532d;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# CURRENCY FORMATTING & FX HELPERS
# ==========================================

# Mapping of unambiguous currency symbols to ISO 4217 codes.
# '$' is deliberately excluded because it maps to USD, CAD, AUD, SGD, NZD, etc.
_SYMBOL_TO_CODE = {
    "₹": "INR",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",   # Also CNY — but ¥ is overwhelmingly JPY in international usage
    "CN¥": "CNY",
    "৳": "BDT",
    "CHF": "CHF",
    "AED": "AED",
    "PKR": "PKR",
    "NPR": "NPR",
    "LKR": "LKR",
    "SGD": "SGD",
    "NZD": "NZD",
    "CAD": "CAD",
    "AUD": "AUD",
}

def normalize_currency_code(raw):
    """
    Convert a raw currency string (symbol or code) to a canonical ISO 4217 code.

    Returns the uppercase ISO 4217 code if the input is unambiguous and supported,
    or None if the input is empty, None, or an ambiguous symbol such as '$'.
    """
    if not raw or not isinstance(raw, str):
        return None
    clean = raw.strip()
    if not clean:
        return None
    # Direct ISO code match (case-insensitive)
    upper = clean.upper()
    if upper in SUPPORTED_CURRENCIES:
        return upper
    # Symbol lookup
    return _SYMBOL_TO_CODE.get(clean) or _SYMBOL_TO_CODE.get(upper)

def format_money(amount, currency_code="INR"):
    """Format monetary amount using Babel and proper locale/currency rules.
    Returns '—' (em-dash) for None/missing values."""
    if amount is None:
        return "—"
    try:
        amt = float(amount)
    except (ValueError, TypeError):
        return "—"

    code = (currency_code or DEFAULT_HOME_CURRENCY).upper().strip()
    detail = CURRENCY_INFO.get(code)
    loc = detail["locale"] if detail else "en_IN"
    prec = detail["precision"] if detail else 2

    try:
        formatted = babel.numbers.format_currency(amt, code, locale=loc)
        return formatted.replace('\xa0', ' ')
    except Exception:
        symbol = detail["symbol"] if detail else code
        if prec == 0:
            return f"{symbol}{int(round(amt)):,}"
        return f"{symbol}{amt:,.2f}"

def format_money_html(amount, currency_code="INR"):
    """Format currency for custom HTML cards (escapes '$' to prevent KaTeX issues)."""
    formatted = format_money(amount, currency_code)
    return formatted.replace('$', '&#36;')

def calculate_converted_amount(original_amount, exchange_rate, source_currency=None, target_currency="INR"):
    """Calculate converted amount rounded to target currency precision.

    Args:
        original_amount: The amount in the source/receipt currency.
        exchange_rate: How many target-currency units 1 source-currency unit buys.
        source_currency: Source currency code (informational; not used in arithmetic).
        target_currency: Target/reporting currency code used for decimal-precision rounding.
    """
    if original_amount is None or exchange_rate is None:
        return None
    try:
        amt = float(original_amount)
        rate = float(exchange_rate)
        # If called with the old 3-arg signature, source_currency holds target_currency value
        # Detect: if source_currency looks like a currency code and target_currency is still "INR"
        # We resolve by treating the last meaningful code as target.
        code = target_currency or source_currency or DEFAULT_HOME_CURRENCY
        code = code.upper().strip()
        prec = CURRENCY_INFO.get(code, {}).get("precision", 2)
        if prec == 0:
            return float(round(amt * rate))
        return round(amt * rate, prec)
    except (ValueError, TypeError):
        return None

def render_metric_card(label, value, subtext=None, accent=None):
    """Render an attractive, responsive metric card with custom styling."""
    accent_style = f"border-left: 3px solid {accent};" if accent else ""
    sub_html = f'<div class="rp-metric-sub">{subtext}</div>' if subtext else ""
    safe_value = str(value).replace("$", "&#36;")
    return f"""
    <div class="rp-metric-card" style="{accent_style}">
        <div class="rp-metric-label">{label}</div>
        <div class="rp-metric-value">{safe_value}</div>
        {sub_html}
    </div>
    """

def resolve_image_path(image_path):
    """Resolve an image path to an absolute path, ensuring backwards compatibility."""
    if not image_path:
        return None
    if os.path.isabs(image_path):
        return image_path
    return os.path.join(BASE_DIR, image_path)

def configure_tesseract():
    """Configure pytesseract to find the Tesseract executable."""
    current_cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
    if current_cmd and os.path.isfile(current_cmd):
        return True

    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return True

    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
        return True

    common_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(common_path):
        pytesseract.pytesseract.tesseract_cmd = common_path
        return True

    alt_path = r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(alt_path):
        pytesseract.pytesseract.tesseract_cmd = alt_path
        return True

    return False

# ==========================================
# DATABASE INITIALIZATION & MIGRATIONS
# ==========================================
def init_db():
    """Initialize SQLite database, apply safe schema migrations, and setup settings."""
    conn = get_db_connection()
    try:
        # WAL mode lets readers and writers run concurrently and reduces
        # "database is locked" errors. It supplements (not replaces) correct
        # transaction ordering.
        conn.execute("PRAGMA journal_mode=WAL")
        c = conn.cursor()
        
        # 1. Base expenses table
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_name TEXT,
                transaction_date TEXT,
                total_amount REAL,
                category TEXT,
                raw_text TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Schema migration: Add new multi-currency columns if missing
        c.execute("PRAGMA table_info(expenses)")
        existing_cols = [row[1] for row in c.fetchall()]
        
        columns_to_add = [
            ("original_amount", "REAL"),
            ("original_currency", "TEXT"),
            ("base_currency", "TEXT"),
            ("exchange_rate", "REAL"),
            ("exchange_rate_date", "TEXT"),
            ("exchange_rate_source", "TEXT"),
            ("currency_status", "TEXT DEFAULT 'unverified'")
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_cols:
                c.execute(f"ALTER TABLE expenses ADD COLUMN {col_name} {col_type}")
        
        # 3. Mark legacy records safely: Do NOT assume USD or INR!
        # Legacy records preserve original numeric values and are marked 'unverified'.
        c.execute("""
            UPDATE expenses 
            SET currency_status = 'unverified'
            WHERE currency_status IS NULL OR currency_status = ''
        """)
        c.execute("""
            UPDATE expenses
            SET original_amount = total_amount
            WHERE original_amount IS NULL
        """)
        
        # 4. Settings table for persistent configuration (Home Currency)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('home_currency', ?)", (DEFAULT_HOME_CURRENCY,))
        
        # 5. Local persistent exchange rates cache table
        c.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                source_currency TEXT,
                target_currency TEXT,
                rate_date TEXT,
                rate REAL,
                rate_source TEXT DEFAULT 'Frankfurter API',
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_currency, target_currency, rate_date)
            )
        """)
        
        # 6. Helpful indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_expenses_base_cur ON expenses(base_currency, currency_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(transaction_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_exchange_rates_pair ON exchange_rates(source_currency, target_currency)")
        
        conn.commit()
    finally:
        conn.close()

# Auto-initialize database schema and migrations on module load
try:
    init_db()
except Exception:
    pass

def get_home_currency():
    """Retrieve the current persistent home reporting currency (defaults to INR)."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'home_currency'")
        row = c.fetchone()
        return row[0].upper().strip() if row and row[0] else DEFAULT_HOME_CURRENCY
    except Exception:
        return DEFAULT_HOME_CURRENCY
    finally:
        conn.close()

def set_home_currency(currency_code):
    """Set the persistent home reporting currency."""
    code = (currency_code or DEFAULT_HOME_CURRENCY).upper().strip()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO settings (key, value, updated_at) 
            VALUES ('home_currency', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """, (code,))
        conn.commit()
        return True
    finally:
        conn.close()

def get_exchange_rate(source_currency, target_currency, rate_date=None):
    """
    Retrieve exchange rate from source to target currency on the given date.
    - If currencies match: rate=1.0, no network request.
    - Checks local SQLite cache table first.
    - Requests Frankfurter API with date query parameter.
    - Falls back to closest cached rate if offline or API unavailable.
    - Returns structured dictionary.
    """
    source = (source_currency or "").upper().strip()
    target = (target_currency or "").upper().strip()
    
    if not source or not target:
        return {
            'rate': None, 'rate_date': None, 'source': None,
            'cached': False, 'success': False, 'error': "Source or target currency is missing"
        }
    
    # Same currency: rate is always 1.0, skip network
    if source == target:
        actual_date = rate_date if (rate_date and validate_date(rate_date)) else datetime.now().strftime("%Y-%m-%d")
        return {
            'rate': 1.0,
            'rate_date': actual_date,
            'source': "Same Currency",
            'cached': False,
            'success': True,
            'error': None,
            'warning': None
        }
        
    clean_date = rate_date.strip() if (rate_date and validate_date(str(rate_date).strip())) else None
    
    # 1. Check local persistent SQLite cache (short read-only transaction,
    #    closed before any network request so no lock is held during HTTP)
    cached_row = None
    if clean_date:
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT rate, rate_date, rate_source FROM exchange_rates 
                WHERE source_currency = ? AND target_currency = ? AND rate_date = ?
            """, (source, target, clean_date))
            cached_row = c.fetchone()
        finally:
            conn.close()
    if cached_row:
        return {
            'rate': float(cached_row[0]),
            'rate_date': cached_row[1],
            'source': f"{cached_row[2]} (Local Cache)",
            'cached': True,
            'success': True,
            'error': None,
            'warning': None
        }

    # 2. Attempt Frankfurter API request (no database connection is held while
    #    waiting for the HTTP response)
    url = f"https://api.frankfurter.dev/v2/rate/{source}/{target}"
    params = {}
    if clean_date:
        params['date'] = clean_date

    api_err = None
    returned_rate = None
    actual_date = None
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "rate" in data:
                returned_rate = float(data["rate"])
                actual_date = data.get("date") or clean_date or datetime.now().strftime("%Y-%m-%d")
        elif resp.status_code == 422:
            api_err = f"Currency pair {source} → {target} is not supported by Frankfurter API."
        else:
            api_err = f"API returned HTTP status {resp.status_code}"
    except requests.exceptions.RequestException as e:
        api_err = f"Network connection unavailable ({str(e)})"

    # Cache the freshly retrieved rate in a short write transaction
    if returned_rate is not None and actual_date is not None:
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO exchange_rates (source_currency, target_currency, rate_date, rate, rate_source)
                VALUES (?, ?, ?, ?, 'Frankfurter API')
            """, (source, target, actual_date, returned_rate))
            conn.commit()
        finally:
            conn.close()
        return {
            'rate': returned_rate,
            'rate_date': actual_date,
            'source': "Frankfurter API (Reference Rate)",
            'cached': False,
            'success': True,
            'error': None,
            'warning': None
        }

    # 3. Offline / network failure fallback: check for any cached rate for this
    #    currency pair (short read transaction)
    fallback_row = None
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT rate, rate_date, rate_source FROM exchange_rates 
            WHERE source_currency = ? AND target_currency = ?
            ORDER BY rate_date DESC LIMIT 1
        """, (source, target))
        fallback_row = c.fetchone()
    finally:
        conn.close()
    if fallback_row:
        return {
            'rate': float(fallback_row[0]),
            'rate_date': fallback_row[1],
            'source': f"{fallback_row[2]} (Historical Cache Fallback)",
            'cached': True,
            'success': True,
            'error': None,
            'warning': f"Network rate unavailable ({api_err}). Using closest cached rate from {fallback_row[1]}."
        }

    return {
        'rate': None,
        'rate_date': None,
        'source': None,
        'cached': False,
        'success': False,
        'error': api_err or "Exchange rate could not be obtained. Please enter rate manually or keep unconverted."
    }

def save_expense(
    merchant_name,
    transaction_date,
    total_amount,
    category,
    raw_text="",
    image_path="",
    original_amount=None,
    original_currency=None,
    base_currency=None,
    exchange_rate=None,
    exchange_rate_date=None,
    exchange_rate_source=None,
    currency_status=None
):
    """
    Save an expense to the database. Fully backwards-compatible with existing 6-arg calls.
    - total_amount: Converted amount in base_currency (for reporting totals)
    - original_amount: Actual amount on the receipt
    - original_currency: Receipt's currency code
    - base_currency: Reporting home currency
    """
    conn = get_db_connection()
    try:
        c = conn.cursor()
        
        home = get_home_currency()
        
        # Defaults for backwards compatibility if caller did not supply currency args
        orig_amt = float(original_amount) if original_amount is not None else float(total_amount)
        conv_amt = float(total_amount)
        
        if currency_status is None:
            # If original currency was supplied
            if original_currency:
                status = "verified"
                orig_cur = original_currency
                base_cur = base_currency or home
                ex_rate = float(exchange_rate) if exchange_rate is not None else 1.0
                ex_date = exchange_rate_date or transaction_date
                ex_src = exchange_rate_source or ("Same Currency" if original_currency == base_cur else "Manual Entry")
            else:
                # Default legacy style call: treat as verified in current home currency
                status = "verified"
                orig_cur = home
                base_cur = home
                ex_rate = 1.0
                ex_date = transaction_date
                ex_src = "Same Currency"
        else:
            status = currency_status
            orig_cur = original_currency
            base_cur = base_currency
            ex_rate = exchange_rate
            ex_date = exchange_rate_date
            ex_src = exchange_rate_source

        c.execute("""
            INSERT INTO expenses (
                merchant_name, transaction_date, total_amount, category, raw_text, image_path,
                original_amount, original_currency, base_currency, exchange_rate, exchange_rate_date,
                exchange_rate_source, currency_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            merchant_name, transaction_date, conv_amt, category, raw_text or "", image_path or "",
            orig_amt, orig_cur, base_cur, ex_rate, ex_date, ex_src, status
        ))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_expenses():
    """Retrieve all expenses from the database with all 15 columns ordered by transaction date / id descending."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT id, merchant_name, transaction_date, total_amount, category, raw_text, image_path, created_at,
                   original_amount, original_currency, base_currency, exchange_rate, exchange_rate_date, exchange_rate_source, currency_status
            FROM expenses 
            ORDER BY transaction_date DESC, id DESC
        """)
        rows = c.fetchall()
        return rows
    finally:
        conn.close()

def get_monthly_total(home_currency=None):
    """Get total spending for current month in reporting currency (verified records only)."""
    base = (home_currency or get_home_currency()).upper().strip()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        current_month = datetime.now().strftime("%Y-%m")
        c.execute("""
            SELECT SUM(total_amount) FROM expenses 
            WHERE transaction_date LIKE ? 
              AND base_currency = ? 
              AND currency_status = 'verified'
        """, (f"{current_month}%", base))
        result = c.fetchone()[0]
        return float(result) if result is not None else 0.0
    finally:
        conn.close()

def get_all_time_total(home_currency=None):
    """Get all-time total spending in reporting currency (verified records only)."""
    base = (home_currency or get_home_currency()).upper().strip()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT SUM(total_amount) FROM expenses 
            WHERE base_currency = ? 
              AND currency_status = 'verified'
        """, (base,))
        result = c.fetchone()[0]
        return float(result) if result is not None else 0.0
    finally:
        conn.close()

def get_unverified_count():
    """Get count of expenses with unverified currency status."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM expenses WHERE currency_status = 'unverified' OR currency_status IS NULL")
        result = c.fetchone()[0]
        return int(result) if result else 0
    finally:
        conn.close()

def get_category_summary(home_currency=None):
    """Get spending summary by category in reporting currency (verified records only)."""
    base = (home_currency or get_home_currency()).upper().strip()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT category, SUM(total_amount) FROM expenses 
            WHERE base_currency = ? 
              AND currency_status = 'verified'
            GROUP BY category
            ORDER BY SUM(total_amount) DESC
        """, (base,))
        rows = c.fetchall()
        return {row[0]: float(row[1]) for row in rows}
    finally:
        conn.close()

def update_legacy_expense_currency(expense_id, original_currency, exchange_rate, exchange_rate_date, exchange_rate_source, target_currency=None):
    """Convert and verify an unverified legacy expense record."""
    target = (target_currency or get_home_currency()).upper().strip()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT original_amount, total_amount FROM expenses WHERE id = ?", (expense_id,))
        row = c.fetchone()
        if not row:
            return False
        orig_amt = row[0] if row[0] is not None else row[1]
        converted = calculate_converted_amount(orig_amt, exchange_rate, target_currency=target)
        c.execute("""
            UPDATE expenses 
            SET original_amount = ?,
                original_currency = ?,
                total_amount = ?,
                base_currency = ?,
                exchange_rate = ?,
                exchange_rate_date = ?,
                exchange_rate_source = ?,
                currency_status = 'verified'
            WHERE id = ?
        """, (orig_amt, original_currency, converted, target, exchange_rate, exchange_rate_date, exchange_rate_source, expense_id))
        conn.commit()
        return True
    finally:
        conn.close()

def migrate_verified_expenses_to_new_home_currency(new_home_currency):
    """
    Safely migrate all verified expenses to a new home reporting currency.
    Re-calculates converted amounts using historical rates for each record.

    Two-phase, atomic migration:
      Phase 1 (Prepare): read the verified expenses, fetch/cache every required
      exchange rate via get_exchange_rate() (each call manages its own short
      connection; no write transaction is held), and validate every conversion.
      If any rate cannot be obtained, abort before touching the database.
      Phase 2 (Commit): apply every expense update and the home-currency setting
      change in a single short write transaction; commit only if everything
      succeeds, otherwise roll back. Unverified legacy records are never touched.
    """
    new_base = (new_home_currency or "").upper().strip()
    if not new_base:
        raise ValueError("Home currency code is required")

    current_home = get_home_currency()
    if new_base == current_home:
        # Already the configured home currency: no migration needed (no-op),
        # so repeated clicks/refreshes cannot apply duplicate migrations.
        return 0

    # ---- Phase 1: Prepare (no long-lived write transaction) ----
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT id, original_amount, original_currency, transaction_date 
            FROM expenses 
            WHERE currency_status = 'verified' AND original_currency IS NOT NULL
        """)
        rows = c.fetchall()
    finally:
        conn.close()

    prepared = []
    for exp_id, orig_amt, orig_cur, tx_date in rows:
        fx = get_exchange_rate(orig_cur, new_base, tx_date)
        if not fx.get('success') or fx.get('rate') is None:
            # Never silently guess a missing rate; abort before any modification.
            logger.error(
                "migrate_verified_expenses_to_new_home_currency: rate unavailable "
                "for expense id %s (%s -> %s): %s",
                exp_id, orig_cur, new_base, fx.get('error') or "unknown error"
            )
            raise ValueError(
                f"Cannot convert expense id {exp_id} ({orig_cur} -> {new_base}): "
                f"{fx.get('error') or 'exchange rate unavailable'}. "
                "Migration aborted; no expenses or settings were changed."
            )
        rate = float(fx['rate'])
        r_date = fx['rate_date'] or tx_date
        r_src = fx['source'] or "Manual Migration Rate"
        converted = calculate_converted_amount(orig_amt, rate, target_currency=new_base)
        if converted is None:
            logger.error(
                "migrate_verified_expenses_to_new_home_currency: conversion failed "
                "for expense id %s (%s -> %s, rate %s)", exp_id, orig_cur, new_base, rate
            )
            raise ValueError(
                f"Failed to calculate converted amount for expense id {exp_id}. "
                "Migration aborted; no expenses or settings were changed."
            )
        prepared.append((exp_id, converted, new_base, rate, r_date, r_src))

    # ---- Phase 2: Commit (single short write transaction) ----
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        for exp_id, converted, base_cur, rate, r_date, r_src in prepared:
            c.execute("""
                UPDATE expenses
                SET total_amount = ?,
                    base_currency = ?,
                    exchange_rate = ?,
                    exchange_rate_date = ?,
                    exchange_rate_source = ?
                WHERE id = ?
            """, (converted, base_cur, rate, r_date, r_src, exp_id))
        # Apply the home-currency change in the same transaction so the setting
        # and the converted expenses can never become inconsistent.
        c.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES ('home_currency', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """, (new_base,))
        conn.commit()
        return len(prepared)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def validate_date(date_str):
    """Validate date string in YYYY-MM-DD format."""
    if not date_str:
        return False
    try:
        datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False

def clean_and_validate_amount(amount_val):
    """Validate and convert amount to non-negative float, or None if invalid."""
    if amount_val is None:
        return None
    if isinstance(amount_val, (int, float)):
        return float(amount_val) if amount_val >= 0 else None
    val_str = str(amount_val).strip()
    # Strip currency symbols and commas
    for sym in ("$", "₹", "€", "£", "¥", "৳", "AED", "CA$", "A$", "S$", "NZ$", "CHF"):
        val_str = val_str.replace(sym, "")
    val_str = val_str.replace(",", "").strip()
    if not val_str:
        return None
    try:
        val = float(val_str)
        return val if val >= 0 else None
    except (ValueError, TypeError):
        return None

def extract_text_from_image(image):
    """Extract text from image using Tesseract OCR."""
    if not configure_tesseract():
        st.warning("Tesseract OCR is not available. Ensure Tesseract is installed at C:\\Program Files\\Tesseract-OCR\\tesseract.exe or in PATH.")
        return ""
    try:
        text = pytesseract.image_to_string(image)
        return text.strip() if text else ""
    except Exception as e:
        st.warning(f"OCR error: {str(e)}")
        return ""

def normalize_extracted_data(data):
    """Normalize and sanitize extracted JSON fields from Ollama including currency_code."""
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return {}
    
    # Handle wrapped structures (e.g. {"receipt": {...}} or {"extracted_data": [{...}]})
    for wrapper in ("extracted_data", "data", "receipt", "expense", "expenses", "details"):
        if wrapper in data:
            val = data[wrapper]
            if isinstance(val, list) and val:
                data = val[0]
                break
            elif isinstance(val, dict):
                data = val
                break

    merchant = data.get("merchant_name") or data.get("merchant") or data.get("store") or data.get("vendor") or ""
    date_val = data.get("transaction_date") or data.get("date") or ""
    amount_val = data.get("total_amount") if data.get("total_amount") is not None else data.get("total") or data.get("amount")
    category = data.get("category") or data.get("expense_category") or "Other"
    
    # Multi-currency code extraction (ISO 4217)
    currency_code = data.get("currency_code") or data.get("currency") or None
    normalized_currency = None
    if currency_code and isinstance(currency_code, str):
        c_clean = currency_code.strip().upper()
        # Accept recognized currency codes; ignore ambiguous single symbols like '$'
        if c_clean in SUPPORTED_CURRENCIES:
            normalized_currency = c_clean

    normalized_date = ""
    if date_val and isinstance(date_val, str):
        date_str = date_val.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                normalized_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        if not normalized_date and validate_date(date_str):
            normalized_date = date_str

    if category not in CATEGORIES:
        category = "Other"

    return {
        "merchant_name": str(merchant).strip() if merchant else "",
        "transaction_date": normalized_date,
        "total_amount": clean_and_validate_amount(amount_val),
        "currency_code": normalized_currency,
        "category": category
    }

def extract_details_with_ollama(ocr_text):
    """Send OCR text to Ollama to extract structured details with currency code."""
    if not ocr_text or not ocr_text.strip():
        return None
    
    prompt = f"""Extract the following information from the receipt text:
- Merchant name
- Transaction date (format: YYYY-MM-DD)
- Total amount (as a number)
- Currency code (ISO 4217, e.g. INR, USD, EUR, GBP, CAD, AUD, AED, JPY, CNY, PKR, SGD, NZD, CHF, BDT, NPR, LKR. If ambiguous like '$' or not explicitly identifiable, return null)
- Expense category (choose from: Food, Travel, Software, Office Supplies, Utilities, Medical, Shopping, Other)

Return ONLY a JSON object with keys "merchant_name", "transaction_date", "total_amount", "currency_code", "category". Use null for missing or uncertain values. Never invent missing amounts, dates, or currencies.

Receipt text:
{ocr_text}"""
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        raw_response = result.get("response", "").strip()
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_response = "\n".join(lines).strip()
        extracted = json.loads(raw_response)
        return normalize_extracted_data(extracted)
    except requests.exceptions.RequestException as e:
        st.warning(f"Ollama connection error: {str(e)}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        st.warning(f"Error parsing Ollama response: {str(e)}")
        return None
    except Exception as e:
        st.warning(f"Unexpected error with AI extraction: {str(e)}")
        return None

def save_uploaded_image(uploaded_file):
    """Save uploaded image to receipts directory and return the path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_name = uploaded_file.name
    name, ext = os.path.splitext(original_name)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).rstrip()
    if not safe_name:
        safe_name = "receipt"
    filename = f"{safe_name}_{timestamp}{ext}"
    counter = 1
    while os.path.exists(os.path.join(RECEIPTS_DIR, filename)):
        filename = f"{safe_name}_{timestamp}_{counter}{ext}"
        counter += 1
    
    file_path = os.path.join(RECEIPTS_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

# ==========================================
# PAGE 1: OVERVIEW / DASHBOARD
# ==========================================
def overview_page():
    home_currency = get_home_currency()
    home_symbol = CURRENCY_INFO.get(home_currency, {}).get("symbol", home_currency)
    
    st.markdown(f"""
    <div class="page-header">
        <h1>Dashboard & Overview</h1>
        <p class="page-subtitle">Multi-currency financial monitoring. All reporting figures converted to <strong>{home_currency} ({home_symbol})</strong>.</p>
    </div>
    """, unsafe_allow_html=True)
    
    expenses = get_expenses()
    unverified_count = get_unverified_count()
    
    # Action hero strip
    with st.container(border=True):
        a_col1, a_col2, a_col3 = st.columns([2, 1, 1])
        with a_col1:
            st.markdown(f"""
            <div style="padding-top: 4px;">
                <div style="font-weight: 700; font-size: 1.05rem; color: #0f172a;">Quick Actions</div>
                <div style="color: #64748b; font-size: 0.85rem;">Capture a new receipt with local AI or view expenses in <strong>{home_currency}</strong>.</div>
            </div>
            """, unsafe_allow_html=True)
        with a_col2:
            if st.button("🧾 Scan Receipt", type="primary", use_container_width=True):
                st.session_state.target_page = "Upload Receipt"
                st.rerun()
        with a_col3:
            if st.button("📋 View All Expenses", use_container_width=True):
                st.session_state.target_page = "View Expenses"
                st.rerun()

    monthly_total = get_monthly_total(home_currency)
    total_all = get_all_time_total(home_currency)
    cat_summary = get_category_summary(home_currency)
    top_cat = max(cat_summary, key=cat_summary.get) if cat_summary else "N/A"
    top_cat_amt = cat_summary.get(top_cat, 0.0) if cat_summary else 0.0
    
    # Notice for legacy / unverified expenses if present
    if unverified_count > 0:
        st.markdown(f"""
        <div class="extract-alert extract-alert-warning">
            <span>⚠️</span>
            <span><strong>{unverified_count} legacy expense(s) have unverified currency.</strong> They are listed in your history but excluded from {home_currency} totals until classified.</span>
        </div>
        """, unsafe_allow_html=True)

    # 4 KPI Metric Cards in Home Currency
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(render_metric_card(
            f"Monthly Spending ({home_currency})",
            format_money_html(monthly_total, home_currency),
            "Current calendar month",
            accent="#4f46e5"
        ), unsafe_allow_html=True)
    with m2:
        st.markdown(render_metric_card(
            f"All-Time Total ({home_currency})",
            format_money_html(total_all, home_currency),
            "Converted verified expenses",
            accent="#0284c7"
        ), unsafe_allow_html=True)
    with m3:
        sub_text = f"{unverified_count} unverified" if unverified_count > 0 else "All verified"
        st.markdown(render_metric_card(
            "Total Receipts",
            f"{len(expenses)} records",
            sub_text,
            accent="#059669"
        ), unsafe_allow_html=True)
    with m4:
        top_cat_sub = f"{format_money_html(top_cat_amt, home_currency)} spent" if top_cat_amt > 0 else "No data"
        st.markdown(render_metric_card(
            "Top Category",
            top_cat,
            top_cat_sub,
            accent="#7c3aed"
        ), unsafe_allow_html=True)
        
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    if not expenses:
        st.markdown("""
        <div class="empty-state-card">
            <div class="empty-icon">🧾</div>
            <h3>No Expenses Recorded Yet</h3>
            <p>Upload your first receipt or manually record an expense to start tracking your business finances.</p>
        </div>
        """, unsafe_allow_html=True)
        return
        
    # Split view: Recent Expenses & Category Breakdown
    c_left, c_right = st.columns([1.5, 1], gap="medium")
    
    with c_left:
        with st.container(border=True):
            st.markdown("""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-weight: 700; font-size: 0.98rem; color: #0f172a;">Recent Expenses</span>
                <span style="font-size: 0.76rem; color: #64748b; font-weight: 600; text-transform: uppercase;">Latest entries</span>
            </div>
            """, unsafe_allow_html=True)
            
            recent = expenses[:6]
            recent_rows = []
            for exp in recent:
                exp_id = exp[0]
                merchant = exp[1]
                date_str = exp[2]
                total_amt = exp[3]
                category = exp[4]
                orig_amt = exp[8]
                orig_cur = exp[9]
                base_cur = exp[10]
                status = exp[14] if len(exp) > 14 else "verified"
                
                # Format original amount
                if status == "unverified":
                    orig_disp = f"{orig_amt:.2f} (Unverified)"
                    conv_disp = "Excluded from totals"
                else:
                    orig_disp = format_money(orig_amt, orig_cur or home_currency)
                    conv_disp = format_money(total_amt, base_cur or home_currency)
                    
                recent_rows.append({
                    "Merchant": merchant,
                    "Date": date_str,
                    "Receipt Value": orig_disp,
                    f"Converted ({home_currency})": conv_disp,
                    "Category": category
                })
            st.dataframe(
                recent_rows,
                use_container_width=True,
                hide_index=True
            )
            
    with c_right:
        with st.container(border=True):
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-weight: 700; font-size: 0.98rem; color: #0f172a;">Category Breakdown</span>
                <span style="font-size: 0.76rem; color: #64748b; font-weight: 600; text-transform: uppercase;">In {home_currency}</span>
            </div>
            """, unsafe_allow_html=True)
            
            if cat_summary and total_all > 0:
                for cat, amt in cat_summary.items():
                    pct = (amt / total_all) * 100
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 2px;">
                        <span style="font-weight: 600; color: #1e293b;">{cat}</span>
                        <span style="color: #64748b;">{format_money_html(amt, home_currency)} ({pct:.0f}%)</span>
                    </div>
                    """, unsafe_allow_html=True)
                    st.progress(min(max(pct / 100.0, 0.0), 1.0))
            else:
                st.info(f"No verified expenses in {home_currency} recorded yet.")

# ==========================================
# PAGE 2: UPLOAD RECEIPT (MULTI-CURRENCY)
# ==========================================
def upload_receipt_page():
    home_currency = get_home_currency()
    
    st.markdown(f"""
    <div class="page-header">
        <h1>Upload Receipt</h1>
        <p class="page-subtitle">Scan receipts in any currency. Auto-converts to reporting currency: <strong>{home_currency}</strong>.</p>
    </div>
    """, unsafe_allow_html=True)
    
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    uploaded_file = st.file_uploader(
        "Choose a receipt image (JPG, JPEG, PNG)",
        type=["jpg", "jpeg", "png"],
        key=f"receipt_uploader_{st.session_state.uploader_key}"
    )
    
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        
        # New file uploaded: run OCR and Ollama extraction once
        if st.session_state.get("active_file_id") != file_id:
            st.session_state.active_file_id = file_id
            st.session_state.file_saved = False
            st.session_state.last_saved_info = None
            st.session_state.manual_rate_override = None
            
            image = Image.open(uploaded_file)
            with st.spinner("Stage B: Extracting text using local Tesseract OCR..."):
                st.session_state.raw_text = extract_text_from_image(image)
                
            if st.session_state.raw_text:
                with st.spinner(f"Stage B: Structuring receipt with local AI ({OLLAMA_MODEL})..."):
                    st.session_state.extracted_details = extract_details_with_ollama(st.session_state.raw_text)
            else:
                st.session_state.extracted_details = None

        # Stage Guide Banner (Stages 1 & 2 completed, Stage 3 Active)
        st.markdown("""
        <div class="stage-indicator">
            <div class="stage-item stage-active">
                <span class="stage-badge">✓</span>
                <span>Stage A: Upload</span>
            </div>
            <div class="stage-arrow">→</div>
            <div class="stage-item stage-active">
                <span class="stage-badge">✓</span>
                <span>Stage B: Local Extraction</span>
            </div>
            <div class="stage-arrow">→</div>
            <div class="stage-item stage-active">
                <span class="stage-badge">3</span>
                <span>Stage C: Review, Convert & Save</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # If receipt was already saved, display confirmation card
        if st.session_state.get("file_saved"):
            info = st.session_state.get("last_saved_info", {})
            st.markdown(f"""
            <div class="success-card">
                <div class="success-card-header">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    <span class="success-card-title">Expense #{info.get('id', '')} Saved to Database</span>
                </div>
                <div class="success-grid">
                    <div>
                        <div class="success-grid-label">Merchant</div>
                        <div class="success-grid-val">{info.get('merchant', '')}</div>
                    </div>
                    <div>
                        <div class="success-grid-label">Receipt Amount</div>
                        <div class="success-grid-val">{format_money_html(info.get('orig_amount'), info.get('orig_currency'))}</div>
                    </div>
                    <div>
                        <div class="success-grid-label">Converted ({info.get('base_currency')})</div>
                        <div class="success-grid-val">{format_money_html(info.get('amount'), info.get('base_currency'))}</div>
                    </div>
                    <div>
                        <div class="success-grid-label">Date</div>
                        <div class="success-grid-val">{info.get('date', '')}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                if st.button("📋 View in Expenses", type="primary", use_container_width=True):
                    st.session_state.target_page = "View Expenses"
                    st.rerun()
            with b_col2:
                if st.button("➕ Scan Another Receipt", use_container_width=True):
                    st.session_state.active_file_id = None
                    st.session_state.file_saved = False
                    st.session_state.last_saved_info = None
                    st.session_state.uploader_key += 1
                    st.rerun()
            return

        extracted = st.session_state.get("extracted_details") or {}
        
        # Stage B Status Alert
        if extracted and extracted.get("merchant_name") and extracted.get("total_amount") is not None:
            detected_curr_str = f" · Detected Currency: {extracted.get('currency_code')}" if extracted.get('currency_code') else " · Please confirm currency"
            st.markdown(f"""
            <div class="extract-alert extract-alert-success">
                <span>✓</span>
                <span><strong>Stage B Complete:</strong> Local AI model (<code>{OLLAMA_MODEL}</code>) extracted details{detected_curr_str}.</span>
            </div>
            """, unsafe_allow_html=True)
        elif extracted:
            st.markdown("""
            <div class="extract-alert extract-alert-warning">
                <span>⚠️</span>
                <span><strong>Stage B Partial:</strong> Some fields were uncertain or currency is unstated. Please confirm the fields below.</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="extract-alert extract-alert-info">
                <span>ℹ️</span>
                <span><strong>Stage B Manual Fallback:</strong> Automatic extraction incomplete. You can inspect the receipt and fill in the form.</span>
            </div>
            """, unsafe_allow_html=True)

        # Stage C: 2-Column Responsive Layout
        col_preview, col_form = st.columns([1, 1.25], gap="large")
        
        with col_preview:
            with st.container(border=True):
                st.markdown("""
                <div style="font-weight: 700; font-size: 0.95rem; color: #0f172a; margin-bottom: 8px;">
                    Receipt Preview
                </div>
                """, unsafe_allow_html=True)
                image = Image.open(uploaded_file)
                st.image(image, use_container_width=True)
                
                raw_text = st.session_state.get("raw_text", "")
                if raw_text:
                    with st.expander(f"📄 View OCR Text ({len(raw_text)} chars)", expanded=False):
                        st.text_area("OCR Result", raw_text, height=130, disabled=True, label_visibility="collapsed")

        with col_form:
            with st.container(border=True):
                st.markdown(f"""
                <div style="font-weight: 700; font-size: 1.05rem; color: #0f172a; margin-bottom: 2px;">
                    Stage C: Review & Multi-Currency Conversion
                </div>
                <div style="color: #64748b; font-size: 0.82rem; margin-bottom: 12px;">
                    Confirm receipt currency. Amounts will be converted to reporting currency <strong>{home_currency}</strong>.
                </div>
                """, unsafe_allow_html=True)
                
                # Input fields (outside form to allow reactive exchange rate display)
                c_row1_1, c_row1_2 = st.columns(2)
                with c_row1_1:
                    merchant_val = st.text_input(
                        "Merchant Name *",
                        value=extracted.get("merchant_name", "") or "",
                        placeholder="e.g. Acme Supplies",
                        key=f"m_name_{st.session_state.active_file_id}"
                    )
                with c_row1_2:
                    default_date = extracted.get("transaction_date", "") or datetime.now().strftime("%Y-%m-%d")
                    tx_date_val = st.text_input(
                        "Transaction Date *",
                        value=default_date,
                        help="Format: YYYY-MM-DD",
                        key=f"tx_date_{st.session_state.active_file_id}"
                    )
                    
                c_row2_1, c_row2_2 = st.columns(2)
                with c_row2_1:
                    initial_amt = ""
                    if extracted.get("total_amount") is not None:
                        initial_amt = f"{extracted.get('total_amount'):.2f}"
                    amount_val = st.text_input(
                        "Original Total Amount *",
                        value=initial_amt,
                        placeholder="0.00",
                        key=f"amt_{st.session_state.active_file_id}"
                    )
                with c_row2_2:
                    det_curr = extracted.get("currency_code")
                    default_curr_idx = SUPPORTED_CURRENCIES.index(det_curr) if (det_curr in SUPPORTED_CURRENCIES) else SUPPORTED_CURRENCIES.index(home_currency)
                    orig_currency = st.selectbox(
                        "Receipt Currency *",
                        options=SUPPORTED_CURRENCIES,
                        index=default_curr_idx,
                        key=f"cur_{st.session_state.active_file_id}"
                    )
                    
                cat_val = extracted.get("category", "Other")
                if cat_val not in CATEGORIES:
                    cat_val = "Other"
                selected_cat = st.selectbox(
                    "Expense Category",
                    options=CATEGORIES,
                    index=CATEGORIES.index(cat_val),
                    key=f"cat_{st.session_state.active_file_id}"
                )
                
                # Conversion Card & FX Management
                st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                
                rate_to_use = 1.0
                rate_date_used = tx_date_val
                rate_src_used = "Same Currency"
                conversion_valid = True
                calculated_conv_amt = None
                parsed_amt = clean_and_validate_amount(amount_val)
                
                if orig_currency == home_currency:
                    st.markdown(f"""
                    <div class="fx-card">
                        <div class="fx-header">Currency Match ({home_currency})</div>
                        <div class="fx-rate-text">1 {home_currency} = 1.0000 {home_currency}</div>
                        <div class="fx-subtext">No exchange rate conversion needed. Recorded directly in reporting currency.</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if parsed_amt is not None:
                        calculated_conv_amt = parsed_amt
                else:
                    # Foreign currency: Fetch exchange rate from Frankfurter / Cache
                    fx_info = get_exchange_rate(orig_currency, home_currency, tx_date_val)
                    
                    if fx_info['success']:
                        rate_to_use = fx_info['rate']
                        rate_date_used = fx_info['rate_date']
                        rate_src_used = fx_info['source']
                        if parsed_amt is not None:
                            calculated_conv_amt = calculate_converted_amount(parsed_amt, rate_to_use, target_currency=home_currency)
                            
                        st.markdown(f"""
                        <div class="fx-card">
                            <div class="fx-header">Reference Exchange Rate ({orig_currency} → {home_currency})</div>
                            <div class="fx-rate-text">1 {orig_currency} = {rate_to_use:.4f} {home_currency}</div>
                            <div class="fx-subtext">Rate Date: <strong>{rate_date_used}</strong> · Source: <strong>{rate_src_used}</strong></div>
                            <div style="margin-top: 6px; font-weight: 700; color: #1e40af;">
                                Converted Total: {format_money_html(calculated_conv_amt, home_currency)}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        conversion_valid = False
                        st.markdown(f"""
                        <div class="extract-alert extract-alert-warning">
                            <span>⚠️</span>
                            <span>{fx_info['error']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Option to manually override rate or enter custom settlement rate
                    with st.expander("✏️ Override or Enter Exchange Rate Manually", expanded=not fx_info['success']):
                        manual_rate_input = st.number_input(
                            f"Manual Exchange Rate (1 {orig_currency} = X {home_currency})",
                            min_value=0.00001,
                            value=float(rate_to_use) if rate_to_use else 1.0,
                            step=0.0001,
                            format="%.5f",
                            key=f"m_rate_{st.session_state.active_file_id}"
                        )
                        use_manual_rate = st.checkbox("Apply this manual exchange rate", value=(not fx_info['success']))
                        if use_manual_rate:
                            rate_to_use = manual_rate_input
                            rate_date_used = tx_date_val
                            rate_src_used = "Manual Entry (User Overridden)"
                            conversion_valid = True
                            if parsed_amt is not None:
                                calculated_conv_amt = calculate_converted_amount(parsed_amt, rate_to_use, target_currency=home_currency)
                            st.info(f"Custom rate applied: 1 {orig_currency} = {rate_to_use:.4f} {home_currency}")

                # Save Button Action
                st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
                if st.button("💾 Save Expense to Database", type="primary", use_container_width=True):
                    errors = []
                    m_clean = merchant_val.strip()
                    d_clean = tx_date_val.strip()
                    
                    if not m_clean:
                        errors.append("Merchant name is required.")
                    if not d_clean:
                        errors.append("Transaction date is required.")
                    elif not validate_date(d_clean):
                        errors.append("Invalid date format. Please use YYYY-MM-DD.")
                        
                    if not amount_val.strip():
                        errors.append("Total amount is required.")
                    elif parsed_amt is None:
                        errors.append("Invalid amount. Please enter a valid non-negative number.")
                        
                    if not conversion_valid or calculated_conv_amt is None:
                        errors.append(f"A valid exchange rate is required to convert {orig_currency} to {home_currency}.")
                        
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        try:
                            image_path = save_uploaded_image(uploaded_file)
                            raw_text = st.session_state.get("raw_text", "")
                            new_id = save_expense(
                                merchant_name=m_clean,
                                transaction_date=d_clean,
                                total_amount=calculated_conv_amt,
                                category=selected_cat,
                                raw_text=raw_text,
                                image_path=image_path,
                                original_amount=parsed_amt,
                                original_currency=orig_currency,
                                base_currency=home_currency,
                                exchange_rate=rate_to_use,
                                exchange_rate_date=rate_date_used,
                                exchange_rate_source=rate_src_used,
                                currency_status="verified"
                            )
                            st.session_state.file_saved = True
                            st.session_state.last_saved_info = {
                                "id": new_id,
                                "merchant": m_clean,
                                "date": d_clean,
                                "amount": calculated_conv_amt,
                                "orig_amount": parsed_amt,
                                "orig_currency": orig_currency,
                                "base_currency": home_currency
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save expense: {str(e)}")

    else:
        # Initial Stage Guide Banner (Stage 1 Active)
        st.markdown("""
        <div class="stage-indicator">
            <div class="stage-item stage-active">
                <span class="stage-badge">1</span>
                <span>Stage A: Upload Receipt</span>
            </div>
            <div class="stage-arrow">→</div>
            <div class="stage-item">
                <span class="stage-badge">2</span>
                <span>Stage B: Local Extraction</span>
            </div>
            <div class="stage-arrow">→</div>
            <div class="stage-item">
                <span class="stage-badge">3</span>
                <span>Stage C: Review & Save</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.get("manual_saved_message"):
            st.success(st.session_state.manual_saved_message)
            st.session_state.manual_saved_message = None

        # Clean fallback card for manual entry
        with st.container(border=True):
            st.markdown(f"""
            <div style="font-weight: 700; font-size: 1rem; color: #0f172a; margin-bottom: 2px;">
                Manual Expense Entry
            </div>
            <div style="color: #64748b; font-size: 0.82rem; margin-bottom: 12px;">
                Record an expense directly in any currency without uploading a receipt.
            </div>
            """, unsafe_allow_html=True)
            
            with st.form(key="manual_no_image_form"):
                col1, col2 = st.columns(2)
                with col1:
                    m_name = st.text_input("Merchant Name *", placeholder="e.g. Local Coffee")
                    t_date = st.text_input("Transaction Date *", value=datetime.now().strftime("%Y-%m-%d"), help="Format: YYYY-MM-DD")
                with col2:
                    t_amount = st.text_input("Total Amount *", placeholder="0.00")
                    m_curr = st.selectbox("Currency *", options=SUPPORTED_CURRENCIES, index=SUPPORTED_CURRENCIES.index(home_currency))
                    
                t_cat = st.selectbox("Category", options=CATEGORIES)
                
                st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
                man_submit = st.form_submit_button("💾 Save Manual Expense", type="primary", use_container_width=True)
                if man_submit:
                    errors = []
                    m_clean = m_name.strip()
                    d_clean = t_date.strip()
                    amt_clean = clean_and_validate_amount(t_amount)
                    
                    if not m_clean:
                        errors.append("Merchant name is required.")
                    if not d_clean:
                        errors.append("Transaction date is required.")
                    elif not validate_date(d_clean):
                        errors.append("Invalid date format. Please use YYYY-MM-DD.")
                    if not t_amount.strip():
                        errors.append("Total amount is required.")
                    elif amt_clean is None:
                        errors.append("Invalid amount. Please enter a valid non-negative number.")
                        
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        try:
                            # If manual expense is in foreign currency, fetch or calculate rate
                            if m_curr == home_currency:
                                rate = 1.0
                                conv = amt_clean
                                r_date = d_clean
                                r_src = "Same Currency"
                            else:
                                fx = get_exchange_rate(m_curr, home_currency, d_clean)
                                rate = fx['rate'] if fx['success'] else 1.0
                                conv = calculate_converted_amount(amt_clean, rate, target_currency=home_currency)
                                r_date = fx['rate_date'] or d_clean
                                r_src = fx['source'] or "Manual Fallback Rate"
                                
                            new_id = save_expense(
                                merchant_name=m_clean,
                                transaction_date=d_clean,
                                total_amount=conv,
                                category=t_cat,
                                raw_text="",
                                image_path="",
                                original_amount=amt_clean,
                                original_currency=m_curr,
                                base_currency=home_currency,
                                exchange_rate=rate,
                                exchange_rate_date=r_date,
                                exchange_rate_source=r_src,
                                currency_status="verified"
                            )
                            st.session_state.manual_saved_message = f"✅ Expense #{new_id} ({m_clean}) saved successfully! Converted: {format_money(conv, home_currency)}"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save expense: {str(e)}")

# ==========================================
# PAGE 3: VIEW EXPENSES (TRANSACTION HISTORY)
# ==========================================
def view_expenses_page():
    home_currency = get_home_currency()
    home_symbol = CURRENCY_INFO.get(home_currency, {}).get("symbol", home_currency)
    
    st.markdown(f"""
    <div class="page-header">
        <h1>Transaction History</h1>
        <p class="page-subtitle">Multi-currency transactions converted to reporting currency: <strong>{home_currency} ({home_symbol})</strong>.</p>
    </div>
    """, unsafe_allow_html=True)
    
    expenses = get_expenses()
    unverified_count = get_unverified_count()
    
    if not expenses:
        st.markdown("""
        <div class="empty-state-card">
            <div class="empty-icon">🧾</div>
            <h3>No Expenses Recorded Yet</h3>
            <p>Upload a receipt image or manually record an expense to start tracking your business spending.</p>
        </div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("➕ Scan First Receipt", type="primary", use_container_width=True):
                st.session_state.target_page = "Upload Receipt"
                st.rerun()
        return
    
    # Unverified currency alert
    if unverified_count > 0:
        st.markdown(f"""
        <div class="extract-alert extract-alert-warning">
            <span>⚠️</span>
            <span><strong>{unverified_count} legacy record(s) have unverified currencies.</strong> They are listed below with a ⚠️ badge and excluded from total spending calculations. Expand any record below to confirm its currency.</span>
        </div>
        """, unsafe_allow_html=True)

    # 4 KPI Summary Cards in Home Currency
    monthly_total = get_monthly_total(home_currency)
    total_all = get_all_time_total(home_currency)
    cat_summary = get_category_summary(home_currency)
    top_cat = max(cat_summary, key=cat_summary.get) if cat_summary else "N/A"
    top_cat_amt = cat_summary.get(top_cat, 0.0) if cat_summary else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(render_metric_card(
            f"Spending This Month ({home_currency})",
            format_money_html(monthly_total, home_currency),
            "Active billing month",
            accent="#4f46e5"
        ), unsafe_allow_html=True)
    with m2:
        st.markdown(render_metric_card(
            f"All-Time Total ({home_currency})",
            format_money_html(total_all, home_currency),
            "Across verified records",
            accent="#0284c7"
        ), unsafe_allow_html=True)
    with m3:
        sub_text = f"{unverified_count} unverified" if unverified_count > 0 else "All verified"
        st.markdown(render_metric_card(
            "Total Receipts",
            f"{len(expenses)} records",
            sub_text,
            accent="#059669"
        ), unsafe_allow_html=True)
    with m4:
        top_cat_label = f"{format_money_html(top_cat_amt, home_currency)} spent" if top_cat_amt > 0 else "No data"
        st.markdown(render_metric_card(
            "Top Category",
            top_cat,
            top_cat_label,
            accent="#7c3aed"
        ), unsafe_allow_html=True)
        
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    # Structured Filter Toolbar
    with st.container(border=True):
        st.markdown("""
        <div style="font-size: 0.88rem; font-weight: 700; color: #0f172a; margin-bottom: 6px;">
            Filter & Search Transactions
        </div>
        """, unsafe_allow_html=True)
        
        f_col1, f_col2, f_col3, f_col4 = st.columns([1.8, 1, 1, 1])
        with f_col1:
            search_term = st.text_input("Search", placeholder="🔍 Search merchant, notes, or ID...", label_visibility="collapsed")
        with f_col2:
            category_filter = st.selectbox("Category", options=["All Categories"] + CATEGORIES, label_visibility="collapsed")
        with f_col3:
            currency_filter = st.selectbox("Currency Filter", options=["All Currencies", "Verified Only", "Unverified Only", f"{home_currency} Only"], label_visibility="collapsed")
        with f_col4:
            date_filter_type = st.selectbox(
                "Date Range",
                options=["All Dates", "This Month", "Last 30 Days", "Custom Range"],
                label_visibility="collapsed"
            )
            
        start_date = None
        end_date = None
        if date_filter_type == "Custom Range":
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                start_date = st.date_input("From Date", value=datetime.now().date() - timedelta(days=30))
            with c_col2:
                end_date = st.date_input("To Date", value=datetime.now().date())
            
    # Apply Filtering
    filtered_expenses = []
    today = datetime.now().date()
    current_month_prefix = datetime.now().strftime("%Y-%m")
    
    for exp in expenses:
        exp_id = exp[0]
        merchant = exp[1]
        date_str = exp[2]
        total_amt = exp[3]
        category = exp[4]
        raw_text = exp[5]
        image_path = exp[6]
        created_at = exp[7]
        orig_amt = exp[8]
        orig_cur = exp[9]
        base_cur = exp[10]
        status = exp[14] if len(exp) > 14 else "verified"
        
        # Search query filter
        if search_term:
            q = search_term.lower()
            m_match = merchant and q in merchant.lower()
            c_match = category and q in category.lower()
            t_match = raw_text and q in raw_text.lower()
            id_match = str(exp_id) == q
            if not (m_match or c_match or t_match or id_match):
                continue
                
        # Category filter
        if category_filter != "All Categories" and category != category_filter:
            continue
            
        # Currency status filter
        if currency_filter == "Verified Only" and status != "verified":
            continue
        elif currency_filter == "Unverified Only" and status != "unverified":
            continue
        elif currency_filter == f"{home_currency} Only" and (orig_cur != home_currency and base_cur != home_currency):
            continue
            
        # Date filter
        if date_filter_type == "This Month":
            if not date_str or not date_str.startswith(current_month_prefix):
                continue
        elif date_filter_type == "Last 30 Days":
            try:
                exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if not (today - timedelta(days=30) <= exp_date <= today):
                    continue
            except (ValueError, TypeError):
                continue
        elif date_filter_type == "Custom Range":
            if start_date and end_date:
                try:
                    exp_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if not (start_date <= exp_date <= end_date):
                        continue
                except (ValueError, TypeError):
                    continue
                    
        filtered_expenses.append(exp)
        
    if not filtered_expenses:
        st.markdown("""
        <div class="empty-state-card">
            <div class="empty-icon">🔍</div>
            <h3>No Matching Expenses</h3>
            <p>No records match your active search and filter criteria. Try adjusting your search query or date range.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # Table Container with Header Bar and CSV Export
    with st.container(border=True):
        t_col1, t_col2 = st.columns([2.5, 1])
        with t_col1:
            st.markdown(f"""
            <div style="font-weight: 700; font-size: 1rem; color: #0f172a; padding-top: 4px;">
                Transaction Records <span style="font-size: 0.8rem; color: #64748b; font-weight: 500;">({len(filtered_expenses)} of {len(expenses)} matches)</span>
            </div>
            """, unsafe_allow_html=True)
        with t_col2:
            # 15-column CSV export
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ID", "Merchant Name", "Transaction Date", "Original Amount", "Original Currency",
                "Converted Amount", "Base Currency", "Exchange Rate", "Exchange Rate Date", "Exchange Rate Source",
                "Currency Status", "Category", "Raw Text", "Image Path", "Created At"
            ])
            for exp in filtered_expenses:
                exp_id = exp[0]
                merchant = exp[1]
                date_str = exp[2]
                total_amt = exp[3]
                category = exp[4]
                raw_text = exp[5]
                image_path = exp[6]
                created_at = exp[7]
                orig_amt = exp[8]
                orig_cur = exp[9]
                base_cur = exp[10]
                rate = exp[11]
                rate_date = exp[12]
                rate_src = exp[13]
                status = exp[14] if len(exp) > 14 else "verified"
                writer.writerow([
                    exp_id, merchant, date_str, orig_amt, orig_cur or "",
                    total_amt, base_cur or "", rate or "", rate_date or "", rate_src or "",
                    status, category, raw_text, image_path, created_at
                ])
            csv_bytes = output.getvalue().encode("utf-8")
            
            st.download_button(
                label=f"📥 Export View ({len(filtered_expenses)}) to CSV",
                data=csv_bytes,
                file_name=f"receiptpocket_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        table_rows = []
        for exp in filtered_expenses:
            exp_id = exp[0]
            merchant = exp[1]
            date_str = exp[2]
            total_amt = exp[3]
            category = exp[4]
            image_path = exp[6]
            created_at = exp[7]
            orig_amt = exp[8]
            orig_cur = exp[9]
            base_cur = exp[10]
            rate = exp[11]
            status = exp[14] if len(exp) > 14 else "verified"
            has_img = bool(image_path and os.path.exists(resolve_image_path(image_path)))
            
            if status == "unverified":
                orig_disp = f"{orig_amt:.2f} (Unverified)"
                conv_disp = "Excluded"
                rate_disp = "N/A"
            else:
                orig_disp = format_money(orig_amt, orig_cur or home_currency)
                conv_disp = format_money(total_amt, base_cur or home_currency)
                rate_disp = f"{rate:.4f}" if (rate and orig_cur != base_cur) else "1.0000"
                
            table_rows.append({
                "ID": exp_id,
                "Merchant": merchant,
                "Date": date_str,
                "Original Value": orig_disp,
                f"Converted ({home_currency})": conv_disp,
                "FX Rate": rate_disp,
                "Category": category,
                "Status": "⚠️ Unverified" if status == "unverified" else ("✓ Verified" if status == "verified" else "ℹ️ Unconverted"),
                "Receipt": "Yes" if has_img else "No"
            })
            
        st.dataframe(
            table_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Merchant": st.column_config.TextColumn("Merchant Name"),
                "Date": st.column_config.TextColumn("Date"),
                "Original Value": st.column_config.TextColumn("Receipt Value"),
                f"Converted ({home_currency})": st.column_config.TextColumn(f"Converted ({home_currency})"),
                "FX Rate": st.column_config.TextColumn("FX Rate"),
                "Category": st.column_config.TextColumn("Category"),
                "Status": st.column_config.TextColumn("Currency Status"),
                "Receipt": st.column_config.TextColumn("Receipt")
            }
        )
    
    # Detailed Receipt Viewer Section with Legacy Currency Classifier
    with st.container(border=True):
        st.markdown("""
        <div style="font-weight: 700; font-size: 1rem; color: #0f172a; margin-bottom: 2px;">
            Detailed Receipt Inspection & Currency Verification
        </div>
        <div style="color: #64748b; font-size: 0.82rem; margin-bottom: 12px;">
            Click on any expense record below to inspect attached receipt images, verify foreign currencies, or inspect OCR text.
        </div>
        """, unsafe_allow_html=True)
        
        for exp in filtered_expenses:
            exp_id = exp[0]
            merchant = exp[1]
            date_str = exp[2]
            total_amt = exp[3]
            category = exp[4]
            raw_text = exp[5]
            image_path = exp[6]
            created_at = exp[7]
            orig_amt = exp[8]
            orig_cur = exp[9]
            base_cur = exp[10]
            rate = exp[11]
            rate_date = exp[12]
            rate_src = exp[13]
            status = exp[14] if len(exp) > 14 else "verified"
            resolved_img = resolve_image_path(image_path)
            
            if status == "unverified":
                header_amount = f"{orig_amt:.2f} (Unverified Currency)"
                status_icon = "⚠️"
            else:
                header_amount = f"{format_money(orig_amt, orig_cur)} → {format_money(total_amt, base_cur)}"
                status_icon = "✓"
                
            with st.expander(f"{status_icon} #{exp_id} · {merchant} — {header_amount} · {date_str} [{category}]"):
                col1, col2 = st.columns([1, 1.8], gap="medium")
                
                with col1:
                    if resolved_img and os.path.exists(resolved_img):
                        try:
                            img = Image.open(resolved_img)
                            st.image(img, caption=f"Receipt #{exp_id}", use_container_width=True)
                        except Exception as err:
                            st.write(f"Image load error: {str(err)}")
                    else:
                        st.info("No receipt image attached to this record.")
                        
                with col2:
                    st.markdown(f"**Expense ID:** `{exp_id}`")
                    st.markdown(f"**Merchant:** {merchant}")
                    st.markdown(f"**Transaction Date:** {date_str}")
                    st.markdown(f"**Category:** `{category}`")
                    st.markdown(f"**Recorded On:** {created_at}")
                    
                    if status == "verified":
                        st.markdown(f"**Original Amount:** {format_money(orig_amt, orig_cur)}")
                        st.markdown(f"**Converted ({base_cur}):** {format_money(total_amt, base_cur)}")
                        st.markdown(f"**Exchange Rate:** `{rate}` (Date: {rate_date} · Source: {rate_src})")
                        st.markdown(f"**Currency Status:** <span class='status-badge status-badge-verified'>Verified</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"**Amount Stored:** `{orig_amt}`")
                        st.markdown(f"**Currency Status:** <span class='status-badge status-badge-unverified'>Unverified Legacy Record</span>", unsafe_allow_html=True)
                        
                        # In-place classifier for legacy / unverified records
                        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                        with st.container(border=True):
                            st.markdown(f"**Classify & Convert this Legacy Record to {home_currency}:**")
                            
                            c_sub1, c_sub2 = st.columns(2)
                            with c_sub1:
                                selected_leg_cur = st.selectbox(
                                    f"Original Currency for #{exp_id}",
                                    options=SUPPORTED_CURRENCIES,
                                    index=SUPPORTED_CURRENCIES.index(home_currency),
                                    key=f"leg_cur_{exp_id}"
                                )
                            with c_sub2:
                                if selected_leg_cur == home_currency:
                                    leg_rate = 1.0
                                    st.write(f"Same currency (1:1 conversion)")
                                else:
                                    leg_fx = get_exchange_rate(selected_leg_cur, home_currency, date_str)
                                    leg_rate = leg_fx['rate'] if leg_fx['success'] else 1.0
                                    st.write(f"Rate: 1 {selected_leg_cur} = {leg_rate:.4f} {home_currency}")
                                    
                            if st.button(f"💾 Confirm & Convert #{exp_id} to {home_currency}", key=f"leg_btn_{exp_id}", type="primary"):
                                r_date = date_str
                                r_src = "Frankfurter API" if selected_leg_cur != home_currency else "Same Currency"
                                update_legacy_expense_currency(
                                    expense_id=exp_id,
                                    original_currency=selected_leg_cur,
                                    exchange_rate=leg_rate,
                                    exchange_rate_date=r_date,
                                    exchange_rate_source=r_src,
                                    target_currency=home_currency
                                )
                                st.success(f"Expense #{exp_id} verified and converted to {home_currency}!")
                                st.rerun()

                    if raw_text:
                        with st.expander("Show Extracted OCR Text"):
                            st.text_area(f"OCR Text #{exp_id}", raw_text, height=100, disabled=True, label_visibility="collapsed")

# ==========================================
# PAGE 4: EXPORT DATA
# ==========================================
def export_data_page():
    home_currency = get_home_currency()
    
    st.markdown(f"""
    <div class="page-header">
        <h1>Export Data</h1>
        <p class="page-subtitle">Download your complete multi-currency expense records in CSV format for accounting and bookkeeping.</p>
    </div>
    """, unsafe_allow_html=True)
    
    expenses = get_expenses()
    
    if not expenses:
        st.markdown("""
        <div class="empty-state-card">
            <div class="empty-icon">📁</div>
            <h3>No Expenses to Export</h3>
            <p>Your database does not contain any recorded expenses yet.</p>
        </div>
        """, unsafe_allow_html=True)
        return
        
    total_spending = get_all_time_total(home_currency)
    unverified_count = get_unverified_count()
    
    # Export summary cards
    m1, m2 = st.columns(2)
    with m1:
        st.markdown(render_metric_card("Total Records", f"{len(expenses)} expenses", f"{unverified_count} unverified currencies", accent="#4f46e5"), unsafe_allow_html=True)
    with m2:
        st.markdown(render_metric_card(f"Verified Expenditure ({home_currency})", format_money_html(total_spending, home_currency), f"Converted to {home_currency}", accent="#059669"), unsafe_allow_html=True)
        
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Merchant Name", "Transaction Date", "Original Amount", "Original Currency",
        "Converted Amount", "Base Currency", "Exchange Rate", "Exchange Rate Date", "Exchange Rate Source",
        "Currency Status", "Category", "Raw Text", "Image Path", "Created At"
    ])
    for exp in expenses:
        exp_id = exp[0]
        merchant = exp[1]
        date_str = exp[2]
        total_amt = exp[3]
        category = exp[4]
        raw_text = exp[5]
        image_path = exp[6]
        created_at = exp[7]
        orig_amt = exp[8]
        orig_cur = exp[9]
        base_cur = exp[10]
        rate = exp[11]
        rate_date = exp[12]
        rate_src = exp[13]
        status = exp[14] if len(exp) > 14 else "verified"
        writer.writerow([
            exp_id, merchant, date_str, orig_amt, orig_cur or "",
            total_amt, base_cur or "", rate or "", rate_date or "", rate_src or "",
            status, category, raw_text, image_path, created_at
        ])
        
    csv_bytes = output.getvalue().encode("utf-8")
    
    with st.container(border=True):
        st.markdown("""
        <div style="font-size: 1rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
            Export Full Database
        </div>
        <div style="font-size: 0.85rem; color: #64748b; margin-bottom: 14px;">
            Includes both <code>Original Amount</code> & <code>Currency</code> as well as <code>Converted Amount</code>, <code>Exchange Rate</code>, <code>Rate Source</code>, and local <code>Image Path</code>.
        </div>
        """, unsafe_allow_html=True)
        
        st.download_button(
            label=f"📥 Download All Expenses as CSV ({len(expenses)} records)",
            data=csv_bytes,
            file_name=f"receiptpocket_all_expenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )

# ==========================================
# PAGE 5: SETTINGS & PREFERENCES
# ==========================================
def settings_page():
    st.markdown("""
    <div class="page-header">
        <h1>Settings & Currency Preferences</h1>
        <p class="page-subtitle">Configure your home reporting currency, manage offline exchange rate cache, and review legacy records.</p>
    </div>
    """, unsafe_allow_html=True)
    
    current_home = get_home_currency()
    
    # 1. Home Currency Configuration Card
    with st.container(border=True):
        st.markdown("""
        <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 2px;">
            Home / Reporting Currency
        </div>
        <div style="color: #64748b; font-size: 0.85rem; margin-bottom: 14px;">
            All dashboards, category breakdowns, and monthly totals are aggregated and reported in this primary currency.
        </div>
        """, unsafe_allow_html=True)
        
        c1, c2 = st.columns([1.5, 2], gap="large")
        with c1:
            curr_labels = [f"{c} — {CURRENCY_INFO[c]['name']} ({CURRENCY_INFO[c]['symbol']})" for c in SUPPORTED_CURRENCIES]
            current_idx = SUPPORTED_CURRENCIES.index(current_home) if current_home in SUPPORTED_CURRENCIES else 0
            
            selected_label = st.selectbox(
                "Primary Reporting Currency",
                options=curr_labels,
                index=current_idx
            )
            selected_code = SUPPORTED_CURRENCIES[curr_labels.index(selected_label)]
            
        with c2:
            st.markdown(f"""
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px;">
                <div style="font-size: 0.75rem; font-weight: 600; color: #64748b; text-transform: uppercase;">Formatting Example</div>
                <div style="font-size: 1.35rem; font-weight: 700; color: #0f172a; margin: 4px 0;">{format_money(123456.78, selected_code)}</div>
                <div style="font-size: 0.78rem; color: #64748b;">Locale: <code>{CURRENCY_INFO[selected_code]['locale']}</code> · Precision: {CURRENCY_INFO[selected_code]['precision']} decimals</div>
            </div>
            """, unsafe_allow_html=True)
            
        # Safe migration if user wants to change home currency
        if selected_code != current_home:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            
            # Check how many expenses currently converted to current_home
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM expenses WHERE base_currency = ? AND currency_status = 'verified'", (current_home,))
            converted_count = c.fetchone()[0]
            conn.close()
            
            if converted_count > 0:
                st.markdown(f"""
                <div class="extract-alert extract-alert-warning">
                    <span>⚠️</span>
                    <span>You have <strong>{converted_count} expense(s)</strong> converted to <strong>{current_home}</strong>. To change your reporting currency to <strong>{selected_code}</strong>, these records will be recalculated using historical rates for {selected_code}.</span>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"🔄 Confirm & Re-convert All {converted_count} Expenses to {selected_code}", type="primary"):
                    with st.spinner(f"Migrating records to {selected_code}..."):
                        try:
                            migrated = migrate_verified_expenses_to_new_home_currency(selected_code)
                        except Exception as e:
                            logger.error(
                                "settings_page: home-currency migration to %s failed: %s",
                                selected_code, e
                            )
                            st.error(
                                f"Failed to change home currency to {selected_code}. The setting was not changed. "
                                f"{e}\n\nYou can retry by clicking the button again once the exchange rate is available."
                            )
                            migrated = None
                    if migrated is not None:
                        st.success(f"Successfully migrated {migrated} expense(s) to {selected_code}!")
                        st.rerun()
            else:
                if st.button(f"💾 Save {selected_code} as Reporting Currency", type="primary"):
                    with st.spinner(f"Saving {selected_code}..."):
                        try:
                            migrate_verified_expenses_to_new_home_currency(selected_code)
                        except Exception as e:
                            logger.error(
                                "settings_page: home-currency change to %s failed: %s",
                                selected_code, e
                            )
                            st.error(
                                f"Failed to change home currency to {selected_code}. The setting was not changed. "
                                f"{e}\n\nYou can retry by clicking the button again once the exchange rate is available."
                            )
                        else:
                            st.success(f"Home currency set to {selected_code}!")
                            st.rerun()

    # 2. Local Exchange Rate Cache Information
    with st.container(border=True):
        st.markdown("""
        <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 2px;">
            Local Exchange Rate Cache
        </div>
        <div style="color: #64748b; font-size: 0.85rem; margin-bottom: 12px;">
            Rates retrieved from the Frankfurter API are cached in SQLite for offline access and consistent historical reporting.
        </div>
        """, unsafe_allow_html=True)
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM exchange_rates")
        cached_count = c.fetchone()[0]
        c.execute("SELECT source_currency, target_currency, rate_date, rate, rate_source, fetched_at FROM exchange_rates ORDER BY fetched_at DESC LIMIT 10")
        cached_rows = c.fetchall()
        conn.close()
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Cached Exchange Rates", f"{cached_count} entries")
        with c2:
            if cached_count > 0:
                cache_table = []
                for r in cached_rows:
                    cache_table.append({
                        "Pair": f"{r[0]} → {r[1]}",
                        "Rate Date": r[2],
                        "Rate": f"{r[3]:.5f}",
                        "Source": r[4]
                    })
                st.dataframe(cache_table, use_container_width=True, hide_index=True)
            else:
                st.info("No exchange rates cached yet. Rates are fetched on-demand when foreign receipts are processed.")

    # 3. Legacy Records Review
    unverified_count = get_unverified_count()
    with st.container(border=True):
        st.markdown("""
        <div style="font-weight: 700; font-size: 1.05rem; color: #0f172a; margin-bottom: 2px;">
            Legacy Records Status
        </div>
        """, unsafe_allow_html=True)
        if unverified_count > 0:
            st.warning(f"There are {unverified_count} legacy records with unverified currencies. Head to View Expenses to review and assign their currencies.")
            if st.button("📋 Go to View Expenses to Classify Records", type="secondary"):
                st.session_state.target_page = "View Expenses"
                st.rerun()
        else:
            st.success("All historical expenses have verified currencies!")

# ==========================================
# MAIN APPLICATION CONTROLLER
# ==========================================
def main():
    st.set_page_config(
        page_title="ReceiptPocket — Multi-Currency AI Expense Manager",
        page_icon="🧾",
        layout="wide"
    )
    
    # Inject Centralized Custom Styling
    inject_custom_styles()
    
    # Initialize database and apply migrations
    init_db()
    
    # Check and configure Tesseract availability
    if "tesseract_checked" not in st.session_state:
        st.session_state.tesseract_available = configure_tesseract()
        st.session_state.tesseract_checked = True
    
    NAV_MAPPING = {
        "📊  Overview": "Overview",
        "🧾  Upload Receipt": "Upload Receipt",
        "📋  View Expenses": "View Expenses",
        "📥  Export Data": "Export Data",
        "⚙️  Settings": "Settings"
    }
    REVERSE_NAV = {v: k for k, v in NAV_MAPPING.items()}
    nav_labels = list(NAV_MAPPING.keys())
    
    if "current_page" not in st.session_state:
        st.session_state.current_page = "Overview"
        
    if "target_page" in st.session_state and st.session_state.target_page in REVERSE_NAV:
        st.session_state.current_page = st.session_state.target_page
        del st.session_state.target_page
        
    home_currency = get_home_currency()
    home_symbol = CURRENCY_INFO.get(home_currency, {}).get("symbol", home_currency)
    
    # Sidebar Navigation & Branding
    with st.sidebar:
        st.markdown(f"""
        <div class="sidebar-brand-box">
            <div class="brand-logo-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/>
                    <path d="M16 8h-8"/>
                    <path d="M16 12h-8"/>
                    <path d="M11 16h-3"/>
                </svg>
            </div>
            <div>
                <div class="brand-title">ReceiptPocket</div>
                <div class="brand-pill">Multi-Currency AI</div>
            </div>
        </div>
        <div class="brand-desc">Your expenses, privately managed.</div>
        <div class="nav-label">Main Navigation</div>
        """, unsafe_allow_html=True)

        current_label = REVERSE_NAV.get(st.session_state.current_page, "📊  Overview")
        current_index = nav_labels.index(current_label) if current_label in nav_labels else 0
        
        selected_label = st.radio(
            "Navigation Menu",
            nav_labels,
            index=current_index,
            label_visibility="collapsed"
        )
        selected_page = NAV_MAPPING[selected_label]
        st.session_state.current_page = selected_page
        
        # Sidebar Quick Glance Widget in Home Currency
        try:
            m_tot = get_monthly_total(home_currency)
            all_exp = get_expenses()
            st.markdown(f"""
            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; margin-top:1.25rem; box-shadow:0 1px 2px rgba(15,23,42,0.03);">
                <div style="font-size:0.68rem; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;">Reporting ({home_currency})</div>
                <div style="display:flex; justify-content:space-between; font-size:0.8rem; margin-bottom:3px;">
                    <span style="color:#475569;">This Month:</span>
                    <span style="font-weight:700; color:#0f172a;">{format_money_html(m_tot, home_currency)}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                    <span style="color:#475569;">Total Logged:</span>
                    <span style="font-weight:700; color:#0f172a;">{len(all_exp)} receipts</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            pass

        # Privacy badge at bottom of sidebar
        st.markdown(f"""
        <div class="sidebar-privacy-box">
            <div class="privacy-title">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                <span>Private & Local-First</span>
            </div>
            <div class="privacy-note">
                All OCR and AI inferences run on your machine. Foreign exchange quotes use privacy-preserving rate lookups.
            </div>
            <div class="engine-tags">
                <span class="engine-tag">Tesseract</span>
                <span class="engine-tag">Ollama AI</span>
                <span class="engine-tag">SQLite</span>
                <span class="engine-tag">Frankfurter FX</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Route to selected page
    if selected_page == "Overview":
        overview_page()
    elif selected_page == "Upload Receipt":
        upload_receipt_page()
    elif selected_page == "View Expenses":
        view_expenses_page()
    elif selected_page == "Export Data":
        export_data_page()
    elif selected_page == "Settings":
        settings_page()

if __name__ == "__main__":
    main()