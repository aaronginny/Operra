import { useState, useRef, useEffect } from "react";
import { I } from "../icons";
import { useAuth } from "../AuthContext";
import { CURRENCIES, initials } from "../constants";
import { AREAS } from "../PlacesAutocomplete";

function useSearch(buyers, sellers) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);

  const results = q.trim().length < 2 ? [] : (() => {
    const lq = q.toLowerCase();
    const match = (p) =>
      p.name.toLowerCase().includes(lq) ||
      p.phone.includes(lq) ||
      p.area.toLowerCase().includes(lq) ||
      (p.notes || "").toLowerCase().includes(lq) ||
      (p.type || "").toLowerCase().includes(lq);
    return [
      ...buyers.filter(match).slice(0, 5).map((p) => ({ ...p, _kind: "buyer" })),
      ...sellers.filter(match).slice(0, 5).map((p) => ({ ...p, _kind: "seller" })),
    ];
  })();

  // Area matches: known area names that contain the query, with per-division
  // contact counts so clicking can land on the right listings page
  const areaResults = q.trim().length < 2 ? [] : (() => {
    const lq = q.toLowerCase();
    const all = [...buyers, ...sellers];
    const countIn = (areaName, division) => {
      const la = areaName.toLowerCase();
      return all.filter((p) => p.division === division && (p.area || "").toLowerCase().includes(la)).length;
    };
    const out = [];
    for (const a of AREAS) {
      if (!a.toLowerCase().includes(lq)) continue;
      // strip ", Chennai" style suffix for matching contact areas
      const short = a.split(",")[0].trim();
      const sales = countIn(short, "sales");
      const rentals = countIn(short, "rentals");
      if (sales > 0) out.push({ area: short, division: "sales", count: sales });
      if (rentals > 0) out.push({ area: short, division: "rentals", count: rentals });
      if (out.length >= 4) break;
    }
    return out.slice(0, 4);
  })();

  return { q, setQ, open, setOpen, results, areaResults };
}

export default function TopBar({
  currency, setCurrency, viewPeriod, setViewPeriod, showPeriodToggle,
  buyers = [], sellers = [], onSelectResult, onSelectArea,
  darkMode, toggleDarkMode,
}) {
  const { broker } = useAuth();
  const initl = (n) => n?.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";
  const displayName = broker?.nickname || broker?.name?.split(" ")[0] || broker?.email?.split("@")[0] || "Broker";

  const { q, setQ, open, setOpen, results, areaResults } = useSearch(buyers, sellers);
  const wrapRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const grouped = {
    buyer: results.filter((r) => r._kind === "buyer"),
    seller: results.filter((r) => r._kind === "seller"),
  };

  const handleKeyDown = (e) => {
    if (e.key === "Escape") { setOpen(false); setQ(""); }
  };

  const handleSelect = (item) => {
    onSelectResult?.({ kind: item._kind, id: item.id });
    setOpen(false);
    setQ("");
  };

  const handleSelectArea = (a) => {
    onSelectArea?.(a.area, a.division);
    setOpen(false);
    setQ("");
  };

  return (
    <header className="topbar">
      <div className="search" ref={wrapRef}>
        <I.search />
        <input
          placeholder="Search buyers, sellers, areas, phone numbers…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => q.trim().length >= 2 && setOpen(true)}
          onKeyDown={handleKeyDown}
        />
        {!q && <span className="kbd">⌘ K</span>}
        {open && (results.length > 0 || areaResults.length > 0) && (
          <div className="search-dropdown">
            {areaResults.length > 0 && (
              <div className="search-group">
                <div className="search-group-label">Locations</div>
                {areaResults.map((a) => (
                  <button key={`${a.area}-${a.division}`} className="search-result" onMouseDown={() => handleSelectArea(a)}>
                    <div className="search-av area"><I.pin width="13" height="13" /></div>
                    <div className="search-info">
                      <div className="search-name">Listings in {a.area}</div>
                      <div className="search-meta">{a.division === "sales" ? "Sales" : "Rentals"}</div>
                    </div>
                    <div className="search-phone">{a.count} contact{a.count === 1 ? "" : "s"}</div>
                  </button>
                ))}
              </div>
            )}
            {grouped.buyer.length > 0 && (
              <div className="search-group">
                <div className="search-group-label">Buyers / Tenants</div>
                {grouped.buyer.map((r) => (
                  <button key={r.id} className="search-result" onMouseDown={() => handleSelect(r)}>
                    <div className={`search-av b`}>{initials(r.name)}</div>
                    <div className="search-info">
                      <div className="search-name">{r.name}</div>
                      <div className="search-meta">{r.area} · {r.division}</div>
                    </div>
                    <div className="search-phone">{r.phone}</div>
                  </button>
                ))}
              </div>
            )}
            {grouped.seller.length > 0 && (
              <div className="search-group">
                <div className="search-group-label">Sellers / Landlords</div>
                {grouped.seller.map((r) => (
                  <button key={r.id} className="search-result" onMouseDown={() => handleSelect(r)}>
                    <div className={`search-av s`}>{initials(r.name)}</div>
                    <div className="search-info">
                      <div className="search-name">{r.name}</div>
                      <div className="search-meta">{r.area} · {r.division}</div>
                    </div>
                    <div className="search-phone">{r.phone}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {open && q.trim().length >= 2 && results.length === 0 && areaResults.length === 0 && (
          <div className="search-dropdown">
            <div className="search-empty">No results for "{q}"</div>
          </div>
        )}
      </div>
      <div className="top-right">
        {showPeriodToggle && (
          <div className="period-toggle" title="Rental view">
            <button className={viewPeriod === "monthly" ? "on" : ""} onClick={() => setViewPeriod("monthly")}>Monthly</button>
            <button className={viewPeriod === "yearly" ? "on" : ""} onClick={() => setViewPeriod("yearly")}>Yearly</button>
          </div>
        )}
        <div className="cur-pill" title="Display currency">
          <span style={{ fontSize: 14 }}>{CURRENCIES[currency]?.flag}</span>
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {Object.keys(CURRENCIES).map((k) => <option key={k}>{k}</option>)}
          </select>
        </div>
        <button className="icon-btn" title={darkMode ? "Light mode" : "Dark mode"} onClick={toggleDarkMode}>
          {darkMode ? <I.sun width="16" height="16" /> : <I.moon width="16" height="16" />}
        </button>

        <div className="me">
          <div className="av">{initl(broker?.name || broker?.email)}</div>
          <div>
            <div className="nm">{displayName}</div>
            <div className="ro">Broker</div>
          </div>
          <I.chev width="14" height="14" style={{ color: "var(--ink-400)" }} />
        </div>
      </div>
    </header>
  );
}
