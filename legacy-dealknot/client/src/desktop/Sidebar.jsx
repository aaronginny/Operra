import { useState } from "react";
import { I } from "../icons";
import { useAuth } from "../AuthContext";

export default function Sidebar({ active, go, counts }) {
  const { broker, logout } = useAuth();
  const [confirmLogout, setConfirmLogout] = useState(false);

  const Item = ({ id, label, icon, num }) => (
    <button className={`nav-item ${active === id ? "active" : ""}`} onClick={() => go(id)}>
      {icon}<span>{label}</span>
      {num != null && <span className="num">{num}</span>}
    </button>
  );

  const displayName = broker?.nickname || broker?.name?.split(" ")[0] || broker?.email?.split("@")[0] || "Broker";

  return (
    <>
    <aside className="side">
      <div className="brand">
        <div className="mk">D</div>
        <div>
          <div className="nm">Deal<em>Knot</em></div>
          <div className="tg">Where deals get tied</div>
        </div>
      </div>

      <div className="nav-section">Workspace</div>
      <Item id="dashboard" label="Dashboard" icon={<I.home />} />

      <div className="nav-section">Sales</div>
      <Item id="sales:matches"  label="Matches"  icon={<I.match />}    num={counts.salesMatches} />
      <Item id="sales:listings" label="Listings" icon={<I.list />}     num={counts.salesListings} />
      <Item id="sales:addBuyer" label="Add buyer"  icon={<I.userPlus />} />
      <Item id="sales:addSeller" label="Add seller" icon={<I.tag />} />

      <div className="nav-section">Rentals</div>
      <Item id="rentals:matches"  label="Matches"   icon={<I.match />}    num={counts.rentalsMatches} />
      <Item id="rentals:listings" label="Listings"  icon={<I.list />}     num={counts.rentalsListings} />
      <Item id="rentals:addBuyer" label="Add tenant"   icon={<I.userPlus />} />
      <Item id="rentals:addSeller" label="Add landlord" icon={<I.tag />} />

      <div className="nav-section">Finance</div>
      <Item id="commission" label="Commission" icon={<I.dollar />} />
      <Item id="analytics"  label="Analytics"  icon={<I.chart />} />

      <div className="nav-section">Account</div>
      <Item id="settings" label="Settings" icon={<I.set />} />
      <button className="nav-item" onClick={() => setConfirmLogout(true)} style={{ color: "rgba(255,255,255,.5)" }}>
        <I.logout /><span>Sign out</span>
      </button>

      <div className="side-foot">
        <div className="t">{displayName}</div>
        <div className="s">{broker?.email}</div>
        <button onClick={() => go("settings")}>Manage workspace</button>
      </div>
    </aside>

    {confirmLogout && (
      <div className="confirm-overlay" onClick={() => setConfirmLogout(false)}>
        <div className="confirm-box" onClick={(e) => e.stopPropagation()}>
          <div className="confirm-title">Sign out?</div>
          <div className="confirm-msg">You'll be returned to the landing page. Any unsaved changes will be lost.</div>
          <div className="confirm-actions">
            <button className="btn ghost" onClick={() => setConfirmLogout(false)}>Cancel</button>
            <button className="btn" style={{ background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} onClick={logout}>Sign out</button>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
