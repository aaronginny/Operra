"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

function UPIModal({ plan, onClose }: { plan: "basic" | "premium"; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText("aaronginny@okhdfcbank").then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => alert("UPI ID: aaronginny@okhdfcbank"));
  };
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={e => e.target === e.currentTarget && onClose()}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.75)", backdropFilter: "blur(10px)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <motion.div initial={{ scale: .9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .9, y: 20 }}
        style={{ background: "#0e0e14", border: "1px solid rgba(255,255,255,.08)", borderRadius: 16, padding: 40, maxWidth: 420, width: "90%", textAlign: "center", position: "relative" }}>
        <button onClick={onClose} style={{ position: "absolute", top: 14, right: 18, background: "none", border: "none", color: "#555", fontSize: "1.3rem", cursor: "pointer", lineHeight: 1 }}>×</button>
        <h3 style={{ fontFamily: "Georgia, serif", fontSize: "1.3rem", color: "#fff", marginBottom: 6 }}>
          Upgrade to {plan === "basic" ? "Basic" : "Premium"}
        </h3>
        <div style={{ fontSize: ".88rem", color: "#666", marginBottom: 24 }}>
          {plan === "basic" ? "₹2,000 per project" : "₹5,000 / month"}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#0a0a10", border: "1px solid rgba(255,255,255,.07)", borderRadius: 9, padding: "11px 14px", marginBottom: 20 }}>
          <code style={{ flex: 1, fontSize: ".88rem", color: "#ddd", fontFamily: "inherit", textAlign: "left" }}>aaronginny@okhdfcbank</code>
          <button onClick={copy} style={{ background: copied ? "#10B981" : "#fff", color: copied ? "#fff" : "#06060a", border: "none", padding: "6px 16px", borderRadius: 6, fontSize: ".78rem", fontWeight: 700, cursor: "pointer", transition: "all .2s", whiteSpace: "nowrap" }}>
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
        <div style={{ textAlign: "left", fontSize: ".82rem", color: "#555", lineHeight: 1.9 }}>
          <strong style={{ color: "#888" }}>Step 1.</strong> Copy the UPI ID above and pay via any UPI app.<br />
          <strong style={{ color: "#888" }}>Step 2.</strong> Send a screenshot on WhatsApp to <strong style={{ color: "#888" }}>9150016161</strong>.<br />
          <strong style={{ color: "#888" }}>Step 3.</strong> Your plan is activated within 1 hour.
        </div>
      </motion.div>
    </motion.div>
  );
}

const plans = [
  {
    id: "free", name: "Free", price: "₹0", period: "forever", highlight: false,
    features: ["7-day full-feature trial included", "1 project", "3 tasks maximum", "Basic WhatsApp alerts", "Dashboard access"],
    cta: "Start Free Trial", ctaStyle: "outline",
  },
  {
    id: "basic", name: "Basic", price: "₹2,000", period: "one-time per project", highlight: true,
    features: ["Unlimited tasks per project", "Smart Checkpoints", "Control Tower", "Morning Pulse", "Auto Reminders"],
    cta: "Get Started", ctaStyle: "white",
  },
  {
    id: "premium", name: "Premium", price: "₹5,000", period: "billed monthly", highlight: false,
    features: ["Unlimited projects", "Unlimited tasks", "All features included", "Priority WhatsApp support", "White-glove onboarding"],
    cta: "Get Started", ctaStyle: "outline",
  },
];

