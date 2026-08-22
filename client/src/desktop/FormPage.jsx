import { useState, useEffect } from "react";
import { I } from "../icons";
import {
  COUNTRIES, CURRENCIES, formatMoney,
  DIVISIONS, divisionMeta, propertyTypesFor, LABELS,
} from "../constants";
import PlacesAutocomplete from "../PlacesAutocomplete";
import NameAutocomplete from "../NameAutocomplete";
import ImportModal from "../ImportModal";

export default function FormPage({ kind, division: forcedDivision, onSubmit, onBulkImport, onCancel, initialData, onCurrencyChange, displayCur }) {
  const isBuyer = kind === "buyer";
  const [showImport, setShowImport] = useState(false);
  const [form, setForm] = useState(() => {
    const div = initialData?.division || forcedDivision || "sales";
    if (initialData) {
      return {
        name: initialData.name || "",
        phone: initialData.phone || "",
        country: initialData.country || "AE",
        cur: initialData.cur || "AED",
        area: initialData.area || "",
        type: initialData.type || "",
        intl: initialData.intl || false,
        min: initialData.min != null ? String(initialData.min) : "",
        max: initialData.max != null ? String(initialData.max) : "",
        price: initialData.price != null ? String(initialData.price) : "",
        notes: initialData.notes || "",
        division: div,
        period: initialData.period || "monthly",
        label: initialData.label || "active",
        radiusKm: initialData.radiusKm != null ? String(initialData.radiusKm) : "5",
        referredBy: initialData.referredBy || "",
      };
    }
    const defaultCur = displayCur || "AED";
    const defaultCountry = COUNTRIES.find((c) => c.cur === defaultCur)?.code || "AE";
    return {
      name: "", phone: "", country: defaultCountry, cur: defaultCur,
      area: "", type: "", intl: false,
      min: "", max: "", price: "", notes: "",
      division: div,
      period: "monthly",
      label: "active",
      radiusKm: "5",
      referredBy: "",
    };
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Keep form currency in sync when the global selector changes (new forms only)
  useEffect(() => {
    if (initialData || !displayCur) return;
    const defaultCountry = COUNTRIES.find((c) => c.cur === displayCur)?.code;
    setForm((f) => ({
      ...f,
      cur: displayCur,
      ...(defaultCountry ? { country: defaultCountry } : {}),
    }));
  }, [displayCur]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prevent Backspace from triggering browser back navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Backspace" && e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA") {
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const dial = COUNTRIES.find((c) => c.code === form.country)?.dial || "+1";

  const meta = divisionMeta(form.division);
  const roleName = isBuyer ? meta.buyerRole : meta.sellerRole;
  const isRental = form.division === "rentals";
  const types = propertyTypesFor(form.division);

  const valid = form.name.trim() && form.phone.length >= 6 && form.area && form.type &&
    (isBuyer ? (form.min && form.max && Number(form.max) >= Number(form.min)) : form.price);

  const handleSubmit = async () => {
    if (!valid) return;
    setBusy(true); setErr("");
    const base = {
      name: form.name.trim(), phone: form.phone, dial,
      country: form.country, area: form.area, type: form.type,
      cur: form.cur, intl: form.intl, notes: form.notes.trim(),
      division: form.division,
      period: isRental ? form.period : "monthly",
      label: form.label,
      referredBy: form.referredBy.trim(),
    };
    const rec = isBuyer
      ? { ...base, min: Number(form.min), max: Number(form.max), radiusKm: Math.max(1, Math.min(50, Number(form.radiusKm) || 5)) }
      : { ...base, price: Number(form.price) };
    try {
      await onSubmit(rec);
    } catch (e) {
      setErr(e.message || "Failed to save.");
      setBusy(false);
    }
  };

  return (
    <>
    {showImport && (
      <ImportModal
        kind={kind}
        division={forcedDivision || form.division}
        onClose={() => setShowImport(false)}
        onBulkImport={onBulkImport}
      />
    )}
    <div className="main fade-in">
      <div className="page-head">
        <div>
          <div className="pre">// {initialData ? "edit" : "new"} {roleName.toLowerCase()} brief</div>
          <h1>{initialData ? "Edit" : "Add"} <em>{roleName.toLowerCase()}</em>.</h1>
          <div className="sub">{isBuyer
            ? (isRental ? "Capture what they want to rent." : "Capture what they're looking to buy.")
            : (isRental ? "List the rental property." : "List the property for sale.")}</div>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={onCancel}><I.back /> Back</button>
          <button className="btn primary" disabled={!valid || busy} onClick={handleSubmit}>
            <I.check /> {busy ? "Saving…" : initialData ? `Update ${roleName.toLowerCase()}` : `Save ${roleName.toLowerCase()}`}
          </button>
        </div>
      </div>

      <div className="form-card">
        {err && <div className="form-err">{err}</div>}

        {!initialData && (
          <button
            type="button"
            onClick={() => setShowImport(true)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
              width: "100%", padding: "14px 20px", marginBottom: 24,
              background: "transparent",
              border: "2px solid var(--gold-500)",
              borderRadius: 12, cursor: "pointer",
              fontFamily: "inherit", fontSize: 14, fontWeight: 700,
              color: "var(--gold-700)",
              transition: "all .18s",
            }}
            onMouseOver={(e) => { e.currentTarget.style.background = "rgba(212,168,74,0.08)"; }}
            onMouseOut={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <I.upload width="16" height="16" />
            📥 Already have a list? Import from Excel
          </button>
        )}

        {!forcedDivision && (
          <div className="field">
            <label>Division<span className="req">*</span></label>
            <div className="chip-group">
              {DIVISIONS.map((d) => (
                <button key={d.id} type="button" className={`chip ${form.division === d.id ? "on" : ""}`}
                  onClick={() => setForm((f) => ({
                    ...f, division: d.id,
                    type: propertyTypesFor(d.id).some((t) => t.id === f.type) ? f.type : "",
                  }))}>{d.label}</button>
              ))}
            </div>
          </div>
        )}

        <div className="field">
          <label>Full name<span className="req">*</span></label>
          <NameAutocomplete
            value={form.name}
            onChange={(v) => update("name", v)}
            onSelect={(c) => { update("name", c.name); update("phone", c.phone); }}
            placeholder={isBuyer ? "e.g. Olivia Chen" : "e.g. Marina Heights LLC"}
          />
        </div>

        <div className="field-row">
          <div className="field">
            <label>Country<span className="req">*</span></label>
            <select value={form.country} onChange={(e) => {
              const c = COUNTRIES.find((x) => x.code === e.target.value);
              const newCur = c?.cur || form.cur;
              setForm((f) => ({ ...f, country: e.target.value, cur: newCur, area: "" }));
              onCurrencyChange?.(newCur);
            }}>
              {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.flag} {c.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Currency<span className="req">*</span></label>
            <select value={form.cur} onChange={(e) => update("cur", e.target.value)}>
              {Object.keys(CURRENCIES).map((k) => <option key={k}>{k}</option>)}
            </select>
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label>Phone number<span className="req">*</span></label>
            <div className="phone-input">
              <div className="pre">{dial}</div>
              <input value={form.phone} onChange={(e) => update("phone", e.target.value.replace(/\D/g, ""))} placeholder="00 000 0000" />
            </div>
          </div>
          <div className="field">
            <label>City / Area / Neighbourhood<span className="req">*</span></label>
            <PlacesAutocomplete value={form.area} onChange={(v) => update("area", v)}
              placeholder="Anna Nagar, Mogappair, Kilpauk (comma-separated for radius matching)" />
          </div>
        </div>

        {isBuyer && (
          <div className="field" style={{ maxWidth: 240 }}>
            <label>Search radius (km)</label>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <input type="number" min="1" max="50" value={form.radiusKm}
                onChange={(e) => update("radiusKm", e.target.value)} style={{ maxWidth: 100 }} />
              <span style={{ fontSize: 12, color: "var(--ink-500)" }}>Match sellers within this distance. Default 5km.</span>
            </div>
          </div>
        )}

        <div className="field">
          <label>Property type<span className="req">*</span></label>
          <div className="chip-group">
            {types.map((t) => (
              <button key={t.id} type="button" className={`chip ${form.type === t.id ? "on" : ""}`}
                onClick={() => update("type", t.id)}>{t.label}</button>
            ))}
          </div>
        </div>

        {isRental && (
          <div className="field">
            <label>Listed as<span className="req">*</span></label>
            <div className="chip-group">
              <button type="button" className={`chip ${form.period === "monthly" ? "on" : ""}`}
                onClick={() => update("period", "monthly")}>Monthly</button>
              <button type="button" className={`chip ${form.period === "yearly" ? "on" : ""}`}
                onClick={() => update("period", "yearly")}>Yearly</button>
            </div>
          </div>
        )}

        {isBuyer ? (
          <div className="field-row">
            <div className="field">
              <label>Min {isRental ? `rent (${form.period})` : "budget"}<span className="req">*</span></label>
              <div className="rupee" data-cur={CURRENCIES[form.cur]?.sym}>
                <input type="number" value={form.min} onChange={(e) => update("min", e.target.value)} placeholder="0" />
              </div>
              {form.min && <div className="hint">{formatMoney(Number(form.min), form.cur)}{isRental ? form.period === "yearly" ? " / yr" : " / mo" : ""}</div>}
            </div>
            <div className="field">
              <label>Max {isRental ? `rent (${form.period})` : "budget"}<span className="req">*</span></label>
              <div className="rupee" data-cur={CURRENCIES[form.cur]?.sym}>
                <input type="number" value={form.max} onChange={(e) => update("max", e.target.value)} placeholder="0" />
              </div>
              {form.max && <div className="hint">{formatMoney(Number(form.max), form.cur)}{isRental ? form.period === "yearly" ? " / yr" : " / mo" : ""}</div>}
            </div>
          </div>
        ) : (
          <div className="field">
            <label>{isRental ? `Asking rent (${form.period})` : "Asking price"}<span className="req">*</span></label>
            <div className="rupee" data-cur={CURRENCIES[form.cur]?.sym}>
              <input type="number" value={form.price} onChange={(e) => update("price", e.target.value)} placeholder="0" />
            </div>
            {form.price && <div className="hint">{formatMoney(Number(form.price), form.cur)}{isRental ? form.period === "yearly" ? " / yr" : " / mo" : ""}</div>}
          </div>
        )}

        <div className="field">
          <label>Lead status</label>
          <div className="chip-group">
            {LABELS.map((l) => (
              <button key={l.id} type="button" className={`chip label-chip label-${l.id} ${form.label === l.id ? "on" : ""}`}
                onClick={() => update("label", l.id)}>
                <span aria-hidden>{l.icon}</span> {l.name}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label className="toggle-row">
            <input type="checkbox" checked={form.intl} onChange={(e) => update("intl", e.target.checked)} />
            <span>Mark as <b>international</b> {roleName.toLowerCase()} (cross-border)</span>
          </label>
        </div>

        <div className="field">
          <label>Referred by</label>
          <input value={form.referredBy} onChange={(e) => update("referredBy", e.target.value)}
            placeholder="e.g. Priya Kalyan, Walk-in, Instagram, Cold call…" />
        </div>

        <div className="field">
          <label>Notes</label>
          <textarea value={form.notes} onChange={(e) => update("notes", e.target.value)}
            placeholder={isBuyer ? "Must-haves, timeline, source of funds…" : "Floor, sqft, age, parking, view…"} />
        </div>
      </div>
    </div>
    </>
  );
}
