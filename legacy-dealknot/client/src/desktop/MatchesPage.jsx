import { useState, useMemo } from "react";
import { I } from "../icons";
import {
  CURRENCIES, ptLabel, displayMoney, displayRange,
  displayRental, displayRentalRange, initials, divisionMeta,
} from "../constants";
import { checkAreaProximity } from "../areaCoords";
import { motion } from "framer-motion";
import { listContainer, listItem, tapBounce } from "../motion";
import { exportMatchPDF } from "../pdf";

const SUGGEST_RADIUS_KM = 10;

function AreaBadge({ m }) {
  if (!m.matchedBuyerArea && !m.distanceKm) return null;
  if (m.areaMatchType === "proximity" && m.distanceKm > 0) {
    return (
      <span className="area-badge proximity" style={{ marginTop: 4, display: "inline-flex" }}>
        Near {m.matchedBuyerArea || m.matchedSellerArea} · {m.distanceKm}km
      </span>
    );
  }
  if (m.matchedBuyerArea) {
    return (
      <span className="area-badge exact" style={{ marginTop: 4, display: "inline-flex" }}>
        {m.matchedBuyerArea} ✓
      </span>
    );
  }
  return null;
}

export default function MatchesPage({
  matches, connectedSet, toggleConnect, selected, setSelected, showToast,
  displayCur, viewPeriod, division, waLink, callLink, brokerName, broker, go,
  buyers = [], sellers = [],
}) {
  const meta = divisionMeta(division);
  const isRental = division === "rentals";
  const all = matches.filter((m) => m.buyer.division === division);
  const [filter, setFilter] = useState("all");
  const [extraMatches, setExtraMatches] = useState([]);
  const [dismissedSuggestions, setDismissedSuggestions] = useState(new Set());
  const [showSuggestions, setShowSuggestions] = useState(true);

  const filtered = filter === "all" ? all
    : filter === "new" ? all.filter((m) => !connectedSet.has(m.id))
    : filter === "stretch" ? all.filter((m) => m.kind === "stretch")
    : all.filter((m) => connectedSet.has(m.id));

  // Compute nearby suggestions: buyers with 0 matches but sellers within SUGGEST_RADIUS_KM
  const suggestions = useMemo(() => {
    const matchedBuyerIds = new Set(all.map((m) => m.buyer.id));
    const extraIds = new Set(extraMatches.map((m) => m.id));
    const dBuyers = buyers.filter((b) => b.division === division && !matchedBuyerIds.has(b.id));
    const dSellers = sellers.filter((s) => s.division === division);
    const results = [];
    for (const b of dBuyers) {
      const bAreas = (b.area || "").split(",").map((a) => a.trim()).filter(Boolean);
      for (const s of dSellers) {
        const sAreas = (s.area || "").split(",").map((a) => a.trim()).filter(Boolean);
        const proximity = checkAreaProximity(bAreas, sAreas, SUGGEST_RADIUS_KM);
        if (!proximity || proximity.type === "exact") continue; // exact already covered by matches
        const key = `${b.id}-${s.id}`;
        if (extraIds.has(key) || dismissedSuggestions.has(key)) continue;
        results.push({ key, buyer: b, seller: s, proximity });
      }
    }
    return results.slice(0, 12);
  }, [buyers, sellers, all, extraMatches, dismissedSuggestions, division]);

  const handleConnect = async (m) => {
    const wasConnected = connectedSet.has(m.id);
    await toggleConnect(m.id);
    if (!wasConnected) showToast(`Connected · ${m.buyer.name.split(" ")[0]} → ${m.seller.name.split(" ")[0]}`);
  };

  const includeInMatches = (suggestion) => {
    const { buyer: b, seller: s, proximity } = suggestion;
    const id = `${b.id}-${s.id}`;
    const isRentalB = b.division === "rentals";
    const sPrice = isRentalB
      ? (s.period === "yearly" ? Number(s.price) / 12 : Number(s.price))
      : Number(s.price);
    const bMax = isRentalB
      ? (b.period === "yearly" ? Number(b.max) / 12 : Number(b.max))
      : Number(b.max);
    const bMin = isRentalB
      ? (b.period === "yearly" ? Number(b.min) / 12 : Number(b.min))
      : Number(b.min);
    let kind = "exact";
    if (sPrice > bMax && sPrice <= bMax * 1.25) kind = "stretch";
    else if (sPrice < bMin || sPrice > bMax * 1.25) kind = "proximity_only";
    const mid = (bMin + bMax) / 2;
    const span = (bMax - bMin) / 2 || 1;
    const score = Math.max(50, Math.round(75 - proximity.distanceKm * 2 - (1 - Math.min(1, Math.abs(sPrice - mid) / span)) * (-10)));
    setExtraMatches((prev) => [...prev, {
      id, buyer: b, seller: s, score, kind,
      connected: connectedSet.has(id),
      areaMatchType: "proximity",
      matchedBuyerArea: proximity.buyerArea,
      matchedSellerArea: proximity.sellerArea,
      distanceKm: proximity.distanceKm,
      matchedArea: null,
    }]);
  };

  const dismissSuggestion = (key) => {
    setDismissedSuggestions((prev) => new Set([...prev, key]));
  };

  const stretchCount = all.filter((m) => m.kind === "stretch").length;
  const allFiltered = [...filtered, ...(filter === "all" ? extraMatches.filter((m) => !connectedSet.has(m.id) || filter !== "new") : [])];

  const buyerPrice = (m) => isRental
    ? displayRentalRange(m.buyer.min, m.buyer.max, m.buyer.cur, m.buyer.period, displayCur, viewPeriod)
    : displayRange(m.buyer.min, m.buyer.max, m.buyer.cur, displayCur);
  const sellerPrice = (m) => isRental
    ? displayRental(m.seller.price, m.seller.cur, m.seller.period, displayCur, viewPeriod)
    : displayMoney(m.seller.price, m.seller.cur, displayCur);

  const goToProfile = (e, kind, id) => {
    e.stopPropagation();
    e.nativeEvent.stopImmediatePropagation();
    setSelected({ kind, id });
  };

  return (
    <div className="main fade-in">
      <div className="page-head">
        <div>
          <div className="pre">// {meta.label.toLowerCase()} · {all.length} active</div>
          <h1>{meta.label} matches <em>worth a call.</em></h1>
          <div className="sub">{meta.buyerRole} → {meta.sellerRole}, same area &amp; type, price inside budget. Proximity matching enabled for Chennai areas.</div>
        </div>
        <div className="head-actions" />
      </div>

      <div className="lst-tabs" style={{ display: "inline-flex", marginBottom: 14, flexWrap: "wrap" }}>
        <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All ({all.length})</button>
        <button className={filter === "new" ? "on" : ""} onClick={() => setFilter("new")}>New ({all.length - all.filter((m) => connectedSet.has(m.id)).length})</button>
        <button className={filter === "stretch" ? "on" : ""} onClick={() => setFilter("stretch")}>Stretch ({stretchCount})</button>
        <button className={filter === "done" ? "on" : ""} onClick={() => setFilter("done")}>Connected ({all.filter((m) => connectedSet.has(m.id)).length})</button>
      </div>

      {allFiltered.length === 0 && (
        <div style={{ textAlign: "center", padding: "60px 0", color: "var(--ink-400)" }}>No {meta.label.toLowerCase()} matches in this filter.</div>
      )}

      <motion.div className="match-grid" variants={listContainer} initial="initial" animate="enter">
        {allFiltered.map((m) => {
          const done = connectedSet.has(m.id);
          const isSel = selected?.kind === "split" && selected.matchId === m.id;
          const stretch = m.kind === "stretch";
          return (
            <motion.div key={m.id} className={`match-row ${isSel ? "sel" : ""} ${stretch ? "stretch" : ""} ${m.areaMatchType === "proximity" ? "proximity-match" : ""}`}
              variants={listItem} whileHover={{ y: -2 }} whileTap={tapBounce}>
              <div className="side-c b">
                <div className="role-line"><span className="dot" />{meta.buyerRole}{m.buyer.intl && <span className="intl-tag" style={{ marginLeft: 6 }}>INTL</span>}{stretch && <span className="stretch-tag" style={{ marginLeft: 6 }}>Stretch</span>}</div>
                <div className="nmline">
                  <div className="av b">{initials(m.buyer.name)}</div>
                  <div>
                    <button type="button" className="nm-h profile-link" title="View full profile"
                      onClick={(e) => goToProfile(e, "buyer", m.buyer.id)}>
                      {m.buyer.name} <span style={{ fontSize: 10, color: "var(--gold-600)", marginLeft: 2 }}>→</span>
                    </button>
                    <div className="area-h"><I.pin width="11" height="11" />{m.buyer.area}</div>
                    <AreaBadge m={m} />
                  </div>
                </div>
                <div className="price-h">{buyerPrice(m)}</div>
                <div className="tg-row">
                  <span className="tag">{ptLabel(m.buyer.type)}</span>
                  <span className="tag">{CURRENCIES[m.buyer.cur]?.flag} {m.buyer.cur}</span>
                </div>
              </div>

              <div className="center-c">
                <div className={`score-circle ${stretch ? "stretch" : ""}`} style={{ "--p": m.score }}>
                  <span>{m.score}<small>% fit</small></span>
                </div>
                <div className="actions-stack" onClick={(e) => e.stopPropagation()}>
                  <button className={`connect ${done ? "done" : ""}`} onClick={() => handleConnect(m)}>
                    {done ? <><I.check width="11" height="11" /> Connected</> : <>Connect</>}
                  </button>
                  <button className="view-both-btn" onClick={(e) => {
                    e.stopPropagation();
                    e.nativeEvent.stopImmediatePropagation();
                    setSelected({ kind: "split", matchId: m.id, buyerId: m.buyer.id, sellerId: m.seller.id });
                  }}>
                    ⊞ View Both
                  </button>
                  <a className="wa" href={waLink ? waLink(m.buyer, brokerName) : "#"} target="_blank" rel="noreferrer"><I.whats width="11" height="11" /> WA {meta.buyerRole}</a>
                  <a className="wa" href={waLink ? waLink(m.seller, brokerName) : "#"} target="_blank" rel="noreferrer"><I.whats width="11" height="11" /> WA {meta.sellerRole}</a>
                  <a className="call" href={callLink ? callLink(m.buyer) : "#"}><I.phone width="11" height="11" /> Call {meta.buyerRole}</a>
                  <a className="call" href={callLink ? callLink(m.seller) : "#"}><I.phone width="11" height="11" /> Call {meta.sellerRole}</a>
                  {(() => {
                    const bNum = (m.buyer.dial + m.buyer.phone).replace(/\D/g, "");
                    const shareMsg = encodeURIComponent(
                      `Hi ${m.buyer.name.split(" ")[0]}, I have a property match for you!\n📍 Location: ${m.seller.area}\n🏠 Type: ${ptLabel(m.seller.type)}\n💰 Asking: ${sellerPrice(m)}\nInterested? Let me know and I'll connect you with the seller.\n${brokerName}, DealKnot`
                    );
                    return (
                      <a className="wa-share-btn" href={`https://wa.me/${bNum}?text=${shareMsg}`} target="_blank" rel="noreferrer">
                        <I.whats width="11" height="11" /> Share Match
                      </a>
                    );
                  })()}
                  <button className="pdf-btn" onClick={() => exportMatchPDF(m, displayCur, viewPeriod, brokerName)}>
                    <I.export width="11" height="11" /> Export PDF
                  </button>
                </div>
              </div>

              <div className="side-c s">
                <div className="role-line"><span className="dot" />{meta.sellerRole}{m.seller.intl && <span className="intl-tag" style={{ marginLeft: 6 }}>INTL</span>}</div>
                <div className="nmline">
                  <div>
                    <button type="button" className="nm-h profile-link" title="View full profile"
                      onClick={(e) => goToProfile(e, "seller", m.seller.id)}>
                      <span style={{ fontSize: 10, color: "var(--gold-600)", marginRight: 2 }}>←</span> {m.seller.name}
                    </button>
                    <div className="area-h" style={{ justifyContent: "flex-end" }}><I.pin width="11" height="11" />{m.seller.area}</div>
                  </div>
                  <div className="av s">{initials(m.seller.name)}</div>
                </div>
                <div className="price-h">{sellerPrice(m)}</div>
                <div className="tg-row">
                  <span className="tag">{ptLabel(m.seller.type)}</span>
                  <span className="tag">{CURRENCIES[m.seller.cur]?.flag} {m.seller.cur}</span>
                </div>
              </div>
            </motion.div>
          );
        })}
      </motion.div>

      {/* ── Nearby Suggestions Panel ── */}
      {suggestions.length > 0 && filter === "all" && (
        <div className="suggestions-panel">
          <div className="suggestions-head" onClick={() => setShowSuggestions((v) => !v)}>
            <div>
              <div style={{ fontFamily: "Fraunces, serif", fontWeight: 600, fontSize: 16, color: "var(--navy-900)" }}>
                📍 Nearby {meta.sellerRole}s — no exact area match
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 2 }}>
                {suggestions.length} {meta.buyer_role || meta.buyerRole.toLowerCase()}s have sellers within {SUGGEST_RADIUS_KM}km but different area names
              </div>
            </div>
            <span style={{ fontSize: 13, color: "var(--ink-400)" }}>{showSuggestions ? "▲ hide" : "▼ show"}</span>
          </div>
          {showSuggestions && (
            <div style={{ padding: "0 18px 14px" }}>
              {suggestions.map((s) => (
                <div key={s.key} className="suggestion-row">
                  <div className="suggestion-info">
                    <div className="suggestion-names">
                      <span className="av-mini b" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", fontSize: 9, fontWeight: 700, background: "var(--navy-100)", color: "var(--navy-800)", marginRight: 6, flexShrink: 0 }}>{initials(s.buyer.name)}</span>
                      <b>{s.buyer.name.split(" ")[0]}</b>
                      <span style={{ color: "var(--ink-400)", margin: "0 6px" }}>looking near</span>
                      <span style={{ color: "var(--ink-700)" }}>{s.proximity.buyerArea}</span>
                    </div>
                    <div className="suggestion-detail">
                      <span className="av-mini s" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, borderRadius: "50%", fontSize: 9, fontWeight: 700, background: "var(--gold-100)", color: "var(--gold-700)", marginRight: 6, flexShrink: 0 }}>{initials(s.seller.name)}</span>
                      <b>{s.seller.name.split(" ")[0]}</b>
                      <span style={{ color: "var(--ink-400)", margin: "0 4px" }}>is in</span>
                      <span style={{ color: "var(--ink-700)", fontWeight: 600 }}>{s.proximity.sellerArea}</span>
                      <span className="area-badge proximity" style={{ marginLeft: 8 }}>{s.proximity.distanceKm}km away</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexShrink: 0, alignItems: "center" }}>
                    <button className="btn primary" style={{ fontSize: 11, padding: "6px 10px" }}
                      onClick={() => includeInMatches(s)}>Include in matches</button>
                    <button className="btn ghost" style={{ fontSize: 11, padding: "6px 10px" }}
                      onClick={() => dismissSuggestion(s.key)}>Dismiss</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