export default function Pricing() {
  const [modal, setModal] = useState<"basic" | "premium" | null>(null);

  return (
    <section id="pricing" style={{ padding: "120px 0", textAlign: "center" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#444", marginBottom: 14 }}>Pricing</motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", lineHeight: 1.12, marginBottom: 16, letterSpacing: "-.025em" }}>
          Simple pricing. No surprises.
        </motion.h2>
        <motion.p initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .2 }}
          style={{ color: "#555", fontSize: ".95rem", maxWidth: 480, margin: "0 auto", lineHeight: 1.7 }}>
          Start free. Upgrade when you&apos;re ready. Pay via UPI.
        </motion.p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20, marginTop: 64, alignItems: "start" }} className="price-grid">
          {plans.map((p, i) => (
            <motion.div key={p.id}
              initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * .12 }}
              whileHover={{ y: -5, borderColor: "rgba(255,255,255,.12)", boxShadow: "0 28px 70px rgba(0,0,0,.5)" }}
              style={{
                background: "#0b0b12", border: `1px solid ${p.highlight ? "rgba(255,255,255,.13)" : "rgba(255,255,255,.05)"}`,
                borderRadius: 16, padding: "36px 26px", textAlign: "left", position: "relative",
                transition: "border-color .3s, box-shadow .3s",
              }}>
              {p.highlight && (
                <div style={{ position: "absolute", top: -13, left: "50%", transform: "translateX(-50%)", background: "#fff", color: "#06060a", fontSize: ".62rem", fontWeight: 700, padding: "5px 18px", borderRadius: 100, letterSpacing: "1.5px", textTransform: "uppercase", whiteSpace: "nowrap" }}>
                  Most Popular
                </div>
              )}
              <div style={{ fontSize: ".72rem", color: "#555", textTransform: "uppercase", letterSpacing: "2px", marginBottom: 12 }}>{p.name}</div>
              <div style={{ fontFamily: "Georgia, serif", fontSize: "2.4rem", color: "#fff", marginBottom: 4, lineHeight: 1 }}>
                {p.price} {(p.id === "basic" || p.id === "premium") && <span style={{ fontSize: ".82rem", color: "#444" }}>/ {p.id === "basic" ? "project" : "month"}</span>}
              </div>
              <div style={{ fontSize: ".75rem", color: "#444", marginBottom: 24 }}>{p.period}</div>
              <div style={{ height: 1, background: "rgba(255,255,255,.05)", marginBottom: 20 }} />
              <ul style={{ marginBottom: 28 }}>
                {p.features.map(f => (
                  <li key={f} style={{ padding: "7px 0", color: "#666", fontSize: ".85rem", display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid rgba(255,255,255,.03)" }}>
                    <span style={{ width: 4, height: 4, background: "rgba(255,255,255,.2)", borderRadius: "50%", flexShrink: 0 }} />{f}
                  </li>
                ))}
              </ul>
              {p.id === "free" ? (
                <a href="https://operra-bo0x.onrender.com/dashboard"
                  style={{ display: "block", width: "100%", textAlign: "center", padding: 13, borderRadius: 9, fontWeight: 600, fontSize: ".85rem", border: "1px solid rgba(255,255,255,.08)", color: "#666", transition: "all .25s", cursor: "pointer" }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,.2)"; e.currentTarget.style.color = "#fff"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,.08)"; e.currentTarget.style.color = "#666"; }}>
                  {p.cta}
                </a>
              ) : (
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: .97 }}
                  onClick={() => setModal(p.id as "basic" | "premium")}
                  style={{
                    display: "block", width: "100%", textAlign: "center", padding: 13, borderRadius: 9,
                    fontWeight: 600, fontSize: ".85rem", cursor: "pointer", fontFamily: "inherit",
                    background: p.highlight ? "#fff" : "transparent", color: p.highlight ? "#06060a" : "#666",
                    border: p.highlight ? "none" : "1px solid rgba(255,255,255,.08)",
                  }}>
                  {p.cta}
                </motion.button>
              )}
            </motion.div>
          ))}
        </div>
        <p style={{ color: "#333", fontSize: ".78rem", marginTop: 32 }}>All plans: Secure online payment · Instant activation</p>
      </div>

      <AnimatePresence>
        {modal && <UPIModal plan={modal} onClose={() => setModal(null)} />}
      </AnimatePresence>
      <style>{`@media(max-width:768px){.price-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
