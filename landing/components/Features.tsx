"use client";
import { useRef, useState } from "react";
import { motion } from "framer-motion";

const features = [
  { icon: "🗼", num: "01", title: "Control Tower", desc: "Control everything from WhatsApp. Change deadlines, check status, send updates — just type it." },
  { icon: "✅", num: "02", title: "Smart Checkpoints", desc: "Break tasks into steps. Team members tick them off via WhatsApp as they go. You see progress in real time." },
  { icon: "🌅", num: "03", title: "Morning Pulse", desc: "Every morning, your team gets their task list automatically. No micromanaging needed." },
  { icon: "⚡", num: "04", title: "Live Dashboard", desc: "See every task, every team member, every status — updated in real time. No refresh needed." },
  { icon: "🔁", num: "05", title: "Auto Reminders", desc: "Automatic follow-ups keep your team on track without you lifting a finger. Overdue tasks get reminders sent automatically." },
  { icon: "📈", num: "06", title: "Progress Tracking", desc: "Workers send updates in plain English. AI summarises it for you in clean, actionable reports." },
];

function FeatCard({ f, i }: { f: typeof features[0]; i: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [glow, setGlow] = useState({ x: "50%", y: "50%" });

  const onMove = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    setGlow({ x: `${((e.clientX - r.left) / r.width * 100).toFixed(1)}%`, y: `${((e.clientY - r.top) / r.height * 100).toFixed(1)}%` });
  };

  return (
    <motion.div ref={ref}
      initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: (i % 3) * .1 }}
      onMouseMove={onMove}
      style={{ background: "#06060a", padding: "36px 32px", cursor: "default", position: "relative", overflow: "hidden", transition: "background .3s" }}
      whileHover={{ backgroundColor: "#09090f" } as never}>
      {/* Mouse-follow radial glow */}
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(circle at ${glow.x} ${glow.y},rgba(255,255,255,.04) 0%,transparent 60%)`,
        pointerEvents: "none",
      }} />
      <div style={{ fontSize: "1.3rem", marginBottom: 16, position: "relative" }}>{f.icon}</div>
      <div style={{ fontSize: ".65rem", color: "#333", letterSpacing: "2px", marginBottom: 10, position: "relative" }}>{f.num}</div>
      <h3 style={{ fontSize: "1rem", marginBottom: 10, color: "#ddd", position: "relative" }}>{f.title}</h3>
      <p style={{ fontSize: ".85rem", color: "#555", lineHeight: 1.7, position: "relative" }}>{f.desc}</p>
    </motion.div>
  );
}

export default function Features() {
  return (
    <section id="features" style={{ padding: "120px 0" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#444", marginBottom: 14 }}>Features</motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.8rem,3.5vw,2.6rem)", lineHeight: 1.12, marginBottom: 16, letterSpacing: "-.025em" }}>
          Everything you need to<br />manage your team
        </motion.h2>
        <motion.p initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .2 }}
          style={{ color: "#555", fontSize: ".95rem", maxWidth: 480, lineHeight: 1.7, marginBottom: 64 }}>
          For anyone who leads a team — operations managers, project leads, HR managers, coaches, business owners.
        </motion.p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "1px", background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.04)", borderRadius: 14, overflow: "hidden" }} className="feat-grid">
          {features.map((f, i) => <FeatCard key={f.num} f={f} i={i} />)}
        </div>
      </div>
      <style>{`@media(max-width:1024px){.feat-grid{grid-template-columns:repeat(2,1fr)!important}}@media(max-width:600px){.feat-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
