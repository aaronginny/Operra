"use client";
import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import * as THREE from "three";

function ParticleField() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.1, 1000);
    camera.position.z = 80;

    const COUNT = 1800;
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(COUNT * 3);
    for (let i = 0; i < COUNT * 3; i++) pos[i] = (Math.random() - 0.5) * 200;
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));

    const mat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.28, transparent: true, opacity: 0.35, sizeAttenuation: true });
    const points = new THREE.Points(geo, mat);
    scene.add(points);

    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      points.rotation.y += 0.00015;
      points.rotation.x += 0.00008;
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight);
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} style={{ position: "absolute", inset: 0, zIndex: 0 }} />;
}

const fadeUp = { hidden: { opacity: 0, y: 30 }, show: { opacity: 1, y: 0 } };
const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};

export default function Hero() {
  return (
    <section style={{
      minHeight: "100vh", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      textAlign: "center", padding: "140px 24px 80px",
      position: "relative", overflow: "hidden",
    }}>
      <ParticleField />

      {/* Rock side panels */}
      <div style={{
        position: "absolute", top: 0, left: 0, height: "100%", width: "22%",
        background: "linear-gradient(to right,#020206 0%,rgba(4,4,10,.75) 60%,transparent 100%)",
        clipPath: "polygon(0 0,100% 0,72% 3%,88% 8%,62% 14%,82% 21%,56% 29%,76% 37%,50% 45%,72% 53%,46% 61%,68% 69%,42% 77%,64% 84%,38% 91%,56% 100%,0 100%)",
        zIndex: 1, pointerEvents: "none",
      }} className="rock-panel" />
      <div style={{
        position: "absolute", top: 0, right: 0, height: "100%", width: "22%",
        background: "linear-gradient(to left,#020206 0%,rgba(4,4,10,.75) 60%,transparent 100%)",
        clipPath: "polygon(0 0,100% 0,100% 100%,44% 100%,62% 91%,36% 84%,58% 77%,32% 69%,54% 61%,28% 53%,50% 45%,24% 37%,44% 29%,18% 21%,38% 14%,12% 8%,28% 3%)",
        zIndex: 1, pointerEvents: "none",
      }} className="rock-panel" />

      <motion.div variants={container} initial="hidden" animate="show"
        style={{ position: "relative", zIndex: 2, display: "flex", flexDirection: "column", alignItems: "center" }}>

        {/* Badge */}
        <motion.div variants={fadeUp}
          style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            fontSize: ".72rem", letterSpacing: "2px", textTransform: "uppercase",
            color: "#888", border: "1px solid rgba(255,255,255,.08)",
            padding: "7px 18px", borderRadius: 100, marginBottom: 36,
            position: "relative", overflow: "hidden",
          }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%", background: "#10B981", flexShrink: 0,
            animation: "pulse-dot 2s ease infinite",
          }} />
          Task management via WhatsApp
          <span style={{
            position: "absolute", top: 0, left: 0, width: "60%", height: "100%",
            background: "linear-gradient(90deg,transparent,rgba(255,255,255,.06),transparent)",
            animation: "shimmer 3s ease infinite 1s",
          }} />
        </motion.div>

        {/* H1 */}
        <motion.h1 variants={fadeUp}
          style={{ fontSize: "clamp(2.4rem,6vw,4.4rem)", lineHeight: 1.06, letterSpacing: "-.04em", marginBottom: 24, maxWidth: 720 }}>
          Manage your team<br />on WhatsApp.
        </motion.h1>

        {/* Subtitle */}
        <motion.p variants={fadeUp}
          style={{ fontSize: "1.05rem", color: "#666", maxWidth: 480, margin: "0 auto 44px", lineHeight: 1.7 }}>
          Assign tasks, track progress, and keep your team accountable — all from WhatsApp. No app downloads. No training needed.
        </motion.p>

        {/* CTA */}
        <motion.div variants={fadeUp} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <motion.a
            href="https://operra-bo0x.onrender.com/dashboard"
            whileHover={{ y: -3, boxShadow: "0 20px 60px rgba(255,255,255,.13)" }}
            whileTap={{ scale: .97 }}
            style={{
              display: "inline-block", background: "#fff", color: "#06060a",
              padding: "16px 44px", borderRadius: 8, fontWeight: 700,
              fontSize: ".9rem", letterSpacing: ".3px", cursor: "pointer",
            }}>
            Get Started For Free
          </motion.a>
          <span style={{ fontSize: ".75rem", color: "#444", letterSpacing: ".3px" }}>
            Free 7-day trial — no credit card required
          </span>
        </motion.div>

        {/* Dashboard mockup */}
        <motion.div variants={fadeUp}
          style={{ marginTop: 80, width: "100%", maxWidth: 860, position: "relative" }}>
          <div style={{
            position: "absolute", top: "50%", left: "50%",
            transform: "translate(-50%,-50%)", width: 700, height: 350,
            background: "radial-gradient(ellipse,rgba(255,255,255,.05) 0%,transparent 70%)",
            pointerEvents: "none", zIndex: -1,
          }} />
          <motion.div
            whileHover={{ rotateX: 0, rotateY: 0 }}
            initial={{ rotateX: 4 }}
            style={{
              background: "#0e0e14", border: "1px solid rgba(255,255,255,.07)",
              borderRadius: 14, overflow: "hidden",
              boxShadow: "0 60px 120px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.05)",
              transformStyle: "preserve-3d", perspective: 1200,
            }}>
            {/* Browser bar */}
            <div style={{ height: 36, background: "#0a0a10", borderBottom: "1px solid rgba(255,255,255,.04)", display: "flex", alignItems: "center", padding: "0 14px", gap: 7 }}>
              {[["#EF4444",.6],["#F59E0B",.6],["#10B981",.6]].map(([c,o],i) => (
                <div key={i} style={{ width: 9, height: 9, borderRadius: "50%", background: c as string, opacity: o as number }} />
              ))}
            </div>
            {/* Stats row */}
            <div style={{ padding: 24, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
              {[
                { label: "Active Tasks", value: "24", bar: "72%", color: "#fff" },
                { label: "Completed", value: "156", bar: "88%", color: "#10B981" },
                { label: "On-Time Rate", value: "98%", bar: "98%", color: "#fff" },
              ].map(card => (
                <div key={card.label} style={{ background: "rgba(255,255,255,.025)", border: "1px solid rgba(255,255,255,.05)", borderRadius: 10, padding: 16 }}>
                  <div style={{ fontSize: ".68rem", color: "#555", textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: 10 }}>{card.label}</div>
                  <div style={{ fontFamily: "Georgia, serif", fontSize: "1.7rem", color: "#fff" }}>{card.value}</div>
                  <div style={{ height: 3, background: "rgba(255,255,255,.05)", borderRadius: 2, marginTop: 14, overflow: "hidden" }}>
                    <motion.div initial={{ width: 0 }} animate={{ width: card.bar }} transition={{ duration: 1.2, delay: .8, ease: [.16,1,.3,1] }}
                      style={{ height: "100%", background: card.color, borderRadius: 2 }} />
                  </div>
                </div>
              ))}
            </div>
            {/* Task rows */}
            <div style={{ padding: "4px 24px 16px" }}>
              {[
                { dot: "#10B981", label: "Fix plumbing at Site 3", badge: "Done", badgeBg: "rgba(16,185,129,.1)", badgeColor: "#10B981" },
                { dot: "#74b9ff", label: "Paint walls at Prestige Tower", badge: "In Progress", badgeBg: "rgba(116,185,255,.1)", badgeColor: "#74b9ff" },
                { dot: "#444", label: "Inspect wiring at Block C", badge: "Pending", badgeBg: "rgba(255,255,255,.04)", badgeColor: "#555" },
              ].map((row, i) => (
                <motion.div key={row.label} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 1.1 + i * 0.15, duration: .5 }}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: i < 2 ? "1px solid rgba(255,255,255,.03)" : "none" }}>
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: row.dot, flexShrink: 0 }} />
                  <div style={{ flex: 1, fontSize: ".7rem", color: "#888", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.label}</div>
                  <div style={{ fontSize: ".58rem", padding: "3px 9px", borderRadius: 4, fontWeight: 600, background: row.badgeBg, color: row.badgeColor }}>{row.badge}</div>
                </motion.div>
              ))}
            </div>
            {/* Typing row */}
            <div style={{ padding: "10px 24px 16px", borderTop: "1px solid rgba(255,255,255,.04)", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 26, height: 26, borderRadius: "50%", background: "rgba(255,255,255,.06)", border: "1px solid rgba(255,255,255,.08)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".6rem", color: "#777", flexShrink: 0 }}>You</div>
              <div style={{ background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.06)", borderRadius: 8, padding: "7px 12px", fontSize: ".68rem", color: "#666", overflow: "hidden", whiteSpace: "nowrap" }}>
                <span style={{ display: "inline-block", overflow: "hidden", whiteSpace: "nowrap", borderRight: "2px solid rgba(255,255,255,.35)", animation: "typing 4s steps(45,end) 1s infinite, blink .7s step-end 1s infinite" }}>
                  Fix the AC at Sector 7 by tomorrow 5pm → Rajesh
                </span>
              </div>
            </div>
          </motion.div>
        </motion.div>
      </motion.div>

      <style>{`@media(max-width:900px){.rock-panel{display:none!important}}`}</style>
    </section>
  );
}
