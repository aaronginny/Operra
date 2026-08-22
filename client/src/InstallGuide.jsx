import { useState, useEffect } from "react";

const CSS = `
.ig-root{font-family:'Plus Jakarta Sans',sans-serif;background:#050E1E;color:#fff;min-height:100vh;-webkit-font-smoothing:antialiased}
.ig-nav{position:sticky;top:0;z-index:10;background:rgba(5,14,30,0.95);backdrop-filter:blur(16px);border-bottom:1px solid rgba(255,255,255,0.06);padding:14px 20px;display:flex;align-items:center;gap:12px}
.ig-nav-mark{width:32px;height:32px;background:#D4A84A;border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:'Fraunces',serif;font-weight:700;font-size:16px;color:#050E1E;flex-shrink:0}
.ig-nav-title{font-family:'Fraunces',serif;font-size:17px;font-weight:600;color:#fff}
.ig-nav-title span{color:#D4A84A}
.ig-back-btn{background:none;border:none;color:rgba(255,255,255,0.5);cursor:pointer;font-family:inherit;font-size:13px;padding:0;display:flex;align-items:center;gap:6px;margin-left:auto}
.ig-back-btn:hover{color:#fff}
.ig-hero{padding:36px 20px 28px;text-align:center}
.ig-hero-eyebrow{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.18em;text-transform:uppercase;color:#D4A84A;margin-bottom:12px}
.ig-hero-title{font-family:'Fraunces',serif;font-size:32px;font-weight:600;line-height:1.1;letter-spacing:-0.02em;margin-bottom:12px}
.ig-hero-title em{font-style:italic;color:#D4A84A;text-shadow:0 0 40px rgba(212,168,74,0.5)}
.ig-hero-sub{font-size:14px;color:rgba(255,255,255,0.5);line-height:1.6;max-width:320px;margin:0 auto 0}
.ig-install-btn{display:block;width:calc(100% - 40px);margin:24px 20px 8px;padding:14px;background:#D4A84A;color:#050E1E;border:none;border-radius:12px;font-family:inherit;font-size:15px;font-weight:800;cursor:pointer;text-align:center;transition:all .2s}
.ig-install-btn:hover{background:#E5C374;transform:translateY(-1px)}
.ig-section{padding:28px 20px}
.ig-section-head{margin-bottom:16px}
.ig-os-badge{display:inline-block;padding:6px 14px;border-radius:999px;font-size:12px;font-weight:700;font-family:'JetBrains Mono',monospace;letter-spacing:0.08em;margin-bottom:10px}
.ig-os-badge.android{background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.25);color:#4ade80}
.ig-os-badge.ios{background:rgba(99,179,237,0.12);border:1px solid rgba(99,179,237,0.25);color:#93c5fd}
.ig-section-title{font-family:'Fraunces',serif;font-size:22px;font-weight:600;color:#fff;margin:0}
.ig-steps{display:flex;flex-direction:column;gap:14px;margin-top:18px}
.ig-step{background:rgba(10,26,51,0.8);border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px;display:flex;gap:14px;align-items:flex-start}
.ig-step-num{width:32px;height:32px;border-radius:50%;background:rgba(212,168,74,0.1);border:1px solid rgba(212,168,74,0.25);color:#D4A84A;font-family:'Fraunces',serif;font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px}
.ig-step-title{font-size:14px;font-weight:700;color:#fff;margin-bottom:4px}
.ig-step-desc{font-size:13px;color:rgba(255,255,255,0.5);line-height:1.55}
.ig-warn{background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);border-radius:12px;padding:14px 16px;font-size:13px;color:rgba(251,191,36,0.9);line-height:1.6;margin-top:18px}
.ig-divider{height:1px;background:linear-gradient(90deg,transparent,rgba(212,168,74,0.2),transparent);margin:0 20px}
.ig-footer{padding:28px 20px;text-align:center;font-size:12px;color:rgba(255,255,255,0.25);border-top:1px solid rgba(255,255,255,0.06);margin-top:8px}
`;

function useInstallPrompt() {
  const [prompt, setPrompt] = useState(() => window._dkInstallPrompt || null);

  useEffect(() => {
    if (window._dkInstallPrompt) setPrompt(window._dkInstallPrompt);
    const handler = (e) => { e.preventDefault(); window._dkInstallPrompt = e; setPrompt(e); };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const install = async () => {
    if (!prompt) return;
    prompt.prompt();
    await prompt.userChoice;
    window._dkInstallPrompt = null;
    setPrompt(null);
  };

  return { canInstall: !!prompt, install };
}

export default function InstallGuide({ onClose }) {
  const { canInstall, install } = useInstallPrompt();

  useEffect(() => {
    const style = document.createElement("style");
    style.id = "ig-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
    return () => document.getElementById("ig-styles")?.remove();
  }, []);

  return (
    <div className="ig-root">
      <nav className="ig-nav">
        <div className="ig-nav-mark">D</div>
        <div className="ig-nav-title">Deal<span>Knot</span></div>
        {onClose && <button className="ig-back-btn" onClick={onClose}>← Back</button>}
      </nav>

      <div className="ig-hero">
        <div className="ig-hero-eyebrow">// Install guide</div>
        <h1 className="ig-hero-title">Add DealKnot to your<br /><em>home screen.</em></h1>
        <p className="ig-hero-sub">Install the app for faster access, offline support, and a native app feel.</p>
      </div>

      {canInstall && (
        <button className="ig-install-btn" onClick={install}>📲 Install DealKnot now</button>
      )}

      {/* ANDROID */}
      <div className="ig-section">
        <div className="ig-section-head">
          <div className="ig-os-badge android">Android · Chrome</div>
          <h2 className="ig-section-title">Install on Android</h2>
        </div>
        <div className="ig-steps">
          {[
            { title: "Open dealknot.live in Chrome", desc: "Make sure you're using Chrome browser on your Android phone." },
            { title: "⋮ Tap the 3-dot menu", desc: "Tap the three dots at the top right of Chrome." },
            { title: "Tap \"Add to Home Screen\"", desc: "Or tap the Install banner that appears at the bottom of the screen." },
            { title: "Tap \"Install\" ✓", desc: "DealKnot appears on your home screen like a native app." },
          ].map((s, i) => (
            <div className="ig-step" key={i}>
              <div className="ig-step-num">{i + 1}</div>
              <div>
                <div className="ig-step-title">{s.title}</div>
                <div className="ig-step-desc">{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="ig-divider" />

      {/* iOS */}
      <div className="ig-section">
        <div className="ig-section-head">
          <div className="ig-os-badge ios">iPhone · Safari</div>
          <h2 className="ig-section-title">Install on iPhone</h2>
        </div>
        <div className="ig-steps">
          {[
            { title: "Open dealknot.live in Safari", desc: "Must be Safari — not Chrome. Chrome on iOS cannot install PWAs." },
            { title: "⬆ Tap the Share button", desc: "The box with an arrow pointing up at the bottom of Safari." },
            { title: "Tap \"Add to Home Screen\"", desc: "Scroll down in the share sheet to find this option." },
            { title: "Tap \"Add\" ✓", desc: "DealKnot appears on your iPhone home screen." },
          ].map((s, i) => (
            <div className="ig-step" key={i}>
              <div className="ig-step-num">{i + 1}</div>
              <div>
                <div className="ig-step-title">{s.title}</div>
                <div className="ig-step-desc">{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="ig-warn">⚠️ Must use Safari on iPhone. Chrome on iOS cannot install home screen apps.</div>
      </div>

      <div className="ig-footer">© 2026 DealKnot · Where Deals Get Tied</div>
    </div>
  );
}
