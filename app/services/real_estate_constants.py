"""Real-estate reference data — ported from DealKnot's client/src/constants.js.

Countries, currencies, divisions, lead labels and property types. These are
static reference data rather than tenant rows, so they live as Python
constants and are served to the dashboard via GET /real-estate/constants
instead of being seeded into the database.

Only the pieces the backend actually needs to reason about are ported.
DealKnot's pure-presentation helpers (formatMoney, displayRental, initials …)
are deliberately left behind — the dashboard formats money itself, and
duplicating that logic server-side would give us two copies to keep in sync.
"""

# ── Countries ────────────────────────────────────────────────
# code -> name, dial prefix, default currency. Order preserved from DealKnot
# so the dashboard's country dropdown reads the same.
COUNTRIES: list[dict] = [
    {"code": "AE", "name": "United Arab Emirates", "flag": "🇦🇪", "dial": "+971", "currency": "AED"},
    {"code": "GB", "name": "United Kingdom", "flag": "🇬🇧", "dial": "+44", "currency": "GBP"},
    {"code": "SG", "name": "Singapore", "flag": "🇸🇬", "dial": "+65", "currency": "SGD"},
    {"code": "IN", "name": "India", "flag": "🇮🇳", "dial": "+91", "currency": "INR"},
    {"code": "US", "name": "United States", "flag": "🇺🇸", "dial": "+1", "currency": "USD"},
    {"code": "HK", "name": "Hong Kong", "flag": "🇭🇰", "dial": "+852", "currency": "HKD"},
    {"code": "AU", "name": "Australia", "flag": "🇦🇺", "dial": "+61", "currency": "AUD"},
    {"code": "CA", "name": "Canada", "flag": "🇨🇦", "dial": "+1", "currency": "CAD"},
    {"code": "FR", "name": "France", "flag": "🇫🇷", "dial": "+33", "currency": "EUR"},
    {"code": "DE", "name": "Germany", "flag": "🇩🇪", "dial": "+49", "currency": "EUR"},
]

COUNTRY_CODES: set[str] = {c["code"] for c in COUNTRIES}


# ── Currencies ───────────────────────────────────────────────
CURRENCIES: dict[str, dict] = {
    "AED": {"symbol": "AED", "flag": "🇦🇪"},
    "GBP": {"symbol": "£", "flag": "🇬🇧"},
    "SGD": {"symbol": "S$", "flag": "🇸🇬"},
    "INR": {"symbol": "₹", "flag": "🇮🇳"},
    "USD": {"symbol": "$", "flag": "🇺🇸"},
    "HKD": {"symbol": "HK$", "flag": "🇭🇰"},
    "AUD": {"symbol": "A$", "flag": "🇦🇺"},
    "CAD": {"symbol": "C$", "flag": "🇨🇦"},
    "EUR": {"symbol": "€", "flag": "🇪🇺"},
}

CURRENCY_CODES: set[str] = set(CURRENCIES)

# Approximate rates relative to USD. Carried over from DealKnot as-is; these
# are stale reference values, not a live FX feed. The matching engine never
# uses them — it refuses to match across currencies outright — so they only
# ever affect display conversion.
FX_TO_USD: dict[str, float] = {
    "AED": 0.272,
    "GBP": 1.27,
    "SGD": 0.74,
    "INR": 0.012,
    "USD": 1.0,
    "HKD": 0.128,
    "AUD": 0.65,
    "CAD": 0.73,
    "EUR": 1.08,
}


# ── Divisions ────────────────────────────────────────────────
# Sales: a buyer purchases from a seller.
# Rentals: a tenant rents from a landlord. Same two tables, different labels.
DIVISIONS: list[dict] = [
    {"id": "sales", "label": "Sales", "buyer_role": "Buyer", "seller_role": "Seller"},
    {"id": "rentals", "label": "Rentals", "buyer_role": "Tenant", "seller_role": "Landlord"},
]

DIVISION_IDS: set[str] = {d["id"] for d in DIVISIONS}


# ── Lead labels ──────────────────────────────────────────────
LABELS: list[dict] = [
    {"id": "hot", "name": "Hot", "icon": "🔥", "description": "Serious, ready to close fast", "sort": 0},
    {"id": "active", "name": "Active", "icon": "✅", "description": "Currently looking", "sort": 1},
    {"id": "warm", "name": "Warm", "icon": "⏳", "description": "Interested but not urgent", "sort": 2},
    {"id": "cold", "name": "Cold", "icon": "💤", "description": "Gone quiet", "sort": 3},
    {"id": "closed", "name": "Closed", "icon": "✔️", "description": "Deal done", "sort": 4},
]

