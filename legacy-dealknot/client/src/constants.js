export const COUNTRIES = [
  { code: "AE", name: "United Arab Emirates", flag: "🇦🇪", dial: "+971", cur: "AED" },
  { code: "GB", name: "United Kingdom",       flag: "🇬🇧", dial: "+44",  cur: "GBP" },
  { code: "SG", name: "Singapore",            flag: "🇸🇬", dial: "+65",  cur: "SGD" },
  { code: "IN", name: "India",                flag: "🇮🇳", dial: "+91",  cur: "INR" },
  { code: "US", name: "United States",        flag: "🇺🇸", dial: "+1",   cur: "USD" },
  { code: "HK", name: "Hong Kong",            flag: "🇭🇰", dial: "+852", cur: "HKD" },
  { code: "AU", name: "Australia",            flag: "🇦🇺", dial: "+61",  cur: "AUD" },
  { code: "CA", name: "Canada",               flag: "🇨🇦", dial: "+1",   cur: "CAD" },
  { code: "FR", name: "France",               flag: "🇫🇷", dial: "+33",  cur: "EUR" },
  { code: "DE", name: "Germany",              flag: "🇩🇪", dial: "+49",  cur: "EUR" },
];

// Sales: Buyer wants to purchase, Seller wants to sell
// Rentals: Tenant wants to rent, Landlord wants to rent out
export const DIVISIONS = [
  { id: "sales",   label: "Sales",   buyerRole: "Buyer",  sellerRole: "Seller"   },
  { id: "rentals", label: "Rentals", buyerRole: "Tenant", sellerRole: "Landlord" },
];

export const divisionMeta = (id) => DIVISIONS.find((d) => d.id === id) || DIVISIONS[0];
export const buyerRole  = (division) => divisionMeta(division).buyerRole;
export const sellerRole = (division) => divisionMeta(division).sellerRole;

// Lead status labels — visible on every card and filterable
export const LABELS = [
  { id: "hot",    name: "Hot",    icon: "🔥", short: "Hot",    desc: "Serious, ready to close fast", sort: 0 },
  { id: "active", name: "Active", icon: "✅", short: "Active", desc: "Currently looking",            sort: 1 },
  { id: "warm",   name: "Warm",   icon: "⏳", short: "Warm",   desc: "Interested but not urgent",    sort: 2 },
  { id: "cold",   name: "Cold",   icon: "💤", short: "Cold",   desc: "Gone quiet",                   sort: 3 },
  { id: "closed", name: "Closed", icon: "✔️", short: "Closed", desc: "Deal done",                    sort: 4 },
];

export const labelMeta = (id) => LABELS.find((l) => l.id === id) || LABELS[1];
export const labelSort = (id) => labelMeta(id).sort;

export const PROPERTY_TYPES = [
  { id: "villa_primary", label: "Villa · Primary Sale",        short: "Villa Primary", divisions: ["sales"], matchGroup: "villa_primary" },
  { id: "apt_primary",   label: "Apartment · Primary Sale",    short: "Apt. Primary",  divisions: ["sales"], matchGroup: "apt_primary"   },
  { id: "villa_resale",  label: "Villa · Resale",              short: "Villa Resale",  divisions: ["sales"], matchGroup: "villa_resale"  },
  { id: "apt_resale",    label: "Apartment · Resale",          short: "Apt. Resale",   divisions: ["sales"], matchGroup: "apt_resale"    },
  { id: "com_primary",   label: "Commercial · Primary Sale",   short: "Com. Primary",  divisions: ["sales"], matchGroup: "com_primary"   },
  { id: "com_resale",    label: "Commercial · Resale",         short: "Com. Resale",   divisions: ["sales"], matchGroup: "com_resale"    },
  { id: "land_res",      label: "Land · Residential",          short: "Land · Res",    divisions: ["sales"], matchGroup: "land_res"      },
  { id: "land_com",      label: "Land · Commercial",           short: "Land · Com",    divisions: ["sales"], matchGroup: "land_com"      },
  { id: "agri",          label: "Agricultural Land",           short: "Agri. Land",    divisions: ["sales"], matchGroup: "agri"          },
  // Legacy — kept so existing records display correctly; hidden from new-entry forms via isLegacy flag
  { id: "res_primary", label: "Residential · Primary Sale", short: "Res. Primary", divisions: ["sales"], matchGroup: "res_primary", isLegacy: true },
  { id: "res_resale",  label: "Residential · Resale",       short: "Res. Resale",  divisions: ["sales"], matchGroup: "res_resale",  isLegacy: true },
  { id: "rent_res",    label: "Residential Rental",         short: "Res. Rental",  divisions: ["rentals"], matchGroup: "rent_res"  },
  { id: "rent_com",    label: "Commercial Rental",          short: "Com. Rental",  divisions: ["rentals"], matchGroup: "rent_com"  },
];

