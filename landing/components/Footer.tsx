"use client";

export default function Footer() {
  return (
    <footer style={{ padding: "28px 0", borderTop: "1px solid rgba(16,185,129,.06)" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div style={{ color: "#2d3d2d", fontSize: ".78rem", fontFamily: "var(--font-dm-sans)" }}>© 2026 PhantomPilot</div>
        <div style={{ display: "flex", gap: 24 }}>
          {[
            { href: "https://operra-bo0x.onrender.com/static/terms.html", label: "Terms" },
            { href: "https://operra-bo0x.onrender.com/static/privacy.html", label: "Privacy" },
            { href: "mailto:aaronginnycodes@gmail.com", label: "Contact" },
          ].map(l => (
            <a key={l.label} href={l.href} style={{ color: "#2d3d2d", fontSize: ".78rem", transition: "color .2s", textDecoration: "none" }}
              onMouseEnter={e => (e.currentTarget.style.color = "#666")}
              onMouseLeave={e => (e.currentTarget.style.color = "#2d3d2d")}>
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  );
}
