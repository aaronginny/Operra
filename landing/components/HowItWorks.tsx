"use client";
import { motion } from "framer-motion";

const steps = [
  { num: "01", icon: "💬", title: "You assign the task", desc: 'Type naturally on WhatsApp. e.g. "Fix the wiring at Block C by Friday". PhantomPilot understands and assigns it instantly.' },
  { num: "02", icon: "🔔", title: "Team member gets notified", desc: "Your team member receives a clear WhatsApp message instantly with the task details and deadline — no app needed." },
  { num: "03", icon: "📊", title: "You see it all", desc: "They reply DONE, UPDATE, or HELP — and your dashboard updates in real time. Every task, every status, one screen." },
];

export default function HowItWorks() {
  return (
    <section id="how" style={{ padding: "120px 0" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px", textAlign: "center" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#444", marginBottom: 14 }}>
          How It Works
        </motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", lineHeight: 1.12, marginBottom: 16, letterSpacing: "-.025em" }}>
          Three steps. Zero friction.
        </motion.h2>
        <motion.p initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .2 }}
          style={{ color: "#555", fontSize: ".95rem", maxWidth: 480, margin: "0 auto", lineHeight: 1.7 }}>
          No sign-ups for your team. No training sessions. Just WhatsApp.
        </motion.p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20, marginTop: 64 }} className="how-grid">
          {steps.map((s, i) => (
            <motion.div key={s.num}
              initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * .12 }}
              whileHover={{ y: -5, borderColor: "rgba(255,255,255,.1)", boxShadow: "0 24px 60px rgba(0,0,0,.4)" }}
              style={{ textAlign: "left", padding: "32px 28px", background: "#09090f", border: "1px solid rgba(255,255,255,.05)", borderRadius: 12, cursor: "default", transition: "border-color .3s, box-shadow .3s" }}>
              <div style={{ fontFamily: "Georgia, serif", fontSize: "2.4rem", color: "rgba(255,255,255,.07)", lineHeight: 1, marginBottom: 8 }}>{s.num}</div>
              <div style={{ fontSize: "1.4rem", marginBottom: 14 }}>{s.icon}</div>
              <h3 style={{ fontSize: "1rem", marginBottom: 10, color: "#ddd" }}>{s.title}</h3>
              <p style={{ fontSize: ".85rem", color: "#555", lineHeight: 1.7 }}>{s.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
      <style>{`@media(max-width:768px){.how-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
