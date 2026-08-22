import * as XLSX from "xlsx";
import { COUNTRIES, CURRENCIES, PROPERTY_TYPES, LABELS, ptLabel } from "./constants";

// ── colours ──────────────────────────────────────────────────────────────────
const NAVY  = "050E1E";
const GOLD  = "D4A84A";
const WHITE = "FFFFFF";
const GREY  = "F2F4F7";

function cell(v, bold = false, bg = null, color = null, hAlign = "left", wrapText = false) {
  const c = { v, t: typeof v === "number" ? "n" : "s" };
  const font = { name: "Plus Jakarta Sans", sz: 10, bold, color: color ? { rgb: color } : undefined };
  const fill = bg ? { patternType: "solid", fgColor: { rgb: bg } } : undefined;
  const alignment = { horizontal: hAlign, vertical: "center", wrapText };
  c.s = { font, fill, alignment, border: { bottom: { style: "thin", color: { rgb: "E2E7EF" } } } };
  return c;
}

function numCell(v, bg = null) {
  const c = { v: Number(v) || 0, t: "n" };
  const fill = bg ? { patternType: "solid", fgColor: { rgb: bg } } : undefined;
  c.s = { font: { name: "Plus Jakarta Sans", sz: 10 }, fill, alignment: { horizontal: "right", vertical: "center" } };
  return c;
}

export function exportExcel(rows, kind, division, divLabel, roleName) {
  const isBuyer = kind === "buyer";
  const wb = XLSX.utils.book_new();
  const ws = {};

  const COLS = ["#", "Name", "Phone", "Country", "Area", "Property Type",
    isBuyer ? "Min Budget" : "Asking Price",
    isBuyer ? "Max Budget" : "",
    "Currency", "Status", "International", "Notes", "Date Added"].filter((c) => c !== "");

  const colWidths = [4, 22, 16, 18, 20, 20, 14, ...(isBuyer ? [14] : []), 10, 10, 12, 30, 14];

  // Row 1 — branding banner (merged)
  const totalCols = COLS.length;
  const brandText = `DealKnot — ${divLabel} · ${roleName}s`;
  ws["A1"] = {
    v: brandText, t: "s",
    s: {
      font: { name: "Fraunces", sz: 14, bold: true, color: { rgb: GOLD } },
      fill: { patternType: "solid", fgColor: { rgb: NAVY } },
      alignment: { horizontal: "center", vertical: "center" },
    },
  };
  // Blank cells for merge range
  for (let i = 1; i < totalCols; i++) {
    const addr = XLSX.utils.encode_cell({ r: 0, c: i });
    ws[addr] = { v: "", t: "s", s: { fill: { patternType: "solid", fgColor: { rgb: NAVY } } } };
  }

  // Row 2 — column headers
  COLS.forEach((h, ci) => {
    const addr = XLSX.utils.encode_cell({ r: 1, c: ci });
    ws[addr] = cell(h, true, NAVY, GOLD, ci === 0 ? "center" : "left");
  });

  // Data rows
  rows.forEach((p, idx) => {
    const r = idx + 2; // row index (0-based), rows 0=brand, 1=header, 2+=data
    const bg = idx % 2 === 0 ? WHITE : GREY;
    const country = COUNTRIES.find((c) => c.code === p.country);
    const phone = (p.dial || "") + (p.phone || "");
    const dateStr = p.createdAt ? new Date(p.createdAt).toLocaleDateString("en-GB") : "";

    const values = [
      idx + 1,
      p.name,
      phone,
      country?.name || p.country || "",
      p.area || "",
      ptLabel(p.type),
      ...(isBuyer ? [p.min ?? 0, p.max ?? 0] : [p.price ?? 0]),
      p.cur || "",
      p.label || "active",
      p.intl ? "Yes" : "No",
      p.notes || "",
      dateStr,
    ];

    values.forEach((v, ci) => {
      const addr = XLSX.utils.encode_cell({ r, c: ci });
      if (ci === 0) {
        ws[addr] = numCell(v, bg);
      } else if (typeof v === "number") {
        ws[addr] = numCell(v, bg);
      } else {
        ws[addr] = cell(String(v ?? ""), false, bg, null, ci === 0 ? "center" : "left");
      }
    });
  });

  // Summary row
  const sumR = rows.length + 2;
  const sumText = `Total: ${rows.length} ${roleName.toLowerCase()}${rows.length !== 1 ? "s" : ""}`;
  ws[XLSX.utils.encode_cell({ r: sumR, c: 0 })] = cell(sumText, true, NAVY, GOLD, "left");
  for (let ci = 1; ci < totalCols; ci++) {
    ws[XLSX.utils.encode_cell({ r: sumR, c: ci })] = {
      v: "", t: "s",
      s: { fill: { patternType: "solid", fgColor: { rgb: NAVY } } },
    };
  }

  // Worksheet range
  ws["!ref"] = XLSX.utils.encode_range({ r: 0, c: 0 }, { r: sumR, c: totalCols - 1 });

  // Merge branding row and summary row across all columns
  ws["!merges"] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: totalCols - 1 } },
    { s: { r: sumR, c: 0 }, e: { r: sumR, c: totalCols - 1 } },
  ];

  // Column widths
  ws["!cols"] = colWidths.map((w) => ({ wch: w }));

  // Row heights
  ws["!rows"] = [{ hpt: 28 }, { hpt: 20 }, ...rows.map(() => ({ hpt: 18 })), { hpt: 20 }];

  const filename = `DealKnot-${divLabel}-${roleName}s.xlsx`;
  XLSX.utils.book_append_sheet(wb, ws, `${divLabel} ${roleName}s`);
  XLSX.writeFile(wb, filename);
}

