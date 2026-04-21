"use client";
import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import GhostMascot from "./GhostMascot";

/* ── Shared ── */
const SectionLabel = ({ children }: { children: React.ReactNode }) => (
  <div style={{ fontSize: ".68rem", letterSpacing: "3px", textTransform: "uppercase", color: "#10B981", marginBottom: 14, fontFamily: "var(--font-dm-sans)", fontWeight: 600 }}>{children}</div>
);

function FadeIn({ children, delay = 0, style = {} }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <motion.div ref={ref} initial={{ opacity: 0, y: 28 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ duration: .75, delay, ease: [.16,1,.3,1] }} style={style}>
      {children}
    </motion.div>
  );
}

/* ── Chapter 1: The Problem ── */
const chaosMessages = [
  { text: "where is the report? 🤔", left: "5%", top: "10%", delay: 0.1, rotate: -3 },
  { text: "did you finish the task?", left: "55%", top: "5%", delay: 0.25, rotate: 2 },
  { text: "I forgot 😬", left: "20%", top: "38%", delay: 0.4, rotate: -1.5 },
  { text: "which task was mine??", left: "50%", top: "35%", delay: 0.55, rotate: 3 },
  { text: "no update since yesterday", left: "2%", top: "62%", delay: 0.7, rotate: -2 },
  { text: "please respond 🙏", left: "60%", top: "60%", delay: 0.85, rotate: 1.5 },
  { text: "bhai kab hoga?", left: "28%", top: "70%", delay: 1.0, rotate: -1 },
];

function TheProblem() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} style={{ padding: "130px 24px", position: "relative", overflow: "hidden" }}>
      <div style={{ maxWidth: 900, margin: "0 auto", textAlign: "center", position: "relative", zIndex: 2 }}>
        <FadeIn><SectionLabel>Chapter 01 — The Problem</SectionLabel></FadeIn>
        <FadeIn delay={.1}>
          <h2 style={{ fontSize: "clamp(2rem,4vw,3.2rem)", lineHeight: 1.1, letterSpacing: "-.025em", marginBottom: 20 }}>
            Managing your team is<br />
            <span style={{ color: "#EF4444" }}>a WhatsApp nightmare.</span>
          </h2>
        </FadeIn>
        <FadeIn delay={.2}>
          <p style={{ color: "#5a6a7a", fontSize: "1rem", maxWidth: 480, margin: "0 auto 80px" }}>
            Every day. Missed tasks, lost messages, zero accountability.
          </p>
        </FadeIn>

        {/* Chaos bubble field */}
        <div style={{ position: "relative", height: 320, width: "100%", marginBottom: 40 }}>
          {chaosMessages.map((m, i) => (
            <motion.div key={i}
              initial={{ opacity: 0, scale: .7, rotate: m.rotate * 2 }}
              animate={inView ? { opacity: 1, scale: 1, rotate: m.rotate } : {}}
              transition={{ delay: m.delay, duration: .55, ease: [.16,1,.3,1] }}
              style={{
                position: "absolute", left: m.left, top: m.top,
                background: "rgba(239,68,68,.07)", border: "1px solid rgba(239,68,68,.18)",
                borderRadius: 12, padding: "8px 14px", fontSize: ".82rem",
                color: "rgba(255,180,180,.8)", backdropFilter: "blur(8px)",
                whiteSpace: "nowrap", boxShadow: "0 4px 20px rgba(239,68,68,.12)",
              }}>
              {m.text}
            </motion.div>
          ))}
          {/* Red chaos glow */}
          <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 300, height: 300, background: "radial-gradient(circle, rgba(239,68,68,.08) 0%, transparent 70%)", borderRadius: "50%", filter: "blur(30px)", pointerEvents: "none" }} />
        </div>
      </div>
    </section>
  );
}

