"use client";
import { useRef, useState } from "react";
import { motion } from "framer-motion";

const features = [
  { icon: "📋", num: "01", title: "Task Management", desc: "Assign tasks in plain English on WhatsApp. Deadlines, assignees, priorities — all tracked automatically." },
  { icon: "💬", num: "02", title: "WhatsApp Commands", desc: "Your team already uses WhatsApp. No new app, no training. Just type and Phantom handles the rest." },
  { icon: "🤖", num: "03", title: "AI Summaries", desc: "Workers send updates in plain language. Phantom summarises everything into clean, actionable reports for you." },
  { icon: "📥", num: "04", title: "Enquiry Pipeline", desc: "Capture leads and service requests from WhatsApp. Route them to the right team member automatically." },
  { icon: "🔔", num: "05", title: "Auto Reminders", desc: "Overdue tasks trigger automatic follow-ups. Your team stays on track without you chasing anyone." },
  { icon: "🗼", num: "06", title: "Control Tower", desc: "One dashboard. Every task, every team member, every status — updated live. No refresh needed." },
];

function FeatCard({ f, i }: { f: typeof features[0]; i: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [glow, setGlow] = useState({ x: "50%", y: "50%" });
  const [hovered, setHovered] = useState(false);

  const onMove = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    setGlow({
      x: `${((e.clientX - r.left) / r.width * 100).toFixed(1)}%`,
      y: `${((e.clientY - r.top) / r.height * 100).toFixed(1)}%`,
    });
  };

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: (i % 3) * 0.12, duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
      onMouseMove={onMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? "rgba(16,185,129,.05)" : "rgba(16,185,129,.02)",
        padding: "36px 32px",
        cursor: "default",
        position: "relative",
        overflow: "hidden",
        transition: "background .3s",
      }}>
      {/* Mouse-follow radial glow */}
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(circle at ${glow.x} ${glow.y}, rgba(16,185,129,.10) 0%, transparent 55%)`,
        opacity: hovered ? 1 : 0,
        transition: "opacity .3s",
        pointerEvents: "none",
      }} />
      {/* Shimmer on hover */}
      {hovered && (
        <div style={{
          position: "absolute", inset: 0,
          background: "linear-gradient(105deg, transparent 40%, rgba(16,185,129,.06) 50%, transparent 60%)",
          backgroundSize: "200% 100%",
          animation: "shimmer-slide 1.5s ease infinite",
          pointerEvents: "none",
        }} />
      )}
      <div style={{ fontSize: "1.5rem", marginBottom: 18, position: "relative" }}>{f.icon}</div>
      <div style={{ fontSize: ".6rem", color: "rgba(16,185,129,.4)", letterSpacing: "3px", textTransform: "uppercase", marginBottom: 10, position: "relative", fontFamily: "var(--font-dm-sans)", fontWeight: 600 }}>{f.num}</div>
      <h3 style={{ fontSize: "1.05rem", marginBottom: 12, color: hovered ? "#fff" : "rgba(255,255,255,.85)", position: "relative", transition: "color .3s", fontFamily: "var(--font-dm-sans)", fontWeight: 600, letterSpacing: "-.01em" }}>{f.title}</h3>
      <p style={{ fontSize: ".875rem", color: hovered ? "rgba(255,255,255,.55)" : "#4a5a6a", lineHeight: 1.75, position: "relative", transition: "color .3s" }}>{f.desc}</p>
    </motion.div>
  );
}

export default function Features() {
  return (
    <section id="features" style={{ padding: "120px 0" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#10B981", marginBottom: 14, fontFamily: "var(--font-dm-sans)", fontWeight: 600 }}>
          Chapter 04 — Features
        </motion.div>
        <motion.h2 initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
          style={{ fontSize: "clamp(1.9rem,3.5vw,3rem)", lineHeight: 1.1, marginBottom: 16, letterSpacing: "-.025em" }}>
          Everything you need.<br />
          <span style={{ color: "#10B981" }}>Nothing you don&apos;t.</span>
        </motion.h2>
        <motion.p initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .2 }}
          style={{ color: "#5a6a7a", fontSize: ".98rem", maxWidth: 480, lineHeight: 1.75, marginBottom: 64 }}>
          For anyone who leads a team — operations managers, project leads, business owners. If you use WhatsApp, you&apos;re already ready.
        </motion.p>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(3,1fr)",
          gap: "1px",
          background: "rgba(16,185,129,.08)",
          border: "1px solid rgba(16,185,129,.12)",
          borderRadius: 16,
          overflow: "hidden",
          backdropFilter: "blur(20px)",
        }} className="feat-grid">
          {features.map((f, i) => <FeatCard key={f.num} f={f} i={i} />)}
        </div>
      </div>
      <style>{`@media(max-width:1024px){.feat-grid{grid-template-columns:repeat(2,1fr)!important}}@media(max-width:600px){.feat-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
