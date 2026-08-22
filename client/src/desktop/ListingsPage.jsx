import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { listContainer, listItem, tapBounce } from "../motion";
import { I } from "../icons";
import {
  COUNTRIES, CURRENCIES, ptShort, ptLabel,
  displayMoney, displayRange, displayRental, displayRentalRange,
  initials, formatPhone,
  divisionMeta, LABELS, labelSort, labelMeta,
} from "../constants";
import { AREAS } from "../PlacesAutocomplete";
import LabelBadge from "../LabelBadge";
import { exportListingsPDF } from "../pdf";
import { exportExcel } from "../excel";
import ImportModal from "../ImportModal";
import NameAutocomplete from "../NameAutocomplete";

function exportCSV(rows, filename) {
  const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const headers = ["Name", "Phone", "Country", "Area", "Property Type", "Budget/Price", "Currency", "Status", "International", "Notes", "Date Added"];
  const lines = [
    headers.join(","),
    ...rows.map((p) => [
      escape(p.name),
      escape((p.dial || "") + (p.phone || "")),
      escape(COUNTRIES.find((c) => c.code === p.country)?.name || p.country),
      escape(p.area),
      escape(ptLabel(p.type)),
      escape(p.min != null ? `${p.min}–${p.max}` : (p.price ?? "")),
      escape(p.cur),
      escape(p.label || "active"),
      escape(p.intl ? "Yes" : "No"),
      escape(p.notes || ""),
      escape(p.createdAt ? new Date(p.createdAt).toLocaleDateString("en-GB") : ""),
    ].join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export default function ListingsPage({
  buyers, sellers, matches, selected, setSelected, go, displayCur, viewPeriod,
  division, onEdit, onDelete, waLink, callLink, brokerName,
  onSetLabel, onBumpBudget, broker, onBulkImport,
  externalSearch, onConsumeExternalSearch,
}) {
  const meta = divisionMeta(division);
  const isRental = division === "rentals";
  const [tab, setTab] = useState("buyers");
  const [q, setQ] = useState("");
  const [labelFilter, setLabelFilter] = useState("all");
  const [showImport, setShowImport] = useState(false);
  const [showRefBy, setShowRefBy] = useState(false);

  // Search handed off from the global top bar (e.g. clicking "Listings in Adyar")
  useEffect(() => {
    if (externalSearch) {
      setQ(externalSearch);
      onConsumeExternalSearch?.();
    }
  }, [externalSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  // Does the query look like a location? (case-insensitive contains against known areas)
  const lq = q.trim().toLowerCase();
  const areaHit = lq.length >= 2 ? AREAS.find((a) => a.toLowerCase().includes(lq)) : null;

  const filteredBuyers = buyers
    .filter((b) => b.division === division)
    .filter((p) => labelFilter === "all" || p.label === labelFilter)
    .filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.area.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => labelSort(a.label) - labelSort(b.label));
  const filteredSellers = sellers
    .filter((s) => s.division === division)
    .filter((p) => labelFilter === "all" || p.label === labelFilter)
    .filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.area.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => labelSort(a.label) - labelSort(b.label));

  const buyerCount = buyers.filter((b) => b.division === division).length;
  const sellerCount = sellers.filter((s) => s.division === division).length;
  const list = tab === "buyers" ? filteredBuyers : filteredSellers;

  const buyerRoleLower = meta.buyerRole.toLowerCase();
  const sellerRoleLower = meta.sellerRole.toLowerCase();
  const addRoute = tab === "buyers" ? `${division}:addBuyer` : `${division}:addSeller`;

  const importKind = tab === "buyers" ? "buyer" : "seller";

  return (
    <div className="main fade-in">
      {showImport && (
        <ImportModal
          kind={importKind}
          division={division}
          onClose={() => setShowImport(false)}
          onBulkImport={(records) => onBulkImport(records, importKind)}
        />
      )}
      <div className="page-head">
        <div>
          <div className="pre">// {meta.label.toLowerCase()} · {buyerCount + sellerCount} contacts</div>
          <h1>{meta.label} <em>listings.</em></h1>
          <div className="sub">All {meta.buyerRole.toLowerCase()}s and {meta.sellerRole.toLowerCase()}s in your book.</div>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={() => {
            const list = tab === "buyers" ? filteredBuyers : filteredSellers;
            const roleName = tab === "buyers" ? meta.buyerRole : meta.sellerRole;
            const divLabel = division === "sales" ? "Sales" : "Rentals";
            exportCSV(list, `DealKnot-${divLabel}-${roleName}s.csv`);
          }}>
            <I.download width="14" height="14" /> Export CSV
          </button>
          <button className="btn ghost" onClick={() => {
            const exportList = tab === "buyers" ? filteredBuyers : filteredSellers;
            const roleName = tab === "buyers" ? meta.buyerRole : meta.sellerRole;
            const divLabel = division === "sales" ? "Sales" : "Rentals";
            exportExcel(exportList, tab === "buyers" ? "buyer" : "seller", division, divLabel, roleName);
          }}>
            <I.download width="14" height="14" /> Export Excel
          </button>
          <button className="btn ghost" onClick={() => {
            const exportList = (tab === "buyers" ? filteredBuyers : filteredSellers).map((p) => ({
              ...p,
              _matchCount: matches.filter((m) => tab === "buyers" ? m.buyer.id === p.id : m.seller.id === p.id).length,
            }));
            exportListingsPDF(exportList, tab, division, brokerName, displayCur);
          }}>
            <I.export width="14" height="14" /> Export PDF
          </button>
          <button className="btn ghost" onClick={() => setShowImport(true)}>
            <I.upload width="14" height="14" /> 📥 Import
          </button>
          <button className="btn primary" onClick={() => go(addRoute)}>
            <I.plus /> Add {tab === "buyers" ? buyerRoleLower : sellerRoleLower}
          </button>
        </div>
      </div>

      <div className="lst-controls">
        <div className="lst-tabs">
          <button className={tab === "buyers" ? "on" : ""} onClick={() => setTab("buyers")}>{meta.buyerRole}s ({buyerCount})</button>
          <button className={tab === "sellers" ? "on" : ""} onClick={() => setTab("sellers")}>{meta.sellerRole}s ({sellerCount})</button>
        </div>
        <div className="search-box">
          <I.search width="16" height="16" />
          <NameAutocomplete
            value={q}
            onChange={setQ}
            onSelect={(c) => { setSelected({ kind: c.type, id: c.id }); setQ(""); }}
            placeholder={`Search ${tab}…`}
          />
        </div>
      </div>

      {areaHit && (
        <div className="area-search-hint">
          <I.pin width="12" height="12" />
          Location search — showing {tab} in areas matching <b>“{q.trim()}”</b> · {list.length} result{list.length === 1 ? "" : "s"}
          <button className="area-search-clear" onClick={() => setQ("")}>✕ clear</button>
        </div>
      )}

      <div className="label-filter-row">
        <button className={`label-filter ${labelFilter === "all" ? "on" : ""}`} onClick={() => setLabelFilter("all")}>All</button>
        {LABELS.map((l) => (
          <button key={l.id} className={`label-filter label-${l.id} ${labelFilter === l.id ? "on" : ""}`}
            onClick={() => setLabelFilter(l.id)}>
            <span aria-hidden>{l.icon}</span> {l.name}
          </button>
        ))}
      </div>

      <div className="panel">
        <table className="lst-table">
          <thead>
            <tr>
              <th>Name</th><th>Status</th><th>Country</th><th>Area</th><th>Type</th>
              <th>{tab === "buyers" ? "Budget" : "Asking"}</th>
              <th>Phone</th>
              {showRefBy && <th>Ref. By</th>}
              <th>Matches</th>
              <th style={{ textAlign: "right" }}>
                <button
                  onClick={() => setShowRefBy((v) => !v)}
                  style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--line)", background: showRefBy ? "var(--gold-100)" : "transparent", color: showRefBy ? "var(--gold-700)" : "var(--ink-400)", cursor: "pointer", fontFamily: "inherit" }}
                  title="Toggle Referred By column"
                >
                  {showRefBy ? "− Ref" : "+ Ref"}
                </button>
              </th>
            </tr>
          </thead>
          <motion.tbody variants={listContainer} initial="initial" animate="enter" key={`${tab}-${labelFilter}`}>
            {list.map((p) => {
              const c = COUNTRIES.find((x) => x.code === p.country);
              const mc = matches.filter((m) => tab === "buyers" ? m.buyer.id === p.id : m.seller.id === p.id).length;
              const isSel = selected?.kind === (tab === "buyers" ? "buyer" : "seller") && selected.id === p.id;
              const kind = tab === "buyers" ? "buyer" : "seller";
              const priceTxt = tab === "buyers"
                ? (isRental
                  ? displayRentalRange(p.min, p.max, p.cur, p.period, displayCur, viewPeriod)
                  : displayRange(p.min, p.max, p.cur, displayCur))
                : (isRental
                  ? displayRental(p.price, p.cur, p.period, displayCur, viewPeriod)
                  : displayMoney(p.price, p.cur, displayCur));
              return (
                <motion.tr key={p.id} className={isSel ? "sel" : ""}
                  variants={listItem}
                  onClick={() => setSelected({ kind, id: p.id })}>
                  <td>
                    <div className="nm-cell">
                      <div className="nm">
                        <div className={`av-mini ${tab === "buyers" ? "b" : "s"}`}>{initials(p.name)}</div>
                        <span className="nm-link" onClick={(e) => { e.stopPropagation(); setSelected({ kind, id: p.id }); }}>{p.name}</span>
                        {p.intl && <span className="intl-tag">INTL</span>}
                        <button className="profile-nav-btn" title="Open profile" onClick={(e) => { e.stopPropagation(); setSelected({ kind, id: p.id }); }}>↗</button>
                      </div>
                    </div>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <LabelBadge label={p.label} kind={kind} id={p.id} onChange={onSetLabel} size="sm" />
                  </td>
                  <td>{c?.flag} {c?.name}</td>
                  <td>
                    <div className="area-pills">
                      {String(p.area || "").split(",").map((a) => a.trim()).filter(Boolean).map((a) => (
                        <span key={a} className={`area-pill${lq && a.toLowerCase().includes(lq) ? " hit" : ""}`}>
                          <I.pin width="9" height="9" />{a}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td><span className="tag">{ptShort(p.type)}</span></td>
                  <td className="price-cell">{priceTxt}</td>
                  <td style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11.5, color: "var(--ink-500)" }}>
                    {p.dial} {formatPhone(p.phone)}
                  </td>
                  {showRefBy && <td style={{ fontSize: 11.5, color: "var(--ink-500)", maxWidth: 100, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.referredBy || <span style={{ color: "var(--ink-300)" }}>—</span>}</td>}
                  <td><span className={`match-pill ${mc === 0 ? "zero" : ""}`}>{mc === 0 ? "none" : mc}</span></td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="row-actions">
                      {tab === "buyers" && p.cur === "INR" && (
                        <>
                          <button className="row-action-btn bump" title="+25 L (₹25 lakhs)" onClick={() => onBumpBudget?.(p.id, 2500000)}>+25L</button>
                          <button className="row-action-btn bump" title="+50 L (₹50 lakhs)" onClick={() => onBumpBudget?.(p.id, 5000000)}>+50L</button>
                        </>
                      )}
                      {tab === "buyers" && p.cur !== "INR" && (
                        <>
                          <button className="row-action-btn bump" title="+25 (in thousands of native currency)" onClick={() => onBumpBudget?.(p.id, 25000)}>+25K</button>
                          <button className="row-action-btn bump" title="+50 (in thousands of native currency)" onClick={() => onBumpBudget?.(p.id, 50000)}>+50K</button>
                        </>
                      )}
                      <a className="row-action-btn wa" href={waLink(p, brokerName)} target="_blank" rel="noreferrer" title="WhatsApp"><I.whats width="13" height="13" /></a>
                      <a className="row-action-btn" href={callLink(p)} title="Call"><I.phone width="13" height="13" /></a>
                      <button className="row-action-btn" title="Edit" onClick={() => onEdit(kind, p)}><I.edit width="13" height="13" /></button>
                      <button className="row-action-btn del" title="Delete" onClick={() => onDelete(kind, p)}><I.trash width="13" height="13" /></button>
                    </div>
                  </td>
                </motion.tr>
              );
            })}
            {list.length === 0 && (
              <tr><td colSpan={showRefBy ? 10 : 9} style={{ textAlign: "center", color: "var(--ink-400)", padding: "28px 0" }}>No {tab} match this filter.</td></tr>
            )}
          </motion.tbody>
        </table>
      </div>
    </div>
  );
}
