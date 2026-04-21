"use client";
import { useEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";

function Counter({ target, suffix }: { target: number; suffix: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });

  useEffect(() => {
    if (!inView) return;
    const start = performance.now();
    const duration = 1600;
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      setVal(Math.floor(ease * target));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [inView, target]);

  return <span ref={ref}>{val}{suffix}</span>;
}

export default function SocialProof() {
  return (
    <section style={{ padding: "52px 0", borderTop: "1px solid rgba(255,255,255,.04)", borderBottom: "1px solid rgba(255,255,255,.04)" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "0 24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 32, flexWrap: "wrap" }}>
          <motion.div initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }}
            style={{ fontSize: ".72rem", color: "#333", letterSpacing: "1.5px", textTransform: "uppercase" }}>
            Trusted by teams across India
          </motion.div>
          <div style={{ width: 1, height: 32, background: "rgba(255,255,255,.05)" }} />
          <div style={{ display: "flex", gap: 48, flexWrap: "wrap" }}>
            {[
              { target: 500, suffix: "+", label: "tasks completed" },
              { target: 48, suffix: "", label: "teams onboarded" },
              { target: 98, suffix: "%", label: "on-time delivery" },
            ].map(s => (
              <motion.div key={s.label} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} style={{ textAlign: "center" }}>
                <span style={{ fontFamily: "Georgia, serif", fontSize: "1.5rem", color: "#fff", display: "block", lineHeight: 1 }}>
                  <Counter target={s.target} suffix={s.suffix} />
                </span>
                <div style={{ fontSize: ".72rem", color: "#444", marginTop: 4, letterSpacing: ".5px" }}>{s.label}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