// ── Import helpers ────────────────────────────────────────────────────────────

const FIELD_ALIASES = {
  name:    ["name", "full name", "contact name", "client name", "broker name", "customer"],
  phone:   ["phone", "mobile", "contact", "telephone", "cell", "number", "phone number", "mobile number"],
  area:    ["area", "location", "city", "neighbourhood", "neighborhood", "locality", "zone", "region", "place"],
  country: ["country", "nation", "market"],
  type:    ["type", "property type", "prop type", "property", "category"],
  min:     ["min", "minimum", "min budget", "budget min", "min price", "from", "rent from", "min rent"],
  max:     ["max", "maximum", "max budget", "budget max", "max price", "to", "rent to", "max rent", "budget"],
  price:   ["price", "asking", "asking price", "amount", "value", "list price", "rent", "rental", "asking rent"],
  cur:     ["currency", "cur", "ccy"],
  notes:   ["notes", "comments", "remarks", "description", "additional info", "info", "memo"],
  label:   ["status", "label", "lead status", "lead", "stage"],
  intl:    ["international", "intl", "cross border", "overseas", "foreign"],
};

function normaliseKey(h) {
  return h.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
}

export function detectColumnMapping(headers) {
  const mapping = {};
  headers.forEach((h, i) => {
    const norm = normaliseKey(h);
    for (const [field, aliases] of Object.entries(FIELD_ALIASES)) {
      if (aliases.includes(norm) && !mapping[field]) {
        mapping[field] = i;
        break;
      }
    }
  });
  return mapping;
}

function resolveCountry(val) {
  if (!val) return null;
  const v = String(val).trim().toLowerCase();
  return COUNTRIES.find(
    (c) => c.name.toLowerCase() === v || c.code.toLowerCase() === v || c.flag === val.trim()
  ) || null;
}

// Legacy label aliases for backwards-compatible Excel import
const TYPE_ALIASES = {
  "villa primary":        "villa_primary",
  "villa · primary sale": "villa_primary",
  "villa primary sale":   "villa_primary",
  "apartment primary":    "apt_primary",
  "apt primary":          "apt_primary",
  "apartment · primary sale": "apt_primary",
  "villa resale":         "villa_resale",
  "villa · resale":       "villa_resale",
  "apartment resale":     "apt_resale",
  "apt resale":           "apt_resale",
  "apartment · resale":   "apt_resale",
  "residential":          "apt_resale",
  "res":                  "apt_resale",
  "res.":                 "apt_resale",
  "res_primary":          "villa_primary",
  "res_resale":           "apt_resale",
  "commercial":           "com_resale",
  "com":                  "com_resale",
  "comm.":                "com_resale",
  "agricultural":         "agri",
  "agri.":                "agri",
  "residential rental":   "rent_res",
  "res. rent":            "rent_res",
  "commercial rental":    "rent_com",
  "com. rent":            "rent_com",
};

