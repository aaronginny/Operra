"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

const faqs = [
  { q: "Is there a free trial?", a: "Yes. Every new account gets 7 days of full access — Control Tower, Smart Checkpoints, Morning Pulse, unlimited tasks — completely free. No credit card needed. After 7 days you automatically move to the free tier unless you upgrade." },
  { q: "Do my team members need to download an app?", a: "No. Your team members only need WhatsApp, which they already have. No downloads, no sign-ups, no training." },
  { q: "What if a team member doesn't reply?", a: "PhantomPilot sends automatic reminders for overdue tasks. You'll also see unresponsive team members flagged on your dashboard." },
  { q: "How do I pay?", a: "Pay via UPI to aaronginny@okhdfcbank. Send your payment screenshot on WhatsApp to 9150016161. Your plan is activated within 1 hour." },
  { q: "Can I manage multiple projects?", a: "Yes! On the Basic plan, pay per project. On Premium, get unlimited projects for a flat monthly fee." },
  { q: "Is my data safe?", a: "Yes. Your data is hosted on secure cloud servers with encryption. Only you and your team can access your tasks and reports." },
];

export default function FAQ() {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section id="faq" style={{ padding: "120px 0" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#444", marginBottom: 14, textAlign: "center" }}>FAQ</motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", lineHeight: 1.12, marginBottom: 56, letterSpacing: "-.025em", textAlign: "center" }}>
          Got questions?
        </motion.h2>

        <div style={{ maxWidth: 660, margin: "0 auto" }}>
          {faqs.map((f, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * .06 }}
              style={{ borderBottom: "1px solid rgba(255,255,255,.05)" }}>
              <button onClick={() => setOpen(open === i ? null : i)}
                style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "20px 0", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
                <h3 style={{ fontSize: ".95rem", fontWeight: 400, color: open === i ? "#fff" : "#888", fontFamily: "Georgia, serif", transition: "color .2s", lineHeight: 1.4 }}>{f.q}</h3>
                <motion.div animate={{ rotate: open === i ? 45 : 0 }} transition={{ duration: .3 }}
                  style={{ width: 24, height: 24, borderRadius: "50%", border: `1px solid ${open === i ? "rgba(255,255,255,.2)" : "rgba(255,255,255,.08)"}`, display: "flex", alignItems: "center", justifyContent: "center", color: open === i ? "#fff" : "#555", fontSize: ".85rem", flexShrink: 0, transition: "border-color .3s, color .3s" }}>
                  +
                </motion.div>
              </button>
              <AnimatePresence initial={false}>
                {open === i && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: .35, ease: [.16,1,.3,1] }}
                    style={{ overflow: "hidden" }}>
                    <p style={{ color: "#555", fontSize: ".88rem", lineHeight: 1.75, paddingBottom: 20 }}>{f.a}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
