"use client";
import { useRef, useState, useEffect } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import GhostMascot from "./GhostMascot";

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.13, duration: 0.75, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] } }),
};

function WaBubble({ text, delay, fromRight }: { text: string; delay: number; fromRight?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: fromRight ? 40 : -40, scale: 0.85 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ delay, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        background: fromRight ? "rgba(16,185,129,.15)" : "rgba(255,255,255,.06)",
        border: `1px solid ${fromRight ? "rgba(16,185,129,.3)" : "rgba(255,255,255,.1)"}`,
        borderRadius: fromRight ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        padding: "10px 16px", fontSize: ".85rem",
        color: fromRight ? "#10B981" : "rgba(255,255,255,.8)",
        backdropFilter: "blur(12px)",
        alignSelf: fromRight ? "flex-end" : "flex-start",
        boxShadow: fromRight ? "0 4px 24px rgba(16,185,129,.2)" : "0 4px 16px rgba(0,0,0,.3)",
      }}>
      {text}
    </motion.div>
  );
}

export default function Hero() {
  const heroRef = useRef<HTMLElement>(null);
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const springX = useSpring(mouseX, { stiffness: 60, damping: 20 });
  const springY = useSpring(mouseY, { stiffness: 60, damping: 20 });
  const orbX = useTransform(springX, [-1, 1], [-18, 18]);
  const orbY = useTransform(springY, [-1, 1], [-12, 12]);
  const ghostX = useTransform(springX, [-1, 1], [-10, 10]);
  const ghostY = useTransform(springY, [-1, 1], [-6, 6]);

  const [showBubble, setShowBubble] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setShowBubble(true), 2200);
    return () => clearTimeout(t);
  }, []);

  const onMouseMove = (e: React.MouseEvent) => {
    const rect = heroRef.current?.getBoundingClientRect();
    if (!rect) return;
    mouseX.set(((e.clientX - rect.left) / rect.width - 0.5) * 2);
    mouseY.set(((e.clientY - rect.top) / rect.height - 0.5) * 2);
  };

  return (
    <section ref={heroRef} onMouseMove={onMouseMove} id="hero"
      style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "120px 24px 80px", position: "relative", overflow: "hidden" }}>

      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 40%, rgba(16,185,129,.07) 0%, transparent 65%), linear-gradient(180deg, rgba(6,6,10,0) 60%, rgba(6,6,10,1) 100%)", pointerEvents: "none", zIndex: 1 }} />

      {/* CSS parallax orbs */}
      <motion.div style={{ x: orbX, y: orbY, position: "absolute", top: "12%", right: "8%", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle, rgba(16,185,129,.09) 0%, transparent 70%)", filter: "blur(40px)", pointerEvents: "none", zIndex: 1 }} />
      <motion.div style={{ x: useTransform(springX,[-1,1],[12,-12]), y: useTransform(springY,[-1,1],[8,-8]), position: "absolute", bottom: "18%", left: "6%", width: 220, height: 220, borderRadius: "50%", background: "radial-gradient(circle, rgba(16,185,129,.06) 0%, transparent 70%)", filter: "blur(30px)", pointerEvents: "none", zIndex: 1 }} />

      <div style={{ maxWidth: 1100, width: "100%", margin: "0 auto", position: "relative", zIndex: 2 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 400px", gap: 60, alignItems: "center" }} className="hero-grid">

          {/* LEFT */}
          <div>
            <motion.div custom={0} variants={fadeUp} initial="hidden" animate="show" style={{ marginBottom: 32 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "rgba(16,185,129,.1)", border: "1px solid rgba(16,185,129,.3)", borderRadius: 100, padding: "7px 18px", fontSize: ".75rem", color: "#10B981", letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 600, animation: "badge-pulse 2.5s ease infinite" }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#10B981", display: "inline-block", boxShadow: "0 0 10px #10B981" }} />
                Early Access — Free
              </span>
            </motion.div>

            <motion.h1 custom={1} variants={fadeUp} initial="hidden" animate="show"
              style={{ fontSize: "clamp(2.6rem,5.5vw,4.8rem)", lineHeight: 1.04, letterSpacing: "-.03em", marginBottom: 24 }}>
              Your team runs<br />
              <span style={{ color: "#10B981", textShadow: "0 0 40px rgba(16,185,129,.5)" }}>on WhatsApp.</span>
            </motion.h1>

            <motion.p custom={2} variants={fadeUp} initial="hidden" animate="show"
              style={{ fontSize: "1.1rem", color: "#6a7a8a", lineHeight: 1.75, marginBottom: 44, maxWidth: 460 }}>
              Assign tasks. Get updates. No app downloads. No training.<br />
              <span style={{ color: "rgba(255,255,255,.4)" }}>Built for Indian teams who already use WhatsApp.</span>
            </motion.p>

            <motion.div custom={3} variants={fadeUp} initial="hidden" animate="show"
              style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              <a href="/signup">
                <button className="btn-green" style={{ padding: "15px 36px", borderRadius: 12, fontSize: "1rem" }}>
                  Start Free Trial →
                </button>
              </a>
              <a href="#how">
                <button className="btn-ghost" style={{ padding: "15px 28px", borderRadius: 12, fontSize: ".95rem" }}>
                  See How It Works
                </button>
              </a>
            </motion.div>

            <motion.div custom={4} variants={fadeUp} initial="hidden" animate="show"
              style={{ marginTop: 28, display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ display: "flex" }}>
                {["R","P","S","A"].map((l, i) => (
                  <div key={i} style={{ width: 28, height: 28, borderRadius: "50%", background: `hsl(${155+i*15},50%,25%)`, border: "2px solid #06060a", marginLeft: i > 0 ? -8 : 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".58rem", color: "#10B981", fontWeight: 700 }}>{l}</div>
                ))}
              </div>
              <span style={{ fontSize: ".8rem", color: "#444" }}>48 teams · <span style={{ color: "#10B981" }}>Free while in beta</span></span>
            </motion.div>
          </div>

          {/* RIGHT */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <motion.div style={{ x: ghostX, y: ghostY }}>
              <GhostMascot size={175} glowIntensity={1.2} />
            </motion.div>

            <motion.div initial={{ opacity: 0, scale: .85 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 1.1, duration: .5, ease: [.16,1,.3,1] }}
              style={{ marginTop: -16, background: "rgba(16,185,129,.1)", border: "1px solid rgba(16,185,129,.25)", borderRadius: "16px 16px 16px 4px", padding: "9px 16px", fontSize: ".85rem", color: "#10B981", fontStyle: "italic", backdropFilter: "blur(12px)", textAlign: "center" }}>
              I&apos;ll handle your team. 👻
            </motion.div>

            <div style={{ marginTop: 28, width: "100%", display: "flex", flexDirection: "column", gap: 10 }}>
              <WaBubble text="Fix the AC at Site 3 by 5pm → Arjun" delay={1.5} />
              <WaBubble text="✅ Task done boss!" delay={2.1} fromRight />
              {showBubble && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35 }}
                  style={{ alignSelf: "flex-end", background: "rgba(16,185,129,.07)", border: "1px solid rgba(16,185,129,.2)", borderRadius: "18px 4px 18px 18px", padding: "8px 14px", display: "flex", gap: 5, alignItems: "center" }}>
                  {[0,1,2].map(i => <span key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: "#10B981", display: "inline-block", animation: `dot-bounce 1.2s ease ${i*.2}s infinite` }} />)}
                </motion.div>
              )}
            </div>
          </div>
        </div>
      </div>

      <motion.div animate={{ y: [0,10,0] }} transition={{ duration: 1.8, repeat: Infinity }}
        style={{ position: "absolute", bottom: 32, left: "50%", transform: "translateX(-50%)", display: "flex", flexDirection: "column", alignItems: "center", gap: 6, zIndex: 2 }}>
        <span style={{ fontSize: ".65rem", color: "#2a3a2a", letterSpacing: "2px", textTransform: "uppercase" }}>Scroll</span>
        <div style={{ width: 1, height: 36, background: "linear-gradient(to bottom, rgba(16,185,129,.4), transparent)" }} />
      </motion.div>

      <style>{`@media(max-width:860px){.hero-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
