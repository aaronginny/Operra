import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { listContainer, listItem } from "../motion";
import { I } from "../icons";
import { CURRENCIES, formatMoney } from "../constants";
import { api } from "../api";

const STATUSES = ["Pending", "Partial", "Received"];
const STATUS_META = {
  Pending:  { color: "#D97706", bg: "rgba(217,119,6,.12)",  border: "rgba(217,119,6,.3)" },
  Partial:  { color: "#2563EB", bg: "rgba(37,99,235,.12)",  border: "rgba(37,99,235,.3)" },
  Received: { color: "#059669", bg: "rgba(5,150,105,.12)",  border: "rgba(5,150,105,.3)" },
};

function StatusBadge({ status }) {
  const m = STATUS_META[status] || STATUS_META.Pending;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: m.bg, color: m.color, border: `1px solid ${m.border}`,
      borderRadius: 999, padding: "4px 11px", fontSize: 11.5, fontWeight: 700,
      letterSpacing: "0.02em",
    }}>{status}</span>
  );
}

const EMPTY_FORM = {
  buyer_name: "", seller_name: "", area: "", property_type: "",
  deal_value: "", commission_percent: "", commission_amount: "",
  currency: "AED", status: "Pending",
  expected_date: "", received_date: "", notes: "",
};

