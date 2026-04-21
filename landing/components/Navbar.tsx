"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const links = [
    { href: "#features", label: "Features" },
    { href: "#pricing", label: "Pricing" },
    { href: "#how", label: "How It Works" },
  ];

  return (
    <motion.nav
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        padding: scrolled ? "14px 0" : "20px 0",
        background: scrolled ? "rgba(6,6,10,.92)" : "transparent",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        borderBottom: scrolled ? "1px solid rgba(255,255,255,.05)" : "none",
        transition: "all .35s ease",
      }}
    >
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <a href="#" style={{ fontFamily: "Georgia, serif", fontSize: "1.2rem", color: "#fff", letterSpacing: "-.3px" }}>
          PhantomPilot
        </a>

        {/* Desktop links */}
        <div style={{ display: "flex", alignItems: "center", gap: 36 }} className="desktop-nav">
          {links.map(l => (
            <a key={l.href} href={l.href} style={{ fontSize: ".82rem", color: "#666", letterSpacing: ".5px", transition: "color .2s" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
              onMouseLeave={e => (e.currentTarget.style.color = "#666")}>
              {l.label}
            </a>
          ))}
          <a href="https://operra-bo0x.onrender.com/dashboard"
            style={{ fontSize: ".82rem", background: "#fff", color: "#06060a", padding: "9px 24px", borderRadius: 6, fontWeight: 600, transition: "opacity .2s" }}
            onMouseEnter={e => (e.currentTarget.style.opacity = ".85")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "1")}>
            Get Started Free
          </a>
        </div>

        {/* Mobile toggle */}
        <button onClick={() => setOpen(o => !o)}
          style={{ display: "none", background: "none", border: "none", cursor: "pointer", padding: 4, zIndex: 201 }}
          className="mobile-toggle" aria-label="Menu">
          {[0,1,2].map(i => (
            <span key={i} style={{
              display: "block", width: 22, height: 1.5, background: "#fff", margin: "5px 0",
              transition: "all .3s",
              transform: open ? (i === 0 ? "translateY(6.5px) rotate(45deg)" : i === 2 ? "translateY(-6.5px) rotate(-45deg)" : "") : "",
              opacity: open && i === 1 ? 0 : 1,
            }} />
          ))}
        </button>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ position: "fixed", inset: 0, background: "rgba(6,6,10,.98)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 28, zIndex: 199 }}>
            {links.map(l => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)}
                style={{ fontSize: "1.1rem", color: "#999" }}>{l.label}</a>
            ))}
            <a href="https://operra-bo0x.onrender.com/dashboard" onClick={() => setOpen(false)}
              style={{ fontSize: "1rem", background: "#fff", color: "#06060a", padding: "12px 32px", borderRadius: 8, fontWeight: 600 }}>
              Get Started Free
            </a>
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        @media(max-width:768px){.desktop-nav{display:none!important}.mobile-toggle{display:block!important}}
      `}</style>
    </motion.nav>
  );
}
