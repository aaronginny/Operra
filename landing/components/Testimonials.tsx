"use client";
import { motion } from "framer-motion";

const testimonials = [
  { quote: "I used to call each worker 3 times a day. Now I just check the dashboard. My phone bill dropped, my blood pressure dropped.", name: "Ramesh K.", role: "Plumbing Contractor, Chennai" },
  { quote: "Managing attendance, task follow-ups, and daily check-ins used to take up half my morning. Now I send one WhatsApp and the dashboard handles the rest.", name: "Priya M.", role: "HR Manager, Bangalore" },
  { quote: "The morning reminders alone are worth it. Zero missed tasks since we started. My team actually knows what to do each day.", name: "Suresh R.", role: "Site Manager, Hyderabad" },
];

export default function Testimonials() {
  return (
    <section style={{ padding: "120px 0" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#444", marginBottom: 14, textAlign: "center" }}>Testimonials</motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", lineHeight: 1.12, marginBottom: 64, letterSpacing: "-.025em", textAlign: "center" }}>
          What team leads are saying
        </motion.h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }} className="testi-grid">
          {testimonials.map((t, i) => (
            <motion.div key={t.name}
              initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * .12 }}
              whileHover={{ y: -4, borderColor: "rgba(255,255,255,.1)" }}
              style={{ background: "#0a0a11", border: "1px solid rgba(255,255,255,.05)", borderRadius: 14, padding: "28px 24px", position: "relative", overflow: "hidden", transition: "border-color .3s" }}>
              <div style={{ position: "absolute", top: 16, right: 20, fontSize: "3rem", color: "rgba(255,255,255,.03)", lineHeight: 1, pointerEvents: "none" }}>❝</div>
              <p style={{ fontSize: ".9rem", color: "#777", lineHeight: 1.7, fontStyle: "italic", marginBottom: 20 }}>&ldquo;{t.quote}&rdquo;</p>
              <div style={{ height: 1, background: "rgba(255,255,255,.04)", marginBottom: 16 }} />
              <div style={{ color: "#ccc", fontWeight: 600, fontSize: ".85rem" }}>{t.name}</div>
              <div style={{ color: "#444", marginTop: 3, fontSize: ".78rem" }}>{t.role}</div>
            </motion.div>
          ))}
        </div>
      </div>
      <style>{`@media(max-width:768px){.testi-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
