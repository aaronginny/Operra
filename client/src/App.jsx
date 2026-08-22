import { useState, useEffect } from "react";
import { AuthProvider, useAuth } from "./AuthContext";
import LandingPage from "./LandingPage";
import { useAppData } from "./useAppData";
import Sidebar from "./desktop/Sidebar";
import TopBar from "./desktop/TopBar";
import Dashboard from "./desktop/Dashboard";
import MatchesPage from "./desktop/MatchesPage";
import ListingsPage from "./desktop/ListingsPage";
import FormPage from "./desktop/FormPage";
import RightPanel from "./desktop/RightPanel";
import MobileApp from "./mobile/MobileApp";
import CommissionPage from "./desktop/CommissionPage";
import AnalyticsPage from "./desktop/AnalyticsPage";
import { I } from "./icons";
import { motion, AnimatePresence } from "framer-motion";

function SkeletonScreen({ mobile }) {
  if (mobile) {
    return (
      <div className="skeleton-mobile">
        <div className="sk-topbar">
          <div className="sk-brand sk-shimmer" />
          <div className="sk-pill sk-shimmer" />
        </div>
        <div className="sk-page">
          <div className="sk-line sk-shimmer" style={{ width: "60%", height: 26 }} />
          <div className="sk-line sk-shimmer" style={{ width: "40%", height: 14, marginTop: 6 }} />
          <div className="sk-stat-grid">
            <div className="sk-card sk-shimmer" />
            <div className="sk-card sk-shimmer" />
          </div>
          <div className="sk-card sk-shimmer" style={{ height: 70, marginTop: 12 }} />
          <div className="sk-card sk-shimmer" style={{ height: 110, marginTop: 12 }} />
          <div className="sk-card sk-shimmer" style={{ height: 110, marginTop: 12 }} />
        </div>
      </div>
    );
  }
  return (
    <div className="skeleton-desktop">
      <aside className="sk-side">
        <div className="sk-brand sk-shimmer" />
        {Array.from({ length: 8 }).map((_, i) => <div key={i} className="sk-nav sk-shimmer" />)}
      </aside>
      <header className="sk-top">
        <div className="sk-search sk-shimmer" />
        <div className="sk-pill sk-shimmer" />
        <div className="sk-pill sk-shimmer" />
      </header>
      <main className="sk-main">
        <div className="sk-line sk-shimmer" style={{ width: "30%", height: 30 }} />
        <div className="sk-stat-row">
          <div className="sk-stat sk-shimmer" />
          <div className="sk-stat sk-shimmer" />
          <div className="sk-stat sk-shimmer" />
          <div className="sk-stat sk-shimmer" />
        </div>
        <div className="sk-panel sk-shimmer" />
        <div className="sk-panel sk-shimmer" style={{ height: 220 }} />
      </main>
    </div>
  );
}

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== "undefined"
      && (window.innerWidth < 768 || /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent))
  );
  useEffect(() => {
    const fn = () => setMobile(window.innerWidth < 768);
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return mobile;
}

function DesktopApp({
  buyers, sellers, matches, connectedSet,
  addBuyer, addSeller, bulkAddBuyers, bulkAddSellers,
  updateBuyer, updateSeller,
  setBuyerLabel, setSellerLabel, bumpBuyerBudget,
  deleteBuyer, deleteSeller, toggleConnect, logout, broker,
  darkMode, toggleDarkMode,
}) {
  const [active, setActive] = useState("dashboard");
  const [editTarget, setEditTarget] = useState(null);
  const [selected, setSelected] = useState(null);
  const [pendingListingsSearch, setPendingListingsSearch] = useState(null);
  const [currency, setCurrency] = useState(() => localStorage.getItem("dk_currency") || "AED");

  const updateCurrency = (c) => { setCurrency(c); localStorage.setItem("dk_currency", c); };
  const [viewPeriod, setViewPeriod] = useState("monthly");
  const [toast, setToast] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2400); };

  const startEdit = (kind, record) => { setEditTarget({ kind, record }); setActive("editForm"); };
  const startDelete = (kind, record) => setConfirm({
    name: record.name,
    onConfirm: async () => {
      if (kind === "buyer") await deleteBuyer(record.id);
      else await deleteSeller(record.id);
      setSelected(null);
      showToast(`${record.name.split(" ")[0]} removed`);
      setConfirm(null);
    },
  });

  const onSetLabel = async (kind, id, label) => {
    if (kind === "buyer") await setBuyerLabel(id, label);
    else await setSellerLabel(id, label);
    showToast(`Status updated`);
  };

  const onBumpBudget = async (id, delta) => {
    await bumpBuyerBudget(id, delta);
    showToast(`Budget bumped`);
  };

  const waLink = (p, brokerName) => {
    const num = (p.dial + p.phone).replace(/\D/g, "");
    const msg = encodeURIComponent(`Hello, I'm ${brokerName} from DealKnot. I have a property match for you. Are you available for a quick call?`);
    return `https://wa.me/${num}?text=${msg}`;
  };
  const callLink = (p) => `tel:${p.dial}${p.phone}`;
  const brokerName = broker?.nickname || broker?.name?.split(" ")[0] || "your broker";

  const counts = {
    salesMatches:    matches.filter((m) => m.buyer.division === "sales").length,
    rentalsMatches:  matches.filter((m) => m.buyer.division === "rentals").length,
    salesListings:   buyers.filter((b) => b.division === "sales").length + sellers.filter((s) => s.division === "sales").length,
    rentalsListings: buyers.filter((b) => b.division === "rentals").length + sellers.filter((s) => s.division === "rentals").length,
  };

  const parseRoute = (id) => {
    const parts = id.split(":");
    return parts.length === 2 ? { division: parts[0], page: parts[1] } : { page: id };
  };
  const route = parseRoute(active);
  const showPeriodToggle = route.division === "rentals";

  let page;
  if (active === "dashboard") {
    page = (
      <Dashboard buyers={buyers} sellers={sellers} matches={matches} connectedSet={connectedSet}
        selected={selected} setSelected={setSelected} go={setActive}
        showToast={showToast} broker={broker} displayCur={currency} viewPeriod={viewPeriod}
        onSetLabel={onSetLabel} />
    );
  } else if (route.page === "matches") {
    page = (
      <MatchesPage matches={matches} connectedSet={connectedSet} toggleConnect={toggleConnect}
        selected={selected} setSelected={setSelected} showToast={showToast}
        displayCur={currency} viewPeriod={viewPeriod} division={route.division}
        waLink={waLink} callLink={callLink} brokerName={brokerName} broker={broker}
        go={setActive} buyers={buyers} sellers={sellers} />
    );
  } else if (route.page === "listings") {
    page = (
      <ListingsPage buyers={buyers} sellers={sellers} matches={matches}
        selected={selected} setSelected={setSelected} go={setActive}
        displayCur={currency} viewPeriod={viewPeriod} division={route.division}
        externalSearch={pendingListingsSearch}
        onConsumeExternalSearch={() => setPendingListingsSearch(null)}
        onEdit={startEdit} onDelete={startDelete} waLink={waLink} callLink={callLink} brokerName={brokerName}
        onSetLabel={onSetLabel} onBumpBudget={onBumpBudget} broker={broker}
        onBulkImport={async (records, kind) => {
          if (kind === "buyer") return await bulkAddBuyers(records);
          return await bulkAddSellers(records);
        }} />
    );
  } else if (route.page === "addBuyer" || route.page === "addSeller") {
    const kind = route.page === "addBuyer" ? "buyer" : "seller";
    page = (
      <FormPage key={active} kind={kind} division={route.division || "sales"} onCancel={() => setActive("dashboard")}
        onCurrencyChange={updateCurrency} displayCur={currency}
        onBulkImport={async (records) => {
          if (kind === "buyer") return await bulkAddBuyers(records);
          return await bulkAddSellers(records);
        }}
        onSubmit={async (rec) => {
          if (kind === "buyer") await addBuyer(rec);
          else await addSeller(rec);
          showToast(`${rec.name.split(" ")[0]} saved`);
          setActive(`${rec.division}:listings`);
        }} />
    );
  } else if (active === "editForm" && editTarget) {
    const { kind, record } = editTarget;
    page = (
      <FormPage key={`edit-${kind}-${record.id}`} kind={kind} initialData={record}
        onCancel={() => { setActive(`${record.division}:listings`); setEditTarget(null); }}
        onCurrencyChange={updateCurrency}
        onSubmit={async (rec) => {
          if (kind === "buyer") await updateBuyer(record.id, rec);
          else await updateSeller(record.id, rec);
          showToast(`${rec.name.split(" ")[0]} updated`);
          setEditTarget(null);
          setActive(`${rec.division}:listings`);
        }} />
    );
  } else if (active === "commission") {
    page = <CommissionPage displayCur={currency} />;
  } else if (active === "analytics") {
    page = <AnalyticsPage buyers={buyers} sellers={sellers} matches={matches} connectedSet={connectedSet} displayCur={currency} />;
  } else if (active === "settings") {
    page = (
      <div className="main fade-in">
        <div className="page-head">
          <div>
            <div className="pre">// account</div>
            <h1>Settings.</h1>
            <div className="sub">Workspace preferences, integrations, and account management.</div>
          </div>
          <div className="head-actions">
            <button className="btn ghost" onClick={() => setConfirm({
              name: null,
              message: "You'll be returned to the landing page. Any unsaved changes will be lost.",
              title: "Sign out?",
              label: "Sign out",
              onConfirm: () => { logout(); setConfirm(null); },
            })} style={{ color: "var(--red)" }}>
              <I.logout /> Sign out
            </button>
          </div>
        </div>
        <div className="form-card">
          <p style={{ color: "var(--ink-500)", fontSize: 13 }}>Settings &amp; integrations coming soon.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="shell">
      <Sidebar active={active} go={setActive} counts={counts} />
      <TopBar currency={currency} setCurrency={updateCurrency}
        viewPeriod={viewPeriod} setViewPeriod={setViewPeriod} showPeriodToggle={showPeriodToggle}
        buyers={buyers} sellers={sellers}
        onSelectResult={(item) => {
          setSelected(item);
          const found = item.kind === "buyer"
            ? buyers.find((b) => b.id === item.id)
            : sellers.find((s) => s.id === item.id);
          if (found) setActive(`${found.division}:listings`);
        }}
        onSelectArea={(area, division) => {
          setPendingListingsSearch(area);
          setActive(`${division}:listings`);
        }}
        darkMode={darkMode} toggleDarkMode={toggleDarkMode} />
      {page}
      <RightPanel selected={selected} setSelected={setSelected}
        buyers={buyers} sellers={sellers} matches={matches}
        connectedSet={connectedSet} toggleConnect={toggleConnect} showToast={showToast}
        displayCur={currency} viewPeriod={viewPeriod}
        onEdit={startEdit} onDelete={startDelete} waLink={waLink} callLink={callLink} brokerName={brokerName}
        onSetLabel={onSetLabel} broker={broker} />
      <AnimatePresence>
        {toast && (
          <motion.div className="toast"
            initial={{ y: 24, opacity: 0, scale: 0.95 }}
            animate={{ y: 0, opacity: 1, scale: 1, transition: { type: "spring", stiffness: 380, damping: 28 } }}
            exit={{ y: 12, opacity: 0, scale: 0.95, transition: { duration: 0.18 } }}>
            <I.check width="14" height="14" /> {toast}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {confirm && (
          <motion.div className="confirm-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}>
            <motion.div className="confirm-box"
              initial={{ scale: 0.92, opacity: 0, y: 14 }}
              animate={{ scale: 1, opacity: 1, y: 0, transition: { type: "spring", stiffness: 380, damping: 28 } }}
              exit={{ scale: 0.95, opacity: 0, y: 8, transition: { duration: 0.14 } }}>
              <div className="confirm-title">{confirm.title || "Delete contact?"}</div>
              <div className="confirm-msg">{confirm.message || <>Are you sure you want to delete <b>{confirm.name}</b>? This cannot be undone.</>}</div>
              <div className="confirm-actions">
                <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button>
                <button className="btn" style={{ background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} onClick={confirm.onConfirm}>{confirm.label || "Delete"}</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AppInner() {
  const { broker, loading, logout } = useAuth();
  const isMobile = useIsMobile();
  const data = useAppData(!!broker);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("dk_dark") === "1");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("dk_dark", darkMode ? "1" : "0");
  }, [darkMode]);

  const toggleDarkMode = () => setDarkMode((v) => !v);

  if (loading || (broker && data.loading)) {
    return <SkeletonScreen mobile={isMobile} />;
  }

  if (!broker) return <LandingPage />;

  if (data.error) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--navy-900)", gap: 16, padding: 24 }}>
        <div style={{ fontFamily: "Fraunces, serif", fontSize: 22, color: "var(--gold-400)", fontWeight: 600 }}>Couldn't load your data</div>
        <div style={{ fontSize: 13, color: "var(--ink-400)", maxWidth: 320, textAlign: "center" }}>{data.error}</div>
        <button className="btn primary" style={{ marginTop: 8 }} onClick={data.reload}>Retry</button>
      </div>
    );
  }

  const props = {
    buyers: data.buyers, sellers: data.sellers, matches: data.matches,
    connectedSet: data.connectedSet,
    addBuyer: data.addBuyer, addSeller: data.addSeller,
    bulkAddBuyers: data.bulkAddBuyers, bulkAddSellers: data.bulkAddSellers,
    updateBuyer: data.updateBuyer, updateSeller: data.updateSeller,
    setBuyerLabel: data.setBuyerLabel, setSellerLabel: data.setSellerLabel,
    bumpBuyerBudget: data.bumpBuyerBudget,
    deleteBuyer: data.deleteBuyer, deleteSeller: data.deleteSeller,
    toggleConnect: data.toggleConnect,
    logout, broker,
    darkMode, toggleDarkMode,
  };

  return isMobile ? <MobileApp {...props} /> : <DesktopApp {...props} />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}