LABEL_IDS: set[str] = {lab["id"] for lab in LABELS}


# ── Property types ───────────────────────────────────────────
# `match_group` is what the engine compares — two records only match when their
# groups are equal, so a villa never matches an apartment. `legacy` types are
# hidden from new-entry forms but kept so existing records still display and
# still match within their own group.
PROPERTY_TYPES: list[dict] = [
    {"id": "villa_primary", "label": "Villa · Primary Sale", "short": "Villa Primary", "divisions": ["sales"], "match_group": "villa_primary"},
    {"id": "apt_primary", "label": "Apartment · Primary Sale", "short": "Apt. Primary", "divisions": ["sales"], "match_group": "apt_primary"},
    {"id": "villa_resale", "label": "Villa · Resale", "short": "Villa Resale", "divisions": ["sales"], "match_group": "villa_resale"},
    {"id": "apt_resale", "label": "Apartment · Resale", "short": "Apt. Resale", "divisions": ["sales"], "match_group": "apt_resale"},
    {"id": "com_primary", "label": "Commercial · Primary Sale", "short": "Com. Primary", "divisions": ["sales"], "match_group": "com_primary"},
    {"id": "com_resale", "label": "Commercial · Resale", "short": "Com. Resale", "divisions": ["sales"], "match_group": "com_resale"},
    {"id": "land_res", "label": "Land · Residential", "short": "Land · Res", "divisions": ["sales"], "match_group": "land_res"},
    {"id": "land_com", "label": "Land · Commercial", "short": "Land · Com", "divisions": ["sales"], "match_group": "land_com"},
    {"id": "agri", "label": "Agricultural Land", "short": "Agri. Land", "divisions": ["sales"], "match_group": "agri"},
    {"id": "rent_res", "label": "Residential Rental", "short": "Res. Rental", "divisions": ["rentals"], "match_group": "rent_res"},
    {"id": "rent_com", "label": "Commercial Rental", "short": "Com. Rental", "divisions": ["rentals"], "match_group": "rent_com"},
    # Legacy — hidden from new-entry forms, kept so imported records still work.
    {"id": "res_primary", "label": "Residential · Primary Sale", "short": "Res. Primary", "divisions": ["sales"], "match_group": "res_primary", "legacy": True},
    {"id": "res_resale", "label": "Residential · Resale", "short": "Res. Resale", "divisions": ["sales"], "match_group": "res_resale", "legacy": True},
]

PROPERTY_TYPE_IDS: set[str] = {p["id"] for p in PROPERTY_TYPES}

# id -> match group. Mirrors DealKnot's TYPE_MATCH_GROUPS, including its two
# aliases that fold bare "res"/"com" records into their resale groups.
TYPE_MATCH_GROUPS: dict[str, str] = {p["id"]: p["match_group"] for p in PROPERTY_TYPES}
TYPE_MATCH_GROUPS["res"] = "res_resale"
TYPE_MATCH_GROUPS["com"] = "com_resale"


def type_group(property_type: str | None) -> str:
    """Return the match group for a property type (unknown types match only themselves)."""
    return TYPE_MATCH_GROUPS.get(property_type or "", property_type or "")


def property_types_for(division: str) -> list[dict]:
    """Selectable (non-legacy) property types for a division."""
    return [
        p for p in PROPERTY_TYPES
        if division in p["divisions"] and not p.get("legacy")
    ]


# ── Enquiry pipeline / commission vocabularies ───────────────
# Commission sources — constrained so the commissions summary can group on them.
COMMISSION_SOURCES: list[dict] = [
    {"id": "buyer_side", "label": "Buyer Side"},
    {"id": "seller_side", "label": "Seller Side"},
    {"id": "both_sides", "label": "Both Sides"},
    {"id": "referral", "label": "Referral"},
    {"id": "other", "label": "Other"},
]

COMMISSION_SOURCE_IDS: set[str] = {s["id"] for s in COMMISSION_SOURCES}

# DealKnot's VALID_STATUSES, preserved verbatim (capitalised).
COMMISSION_STATUSES: list[str] = ["Pending", "Partial", "Received"]

LISTING_STATUSES: list[dict] = [
    {"id": "available", "label": "Available"},
    {"id": "under_offer", "label": "Under Offer"},
    {"id": "sold", "label": "Sold"},
    {"id": "withdrawn", "label": "Withdrawn"},
]

LISTING_STATUS_IDS: set[str] = {s["id"] for s in LISTING_STATUSES}

RENTAL_PERIODS: set[str] = {"monthly", "yearly"}