function resolveType(val, division) {
  if (!val) return null;
  const v = String(val).trim().toLowerCase();
  // Check legacy aliases first
  const aliasId = TYPE_ALIASES[v];
  if (aliasId) {
    const found = PROPERTY_TYPES.find((t) => t.id === aliasId && t.divisions.includes(division));
    if (found) return found;
  }
  // Then match by id, label, or short against current types
  return PROPERTY_TYPES.find(
    (t) =>
      t.divisions.includes(division) &&
      (t.label.toLowerCase() === v || t.short.toLowerCase() === v || t.id === v || v.includes(t.id))
  ) || null;
}

function resolveLabel(val) {
  if (!val) return "active";
  const v = String(val).trim().toLowerCase();
  return LABELS.find((l) => l.id === v || l.name.toLowerCase() === v)?.id || "active";
}

export function parseRows(sheetRows, headers, mapping, kind, division, defaultCur = "AED") {
  const isBuyer = kind === "buyer";
  const results = [];

  sheetRows.forEach((row, idx) => {
    const get = (field) => {
      const ci = mapping[field];
      if (ci == null) return "";
      const v = row[ci];
      return v != null ? String(v).trim() : "";
    };

    const rawName  = get("name");
    const rawPhone = get("phone").replace(/\D/g, "").slice(0, 14);
    const rawArea  = get("area");

    const errors = [];
    if (!rawName)          errors.push("Missing name");
    if (rawPhone.length < 6) errors.push("Invalid phone (< 6 digits)");
    if (!rawArea)          errors.push("Missing area");

    // Country
    const countryObj = resolveCountry(get("country")) || COUNTRIES[0];
    const cur = (get("cur") && Object.keys(CURRENCIES).includes(get("cur").toUpperCase()))
      ? get("cur").toUpperCase()
      : countryObj.cur || defaultCur;

    // Property type
    const typeObj = resolveType(get("type"), division);
    if (!typeObj) errors.push("Unknown property type — will need manual fix");

    // Budget / price
    let min = 0, max = 0, price = 0;
    if (isBuyer) {
      min = Number(get("min").replace(/[^0-9.]/g, "")) || 0;
      max = Number(get("max").replace(/[^0-9.]/g, "")) || Number(get("price").replace(/[^0-9.]/g, "")) || 0;
      if (!min && !max) errors.push("Missing budget (min/max)");
      else if (max < min && max > 0) { const t = min; min = max; max = t; }
    } else {
      price = Number(get("price").replace(/[^0-9.]/g, "")) || Number(get("max").replace(/[^0-9.]/g, "")) || 0;
      if (!price) errors.push("Missing asking price");
    }

    const rec = {
      _row: idx + 1,
      _errors: errors,
      _valid: errors.filter((e) => !e.includes("manual")).length === 0,
      name:     rawName,
      phone:    rawPhone,
      dial:     countryObj.dial,
      country:  countryObj.code,
      area:     rawArea,
      type:     typeObj?.id || "",
      cur,
      intl:     ["yes","true","1","x"].includes(get("intl").toLowerCase()),
      notes:    get("notes"),
      label:    resolveLabel(get("label")),
      division,
      period:   "monthly",
      ...(isBuyer ? { min, max } : { price }),
    };
    results.push(rec);
  });

  return results;
}

export async function readExcelFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, { type: "array" });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
        resolve(rows);
      } catch (err) {
        reject(new Error("Could not read file. Make sure it's a valid .xlsx or .csv file."));
      }
    };
    reader.onerror = () => reject(new Error("File read failed."));
    reader.readAsArrayBuffer(file);
  });
}