export const propertyTypesFor = (division) =>
  PROPERTY_TYPES.filter((t) => t.divisions.includes(division) && !t.isLegacy);

export const CURRENCIES = {
  AED: { sym: "AED", flag: "🇦🇪" },
  GBP: { sym: "£",   flag: "🇬🇧" },
  SGD: { sym: "S$",  flag: "🇸🇬" },
  INR: { sym: "₹",   flag: "🇮🇳" },
  USD: { sym: "$",   flag: "🇺🇸" },
  HKD: { sym: "HK$", flag: "🇭🇰" },
  AUD: { sym: "A$",  flag: "🇦🇺" },
  CAD: { sym: "C$",  flag: "🇨🇦" },
  EUR: { sym: "€",   flag: "🇪🇺" },
};

// Approximate rates relative to USD (update periodically)
export const FX_TO_USD = {
  AED: 0.272, GBP: 1.27, SGD: 0.74, INR: 0.012,
  USD: 1, HKD: 0.128, AUD: 0.65, CAD: 0.73, EUR: 1.08,
};

export const convertAmount = (amount, fromCur, toCur) => {
  if (!amount || fromCur === toCur) return amount;
  const usd = (amount || 0) * (FX_TO_USD[fromCur] || 1);
  return Math.round(usd / (FX_TO_USD[toCur] || 1));
};

export const ptLabel = (id) => PROPERTY_TYPES.find((p) => p.id === id)?.label || id;
export const ptShort = (id) => PROPERTY_TYPES.find((p) => p.id === id)?.short || id;

export const formatMoney = (n, cur = "USD") => {
  if (n == null || isNaN(n)) return "–";
  const c = CURRENCIES[cur] || CURRENCIES.USD;
  let scaled = n, suffix = "";
  if (cur === "INR" && n >= 10000000) { scaled = n / 10000000; suffix = " Cr"; }
  else if (cur === "INR" && n >= 100000) { scaled = n / 100000; suffix = " L"; }
  else if (n >= 1000000) { scaled = n / 1000000; suffix = "M"; }
  else if (n >= 1000) { scaled = n / 1000; suffix = "K"; }
  const num = scaled >= 100 ? Math.round(scaled).toString()
    : scaled.toFixed(scaled === Math.floor(scaled) ? 0 : 1);
  return `${c.sym} ${num}${suffix}`;
};

export const formatRange = (a, b, cur) =>
  `${formatMoney(a, cur)} – ${formatMoney(b, cur)}`;

// Display helpers — INR records are never converted out (shown in INR always).
// Non-INR records can be converted to any display currency including INR.
export const displayMoney = (amount, nativeCur, displayCur) => {
  if (!displayCur || displayCur === nativeCur) return formatMoney(amount, nativeCur);
  if (nativeCur === "INR") return formatMoney(amount, nativeCur);
  return formatMoney(convertAmount(amount, nativeCur, displayCur), displayCur);
};

export const displayRange = (a, b, nativeCur, displayCur) =>
  `${displayMoney(a, nativeCur, displayCur)} – ${displayMoney(b, nativeCur, displayCur)}`;

// Rental period helpers — convert between monthly and yearly so a broker viewing
// in monthly mode sees a yearly-listed amount converted to its monthly equivalent.
export const toMonthly = (amount, period) =>
  period === "yearly" ? Math.round(Number(amount) / 12) : Number(amount);

export const toYearly = (amount, period) =>
  period === "monthly" ? Math.round(Number(amount) * 12) : Number(amount);

export const toViewPeriod = (amount, nativePeriod, viewPeriod) => {
  if (!nativePeriod || !viewPeriod || nativePeriod === viewPeriod) return Number(amount);
  return viewPeriod === "monthly" ? toMonthly(amount, nativePeriod) : toYearly(amount, nativePeriod);
};

export const periodSuffix = (period) => period === "yearly" ? "/yr" : "/mo";

export const displayRental = (amount, nativeCur, nativePeriod, displayCur, viewPeriod) => {
  const base = toViewPeriod(amount, nativePeriod, viewPeriod);
  return `${displayMoney(base, nativeCur, displayCur)}${periodSuffix(viewPeriod)}`;
};

export const displayRentalRange = (a, b, nativeCur, nativePeriod, displayCur, viewPeriod) =>
  `${displayRental(a, nativeCur, nativePeriod, displayCur, viewPeriod).replace(periodSuffix(viewPeriod), "")} – ${displayRental(b, nativeCur, nativePeriod, displayCur, viewPeriod)}`;

export const initials = (n) =>
  (n || "").split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

export const formatPhone = (p) =>
  p ? p.replace(/(\d{4,5})(\d{4,5})/, "$1 $2") : "";