/* ── Chapter 2: Meet Phantom ── */
function MeetPhantom() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section ref={ref} id="how" style={{ padding: "120px 24px", position: "relative" }}>
      <div style={{ maxWidth: 1000, margin: "0 auto" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "center" }} className="story-grid">
          {/* Ghost entrance */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
            <motion.div
              initial={{ opacity: 0, y: 60, scale: .8 }}
              animate={inView ? { opacity: 1, y: 0, scale: 1 } : {}}
              transition={{ duration: .9, ease: [.16,1,.3,1] }}>
              <GhostMascot size={200} glowIntensity={1.5} />
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: .5, duration: .6 }}
              style={{ background: "rgba(16,185,129,.1)", border: "1px solid rgba(16,185,129,.25)", borderRadius: "16px 16px 16px 4px", padding: "12px 20px", fontSize: ".95rem", color: "#10B981", fontStyle: "italic", backdropFilter: "blur(12px)", textAlign: "center", maxWidth: 260 }}>
              I&apos;ll take it from here. 👻<br />
              <span style={{ fontSize: ".78rem", opacity: .7 }}>No training. No onboarding.</span>
            </motion.div>
          </div>

          {/* Copy */}
          <div>
            <FadeIn><SectionLabel>Chapter 02 — Meet Phantom</SectionLabel></FadeIn>
            <FadeIn delay={.15}>
              <h2 style={{ fontSize: "clamp(1.9rem,3.5vw,3rem)", lineHeight: 1.1, letterSpacing: "-.02em", marginBottom: 20 }}>
                Meet your AI<br />
                <span style={{ color: "#10B981" }}>team manager.</span>
              </h2>
            </FadeIn>
            <FadeIn delay={.25}>
              <p style={{ color: "#5a6a7a", fontSize: ".98rem", lineHeight: 1.75, marginBottom: 32 }}>
                PhantomPilot lives in your WhatsApp. You type naturally — <em style={{ color: "rgba(255,255,255,.5)" }}>"Fix the AC at Block B by Friday → Rajesh"</em> — and Phantom handles the rest.
              </p>
            </FadeIn>
            {[
              { icon: "💬", text: "You assign in plain English on WhatsApp" },
              { icon: "📲", text: "Team member gets notified instantly" },
              { icon: "📊", text: "Dashboard updates in real time" },
            ].map((s, i) => (
              <FadeIn key={i} delay={.35 + i * .12}>
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16, padding: "14px 18px", background: "rgba(16,185,129,.04)", border: "1px solid rgba(16,185,129,.08)", borderRadius: 10 }}>
                  <span style={{ fontSize: "1.2rem" }}>{s.icon}</span>
                  <span style={{ fontSize: ".9rem", color: "rgba(255,255,255,.65)" }}>{s.text}</span>
                </div>
              </FadeIn>
            ))}
          </div>
        </div>
      </div>
      <style>{`@media(max-width:760px){.story-grid{grid-template-columns:1fr!important}}`}</style>
    </section>
  );
}

/* ── Chapter 3: The Magic Moment ── */
const conversation = [
  { from: "manager", text: "Fix AC at Sector 7 by 5pm → Rajesh", time: "9:02 AM" },
  { from: "phantom", text: "✅ Got it! Notifying Rajesh now...", time: "9:02 AM" },
  { from: "employee", text: "On my way boss 👍", time: "9:04 AM" },
  { from: "employee", text: "DONE. AC fixed ✅", time: "11:47 AM" },
  { from: "phantom", text: "📊 Dashboard updated. Task closed.", time: "11:47 AM" },
];

