"use client";
import { motion } from "framer-motion";

interface Props {
  size?: number;
  glowIntensity?: number;
}

export default function GhostMascot({ size = 140, glowIntensity = 1 }: Props) {
  return (
    <div style={{ position: "relative", width: size, height: size * 1.2, display: "flex", alignItems: "center", justifyContent: "center" }}>
      {/* Glow rings */}
      {[1, 2, 3].map(i => (
        <motion.div key={i}
          animate={{ scale: [1, 2.6, 1], opacity: [0.5 * glowIntensity, 0, 0.5 * glowIntensity] }}
          transition={{ duration: 3, delay: i * 0.9, repeat: Infinity, ease: "easeOut" }}
          style={{
            position: "absolute",
            width: size * 0.7, height: size * 0.7,
            borderRadius: "50%",
            border: `1px solid rgba(16,185,129,${0.3 * glowIntensity})`,
            pointerEvents: "none",
          }}
        />
      ))}
      {/* Ambient glow blob */}
      <motion.div
        animate={{ scale: [1, 1.15, 1], opacity: [0.35 * glowIntensity, 0.7 * glowIntensity, 0.35 * glowIntensity] }}
        transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
        style={{
          position: "absolute",
          width: size * 1.1, height: size * 1.1,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(16,185,129,${0.25 * glowIntensity}) 0%, transparent 70%)`,
          filter: "blur(20px)",
          pointerEvents: "none",
        }}
      />
      {/* Ghost SVG — floating */}
      <motion.div
        animate={{ y: [0, -18, -8, 0], rotate: [-1.5, 1.5, -0.5, -1.5] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
        style={{ position: "relative", zIndex: 2 }}
      >
        <svg width={size} height={size * 1.1} viewBox="0 0 120 132" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="ghostGrad" cx="50%" cy="40%" r="55%">
              <stop offset="0%" stopColor="#e8fff8" />
              <stop offset="60%" stopColor="#b2f5e4" />
              <stop offset="100%" stopColor="#6ee7b7" />
            </radialGradient>
            <radialGradient id="ghostShadow" cx="50%" cy="70%" r="50%">
              <stop offset="0%" stopColor="rgba(16,185,129,.15)" />
              <stop offset="100%" stopColor="transparent" />
            </radialGradient>
            <filter id="ghostGlow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Body */}
          <path
            d="M20 60 C20 28 38 10 60 10 C82 10 100 28 100 60 L100 110 C100 110 92 102 82 110 C72 118 68 106 60 110 C52 114 48 118 38 110 C28 102 20 110 20 110 Z"
            fill="url(#ghostGrad)"
            filter="url(#ghostGlow)"
          />
          {/* Inner glass sheen */}
          <path
            d="M35 35 C42 22 58 18 70 24"
            stroke="rgba(255,255,255,0.6)"
            strokeWidth="3"
            strokeLinecap="round"
            fill="none"
          />
          {/* Eyes */}
          <ellipse cx="44" cy="58" rx="9" ry="11" fill="#06060a" />
          <ellipse cx="76" cy="58" rx="9" ry="11" fill="#06060a" />
          {/* Eye pupils — green glow */}
          <ellipse cx="44" cy="58" rx="5" ry="6" fill="#10B981" />
          <ellipse cx="76" cy="58" rx="5" ry="6" fill="#10B981" />
          {/* Eye shine */}
          <circle cx="46" cy="55" r="2" fill="white" opacity="0.9" />
          <circle cx="78" cy="55" r="2" fill="white" opacity="0.9" />
          {/* Smile */}
          <path d="M48 76 Q60 86 72 76" stroke="#06060a" strokeWidth="2.5" strokeLinecap="round" fill="none" />
          {/* Wavy bottom */}
          <path
            d="M20 100 C20 100 28 92 36 100 C44 108 48 96 56 100 C64 104 64 108 72 100 C80 92 88 108 96 100 L100 110 C100 110 92 102 82 110 C72 118 68 106 60 110 C52 114 48 118 38 110 C28 102 20 110 20 110 Z"
            fill="rgba(16,185,129,0.15)"
          />
          {/* Green collar glow */}
          <ellipse cx="60" cy="108" rx="28" ry="6" fill="rgba(16,185,129,0.2)" filter="url(#ghostGlow)" />
        </svg>
      </motion.div>
    </div>
  );
}