function CommissionForm({ initial, onSave, onCancel, displayCur }) {
  const [form, setForm] = useState(() => initial ? {
    ...initial,
    deal_value: initial.deal_value != null ? String(initial.deal_value) : "",
    commission_percent: initial.commission_percent != null ? String(initial.commission_percent) : "",
    commission_amount: initial.commission_amount != null ? String(initial.commission_amount) : "",
  } : { ...EMPTY_FORM, currency: displayCur || "AED" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const up = (k, v) => setForm((f) => {
    const next = { ...f, [k]: v };
    // Auto-calculate commission amount when deal_value or commission_percent changes
    if ((k === "deal_value" || k === "commission_percent") && next.deal_value && next.commission_percent) {
      next.commission_amount = String(
        Math.round(Number(next.deal_value) * Number(next.commission_percent) / 100 * 100) / 100
      );
    }
    return next;
  });

  const handleSave = async () => {
    if (!form.buyer_name.trim() && !form.seller_name.trim()) {
      setErr("Enter at least a buyer or seller name."); return;
    }
    setBusy(true); setErr("");
    try {
      await onSave({
        ...form,
        deal_value: Number(form.deal_value) || 0,
        commission_percent: Number(form.commission_percent) || 0,
        commission_amount: Number(form.commission_amount) || 0,
      });
    } catch (e) {
      setErr(e.message || "Failed to save."); setBusy(false);
    }
  };

  return (
    <div style={FS.overlay} onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div style={FS.modal}>
        <div style={FS.head}>
          <div>
            <div style={FS.eyebrow}>// {initial ? "edit" : "new"} commission</div>
            <h2 style={FS.title}>{initial ? "Edit" : "Log"} <em style={{ color: "var(--gold-600)", fontStyle: "italic" }}>commission</em></h2>
          </div>
          <button style={FS.closeBtn} onClick={onCancel}><I.x width="16" height="16" /></button>
        </div>
        <div style={FS.body}>
          {err && <div style={FS.err}>{err}</div>}

          <div style={FS.fieldRow}>
            <div style={FS.field}>
              <label style={FS.label}>Buyer name</label>
              <input style={FS.input} value={form.buyer_name} onChange={(e) => up("buyer_name", e.target.value)} placeholder="e.g. Olivia Chen" />
            </div>
            <div style={FS.field}>
              <label style={FS.label}>Seller name</label>
              <input style={FS.input} value={form.seller_name} onChange={(e) => up("seller_name", e.target.value)} placeholder="e.g. Marina Heights LLC" />
            </div>
          </div>

          <div style={FS.fieldRow}>
            <div style={FS.field}>
              <label style={FS.label}>Area</label>
              <input style={FS.input} value={form.area} onChange={(e) => up("area", e.target.value)} placeholder="e.g. Dubai Marina" />
            </div>
            <div style={FS.field}>
              <label style={FS.label}>Property type</label>
              <input style={FS.input} value={form.property_type} onChange={(e) => up("property_type", e.target.value)} placeholder="e.g. Apartment" />
            </div>
          </div>

          <div style={FS.fieldRow}>
            <div style={FS.field}>
              <label style={FS.label}>Currency</label>
              <select style={FS.input} value={form.currency} onChange={(e) => up("currency", e.target.value)}>
                {Object.keys(CURRENCIES).map((k) => <option key={k}>{k}</option>)}
              </select>
            </div>
            <div style={FS.field}>
              <label style={FS.label}>Deal value</label>
              <input style={FS.input} type="number" value={form.deal_value} onChange={(e) => up("deal_value", e.target.value)} placeholder="0" />
            </div>
          </div>

          <div style={FS.fieldRow}>
            <div style={FS.field}>
              <label style={FS.label}>Commission % </label>
              <input style={FS.input} type="number" value={form.commission_percent} onChange={(e) => up("commission_percent", e.target.value)} placeholder="2.5" step="0.1" min="0" max="100" />
            </div>
            <div style={FS.field}>
              <label style={FS.label}>Commission amount (auto-calculated)</label>
              <input style={FS.input} type="number" value={form.commission_amount} onChange={(e) => up("commission_amount", e.target.value)} placeholder="0" />
            </div>
          </div>

          <div style={FS.fieldRow}>
            <div style={FS.field}>
              <label style={FS.label}>Status</label>
              <select style={FS.input} value={form.status} onChange={(e) => up("status", e.target.value)}>
                {STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div style={FS.field}>
              <label style={FS.label}>Expected date</label>
              <input style={FS.input} type="date" value={form.expected_date} onChange={(e) => up("expected_date", e.target.value)} />
            </div>
          </div>

          {form.status !== "Pending" && (
            <div style={FS.field}>
              <label style={FS.label}>Received date</label>
              <input style={FS.input} type="date" value={form.received_date} onChange={(e) => up("received_date", e.target.value)} />
            </div>
          )}

          <div style={FS.field}>
            <label style={FS.label}>Notes</label>
            <textarea style={{ ...FS.input, minHeight: 70, resize: "vertical" }} value={form.notes} onChange={(e) => up("notes", e.target.value)} placeholder="Anything about this deal…" />
          </div>
        </div>
        <div style={FS.foot}>
          <button style={FS.btnGhost} onClick={onCancel}>Cancel</button>
          <button style={{ ...FS.btnPrimary, ...(busy ? { opacity: .6, cursor: "not-allowed" } : {}) }} disabled={busy} onClick={handleSave}>
            <I.check width="14" height="14" /> {busy ? "Saving…" : initial ? "Update commission" : "Log commission"}
          </button>
        </div>
      </div>
    </div>
  );
}

const FS = {
  overlay: { position: "fixed", inset: 0, background: "rgba(5,14,30,.72)", zIndex: 9000, display: "flex", alignItems: "center", justifyContent: "center", backdropFilter: "blur(4px)", padding: 20 },
  modal: { background: "var(--paper)", borderRadius: 18, width: "100%", maxWidth: 700, maxHeight: "90vh", display: "flex", flexDirection: "column", boxShadow: "0 32px 80px rgba(0,0,0,.35)" },
  head: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", padding: "22px 24px 18px", borderBottom: "1px solid var(--line-2)", flexShrink: 0 },
  eyebrow: { fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--ink-400)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4 },
  title: { fontFamily: "Fraunces, serif", fontSize: 22, fontWeight: 600, color: "var(--navy-900)", margin: 0 },
  closeBtn: { background: "none", border: "1px solid var(--line)", borderRadius: 8, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "var(--ink-500)" },
  body: { flex: 1, overflowY: "auto", padding: "20px 24px" },
  foot: { display: "flex", justifyContent: "flex-end", gap: 10, padding: "14px 24px", borderTop: "1px solid var(--line-2)", flexShrink: 0 },
  err: { background: "var(--red-bg)", color: "var(--red)", padding: "10px 14px", borderRadius: 8, marginBottom: 16, fontSize: 13 },
  field: { marginBottom: 14, flex: 1 },
  fieldRow: { display: "flex", gap: 14, marginBottom: 0 },
  label: { display: "block", fontSize: 11.5, fontWeight: 600, color: "var(--ink-700)", marginBottom: 5 },
  input: { width: "100%", padding: "10px 12px", border: "1px solid var(--line)", background: "var(--paper)", borderRadius: 8, fontFamily: "inherit", fontSize: 13.5, color: "var(--ink-900)", outline: "none", boxSizing: "border-box" },
  btnGhost: { padding: "9px 18px", borderRadius: 9, border: "1px solid var(--line)", background: "transparent", fontFamily: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer", color: "var(--ink-700)" },
  btnPrimary: { display: "inline-flex", alignItems: "center", gap: 6, padding: "9px 22px", borderRadius: 9, border: "none", background: "var(--navy-900)", fontFamily: "inherit", fontSize: 13, fontWeight: 700, cursor: "pointer", color: "var(--gold-400)" },
};

export default function CommissionPage({ displayCur }) {
  const [commissions, setCommissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [confirm, setConfirm] = useState(null);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  async function load() {
    setLoadError(null);
    try {
      const data = await api.getCommissions();
      setCommissions(data);
    } catch (e) {
      setLoadError(e.message || "Failed to load commissions");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(form) {
    if (editItem) {
      const updated = await api.updateCommission(editItem.id, form);
      setCommissions((prev) => prev.map((c) => c.id === updated.id ? updated : c));
    } else {
      const created = await api.addCommission(form);
      setCommissions((prev) => [created, ...prev]);
    }
    setShowForm(false); setEditItem(null);
  }

  async function handleDelete(id) {
    await api.deleteCommission(id);
    setCommissions((prev) => prev.filter((c) => c.id !== id));
    setConfirm(null);
  }

  const cur = displayCur || "AED";
  const sym = CURRENCIES[cur]?.sym || cur;

  const filtered = statusFilter === "All"
    ? commissions
    : commissions.filter((c) => c.status === statusFilter);

  const totalExpected = commissions.reduce((s, c) => s + (c.commission_amount || 0), 0);
  const totalReceived = commissions.filter((c) => c.status === "Received").reduce((s, c) => s + (c.commission_amount || 0), 0);
  const totalPending  = commissions.filter((c) => c.status !== "Received").reduce((s, c) => s + (c.commission_amount || 0), 0);

  const fmt = (n) => formatMoney(n, cur);

  return (
    <div className="main fade-in">
      {(showForm || editItem) && (
        <CommissionForm
          initial={editItem}
          displayCur={cur}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditItem(null); }}
        />
      )}

      {confirm && (
        <div className="confirm-overlay">
          <div className="confirm-box">
            <div className="confirm-title">Delete commission?</div>
            <div className="confirm-msg">Remove this deal record? This cannot be undone.</div>
            <div className="confirm-actions">
              <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button>
              <button className="btn" style={{ background: "var(--red)", color: "#fff", borderColor: "var(--red)" }} onClick={() => handleDelete(confirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}

      <div className="page-head">
        <div>
          <div className="pre">// commission tracker</div>
          <h1>Commission <em>tracker.</em></h1>
          <div className="sub">Track deals, commissions earned, and pipeline value.</div>
        </div>
        <div className="head-actions">
          <button className="btn primary" onClick={() => setShowForm(true)}>
            <I.plus /> Log commission
          </button>
        </div>
      </div>

      {/* Summary bar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        {[
          { label: "Total Pipeline", value: fmt(totalExpected), color: "var(--navy-900)", bg: "var(--paper)" },
          { label: "Received", value: fmt(totalReceived), color: "#059669", bg: "rgba(5,150,105,.06)" },
          { label: "Pending", value: fmt(totalPending), color: "#D97706", bg: "rgba(217,119,6,.06)" },
        ].map((s) => (
          <div key={s.label} style={{ background: s.bg, border: "1px solid var(--line-2)", borderRadius: 12, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--ink-400)", marginBottom: 8 }}>{s.label}</div>
            <div style={{ fontFamily: "Fraunces, serif", fontSize: 28, fontWeight: 600, color: s.color, letterSpacing: "-0.02em", lineHeight: 1 }}>{s.value}</div>
            <div style={{ fontSize: 11, color: "var(--ink-400)", marginTop: 4 }}>{sym} · {commissions.length} deal{commissions.length !== 1 ? "s" : ""}</div>
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
        {["All", ...STATUSES].map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
            style={{
              padding: "6px 14px", borderRadius: 999, border: "1px solid var(--line)",
              background: statusFilter === s ? "var(--navy-800)" : "var(--paper)",
              color: statusFilter === s ? "var(--gold-400)" : "var(--ink-700)",
              fontFamily: "inherit", fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>
            {s}
            {s !== "All" && <span style={{ marginLeft: 6, fontSize: 10, opacity: .75 }}>({commissions.filter((c) => c.status === s).length})</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "var(--ink-400)" }}>Loading…</div>
      ) : loadError ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "var(--red)" }}>{loadError}</div>
      ) : filtered.length === 0 ? (
        <div className="empty">
          <div className="ico"><I.dollar width="24" height="24" /></div>
          <div style={{ fontFamily: "Fraunces, serif", fontSize: 17, fontWeight: 600, color: "var(--navy-900)", marginBottom: 4 }}>No commissions yet</div>
          <div style={{ fontSize: 12.5, color: "var(--ink-500)" }}>Log your first deal using the button above.</div>
        </div>
      ) : (
        <div className="panel clip">
          <motion.div variants={listContainer} initial="initial" animate="enter">
            {filtered.map((c) => (
              <motion.div key={c.id} variants={listItem}
                style={{ padding: "18px 22px", borderBottom: "1px solid var(--line-2)", display: "grid", gridTemplateColumns: "1fr auto", gap: 16, alignItems: "start" }}>
                <div>
                  {/* Names row */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 15, color: "var(--navy-900)" }}>
                      <span style={{ background: "var(--navy-100)", color: "var(--navy-800)", borderRadius: "50%", width: 28, height: 28, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
                        {(c.buyer_name || "?")[0].toUpperCase()}
                      </span>
                      {c.buyer_name || "—"}
                    </div>
                    <span style={{ color: "var(--ink-300)", fontSize: 12 }}>↔</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 15, color: "var(--navy-900)" }}>
                      <span style={{ background: "var(--gold-100)", color: "var(--gold-700)", borderRadius: "50%", width: 28, height: 28, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
                        {(c.seller_name || "?")[0].toUpperCase()}
                      </span>
                      {c.seller_name || "—"}
                    </div>
                    <StatusBadge status={c.status} />
                  </div>

                  {/* Meta row */}
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", fontSize: 12, color: "var(--ink-500)" }}>
                    {c.area && <span><I.pin width="11" height="11" style={{ verticalAlign: "middle" }} /> {c.area}</span>}
                    {c.property_type && <span className="tag">{c.property_type}</span>}
                    {c.deal_value > 0 && <span>Deal: <b style={{ color: "var(--ink-700)" }}>{fmt(c.deal_value)}</b></span>}
                    {c.commission_percent > 0 && <span>{c.commission_percent}%</span>}
                    {c.expected_date && <span><I.calendar width="11" height="11" style={{ verticalAlign: "middle" }} /> {c.expected_date}</span>}
                  </div>

                  {c.notes && <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-500)", fontStyle: "italic" }}>{c.notes}</div>}
                </div>

                {/* Right: amount + actions */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 10 }}>
                  <div style={{ fontFamily: "Fraunces, serif", fontSize: 26, fontWeight: 600, color: "var(--gold-600)", letterSpacing: "-0.015em", whiteSpace: "nowrap" }}>
                    {fmt(c.commission_amount)}
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button className="row-action-btn" title="Edit" onClick={() => setEditItem(c)}><I.edit width="13" height="13" /></button>
                    <button className="row-action-btn del" title="Delete" onClick={() => setConfirm(c.id)}><I.trash width="13" height="13" /></button>
                  </div>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      )}
    </div>
  );
}