function MagicMoment() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });

  return (
    <section ref={ref} style={{ padding: "120px 24px" }}>
      <div style={{ maxWidth: 900, margin: "0 auto", textAlign: "center" }}>
        <FadeIn><SectionLabel>Chapter 03 — The Magic Moment</SectionLabel></FadeIn>
        <FadeIn delay={.1}>
          <h2 style={{ fontSize: "clamp(1.9rem,3.5vw,3rem)", lineHeight: 1.1, letterSpacing: "-.02em", marginBottom: 16 }}>
            From WhatsApp message<br />
            <span style={{ color: "#10B981" }}>to done — automatically.</span>
          </h2>
        </FadeIn>
        <FadeIn delay={.2}>
          <p style={{ color: "#5a6a7a", fontSize: ".98rem", maxWidth: 460, margin: "0 auto 56px" }}>
            Watch the full loop. You type once. Phantom does everything else.
          </p>
        </FadeIn>

        {/* Phone mockup with animated chat */}
        <div style={{ display: "inline-block", position: "relative" }}>
          <motion.div initial={{ opacity: 0, y: 40, scale: .95 }} animate={inView ? { opacity: 1, y: 0, scale: 1 } : {}} transition={{ duration: .8, ease: [.16,1,.3,1] }}
            style={{ width: 320, background: "#0e0e14", border: "1px solid rgba(255,255,255,.08)", borderRadius: 24, overflow: "hidden", boxShadow: "0 40px 80px rgba(0,0,0,.7), 0 0 0 1px rgba(16,185,129,.1)" }}>
            {/* Phone top bar */}
            <div style={{ background: "#0a0f0a", padding: "14px 18px", borderBottom: "1px solid rgba(255,255,255,.05)", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "rgba(16,185,129,.2)", border: "1px solid rgba(16,185,129,.3)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.1rem" }}>👻</div>
              <div>
                <div style={{ fontSize: ".8rem", color: "#fff", fontWeight: 600 }}>PhantomPilot</div>
                <div style={{ fontSize: ".65rem", color: "#10B981" }}>● Online</div>
              </div>
            </div>
            {/* Messages */}
            <div style={{ padding: "16px 14px", display: "flex", flexDirection: "column", gap: 10, minHeight: 300 }}>
              {conversation.map((msg, i) => (
                <motion.div key={i}
                  initial={{ opacity: 0, x: msg.from === "manager" ? 30 : -30, scale: .9 }}
                  animate={inView ? { opacity: 1, x: 0, scale: 1 } : {}}
                  transition={{ delay: .4 + i * .35, duration: .45, ease: [.16,1,.3,1] }}
                  style={{ display: "flex", justifyContent: msg.from === "manager" ? "flex-end" : "flex-start" }}>
                  <div style={{
                    maxWidth: "80%", padding: "8px 12px", borderRadius: msg.from === "manager" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                    background: msg.from === "manager" ? "rgba(16,185,129,.2)" : msg.from === "phantom" ? "rgba(255,255,255,.06)" : "rgba(255,255,255,.04)",
                    border: `1px solid ${msg.from === "manager" ? "rgba(16,185,129,.3)" : "rgba(255,255,255,.07)"}`,
                    fontSize: ".75rem", color: msg.from === "manager" ? "#10B981" : msg.from === "phantom" ? "#a0c8b0" : "rgba(255,255,255,.7)",
                    lineHeight: 1.5,
                  }}>
                    {msg.from === "phantom" && <div style={{ fontSize: ".6rem", color: "#10B981", marginBottom: 2, fontWeight: 600 }}>PHANTOM</div>}
                    {msg.text}
                    <div style={{ fontSize: ".55rem", color: "rgba(255,255,255,.25)", marginTop: 3, textAlign: "right" }}>{msg.time}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* Live dashboard ping */}
          <motion.div initial={{ opacity: 0, x: 20 }} animate={inView ? { opacity: 1, x: 0 } : {}} transition={{ delay: 2.2, duration: .5 }}
            style={{ position: "absolute", right: -170, top: "30%", background: "rgba(16,185,129,.1)", border: "1px solid rgba(16,185,129,.25)", borderRadius: 12, padding: "12px 16px", fontSize: ".75rem", color: "#10B981", backdropFilter: "blur(12px)", whiteSpace: "nowrap", boxShadow: "0 8px 32px rgba(16,185,129,.2)" }}
            className="dashboard-ping">
            <div style={{ fontWeight: 600, marginBottom: 4 }}>📊 Dashboard</div>
            <div style={{ color: "rgba(255,255,255,.5)" }}>Task closed ✓</div>
            <div style={{ color: "#10B981", fontSize: ".68rem", marginTop: 2 }}>98% on-time rate</div>
          </motion.div>
        </div>
      </div>
      <style>{`@media(max-width:600px){.dashboard-ping{display:none!important}}`}</style>
    </section>
  );
}

export default function ScrollStory() {
  return (
    <>
      <TheProblem />
      <MeetPhantom />
      <MagicMoment />
    </>
  );
}
