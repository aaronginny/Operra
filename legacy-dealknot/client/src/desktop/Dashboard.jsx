import { I } from "../icons";
import {
  COUNTRIES, CURRENCIES, ptShort, displayMoney, displayRange,
  displayRental, displayRentalRange, initials, labelSort,
} from "../constants";
import LabelBadge from "../LabelBadge";

function StatCard({ kind, ico, label, value, delta, deltaDir = "up", spark }) {
  return (
    <div className={`stat ${kind}`}>
      <div className="top">
        <div className="ico">{ico}</div>
        <div className="lbl">{label}</div>
      </div>
      <div className="val">{value}</div>
      <div className={`delta ${deltaDir === "down" ? "dn" : ""}`}>
        <I.arrowUp width="12" height="12" style={deltaDir === "down" ? { transform: "rotate(180deg)" } : {}} />
        <b>{delta}</b> <span>vs last week</span>
      </div>
      <svg className="spark" viewBox="0 0 60 28" preserveAspectRatio="none">
        <polyline fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
          style={{ color: kind === "pending" ? "var(--red)" : kind === "matches" ? "var(--green)" : kind === "sellers" ? "var(--gold-600)" : "var(--navy-600)" }}
          points={spark} />
      </svg>
    </div>
  );
}

export default function Dashboard({ buyers, sellers, matches, connectedSet, selected, setSelected, go,
  showToast, broker, displayCur, viewPeriod,
  onSetLabel }) {
  const recent = matches.slice(0, 6);
  const intlCount = [...buyers, ...sellers].filter((p) => p.intl).length;
  const greetName = broker?.nickname || broker?.name?.split(" ")[0] || broker?.email?.split("@")[0] || "broker";

  const sortedBuyers = [...buyers].sort((a, b) => labelSort(a.label) - labelSort(b.label));

  return (
    <div className="main fade-in">
      <div className="page-head">
        <div>
          <div className="pre">// {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</div>
          <h1>Good to see you, <em style={{ color: "var(--gold-400)" }}>{greetName}</em>.</h1>
          <div className="sub">{matches.length} active matches · {intlCount} international leads</div>
        </div>
        <div className="head-actions">
          <button className="btn ghost" onClick={() => go("sales:addBuyer")}><I.userPlus /> Add buyer</button>
          <button className="btn primary" onClick={() => go("sales:addSeller")}><I.plus /> Add seller</button>
        </div>
      </div>

      <div className="stat-row">
        <StatCard kind="buyers"  ico={<I.user width="16" height="16" />}  label="Total buyers / tenants"     value={buyers.length}  delta={`${buyers.filter(b => b.division === "sales").length} sales`} spark="0,18 8,14 16,16 24,10 32,12 40,8 48,10 60,4" />
        <StatCard kind="sellers" ico={<I.tag width="16" height="16" />}   label="Total sellers / landlords"  value={sellers.length} delta={`${sellers.filter(s => s.division === "sales").length} sales`} spark="0,16 10,18 20,12 30,14 40,10 50,12 60,8" />
        <StatCard kind="matches" ico={<I.match width="16" height="16" />} label="Active matches"             value={matches.length} delta={`${matches.filter(m => m.kind === "exact").length} exact`} spark="0,20 10,18 20,14 30,16 40,8 50,10 60,4" />
        <StatCard kind="pending" ico={<I.flame width="14" height="14" />} label="Follow-ups"                 value={matches.length - connectedSet.size} delta={`${connectedSet.size} connected`} deltaDir="down" spark="0,8 10,12 20,10 30,14 40,12 50,16 60,18" />
      </div>

      <div className="dash-grid">
        <div className="panel">
          <div className="panel-head">
            <h3>Top matches</h3>
            <div className="actions"><button className="on">Hot</button><button>This week</button></div>
          </div>
          <table className="match-table">
            <thead>
              <tr>
                <th>Pair</th><th>Area</th><th>Price</th><th>Fit</th><th></th>
              </tr>
            </thead>
            <tbody>
              {recent.map((m) => {
                const isSel = selected?.kind === "match" && selected.id === m.id;
                const isRental = m.buyer.division === "rentals";
                const priceTxt = isRental
                  ? displayRental(m.seller.price, m.seller.cur, m.seller.period, displayCur, viewPeriod)
                  : displayMoney(m.seller.price, m.seller.cur, displayCur);
                return (
                  <tr key={m.id} className={`${isSel ? "sel" : ""} ${m.kind === "stretch" ? "stretch-row" : ""}`}
                    onClick={() => setSelected({ kind: "match", id: m.id })}>
                    <td>
                      <div className="pair-cell">
                        <div className="av-mini b">{initials(m.buyer.name)}</div>
                        <div className="av-mini s">{initials(m.seller.name)}</div>
                        <div className="nm-cell">
                          <div className="nm">
                            {m.buyer.name.split(" ")[0]} → {m.seller.name.split(" ")[0]}
                            {(m.buyer.intl || m.seller.intl) && <span className="intl-tag">INTL</span>}
                            {m.kind === "stretch" && <span className="stretch-tag">Stretch</span>}
                          </div>
                          <div className="meta">{ptShort(m.buyer.type)} · {CURRENCIES[m.buyer.cur]?.flag} {m.buyer.cur}</div>
                        </div>
                      </div>
                    </td>
                    <td style={{ color: "var(--ink-700)" }}>{m.buyer.area}</td>
                    <td style={{ fontFamily: "Fraunces, serif", fontWeight: 600, fontSize: 14 }}>{priceTxt}</td>
                    <td>
                      <div className="score-bar">
                        <div className="bar"><i style={{ width: `${m.score}%` }} /></div>
                        <span className="pct">{m.score}</span>
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <span className={`pill ${connectedSet.has(m.id) ? "done" : "new"}`}>
                        {connectedSet.has(m.id) ? "Connected" : "New"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {recent.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--ink-400)", padding: "28px 0" }}>No matches yet — add buyers and sellers in the same area &amp; type.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Activity</h3></div>
          <div className="activity">
            {matches.slice(0, 3).map((m) => (
              <div className="a-row match" key={m.id}>
                <div className="dot" />
                <div className="ct">
                  <div className="t">Match · <b>{m.buyer.name.split(" ")[0]}</b> → <b>{m.seller.name.split(" ")[0]}</b> at <em>{m.score}% fit</em></div>
                  <div className="ts">{m.buyer.area}</div>
                </div>
              </div>
            ))}
            {buyers.slice(0, 2).map((b) => (
              <div className="a-row buyer" key={b.id}>
                <div className="dot" />
                <div className="ct">
                  <div className="t"><b>{b.name}</b> added · {ptShort(b.type)}</div>
                  <div className="ts">{b.area}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h3>Recent buyers / tenants</h3>
          <div className="lst-tabs">
            <button className="on">By status</button>
            <button onClick={() => go("sales:listings")}>Sales</button>
            <button onClick={() => go("rentals:listings")}>Rentals</button>
          </div>
        </div>
        <table className="lst-table">
          <thead>
            <tr><th>Name</th><th>Status</th><th>Country</th><th>Area</th><th>Type</th><th>Budget</th><th>Matches</th></tr>
          </thead>
          <tbody>
            {sortedBuyers.slice(0, 5).map((b) => {
              const c = COUNTRIES.find((x) => x.code === b.country);
              const mc = matches.filter((m) => m.buyer.id === b.id).length;
              const isSel = selected?.kind === "buyer" && selected.id === b.id;
              const isRental = b.division === "rentals";
              const priceTxt = isRental
                ? displayRentalRange(b.min, b.max, b.cur, b.period, displayCur, viewPeriod)
                : displayRange(b.min, b.max, b.cur, displayCur);
              return (
                <tr key={b.id} className={isSel ? "sel" : ""} onClick={() => setSelected({ kind: "buyer", id: b.id })}>
                  <td><div className="nm-cell"><div className="nm"><div className="av-mini b">{initials(b.name)}</div>{b.name}{b.intl && <span className="intl-tag">INTL</span>}</div></div></td>
                  <td onClick={(e) => e.stopPropagation()}><LabelBadge label={b.label} kind="buyer" id={b.id} onChange={onSetLabel} size="sm" /></td>
                  <td>{c?.flag} {c?.name}</td>
                  <td>{b.area}</td>
                  <td><span className="tag">{ptShort(b.type)}</span></td>
                  <td className="price-cell">{priceTxt}</td>
                  <td><span className={`match-pill ${mc === 0 ? "zero" : ""}`}>{mc === 0 ? "none" : `${mc} match${mc > 1 ? "es" : ""}`}</span></td>
                </tr>
              );
            })}
            {buyers.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-400)", padding: "28px 0" }}>No buyers or tenants yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
