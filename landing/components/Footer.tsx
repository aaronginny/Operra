"use client";
import { motion } from "framer-motion";

export default function Footer() {
  return (
    <>
      {/* Final CTA */}
      <section style={{ padding: "130px 0 90px", textAlign: "center", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 800, height: 400, background: "radial-gradient(ellipse,rgba(255,255,255,.04) 0%,transparent 70%)", pointerEvents: "none" }} />
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px", position: "relative", zIndex: 1 }}>
          <motion.h2 initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
            style={{ fontSize: "clamp(2rem,4.5vw,3rem)", lineHeight: 1.1, letterSpacing: "-.025em", marginBottom: 20 }}>
            Ready to run your team<br />from WhatsApp?
          </motion.h2>
          <motion.p initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .1 }}
            style={{ color: "#555", fontSize: "1rem", marginBottom: 40 }}>
            Join 48 teams already managing smarter with PhantomPilot.
          </motion.p>
          <motion.a href="https://operra-bo0x.onrender.com/dashboard"
            initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: .2 }}
            whileHover={{ y: -3, boxShadow: "0 20px 60px rgba(255,255,255,.12)" }}
            whileTap={{ scale: .97 }}
            style={{ display: "inline-block", background: "#fff", color: "#06060a", padding: "16px 44px", borderRadius: 8, fontWeight: 700, fontSize: ".9rem", letterSpacing: ".3px" }}>
            Start Free Today
          </motion.a>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ padding: "28px 0", borderTop: "1px solid rgba(255,255,255,.04)" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div style={{ color: "#2d2d35", fontSize: ".78rem" }}>© 2026 PhantomPilot</div>
          <div style={{ display: "flex", gap: 24 }}>
            {[
              { href: "https://operra-bo0x.onrender.com/static/terms.html", label: "Terms" },
              { href: "https://operra-bo0x.onrender.com/static/privacy.html", label: "Privacy" },
              { href: "mailto:aaronginnycodes@gmail.com", label: "Contact" },
            ].map(l => (
              <a key={l.label} href={l.href} style={{ color: "#333", fontSize: ".78rem", transition: "color .2s" }}
                onMouseEnter={e => (e.currentTarget.style.color = "#888")}
                onMouseLeave={e => (e.currentTarget.style.color = "#333")}>
                {l.label}
              </a>
            ))}
          </div>
        </div>
      </footer>
    </>
  );
}
