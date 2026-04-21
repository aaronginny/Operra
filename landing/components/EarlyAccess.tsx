"use client";
import { useRef } from "react";
import { motion, useInView } from "framer-motion";

function FadeIn({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.div ref={ref} initial={{ opacity: 0, y: 28 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.75, delay, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </motion.div>
  );
}

export default function EarlyAccess() {
  return (
    <section style={{ padding: "130px 24px", position: "relative", overflow: "hidden" }}>
      {/* Green ambient glow */}
      <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 600, height: 400, background: "radial-gradient(ellipse, rgba(16,185,129,.08) 0%, transparent 70%)", filter: "blur(40px)", pointerEvents: "none" }} />

      <div style={{ maxWidth: 680, margin: "0 auto", textAlign: "center", position: "relative", zIndex: 2 }}>
        <FadeIn>
          <div style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#10B981", marginBottom: 14, fontFamily: "var(--font-dm-sans)", fontWeight: 600 }}>
            Chapter 05 — Early Access
          </div>
        </FadeIn>

        <FadeIn delay={0.1}>
          <h2 style={{ fontSize: "clamp(2.2rem,5vw,4rem)", lineHeight: 1.05, letterSpacing: "-.03em", marginBottom: 20 }}>
            Free while we&apos;re<br />
            <span style={{ color: "#10B981", textShadow: "0 0 40px rgba(16,185,129,.4)" }}>in beta.</span>
          </h2>
        </FadeIn>

        <FadeIn delay={0.2}>
          <p style={{ color: "#5a6a7a", fontSize: "1.05rem", lineHeight: 1.8, marginBottom: 16 }}>
            We&apos;re onboarding the first 100 businesses personally. You get full access, we get feedback. No credit card. No catch.
          </p>
        </FadeIn>

        <FadeIn delay={0.3}>
          <p style={{ color: "rgba(16,185,129,.6)", fontSize: ".85rem", marginBottom: 48, fontFamily: "var(--font-dm-sans)" }}>
            67 spots left
          </p>
        </FadeIn>

        <FadeIn delay={0.4}>
          <a href="/signup">
            <button className="btn-green" style={{ padding: "18px 48px", borderRadius: 14, fontSize: "1.05rem", fontWeight: 700, letterSpacing: "-.01em" }}>
              Claim Your Free Spot →
            </button>
          </a>
        </FadeIn>

        <FadeIn delay={0.55}>
          <div style={{ marginTop: 28, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#10B981", display: "inline-block", boxShadow: "0 0 10px #10B981", animation: "badge-pulse 2.5s ease infinite" }} />
            <span style={{ fontSize: ".78rem", color: "#3a4a5a" }}>No credit card · Free during beta · Cancel anytime</span>
          </div>
        </FadeIn>

        <FadeIn delay={0.7}>
          <div style={{ marginTop: 56, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }} className="perks-grid">
            {[
              { icon: "✓", text: "Full feature access" },
              { icon: "✓", text: "Personal onboarding" },
              { icon: "✓", text: "Direct founder support" },
            ].map((p, i) => (
              <div key={i} style={{ padding: "16px", background: "rgba(16,185,129,.04)", border: "1px solid rgba(16,185,129,.1)", borderRadius: 10, fontSize: ".82rem", color: "rgba(255,255,255,.5)" }}>
                <span style={{ color: "#10B981", marginRight: 8, fontWeight: 700 }}>{p.icon}</span>{p.text}
              </div>
            ))}
          </div>
        </FadeIn>
      </div>
      <style>{`@media(max-width:560px){.perks-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}
