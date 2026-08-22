import { I } from "../icons";
import {
  COUNTRIES, CURRENCIES, ptLabel,
  displayMoney, displayRange, displayRental, displayRentalRange,
  initials, formatPhone, divisionMeta,
} from "../constants";
import LabelBadge from "../LabelBadge";
import { exportMatchPDF } from "../pdf";
import ClientNotes from "../ClientNotes";

export default function RightPanel({
  selected, setSelected, buyers, sellers, matches, connectedSet, toggleConnect,
  showToast, displayCur, viewPeriod,
  onEdit, onDelete, waLink, callLink, brokerName, onSetLabel, broker,
}) {
  if (!selected) {
    return (
      <aside className="right">
        <div className="empty-right">
          <div className="ico"><I.match width="22" height="22" /></div>
          <div className="t">Pick a row to preview</div>
          <div className="s">Click a buyer or seller name to see their full profile, or View Both for a side-by-side match view.</div>
        </div>
      </aside>
    );
  }

  // ── Split view: buyer + seller side by side ──────────────────────────────
  if (selected.kind === "split") {
    const m = matches.find((x) => x.id === selected.matchId);
    const buyer  = buyers.find((x) => x.id === selected.buyerId);
    const seller = sellers.find((x) => x.id === selected.sellerId);
    if (!buyer || !seller) return null;
    const meta = divisionMeta(buyer.division);
    const isRental = buyer.division === "rentals";
    const stretch = m?.kind === "stretch";
    const bC = COUNTRIES.find((c) => c.code === buyer.country);
    const sC = COUNTRIES.find((c) => c.code === seller.country);
    const buyerPriceTxt = isRental
      ? displayRentalRange(buyer.min, buyer.max, buyer.cur, buyer.period, displayCur, viewPeriod)
      : displayRange(buyer.min, buyer.max, buyer.cur, displayCur);
    const sellerPriceTxt = isRental
      ? displayRental(seller.price, seller.cur, seller.period, displayCur, viewPeriod)
      : displayMoney(seller.price, seller.cur, displayCur);

    return (
      <aside className="right">
        <div className="right-head">
          <div>
            <div className="pre">// {meta.label.toLowerCase()} match{m ? ` · ${m.score}% fit` : ""}{stretch ? " · stretch" : ""}</div>
            <h2>{buyer.name.split(" ")[0]} ⇅ {seller.name.split(" ")[0]}</h2>
          </div>
          <button className="close" onClick={() => setSelected(null)}><I.x width="14" height="14" /></button>
        </div>
        <div className="right-body">
          {m && (
            <div className={`preview-banner${stretch ? " stretch" : ""}`} style={{ marginBottom: 12 }}>
              <div className="l">
                <div className="t">{buyer.area} → {seller.area}</div>
                <div className="b">{ptLabel(buyer.type)} · {meta.label}{stretch ? " · Stretch" : ""}</div>
              </div>
              <div className="score-tag">{m.score}%{stretch ? " stretch" : " fit"}</div>
            </div>
          )}
          {m && m.areaMatchType === "proximity" && m.distanceKm > 0 && (
            <div style={{ marginBottom: 10 }}>
              <span className="area-badge proximity">Near {m.matchedBuyerArea || m.matchedSellerArea} · {m.distanceKm}km</span>
            </div>
          )}
          {m && m.areaMatchType === "exact" && m.matchedBuyerArea && (
            <div style={{ marginBottom: 10 }}>
              <span className="area-badge exact">{m.matchedBuyerArea} ✓</span>
            </div>
          )}

          <div className="split-cards">
            {/* Buyer card */}
            <div className="split-card b">
              <div className="sc-role"><span className="dot" />{meta.buyerRole}</div>
              <div className="sc-av b">{initials(buyer.name)}</div>
              <div className="sc-name" title={buyer.name}>{buyer.name}</div>
              <div className="sc-phone">{bC?.flag} {buyer.dial} {formatPhone(buyer.phone)}</div>
              <div className="sc-area"><I.pin width="10" height="10" />{buyer.area}</div>
              <div className="sc-price">{buyerPriceTxt}</div>
              <div className="sc-tags">
                <span className="tag" style={{ fontSize: 9, padding: "2px 5px" }}>{ptLabel(buyer.type)}</span>
                <LabelBadge label={buyer.label} kind="buyer" id={buyer.id} onChange={onSetLabel} size="sm" />
              </div>
              {buyer.referredBy && (
                <div className="sc-ref"><span className="sc-ref-lbl">via</span> {buyer.referredBy}</div>
              )}
              {buyer.notes && <div className="nt" style={{ fontSize: 11, marginTop: 4 }}>{buyer.notes}</div>}
              <div className="sc-actions">
                <a href={waLink ? waLink(buyer, brokerName) : "#"} target="_blank" rel="noreferrer" className="sc-wa" title="WhatsApp"><I.whats width="12" height="12" /></a>
                <a href={callLink ? callLink(buyer) : "#"} className="sc-call" title="Call"><I.phone width="12" height="12" /></a>
                <button className="sc-edit" title="Edit" onClick={() => onEdit && onEdit("buyer", buyer)}><I.edit width="12" height="12" /></button>
              </div>
            </div>

            {/* Seller card */}
            <div className="split-card s">
              <div className="sc-role"><span className="dot" />{meta.sellerRole}</div>
              <div className="sc-av s">{initials(seller.name)}</div>
              <div className="sc-name" title={seller.name}>{seller.name}</div>
              <div className="sc-phone">{sC?.flag} {seller.dial} {formatPhone(seller.phone)}</div>
              <div className="sc-area"><I.pin width="10" height="10" />{seller.area}</div>
              <div className="sc-price">{sellerPriceTxt}</div>
              <div className="sc-tags">
                <span className="tag" style={{ fontSize: 9, padding: "2px 5px" }}>{ptLabel(seller.type)}</span>
                <LabelBadge label={seller.label} kind="seller" id={seller.id} onChange={onSetLabel} size="sm" />
              </div>
              {seller.referredBy && (
                <div className="sc-ref"><span className="sc-ref-lbl">via</span> {seller.referredBy}</div>
              )}
              {seller.notes && <div className="nt" style={{ fontSize: 11, marginTop: 4 }}>{seller.notes}</div>}
              <div className="sc-actions">
                <a href={waLink ? waLink(seller, brokerName) : "#"} target="_blank" rel="noreferrer" className="sc-wa" title="WhatsApp"><I.whats width="12" height="12" /></a>
                <a href={callLink ? callLink(seller) : "#"} className="sc-call" title="Call"><I.phone width="12" height="12" /></a>
                <button className="sc-edit" title="Edit" onClick={() => onEdit && onEdit("seller", seller)}><I.edit width="12" height="12" /></button>
              </div>
            </div>
          </div>

          {m && (() => {
            const done = connectedSet.has(m.id);
            return (
              <div className="preview-actions">
                <button className={`connect full ${done ? "done" : ""}`} onClick={async () => {
                  const was = connectedSet.has(m.id);
                  await toggleConnect(m.id);
                  if (!was) showToast(`Connected · ${buyer.name.split(" ")[0]} → ${seller.name.split(" ")[0]}`);
                }}>
                  {done ? <><I.check /> Connected — undo</> : <>Connect {meta.buyerRole.toLowerCase()} &amp; {meta.sellerRole.toLowerCase()}</>}
                </button>
                <button className="pdf-btn full" onClick={() => exportMatchPDF(m, displayCur, viewPeriod, brokerName)}>
                  <I.export width="13" height="13" /> Export Match PDF
                </button>
              </div>
            );
          })()}
        </div>
      </aside>
    );
  }

  // ── Single contact profile: buyer or seller ───────────────────────────────
  const isBuyer = selected.kind === "buyer";
  const list = isBuyer ? buyers : sellers;
  const p = list.find((x) => x.id === selected.id);
  if (!p) return null;
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

  return (
    <aside className="right">
      <div className="right-head">
        <div>
          <div className="pre">// {meta.label.toLowerCase()} · {role.toLowerCase()}{p.intl ? " · international" : ""}</div>
          <h2>{p.name}</h2>
        </div>
        <button className="close" onClick={() => setSelected(null)}><I.x width="14" height="14" /></button>
      </div>
      <div className="right-body">
        <div className={`person-card ${isBuyer ? "b" : "s"}`}>
          <div className="role"><span className="dot" />{role}{p.intl && <span className="intl-tag" style={{ marginLeft: "auto" }}>INTL</span>}</div>
          <div className="nm">{p.name}</div>
          <div className="ph">{c?.flag} {p.dial} {formatPhone(p.phone)}</div>
          <div className="ar"><I.pin width="13" height="13" />{p.area}, {c?.name}</div>
          <div className="pr">{priceTxt}</div>
          <div className="tg">
            <span className="tag">{ptLabel(p.type)}</span>
            <span className="tag">{CURRENCIES[p.cur]?.flag} {p.cur}</span>
            <LabelBadge label={p.label} kind={isBuyer ? "buyer" : "seller"} id={p.id} onChange={onSetLabel} size="sm" />
          </div>
          {p.referredBy && (
            <div className="profile-ref">
              <span className="profile-ref-lbl">Referred by</span>
              <span className="profile-ref-val">{p.referredBy}</span>
            </div>
          )}
          {p.notes && <div className="nt">{p.notes}</div>}
        </div>

        <div className="preview-actions" style={{ marginTop: 14 }}>
          <a className="wa" href={waLink ? waLink(p, brokerName) : "#"} target="_blank" rel="noreferrer"><I.whats width="14" height="14" /> WhatsApp</a>
          <a className="call-btn" href={callLink ? callLink(p) : "#"}><I.phone width="14" height="14" /> Call</a>
          <button className="edit-btn" onClick={() => onEdit && onEdit(isBuyer ? "buyer" : "seller", p)}><I.edit width="14" height="14" /> Edit</button>
          <button className="del-btn" onClick={() => onDelete && onDelete(isBuyer ? "buyer" : "seller", p)}><I.trash width="14" height="14" /> Delete</button>
        </div>

        <div className="timeline">
          <div className="tl-head">// {relatedMatches.length} match{relatedMatches.length === 1 ? "" : "es"}</div>
          {relatedMatches.length === 0 && <div style={{ fontSize: 12, color: "var(--ink-500)" }}>No matches yet.</div>}
          {relatedMatches.map((m) => {
            const counter = isBuyer ? m.seller : m.buyer;
            const cPrice = m.buyer.division === "rentals"
              ? displayRental(m.seller.price, m.seller.cur, m.seller.period, displayCur, viewPeriod)
              : displayMoney(m.seller.price, m.seller.cur, displayCur);
            return (
              <div key={m.id} className="tl-row" style={{ cursor: "pointer" }}
                onClick={() => setSelected({ kind: "split", matchId: m.id, buyerId: m.buyer.id, sellerId: m.seller.id })}>
                <div className="tdot" style={{ background: m.kind === "stretch" ? "var(--gold-500)" : "var(--gold-600)" }} />
                <div className="tt">→ <b>{counter.name}</b> · {cPrice}{m.kind === "stretch" ? " · stretch" : ""}</div>
                <div className="tts">{m.score}%</div>
              </div>
            );
          })}
        </div>
        <ClientNotes clientId={p.id} clientType={isBuyer ? "buyer" : "seller"} />
      </div>
    </aside>
  );
}
