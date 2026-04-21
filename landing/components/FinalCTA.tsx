"use client";
import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import GhostMascot from "./GhostMascot";

export default function FinalCTA() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <section ref={ref} style={{ padding: "160px 24px 120px", textAlign: "center", position: "relative", overflow: "hidden" }}>
      {/* Deep green radial glow */}
      <div style={{ position: "absolute", top: "40%", left: "50%", transform: "translate(-50%,-50%)", width: 900, height: 500, background: "radial-gradient(ellipse, rgba(16,185,129,.1) 0%, transparent 65%)", filter: "blur(60px)", pointerEvents: "none" }} />

      {/* Horizontal line top */}
      <motion.div initial={{ scaleX: 0 }} animate={inView ? { scaleX: 1 } : {}} transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        style={{ position: "absolute", top: 0, left: "10%", right: "10%", height: 1, background: "linear-gradient(90deg, transparent, rgba(16,185,129,.3), transparent)", transformOrigin: "left" }} />

      <div style={{ maxWidth: 760, margin: "0 auto", position: "relative", zIndex: 2 }}>
        <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={inView ? { opacity: 1, scale: 1 } : {}} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "flex", justifyContent: "center", marginBottom: 32 }}>
          <GhostMascot size={100} glowIntensity={2} />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.3, duration: 0.7 }}
          style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#10B981", marginBottom: 24, fontFamily: "var(--font-dm-sans)", fontWeight: 600 }}>
          Chapter 06 — Begin
        </motion.div>

        <motion.h2 initial={{ opacity: 0, y: 32 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.4, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          style={{ fontSize: "clamp(2.4rem,5.5vw,4.5rem)", lineHeight: 1.04, letterSpacing: "-.035em", marginBottom: 24 }}>
          Your team.<br />
          On WhatsApp.<br />
          <span style={{ color: "#10B981", textShadow: "0 0 60px rgba(16,185,129,.5)" }}>Starting today.</span>
        </motion.h2>

        <motion.p initial={{ opacity: 0, y: 20 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.55, duration: 0.7 }}
          style={{ color: "#5a6a7a", fontSize: "1.05rem", lineHeight: 1.8, marginBottom: 52, maxWidth: 500, margin: "0 auto 52px" }}>
          Join the businesses running smarter — no new apps, no onboarding headaches. Just WhatsApp and Phantom.
        </motion.p>

        <motion.div initial={{ opacity: 0, y: 24 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.7, duration: 0.7 }}
          style={{ display: "flex", gap: 16, justifyContent: "center", flexWrap: "wrap" }}>
          <a href="/signup">
            <motion.button
              className="btn-green"
              whileHover={{ y: -3, boxShadow: "0 24px 60px rgba(16,185,129,.4)" }}
              whileTap={{ scale: 0.97 }}
              style={{ padding: "18px 52px", borderRadius: 14, fontSize: "1.05rem", fontWeight: 700, letterSpacing: "-.01em" }}>
              Start Free — No Card Needed
            </motion.button>
          </a>
          <a href="#how">
            <motion.button
              className="btn-ghost"
              whileHover={{ y: -2 }}
              style={{ padding: "18px 32px", borderRadius: 14, fontSize: ".95rem" }}>
              See How It Works
            </motion.button>
          </a>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 1, duration: 0.6 }}
          style={{ marginTop: 36, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10B981", display: "inline-block", boxShadow: "0 0 8px #10B981", animation: "badge-pulse 2.5s ease infinite" }} />
          <span style={{ fontSize: ".75rem", color: "#2a3a4a" }}>Free during beta · 48 teams already running</span>
        </motion.div>
      </div>
    </section>
  );
}
