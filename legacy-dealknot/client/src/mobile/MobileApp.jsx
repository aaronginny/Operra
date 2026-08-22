import { useState, useEffect, useRef } from "react";
import { I } from "../icons";
import InstallGuide from "../InstallGuide";
import ImportModal from "../ImportModal";
import CommissionPage from "../desktop/CommissionPage";
import AnalyticsPage from "../desktop/AnalyticsPage";
import {
  COUNTRIES, CURRENCIES, ptLabel, ptShort,
  formatMoney, displayMoney, displayRange,
  displayRental, displayRentalRange,
  initials, formatPhone,
  DIVISIONS, divisionMeta, propertyTypesFor,
  LABELS, labelSort,
} from "../constants";
import PlacesAutocomplete from "../PlacesAutocomplete";
import NameAutocomplete from "../NameAutocomplete";
import LabelBadge from "../LabelBadge";
import ClientNotes from "../ClientNotes";
import { motion } from "framer-motion";
import { listContainer, listItem, tapBounce } from "../motion";

/* ── Top bar ── */
function MTopBar({ subtitle, currency, onCurrency, viewPeriod, onViewPeriod, showPeriodToggle, darkMode, toggleDarkMode }) {
  const cur = CURRENCIES[currency] || CURRENCIES.USD;
  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">D</div>
        <div>
          <div className="brand-name">Deal<em>Knot</em></div>
          <div className="brand-sub">{subtitle || "Where deals get tied"}</div>
        </div>
      </div>
      <div className="top-actions">
        {showPeriodToggle && (
          <div className="period-toggle mobile" title="Rental view">
            <button className={viewPeriod === "monthly" ? "on" : ""} onClick={() => onViewPeriod("monthly")}>M</button>
            <button className={viewPeriod === "yearly" ? "on" : ""} onClick={() => onViewPeriod("yearly")}>Y</button>
          </div>
        )}
        {onCurrency && (
          <div className="cur-pill" title="Display currency">
            <span className="flag">{cur.flag}</span>
            <select value={currency} onChange={(e) => onCurrency(e.target.value)}>
              {Object.keys(CURRENCIES).map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
        )}
        {toggleDarkMode && (
          <button className="icon-btn" title={darkMode ? "Light mode" : "Dark mode"} onClick={toggleDarkMode} style={{ width: 36, height: 36, borderRadius: 10 }}>
            {darkMode ? <I.sun width="18" height="18" /> : <I.moon width="18" height="18" />}
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Bottom nav ── */
function BottomNav({ tab, go, openAdd }) {
  const Item = ({ id, label, icon }) => (
    <motion.button className={`nav-item ${tab === id ? "active" : ""}`} onClick={() => go(id)}
      whileTap={tapBounce}>
      {icon}<span>{label}</span>
    </motion.button>
  );
  return (
    <nav className="bottom-nav">
      <Item id="dashboard" label="Home"     icon={<I.home />} />
      <Item id="sales"     label="Sales"    icon={<I.tag />} />
      <motion.button className="nav-add" onClick={openAdd}
        whileTap={{ scale: 0.88, transition: { type: "spring", stiffness: 700, damping: 18 } }}
        whileHover={{ y: -22, transition: { type: "spring", stiffness: 380, damping: 24 } }}>
        <I.plus />
      </motion.button>
      <Item id="rentals"   label="Rentals"  icon={<I.list />} />
      <Item id="profile"   label="Me"       icon={<I.user />} />
    </nav>
  );
}

/* ── Dashboard ── */
function MDashboard({ buyers, sellers, matches, go, openAdd, currency, onCurrency, broker, darkMode, toggleDarkMode, pwaBanner }) {
  const recent = matches.slice(0, 3);
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" });
  const intlCount = [...buyers, ...sellers].filter((p) => p.intl).length;
  const greetName = broker?.nickname || broker?.name?.split(" ")[0] || broker?.email?.split("@")[0] || "broker";
  return (
    <>
      <MTopBar subtitle="Where deals get tied" currency={currency} onCurrency={onCurrency} darkMode={darkMode} toggleDarkMode={toggleDarkMode} />
      <div className="page fade-in">
        {pwaBanner}
        <div className="greet">Good to see you, <em style={{ color: "var(--gold-400)" }}>{greetName}</em>.</div>
        <div className="greet-sub">{today} · {intlCount} international leads</div>

        <div className="stat-grid">
          <div className="stat buyers mobile-stat">
            <div className="label"><span className="dot" />Sales</div>
            <div className="value">{buyers.filter((b) => b.division === "sales").length + sellers.filter((s) => s.division === "sales").length}</div>
            <div className="delta">contacts</div>
          </div>
          <div className="stat sellers mobile-stat">
            <div className="label"><span className="dot" />Rentals</div>
            <div className="value">{buyers.filter((b) => b.division === "rentals").length + sellers.filter((s) => s.division === "rentals").length}</div>
            <div className="delta">contacts</div>
          </div>
        </div>

        <div className="kpi-wide" onClick={() => go("sales")}>
          <div className="num">{matches.length}</div>
          <div className="text">
            <div className="t">Active matches</div>
            <div className="s">Across {new Set(matches.map((m) => m.buyer.area)).size} areas · highest {matches[0]?.score || 0}%</div>
          </div>
          <div className="arrow"><I.chevR /></div>
        </div>

        <div className="row-head"><h3>Quick add</h3></div>
        <div className="quick">
          <button onClick={() => openAdd("sales:buyer")}>
            <div className="qi b"><I.user width="16" height="16" /></div>
            <div className="qt">Log a buyer</div>
            <div className="qd">Sales</div>
          </button>
          <button onClick={() => openAdd("sales:seller")}>
            <div className="qi s"><I.pin width="16" height="16" /></div>
            <div className="qt">Log a seller</div>
            <div className="qd">Sales</div>
          </button>
          <button onClick={() => openAdd("rentals:buyer")}>
            <div className="qi b"><I.user width="16" height="16" /></div>
            <div className="qt">Log a tenant</div>
            <div className="qd">Rentals</div>
          </button>
          <button onClick={() => openAdd("rentals:seller")}>
            <div className="qi s"><I.pin width="16" height="16" /></div>
            <div className="qt">Log a landlord</div>
            <div className="qd">Rentals</div>
          </button>
        </div>

        <div className="row-head">
          <h3>Recent matches</h3>
        </div>

        {recent.length === 0 && (
          <div className="empty">
            <div className="ico"><I.match width="22" height="22" /></div>
            No matches yet. Log buyers and sellers in the same area &amp; type.
          </div>
        )}
        {recent.map((m, idx) => {
          const isRental = m.buyer.division === "rentals";
          const sPrice = isRental
            ? displayRental(m.seller.price, m.seller.cur, m.seller.period, currency, "monthly")
            : displayMoney(m.seller.price, m.seller.cur, currency);
          return (
            <motion.div className="match-mini" key={m.id} onClick={() => go(m.buyer.division)}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0, transition: { delay: idx * 0.06, type: "spring", stiffness: 380, damping: 28 } }}
              whileTap={tapBounce}>
              <div className="pair">
                <div className="avatar buyer">{initials(m.buyer.name)}</div>
                <div className="vs">⇅</div>
                <div className="avatar seller">{initials(m.seller.name)}</div>
              </div>
              <div className="info">
                <div className="names">
                  {m.buyer.name.split(" ")[0]} → {m.seller.name.split(" ")[0]}
                  {(m.buyer.intl || m.seller.intl) && <span className="intl-dot" />}
                  {m.kind === "stretch" && <span className="stretch-tag">Stretch</span>}
                </div>
                <div className="meta">{m.buyer.area} · {ptShort(m.buyer.type)} · {sPrice}</div>
              </div>
              <div className="score">{m.score}<span className="pct">%</span></div>
            </motion.div>
          );
        })}
      </div>
    </>
  );
}

/* ── Form ── */
function FormShell({ kind, division: forcedDivision, onBack, onSubmit, onBulkImport, initialData, onCurrencyChange, displayCur }) {
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
      division: div, period: "monthly", label: "active", radiusKm: "5",
      referredBy: "",
    };
  });

  useEffect(() => {
    if (initialData || !displayCur) return;
    const defaultCountry = COUNTRIES.find((c) => c.cur === displayCur)?.code;
    setForm((f) => ({
      ...f,
      cur: displayCur,
      ...(defaultCountry ? { country: defaultCountry } : {}),
    }));
  }, [displayCur]); // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const dial = COUNTRIES.find((c) => c.code === form.country)?.dial || "+1";
  const meta = divisionMeta(form.division);
  const isRental = form.division === "rentals";
  const roleName = isBuyer ? meta.buyerRole : meta.sellerRole;
  const types = propertyTypesFor(form.division);
  const valid = form.name.trim() && form.phone.trim().length >= 6 && form.area && form.type &&
    (isBuyer ? (form.min && form.max && Number(form.max) >= Number(form.min)) : form.price);

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
      <MTopBar subtitle={initialData ? `Edit ${roleName}` : `Add ${roleName}`} />
      <div className="page fade-in">
        <div className="form-header">
          <button className="back-btn" onClick={onBack}><I.back /></button>
          <div className="form-title">
            <span className="pre">{initialData ? "// edit" : `// new ${roleName.toLowerCase()}`}</span>
            {initialData ? `Update ${roleName.toLowerCase()}` : `Log a ${roleName.toLowerCase()}`}
          </div>
        </div>

        {!initialData && (
          <button
            type="button"
            onClick={() => setShowImport(true)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              width: "100%", padding: "13px 16px", marginBottom: 18,
              background: "transparent",
              border: "2px solid var(--gold-500)",
              borderRadius: 12, cursor: "pointer",
              fontFamily: "inherit", fontSize: 14, fontWeight: 700,
              color: "var(--gold-700)",
            }}
          >
            <I.upload width="15" height="15" />
            📥 Already have a list? Import from Excel
          </button>
        )}

        {err && <div className="form-err">{err}</div>}

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
              {Object.keys(CURRENCIES).map((k) => <option key={k} value={k}>{CURRENCIES[k].flag} {k}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label>Phone number<span className="req">*</span></label>
          <div className="phone-input">
            <div className="pre">{dial}</div>
            <input type="tel" maxLength={14} placeholder="00 000 0000"
              value={form.phone} onChange={(e) => update("phone", e.target.value.replace(/\D/g, "").slice(0, 14))} />
          </div>
        </div>
        <div className="field">
          <label>City / Area / Neighbourhood<span className="req">*</span></label>
          <PlacesAutocomplete value={form.area} onChange={(v) => update("area", v)}
            placeholder="Anna Nagar, Mogappair, Kilpauk (comma-separated for radius matching)" />
        </div>
        {isBuyer && (
          <div className="field">
            <label>Search radius (km) <span style={{ fontSize: 10, fontWeight: 400, color: "var(--ink-400)" }}>— match sellers nearby</span></label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="number" min="1" max="50" value={form.radiusKm}
                onChange={(e) => update("radiusKm", e.target.value)}
                style={{ width: 90 }} />
              <span style={{ fontSize: 12, color: "var(--ink-500)" }}>km (default 5)</span>
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
                <input type="number" placeholder="0" value={form.min} onChange={(e) => update("min", e.target.value)} />
              </div>
              {form.min && <div className="hint">{formatMoney(Number(form.min), form.cur)}{isRental ? form.period === "yearly" ? " / yr" : " / mo" : ""}</div>}
            </div>
            <div className="field">
              <label>Max {isRental ? `rent (${form.period})` : "budget"}<span className="req">*</span></label>
              <div className="rupee" data-cur={CURRENCIES[form.cur]?.sym}>
                <input type="number" placeholder="0" value={form.max} onChange={(e) => update("max", e.target.value)} />
              </div>
              {form.max && <div className="hint">{formatMoney(Number(form.max), form.cur)}{isRental ? form.period === "yearly" ? " / yr" : " / mo" : ""}</div>}
            </div>
          </div>
        ) : (
          <div className="field">
            <label>{isRental ? `Asking rent (${form.period})` : "Asking price"}<span className="req">*</span></label>
            <div className="rupee" data-cur={CURRENCIES[form.cur]?.sym}>
              <input type="number" placeholder="0" value={form.price} onChange={(e) => update("price", e.target.value)} />
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
            <span>Mark as <b>international</b> {roleName.toLowerCase()}</span>
          </label>
        </div>
        <div className="field">
          <label>Referred by</label>
          <input placeholder="e.g. Priya Kalyan, Walk-in, Instagram, Cold call…"
            value={form.referredBy} onChange={(e) => update("referredBy", e.target.value)} />
        </div>
        <div className="field">
          <label>Notes</label>
          <textarea placeholder={isBuyer ? "Must-haves, timeline, source of funds…" : "Floor, sqft, age, parking, view…"}
            value={form.notes} onChange={(e) => update("notes", e.target.value)} />
        </div>
        <div className="form-actions">
          <button className="btn ghost" onClick={onBack}>Cancel</button>
          <button className="btn primary" disabled={!valid || busy}
            style={!valid || busy ? { opacity: .55, cursor: "not-allowed" } : {}}
            onClick={async () => {
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
              try { await onSubmit(rec); }
              catch (e) { setErr(e.message || "Failed to save."); setBusy(false); }
            }}>
            <I.check /> {busy ? "Saving…" : initialData ? "Update" : "Save"}
          </button>
        </div>
      </div>
    </>
  );
}

/* ── Division page (matches + listings) ── */
function DivisionPage({
  division, buyers, sellers, matches, connectedSet, toggleConnect,
  showToast, displayCur, viewPeriod, onViewPeriod, currency, onCurrency,
  onEdit, onDelete, brokerName, onSetLabel, onBumpBudget, openAdd,
  darkMode, toggleDarkMode, onViewProfile,
}) {
  const meta = divisionMeta(division);
  const isRental = division === "rentals";
  const [tab, setTab] = useState("matches");
  const [labelFilter, setLabelFilter] = useState("all");
  const [q, setQ] = useState("");

  const dBuyers  = buyers.filter((b) => b.division === division);
  const dSellers = sellers.filter((s) => s.division === division);
  const dMatches = matches.filter((m) => m.buyer.division === division);

  const matchCountFor = (id, side) => dMatches.filter((m) => side === "buyer" ? m.buyer.id === id : m.seller.id === id).length;

  const labeled = (arr) =>
    arr.filter((p) => labelFilter === "all" || p.label === labelFilter)
       .filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.area.toLowerCase().includes(q.toLowerCase()))
       .sort((a, b) => labelSort(a.label) - labelSort(b.label));

  const fBuyers = labeled(dBuyers);
  const fSellers = labeled(dSellers);

  return (
    <>
      <MTopBar subtitle={meta.label} currency={currency} onCurrency={onCurrency}
        viewPeriod={viewPeriod} onViewPeriod={onViewPeriod} showPeriodToggle={isRental}
        darkMode={darkMode} toggleDarkMode={toggleDarkMode} />
      <div className="page fade-in">
        <div className="form-title" style={{ marginBottom: 14 }}>
          <span className="pre">// {meta.label.toLowerCase()} · {dMatches.length} matches</span>
          {meta.label} <span style={{ color: "var(--gold-600)", fontStyle: "italic" }}>workspace.</span>
        </div>

        <div className="tabs">
          <button className={tab === "matches" ? "on" : ""} onClick={() => setTab("matches")}>Matches <span className="count">{dMatches.length}</span></button>
          <button className={tab === "buyers" ? "on" : ""} onClick={() => setTab("buyers")}>{meta.buyerRole}s <span className="count">{dBuyers.length}</span></button>
          <button className={tab === "sellers" ? "on" : ""} onClick={() => setTab("sellers")}>{meta.sellerRole}s <span className="count">{dSellers.length}</span></button>
        </div>

        {tab !== "matches" && (
          <>
            <div className="search-input">
              <I.search />
              <input placeholder={`Search ${tab}…`} value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div className="label-filter-row mobile">
              <button className={`label-filter ${labelFilter === "all" ? "on" : ""}`} onClick={() => setLabelFilter("all")}>All</button>
              {LABELS.map((l) => (
                <button key={l.id} className={`label-filter label-${l.id} ${labelFilter === l.id ? "on" : ""}`}
                  onClick={() => setLabelFilter(l.id)}>
                  <span aria-hidden>{l.icon}</span> {l.name}
                </button>
              ))}
            </div>
          </>
        )}

        {tab === "matches" && (
          <motion.div variants={listContainer} initial="initial" animate="enter">
            {dMatches.length === 0 && (
              <div className="empty"><div className="ico"><I.match width="22" height="22" /></div>No {meta.label.toLowerCase()} matches yet.</div>
            )}
            {dMatches.map((m) => {
              const done = connectedSet.has(m.id);
              const isIntl = m.buyer.intl || m.seller.intl;
              const stretch = m.kind === "stretch";
              const buyerPriceTxt = isRental
                ? displayRentalRange(m.buyer.min, m.buyer.max, m.buyer.cur, m.buyer.period, displayCur, viewPeriod)
                : displayRange(m.buyer.min, m.buyer.max, m.buyer.cur, displayCur);
              const sellerPriceTxt = isRental
                ? displayRental(m.seller.price, m.seller.cur, m.seller.period, displayCur, viewPeriod)
                : displayMoney(m.seller.price, m.seller.cur, displayCur);
              return (
                <motion.div className={`match-card ${stretch ? "stretch" : ""}`} key={m.id} variants={listItem} whileTap={tapBounce}>
                  <div className="match-strip">
                    <span>{CURRENCIES[m.buyer.cur]?.flag} {m.buyer.area}{isIntl && <span className="intl-tag" style={{ marginLeft: 6 }}>International</span>}{stretch && <span className="stretch-tag" style={{ marginLeft: 6 }}>Stretch</span>}</span>
                    <span className="score-tag">{m.score}% fit</span>
                  </div>
                  <div className="match-body">
                    <div className="person buyer">
                      <div className="role"><span className="dot" />{meta.buyerRole}{m.buyer.intl && <span className="intl-mini">INTL</span>}</div>
                      <div className="name profile-link" onClick={(e) => { e.stopPropagation(); e.nativeEvent.stopImmediatePropagation(); onViewProfile?.("buyer", m.buyer.id); }}>{m.buyer.name} <span style={{ fontSize: 9, color: "var(--gold-600)" }}>↗</span></div>
                      <div className="area"><I.pin width="11" height="11" />{m.buyer.area}</div>
                      {m.areaMatchType === "proximity" && m.distanceKm > 0 && (
                        <span className="area-badge proximity" style={{ fontSize: 9, marginTop: 2, display: "inline-flex" }}>Near {m.matchedBuyerArea} · {m.distanceKm}km</span>
                      )}
                      {m.areaMatchType === "exact" && m.matchedBuyerArea && (
                        <span className="area-badge exact" style={{ fontSize: 9, marginTop: 2, display: "inline-flex" }}>{m.matchedBuyerArea} ✓</span>
                      )}
                      <div className="price">{buyerPriceTxt}</div>
                      <span className="ptype">{ptLabel(m.buyer.type)}</span>
                    </div>
                    <div className="person seller">
                      <div className="role"><span className="dot" />{meta.sellerRole}{m.seller.intl && <span className="intl-mini">INTL</span>}</div>
                      <div className="name profile-link" onClick={(e) => { e.stopPropagation(); e.nativeEvent.stopImmediatePropagation(); onViewProfile?.("seller", m.seller.id); }}>{m.seller.name} <span style={{ fontSize: 9, color: "var(--gold-600)" }}>↗</span></div>
                      <div className="area"><I.pin width="11" height="11" />{m.seller.area}</div>
                      <div className="price">{sellerPriceTxt}</div>
                      <span className="ptype">{ptLabel(m.seller.type)}</span>
                    </div>
                  </div>
                  <div className="match-actions">
                    {(() => {
                      const mkMsg = () => encodeURIComponent(`Hello, I'm ${brokerName} from DealKnot. I have a property match for you. Are you available for a quick call?`);
                      const bNum = (m.buyer.dial + m.buyer.phone).replace(/\D/g, "");
                      const sNum = (m.seller.dial + m.seller.phone).replace(/\D/g, "");
                      const shareMsg = encodeURIComponent(
                        `Hi ${m.buyer.name.split(" ")[0]}, I have a property match for you!\n📍 Location: ${m.seller.area}\n🏠 Type: ${ptLabel(m.seller.type)}\n💰 Asking: ${sellerPriceTxt}\nInterested? Let me know and I'll connect you with the seller.\n${brokerName}, DealKnot`
                      );
                      return (<>
                        <a className="wa" href={`https://wa.me/${bNum}?text=${shareMsg}`} target="_blank" rel="noreferrer"><I.whats width="15" height="15" /> Share Match</a>
                        <a className="wa" href={`https://wa.me/${sNum}?text=${mkMsg()}`} target="_blank" rel="noreferrer"><I.whats width="15" height="15" /> WA {meta.sellerRole}</a>
                        <a className="call" href={`tel:${m.buyer.dial}${m.buyer.phone}`}><I.phone width="15" height="15" /> {meta.buyerRole}</a>
                        <a className="call" href={`tel:${m.seller.dial}${m.seller.phone}`}><I.phone width="15" height="15" /> {meta.sellerRole}</a>
                      </>);
                    })()}
                    <button className={`connect ${done ? "done" : ""}`} onClick={async () => {
                      const wasConnected = done;
                      await toggleConnect(m.id);
                      if (!wasConnected) showToast(`Connected · ${m.buyer.name.split(" ")[0]} → ${m.seller.name.split(" ")[0]}`);
                    }}>
                      {done ? <><I.check width="15" height="15" /> Connected</> : <>Connect <I.chevR width="15" height="15" /></>}
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        )}

        {tab === "buyers" && (fBuyers.length === 0
          ? <div className="empty"><div className="ico"><I.user width="22" height="22" /></div>No {meta.buyerRole.toLowerCase()}s match this filter.</div>
          : fBuyers.map((b, idx) => {
            const mc = matchCountFor(b.id, "buyer");
            const c = COUNTRIES.find((x) => x.code === b.country);
            const priceTxt = isRental
              ? displayRentalRange(b.min, b.max, b.cur, b.period, displayCur, viewPeriod)
              : displayRange(b.min, b.max, b.cur, displayCur);
            return (
              <motion.div className="listing-card" key={b.id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0, transition: { delay: idx * 0.04, type: "spring", stiffness: 380, damping: 30 } }}
                whileTap={tapBounce}
                onClick={() => onViewProfile?.("buyer", b.id)}>
                <div className="top">
                  <div className="avatar buyer">{initials(b.name)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="name">{b.name} {b.intl && <span className="intl-tag inline">International</span>}</div>
                    <div className="phone">{c?.flag} {b.dial} {formatPhone(b.phone)}</div>
                  </div>
                  <LabelBadge label={b.label} kind="buyer" id={b.id} onChange={onSetLabel} size="sm" onClick={(e) => e.stopPropagation()} />
                </div>
                <div className="meta-row">
                  <span className="meta-tag"><I.pin width="11" height="11" /> {b.area}</span>
                  <span className="meta-tag">{ptShort(b.type)}</span>
                  <span className="meta-tag">{CURRENCIES[b.cur]?.flag} {b.cur}</span>
                  <span className={`matches-pill ${mc === 0 ? "zero" : ""}`}>{mc === 0 ? "no match" : `${mc} match${mc > 1 ? "es" : ""}`}</span>
                </div>
                <div className="price-line">
                  <span className="lbl">{isRental ? "Rent" : "Budget"}</span>
                  <span className="val">{priceTxt}</span>
                </div>
                {!isRental && (
                  <div className="bump-row">
                    {b.cur === "INR" ? (
                      <>
                        <button className="bump-btn" onClick={() => onBumpBudget(b.id, 2500000)}>+25 L</button>
                        <button className="bump-btn" onClick={() => onBumpBudget(b.id, 5000000)}>+50 L</button>
                      </>
                    ) : (
                      <>
                        <button className="bump-btn" onClick={() => onBumpBudget(b.id, 25000)}>+25 K</button>
                        <button className="bump-btn" onClick={() => onBumpBudget(b.id, 50000)}>+50 K</button>
                      </>
                    )}
                  </div>
                )}
                <div onClick={(e) => e.stopPropagation()}>
                  <CardActions p={b} kind="buyer" onEdit={onEdit} onDelete={onDelete} brokerName={brokerName} />
                  <ClientNotes clientId={b.id} clientType="buyer" />
                </div>
              </motion.div>
            );
          })
        )}

        {tab === "sellers" && (fSellers.length === 0
          ? <div className="empty"><div className="ico"><I.pin width="22" height="22" /></div>No {meta.sellerRole.toLowerCase()}s match this filter.</div>
          : fSellers.map((s, idx) => {
            const mc = matchCountFor(s.id, "seller");
            const c = COUNTRIES.find((x) => x.code === s.country);
            const priceTxt = isRental
              ? displayRental(s.price, s.cur, s.period, displayCur, viewPeriod)
              : displayMoney(s.price, s.cur, displayCur);
            return (
              <motion.div className="listing-card" key={s.id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0, transition: { delay: idx * 0.04, type: "spring", stiffness: 380, damping: 30 } }}
                whileTap={tapBounce}
                onClick={() => onViewProfile?.("seller", s.id)}>
                <div className="top">
                  <div className="avatar seller">{initials(s.name)}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="name">{s.name} {s.intl && <span className="intl-tag inline">International</span>}</div>
                    <div className="phone">{c?.flag} {s.dial} {formatPhone(s.phone)}</div>
                  </div>
                  <LabelBadge label={s.label} kind="seller" id={s.id} onChange={onSetLabel} size="sm" onClick={(e) => e.stopPropagation()} />
                </div>
                <div className="meta-row">
                  <span className="meta-tag"><I.pin width="11" height="11" /> {s.area}</span>
                  <span className="meta-tag">{ptShort(s.type)}</span>
                  <span className="meta-tag">{CURRENCIES[s.cur]?.flag} {s.cur}</span>
                  <span className={`matches-pill ${mc === 0 ? "zero" : ""}`}>{mc === 0 ? "no match" : `${mc} match${mc > 1 ? "es" : ""}`}</span>
                </div>
                <div className="price-line">
                  <span className="lbl">{isRental ? "Asking rent" : "Asking"}</span>
                  <span className="val">{priceTxt}</span>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <CardActions p={s} kind="seller" onEdit={onEdit} onDelete={onDelete} brokerName={brokerName} />
                  <ClientNotes clientId={s.id} clientType="seller" />
                </div>
              </motion.div>
            );
          })
        )}
      </div>
    </>
  );
}

function CardActions({ p, kind, onEdit, onDelete, brokerName }) {
  const num = (p.dial + p.phone).replace(/\D/g, "");
  const msg = encodeURIComponent(`Hello, I'm ${brokerName} from DealKnot. I have a property match for you. Are you available for a quick call?`);
  const waHref = `https://wa.me/${num}?text=${msg}`;
  const callHref = `tel:${p.dial}${p.phone}`;
  return (
    <div className="card-actions">
      <a className="ca-btn wa" href={waHref} target="_blank" rel="noreferrer"><I.whats width="15" height="15" /></a>
      <a className="ca-btn call" href={callHref}><I.phone width="15" height="15" /></a>
      <button className="ca-btn edit" onClick={() => onEdit(kind, p)}><I.edit width="15" height="15" /></button>
      <button className="ca-btn del" onClick={() => onDelete(kind, p)}><I.trash width="15" height="15" /></button>
    </div>
  );
}

/* ── Profile ── */
function ProfilePage({ buyers, sellers, connectedSet, logout, broker, onInstallGuide, onCommission, onAnalytics }) {
  const displayName = broker?.nickname || broker?.name?.split(" ")[0] || broker?.email?.split("@")[0] || "Broker";
  const avatarLetter = (broker?.nickname || broker?.name || broker?.email || "B")[0].toUpperCase();
  const [confirmLogout, setConfirmLogout] = useState(false);
  const MenuItem = ({ onClick, emoji, title, sub, icon }) => (
    <div className="match-mini" style={{ cursor: "pointer" }} onClick={onClick}>
      <div style={{ width: 36, height: 36, borderRadius: 10, background: "var(--navy-800)", color: "var(--gold-400)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontSize: 16 }}>{emoji}</div>
      <div className="info" style={{ flex: 1 }}>
        <div className="names">{title}</div>
        <div className="meta">{sub}</div>
      </div>
      {icon || <I.chevR width="16" height="16" />}
    </div>
  );
  return (
    <>
      <MTopBar subtitle="Profile" />
      <div className="page fade-in">
        <div style={{ textAlign: "center", padding: "20px 0 24px" }}>
          <div style={{ width: 84, height: 84, margin: "0 auto 12px", borderRadius: "50%", background: "linear-gradient(160deg, var(--navy-800), var(--navy-700))", color: "var(--gold-400)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Fraunces, serif", fontSize: 30, fontWeight: 600 }}>{avatarLetter}</div>
          <div style={{ fontFamily: "Fraunces, serif", fontSize: 20, fontWeight: 600, color: "var(--navy-900)" }}>{displayName}</div>
          <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 2 }}>{broker?.email || "Your DealKnot workspace"}</div>
        </div>
        <div className="stat-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          <div className="stat" style={{ padding: "12px 10px" }}><div className="label" style={{ fontSize: 9.5 }}>Buyers</div><div className="value" style={{ fontSize: 24 }}>{buyers.length}</div></div>
          <div className="stat" style={{ padding: "12px 10px" }}><div className="label" style={{ fontSize: 9.5 }}>Sellers</div><div className="value" style={{ fontSize: 24 }}>{sellers.length}</div></div>
          <div className="stat" style={{ padding: "12px 10px" }}><div className="label" style={{ fontSize: 9.5 }}>Closed</div><div className="value" style={{ fontSize: 24 }}>{connectedSet.size}</div></div>
        </div>
        <div className="row-head" style={{ marginTop: 18 }}><h3>Finance</h3></div>
        <MenuItem onClick={onCommission} emoji="💰" title="Commission Tracker" sub="Log and track your deal commissions" />
        <MenuItem onClick={onAnalytics}  emoji="📊" title="Analytics" sub="Charts and insights from your book" />
        <div className="row-head" style={{ marginTop: 18 }}><h3>App</h3></div>
        <MenuItem onClick={onInstallGuide} emoji="📲" title="Install as App" sub="Add DealKnot to your home screen" />
        <div className="row-head" style={{ marginTop: 18 }}><h3>Account</h3></div>
        <div className="match-mini" style={{ cursor: "pointer" }} onClick={() => setConfirmLogout(true)}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(179,58,38,.1)", color: "var(--red)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><I.logout width="16" height="16" /></div>
          <div className="info" style={{ flex: 1 }}>
            <div className="names" style={{ color: "var(--red)" }}>Sign out</div>
            <div className="meta">Log out of your broker workspace</div>
          </div>
        </div>
      </div>

      {confirmLogout && (
        <div className="add-sheet-bg" onClick={() => setConfirmLogout(false)}>
          <div className="add-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sheet-grab" />
            <div className="sheet-title" style={{ color: "var(--red)" }}>Sign out?</div>
            <div className="sheet-sub">You'll be returned to the landing page. Any unsaved changes will be lost.</div>
            <div style={{ display: "flex", gap: 10, padding: "8px 0 4px" }}>
              <button className="btn ghost" style={{ flex: 1 }} onClick={() => setConfirmLogout(false)}>Cancel</button>
              <button className="btn" style={{ flex: 1, background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} onClick={logout}>Sign out</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ── Profile Detail ── */
function ProfileDetail({ kind, id, buyers, sellers, matches, onBack, onEdit, onDelete, waLink, callLink, displayCur, viewPeriod, brokerName, connectedSet }) {
  const isBuyer = kind === "buyer";
  const list = isBuyer ? buyers : sellers;
  const p = list.find((x) => x.id === id);
  if (!p) return (
    <>
      <MTopBar subtitle="Profile" />
      <div className="page fade-in">
        <button className="back-btn" onClick={onBack} style={{ marginBottom: 16 }}><I.back /> Back</button>
        <div className="empty" style={{ paddingTop: 60 }}>Contact not found.</div>
      </div>
    </>
  );

  const c = COUNTRIES.find((x) => x.code === p.country);
  const meta = divisionMeta(p.division);
  const isRental = p.division === "rentals";
  const role = isBuyer ? meta.buyerRole : meta.sellerRole;
  const relatedMatches = matches.filter((m) => isBuyer ? m.buyer.id === p.id : m.seller.id === p.id);

  const priceTxt = isBuyer
    ? (isRental
      ? displayRentalRange(p.min, p.max, p.cur, p.period, displayCur, viewPeriod)
      : displayRange(p.min, p.max, p.cur, displayCur))
    : (isRental
      ? displayRental(p.price, p.cur, p.period, displayCur, viewPeriod)
      : displayMoney(p.price, p.cur, displayCur));

  const num = (p.dial + p.phone).replace(/\D/g, "");
  const msg = encodeURIComponent(`Hello, I'm ${brokerName} from DealKnot. I have a property match for you. Are you available for a quick call?`);

  return (
    <>
      <MTopBar subtitle={role} />
      <div className="page fade-in">
        <div className="form-header" style={{ marginBottom: 18 }}>
          <button className="back-btn" onClick={onBack}><I.back /></button>
          <div className="form-title">
            <span className="pre">// {meta.label.toLowerCase()} · {role.toLowerCase()}</span>
            Profile
          </div>
        </div>

        <div className="listing-card" style={{ marginBottom: 14 }}>
          <div className="top">
            <div className={`avatar ${isBuyer ? "buyer" : "seller"}`} style={{ width: 44, height: 44, fontSize: 15 }}>{initials(p.name)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="name" style={{ fontSize: 17 }}>{p.name}{p.intl && <span className="intl-tag inline" style={{ marginLeft: 6 }}>International</span>}</div>
              <div className="phone">{c?.flag} {p.dial} {formatPhone(p.phone)}</div>
            </div>
          </div>
          <div className="meta-row" style={{ marginTop: 10 }}>
            <span className="meta-tag"><I.pin width="11" height="11" /> {p.area}</span>
            <span className="meta-tag">{ptShort(p.type)}</span>
            <span className="meta-tag">{CURRENCIES[p.cur]?.flag} {p.cur}</span>
          </div>
          <div className="price-line" style={{ marginTop: 10 }}>
            <span className="lbl">{isBuyer ? (isRental ? "Rent budget" : "Budget") : (isRental ? "Asking rent" : "Asking")}</span>
            <span className="val">{priceTxt}</span>
          </div>
          {p.notes && (
            <div style={{ marginTop: 10, fontSize: 12.5, color: "var(--ink-700)", lineHeight: 1.5, padding: "8px 0", borderTop: "1px dashed var(--line-2)" }}>{p.notes}</div>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          <a className="btn success" href={`https://wa.me/${num}?text=${msg}`} target="_blank" rel="noreferrer" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, textDecoration: "none" }}>
            <I.whats width="15" height="15" /> WhatsApp
          </a>
          <a className="btn ghost" href={`tel:${p.dial}${p.phone}`} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, textDecoration: "none" }}>
            <I.phone width="15" height="15" /> Call
          </a>
          <button className="btn ghost" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
            onClick={() => onEdit(kind, p)}><I.edit width="14" height="14" /> Edit</button>
          <button className="btn ghost" style={{ color: "var(--red)", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
            onClick={() => onDelete(kind, p)}><I.trash width="14" height="14" /> Delete</button>
        </div>

        <div className="row-head"><h3>Matches <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ink-500)" }}>({relatedMatches.length})</span></h3></div>
        {relatedMatches.length === 0 && (
          <div className="empty" style={{ paddingTop: 24, paddingBottom: 24 }}>
            <div className="ico"><I.match width="20" height="20" /></div>No matches yet.
          </div>
        )}
        {relatedMatches.map((m) => {
          const counter = isBuyer ? m.seller : m.buyer;
          const done = connectedSet.has(m.id);
          const isRentalM = m.buyer.division === "rentals";
          const cPrice = isRentalM
            ? displayRental(m.seller.price, m.seller.cur, m.seller.period, displayCur, viewPeriod)
            : displayMoney(m.seller.price, m.seller.cur, displayCur);
          return (
            <div key={m.id} className="match-mini">
              <div className="avatar" style={{ background: "var(--navy-100)", color: "var(--navy-800)" }}>{initials(counter.name)}</div>
              <div className="info">
                <div className="names">{counter.name.split(" ")[0]} · {m.score}% fit{m.kind === "stretch" ? " · stretch" : ""}</div>
                <div className="meta">{counter.area} · {cPrice}</div>
              </div>
              {done && <span style={{ fontSize: 9.5, background: "var(--green-bg)", color: "var(--green)", padding: "2px 7px", borderRadius: 999, fontWeight: 700, flexShrink: 0 }}>Connected</span>}
            </div>
          );
        })}

        <ClientNotes clientId={p.id} clientType={isBuyer ? "buyer" : "seller"} />
      </div>
    </>
  );
}

/* ── Add sheet ── */
function AddSheet({ onClose, onPick }) {
  return (
    <div className="add-sheet-bg" onClick={onClose}>
      <div className="add-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-grab" />
        <div className="sheet-title">What are you logging?</div>
        <div className="sheet-sub">Pick the side and division.</div>
        <div className="sheet-options">
          <button onClick={() => onPick("sales:buyer")}>
            <div className="si b"><I.user width="18" height="18" /></div>
            <div className="st">Sales · Buyer</div>
            <div className="sd">Wants to purchase</div>
          </button>
          <button onClick={() => onPick("sales:seller")}>
            <div className="si s"><I.pin width="18" height="18" /></div>
            <div className="st">Sales · Seller</div>
            <div className="sd">Wants to sell</div>
          </button>
          <button onClick={() => onPick("rentals:buyer")}>
            <div className="si b"><I.user width="18" height="18" /></div>
            <div className="st">Rentals · Tenant</div>
            <div className="sd">Wants to rent</div>
          </button>
          <button onClick={() => onPick("rentals:seller")}>
            <div className="si s"><I.pin width="18" height="18" /></div>
            <div className="st">Rentals · Landlord</div>
            <div className="sd">Wants to rent out</div>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Main mobile app ── */
function useInstallPrompt() {
  // Use ref so storing the event object doesn't trigger re-renders
  const promptRef = useRef(window._dkInstallPrompt || null);
  const [hasPrompt, setHasPrompt] = useState(!!promptRef.current);
  const [dismissed, setDismissed] = useState(() => !!localStorage.getItem("dk_pwa_dismissed"));
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches;
  const [installed, setInstalled] = useState(() => isStandalone || !!localStorage.getItem("dk_pwa_installed"));

  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      promptRef.current = e;
      window._dkInstallPrompt = e;
      setHasPrompt(true);
    };
    window.addEventListener("beforeinstallprompt", handler);
    // Capture event fired before this component mounted
    if (window._dkInstallPrompt && !promptRef.current) {
      promptRef.current = window._dkInstallPrompt;
      setHasPrompt(true);
    }
    const installedHandler = () => {
      localStorage.setItem("dk_pwa_installed", "1");
      setInstalled(true);
      promptRef.current = null;
      window._dkInstallPrompt = null;
      setHasPrompt(false);
    };
    window.addEventListener("appinstalled", installedHandler);
    return () => {
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", installedHandler);
    };
  }, []);

  const install = async () => {
    if (!promptRef.current) return;
    promptRef.current.prompt();
    await promptRef.current.userChoice;
    promptRef.current = null;
    window._dkInstallPrompt = null;
    setHasPrompt(false);
  };

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem("dk_pwa_dismissed", "1");
  };

  // Android Chrome fallback: show install button even if beforeinstallprompt hasn't fired yet
  const isAndroidChrome = /Android/.test(navigator.userAgent) && /Chrome\//.test(navigator.userAgent);
  const canInstall = hasPrompt && !installed;
  const show = !installed && !dismissed && (hasPrompt || isAndroidChrome);
  return { show, install, dismiss, canInstall };
}

export default function MobileApp({
  buyers, sellers, matches, connectedSet,
  addBuyer, addSeller, bulkAddBuyers, bulkAddSellers,
  updateBuyer, updateSeller,
  setBuyerLabel, setSellerLabel, bumpBuyerBudget,
  deleteBuyer, deleteSeller, toggleConnect, logout, broker,
  darkMode, toggleDarkMode,
}) {
  const [tab, setTab] = useState("dashboard");
  const [route, setRoute] = useState({ name: "tab" });
  const [showAdd, setShowAdd] = useState(false);
  const [showInstallGuide, setShowInstallGuide] = useState(false);
  const [toast, setToast] = useState(null);
  const [currency, setCurrency] = useState(() => localStorage.getItem("dk_currency") || "AED");
  const updateCurrency = (c) => { setCurrency(c); localStorage.setItem("dk_currency", c); };
  const [viewPeriod, setViewPeriod] = useState("monthly");
  const [confirm, setConfirm] = useState(null);
  const pwa = useInstallPrompt();

  const brokerName = broker?.nickname || broker?.name?.split(" ")[0] || "your broker";
  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2400); };
  const go = (id) => { setRoute({ name: "tab" }); setTab(id); };

  const openAdd = (which) => {
    if (!which) { setShowAdd(true); return; }
    setShowAdd(false);
    const [div, kind] = which.split(":");
    setRoute({ name: "form", division: div, kind });
  };

  const startEdit = (kind, record) => setRoute({ name: "form", kind, division: record.division, editData: record });
  const startDelete = (kind, record) => setConfirm({ name: record.name, onConfirm: async () => {
    if (kind === "buyer") await deleteBuyer(record.id);
    else await deleteSeller(record.id);
    showToast(`${record.name.split(" ")[0]} removed`);
    setConfirm(null);
  }});

  const onSetLabel = async (kind, id, label) => {
    if (kind === "buyer") await setBuyerLabel(id, label);
    else await setSellerLabel(id, label);
    showToast("Status updated");
  };
  const onBumpBudget = async (id, delta) => {
    await bumpBuyerBudget(id, delta);
    showToast("Budget bumped");
  };

  if (showInstallGuide) {
    return (
      <div className="app-mobile">
        <div className="page" style={{ paddingBottom: 24 }}>
          <InstallGuide onClose={() => setShowInstallGuide(false)} />
        </div>
      </div>
    );
  }

  const onViewProfile = (kind, id) => setRoute({ name: "profile", kind, id });

  let content;
  if (route.name === "profile") {
    const brokerName_ = brokerName;
    content = (
      <ProfileDetail
        kind={route.kind} id={route.id}
        buyers={buyers} sellers={sellers} matches={matches}
        connectedSet={connectedSet}
        onBack={() => setRoute({ name: "tab" })}
        onEdit={(kind, record) => setRoute({ name: "form", kind, division: record.division, editData: record })}
        onDelete={startDelete}
        waLink={(p) => { const num = (p.dial + p.phone).replace(/\D/g, ""); const msg = encodeURIComponent(`Hello, I'm ${brokerName_} from DealKnot. Are you available for a quick call?`); return `https://wa.me/${num}?text=${msg}`; }}
        callLink={(p) => `tel:${p.dial}${p.phone}`}
        displayCur={currency} viewPeriod={viewPeriod}
        brokerName={brokerName_}
      />
    );
  } else if (route.name === "form") {
    const isEdit = !!route.editData;
    content = (
      <FormShell key={`${route.division || "sales"}:${route.kind}:${route.editData?.id || "new"}`}
        kind={route.kind} division={route.division || "sales"} initialData={route.editData}
        onBack={() => setRoute({ name: "tab" })}
        onCurrencyChange={updateCurrency} displayCur={currency}
        onBulkImport={async (records) => {
          if (route.kind === "buyer") return await bulkAddBuyers(records);
          return await bulkAddSellers(records);
        }}
        onSubmit={async (rec) => {
          if (isEdit) {
            if (route.kind === "buyer") await updateBuyer(route.editData.id, rec);
            else await updateSeller(route.editData.id, rec);
            showToast(`${rec.name.split(" ")[0]} updated`);
          } else {
            if (route.kind === "buyer") await addBuyer(rec);
            else await addSeller(rec);
            showToast(`${rec.name.split(" ")[0]} saved`);
          }
          setRoute({ name: "tab" }); setTab(rec.division);
        }} />
    );
  } else if (tab === "dashboard") {
    const pwaBanner = pwa.show ? (
      <div className="pwa-dash-banner">
        <span>📲 Install DealKnot for faster access</span>
        <div style={{ display: "flex", gap: 8 }}>
          {pwa.canInstall
            ? <button className="pwa-dash-install" onClick={pwa.install}>Install</button>
            : <button className="pwa-dash-install" onClick={() => setShowInstallGuide(true)}>How to install</button>
          }
          <button className="pwa-dash-guide" onClick={() => setShowInstallGuide(true)}>How?</button>
          <button className="pwa-dash-dismiss" onClick={pwa.dismiss}>✕</button>
        </div>
      </div>
    ) : null;
    content = (
      <MDashboard buyers={buyers} sellers={sellers} matches={matches} go={go} openAdd={openAdd} currency={currency} onCurrency={updateCurrency} broker={broker} darkMode={darkMode} toggleDarkMode={toggleDarkMode} pwaBanner={pwaBanner} />
    );
  } else if (tab === "sales" || tab === "rentals") {
    content = (
      <DivisionPage division={tab}
        buyers={buyers} sellers={sellers} matches={matches} connectedSet={connectedSet}
        toggleConnect={toggleConnect} showToast={showToast}
        displayCur={currency} viewPeriod={viewPeriod} onViewPeriod={setViewPeriod}
        currency={currency} onCurrency={updateCurrency}
        onEdit={startEdit} onDelete={startDelete} brokerName={brokerName}
        onSetLabel={onSetLabel} onBumpBudget={onBumpBudget} openAdd={openAdd}
        darkMode={darkMode} toggleDarkMode={toggleDarkMode}
        onViewProfile={onViewProfile} />
    );
  } else if (tab === "profile") {
    content = <ProfilePage buyers={buyers} sellers={sellers} connectedSet={connectedSet} logout={logout} broker={broker}
      onInstallGuide={() => setShowInstallGuide(true)}
      onCommission={() => setRoute({ name: "commission" })}
      onAnalytics={() => setRoute({ name: "analytics" })}
    />;
  } else if (tab === "commission" || route.name === "commission") {
    content = (
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "14px 20px 10px", background: "var(--paper)", borderBottom: "1px solid var(--line-2)", display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <button className="back-btn" onClick={() => setRoute({ name: "tab" })}><I.back /></button>
          <span style={{ fontFamily: "Fraunces, serif", fontWeight: 600, fontSize: 18, color: "var(--navy-900)" }}>Commission</span>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", WebkitOverflowScrolling: "touch", padding: "16px 16px 32px", background: "var(--ivory)" }}>
          <CommissionPage displayCur={currency} mobile />
        </div>
      </div>
    );
  } else if (route.name === "analytics") {
    content = (
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "14px 20px 10px", background: "var(--paper)", borderBottom: "1px solid var(--line-2)", display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <button className="back-btn" onClick={() => setRoute({ name: "tab" })}><I.back /></button>
          <span style={{ fontFamily: "Fraunces, serif", fontWeight: 600, fontSize: 18, color: "var(--navy-900)" }}>Analytics</span>
        </div>
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", WebkitOverflowScrolling: "touch", padding: "16px 16px 32px", background: "var(--ivory)" }}>
          <AnalyticsPage buyers={buyers} sellers={sellers} matches={matches} connectedSet={connectedSet} displayCur={currency} mobile />
        </div>
      </div>
    );
  }

  return (
    <div className="app-mobile">
      {content}
      {route.name === "tab" && <BottomNav tab={tab} go={go} openAdd={() => openAdd()} />}
      {showAdd && <AddSheet onClose={() => setShowAdd(false)} onPick={openAdd} />}
      {toast && <div className="toast"><I.check width="14" height="14" /> {toast}</div>}
      {/* Legacy bottom banner — only show if dash banner is not visible */}
      {pwa.show && tab !== "dashboard" && route.name === "tab" && (
        <div className="pwa-banner">
          <div className="pwa-banner-mark">D</div>
          <div className="pwa-banner-text">
            <span className="pwa-banner-title">Install DealKnot</span>
            <span className="pwa-banner-sub">Add to your home screen</span>
          </div>
          <button className="pwa-banner-btn" onClick={pwa.canInstall ? pwa.install : () => setShowInstallGuide(true)}>Install</button>
          <button className="pwa-banner-close" onClick={pwa.dismiss} aria-label="Dismiss">✕</button>
        </div>
      )}
      {confirm && (
        <div className="confirm-overlay" onClick={() => setConfirm(null)}>
          <div className="confirm-box" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-title">Delete contact?</div>
            <div className="confirm-msg">Are you sure you want to delete <b>{confirm.name}</b>?</div>
            <div className="confirm-actions">
              <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button>
              <button className="btn" style={{ background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} onClick={confirm.onConfirm}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
