import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import InstallGuide from "./InstallGuide";

function usePWAInstall() {
  const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  const isAndroid = /Android/i.test(navigator.userAgent);
  const isMobileDevice = isIOS || isAndroid;
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches
    || navigator.standalone === true;

  const [promptAvailable, setPromptAvailable] = useState(() => !!window._dkInstallPrompt);
  const [installed, setInstalled] = useState(isStandalone);

  useEffect(() => {
    // Capture the prompt (fired before login, so we must register here too)
    const handler = (e) => {
      e.preventDefault();
      window._dkInstallPrompt = e;
      setPromptAvailable(true);
    };
    const installedHandler = () => { setInstalled(true); setPromptAvailable(false); };
    window.addEventListener("beforeinstallprompt", handler);
    window.addEventListener("appinstalled", installedHandler);
    // Sync in case it was already captured
    if (window._dkInstallPrompt) setPromptAvailable(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", installedHandler);
    };
  }, []);

  const triggerInstall = async () => {
    if (!window._dkInstallPrompt) return;
    window._dkInstallPrompt.prompt();
    const { outcome } = await window._dkInstallPrompt.userChoice;
    if (outcome === "accepted") { setInstalled(true); setPromptAvailable(false); }
    window._dkInstallPrompt = null;
  };

  return { isIOS, isAndroid, isMobileDevice, installed, promptAvailable, triggerInstall };
}

const CSS = `
.lp-root *{margin:0;padding:0;box-sizing:border-box}
.lp-root{
  --navy:#050E1E;--navy-2:#07111E;--navy-3:#0A1A33;--navy-4:#102A4D;
  --gold:#D4A84A;--gold-light:#E5C374;--gold-pale:#F2E7CC;
  --white:#FFFFFF;--grey:#8590A0;--line:rgba(255,255,255,0.06);
  font-family:'Plus Jakarta Sans',sans-serif;background:var(--navy);color:var(--white);overflow-x:hidden;-webkit-font-smoothing:antialiased;scroll-behavior:smooth;
}
/* NAV */
.lp-nav{position:fixed;top:0;left:0;right:0;z-index:200;padding:18px 56px;display:flex;align-items:center;justify-content:space-between;background:rgba(5,14,30,0.92);backdrop-filter:blur(24px);border-bottom:1px solid var(--line)}
.lp-logo{display:flex;align-items:center;gap:12px;text-decoration:none;cursor:pointer}
.lp-logo-mark{width:36px;height:36px;background:var(--gold);border-radius:9px;display:flex;align-items:center;justify-content:center;font-family:'Fraunces',serif;font-weight:700;font-size:19px;color:var(--navy);box-shadow:0 0 24px rgba(212,168,74,0.4)}
.lp-logo-text{font-family:'Fraunces',serif;font-size:19px;font-weight:600;color:var(--white);letter-spacing:-0.01em}
.lp-logo-text span{color:var(--gold)}
.lp-nav-links{display:flex;align-items:center;gap:6px}
.lp-nav-link{color:rgba(255,255,255,0.55);font-size:13px;font-weight:500;text-decoration:none;padding:7px 14px;border-radius:7px;transition:all .2s;background:none;border:none;cursor:pointer;font-family:inherit}
.lp-nav-link:hover{color:var(--white);background:rgba(255,255,255,0.05)}
.lp-nav-btn{padding:8px 18px;border-radius:8px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;transition:all .2s;text-decoration:none;display:inline-flex;align-items:center;border:none}
.lp-nav-btn.ghost{background:transparent;color:var(--white);border:1px solid rgba(255,255,255,0.14)}
.lp-nav-btn.ghost:hover{border-color:var(--gold);color:var(--gold)}
.lp-nav-btn.gold{background:var(--gold);color:var(--navy)}
.lp-nav-btn.gold:hover{background:var(--gold-light);transform:translateY(-1px);box-shadow:0 4px 20px rgba(212,168,74,0.4)}
/* HERO */
.lp-hero{min-height:100vh;display:grid;grid-template-columns:1.1fr 0.9fr;position:relative;overflow:hidden}
.lp-hero-bg{position:absolute;inset:0;background:radial-gradient(ellipse 55% 70% at 15% 55%, rgba(212,168,74,0.09) 0%, transparent 65%),radial-gradient(ellipse 45% 55% at 85% 25%, rgba(10,26,51,0.8) 0%, transparent 70%),radial-gradient(ellipse 70% 50% at 50% 100%, rgba(5,14,30,0.95) 0%, transparent 60%),var(--navy)}
.lp-hero-left{position:relative;z-index:2;display:flex;flex-direction:column;justify-content:center;padding:140px 56px 80px 64px}
.lp-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(212,168,74,0.08);border:1px solid rgba(212,168,74,0.18);border-radius:999px;padding:6px 16px;font-size:11px;font-weight:600;color:var(--gold-light);font-family:'JetBrains Mono',monospace;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:36px;width:fit-content;animation:lp-fadeUp .9s ease both}
.lp-badge .lp-dot{width:6px;height:6px;border-radius:50%;background:var(--gold);animation:lp-pulse 2s infinite}
@keyframes lp-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}
.lp-headline{font-family:'Fraunces',serif;font-size:78px;font-weight:600;line-height:1.01;letter-spacing:-0.025em;margin-bottom:26px;animation:lp-fadeUp .9s .1s ease both}
.lp-headline .line1{display:block;text-shadow:0 0 80px rgba(255,255,255,0.1),0 0 160px rgba(255,255,255,0.05)}
.lp-headline .line2{display:block}
.lp-headline em{font-style:italic;color:var(--gold);text-shadow:0 0 50px rgba(212,168,74,0.7),0 0 100px rgba(212,168,74,0.35),0 0 180px rgba(212,168,74,0.15);position:relative}
.lp-headline em::after{content:'';position:absolute;bottom:-6px;left:0;width:55%;height:2px;background:linear-gradient(90deg,var(--gold),transparent);box-shadow:0 0 14px rgba(212,168,74,0.6)}
.lp-sub{font-size:17px;color:rgba(255,255,255,0.55);line-height:1.7;max-width:460px;margin-bottom:44px;animation:lp-fadeUp .9s .2s ease both}
.lp-sub strong{color:rgba(255,255,255,0.9)}
.lp-features-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 28px;margin-bottom:48px;animation:lp-fadeUp .9s .3s ease both}
.lp-feature-item{display:flex;align-items:flex-start;gap:10px;font-size:13px;color:rgba(255,255,255,0.65);line-height:1.45}
.lp-feature-item .lp-check{width:18px;height:18px;flex-shrink:0;margin-top:1px;background:rgba(212,168,74,0.12);border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--gold);font-size:9px;font-weight:700}
.lp-feature-item strong{color:rgba(255,255,255,0.9)}
.lp-hero-cta{display:flex;align-items:center;gap:14px;flex-wrap:wrap;animation:lp-fadeUp .9s .4s ease both}
.lp-cta-btn{padding:13px 28px;border-radius:10px;font-family:inherit;font-size:14px;font-weight:700;cursor:pointer;transition:all .2s;text-decoration:none;display:inline-flex;align-items:center;gap:8px;border:none}
.lp-cta-btn.primary{background:var(--gold);color:var(--navy);box-shadow:0 8px 32px rgba(212,168,74,0.35)}
.lp-cta-btn.primary:hover{background:var(--gold-light);transform:translateY(-2px);box-shadow:0 16px 48px rgba(212,168,74,0.5)}
.lp-cta-btn.secondary{background:transparent;color:var(--white);border:1px solid rgba(255,255,255,0.12)}
.lp-cta-btn.secondary:hover{border-color:rgba(255,255,255,0.35);transform:translateY(-1px)}
.lp-beta-note{font-size:12px;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:6px}
/* HERO RIGHT */
.lp-hero-right{position:relative;z-index:2;display:flex;align-items:center;justify-content:center;padding:140px 56px 80px 32px}
.lp-auth-trigger{display:flex;flex-direction:column;align-items:center;gap:24px;text-align:center;animation:lp-fadeUp .9s .3s ease both}
.lp-auth-trigger-headline{font-family:'Fraunces',serif;font-size:36px;font-weight:500;color:rgba(255,255,255,0.75);line-height:1.25;letter-spacing:-0.015em}
.lp-auth-trigger-headline em{color:var(--gold);font-style:italic;text-shadow:0 0 40px rgba(212,168,74,0.5)}
.lp-auth-trigger-sub{font-size:14px;color:rgba(255,255,255,0.35);line-height:1.5;max-width:280px}
.lp-auth-trigger-btns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.lp-trigger-btn{padding:14px 32px;border-radius:10px;font-family:inherit;font-size:14px;font-weight:700;cursor:pointer;transition:all .25s;border:none}
.lp-trigger-btn.signup{background:var(--gold);color:var(--navy);box-shadow:0 8px 32px rgba(212,168,74,0.3)}
.lp-trigger-btn.signup:hover{background:var(--gold-light);transform:translateY(-2px);box-shadow:0 16px 40px rgba(212,168,74,0.5)}
.lp-trigger-btn.login{background:rgba(255,255,255,0.06);color:var(--white);border:1px solid rgba(255,255,255,0.12)}
.lp-trigger-btn.login:hover{background:rgba(255,255,255,0.1);transform:translateY(-1px)}
/* Auth card */
.lp-auth-card-wrap{position:relative;width:100%;max-width:400px}
.lp-auth-card{width:100%;background:rgba(8,20,40,0.88);border:1px solid rgba(255,255,255,0.07);border-radius:20px;padding:36px;backdrop-filter:blur(24px);box-shadow:0 40px 100px rgba(0,0,0,0.5),0 0 0 1px rgba(212,168,74,0.04);animation:lp-scaleIn .3s ease}
@keyframes lp-scaleIn{from{opacity:0;transform:scale(0.95) translateY(12px)}to{opacity:1;transform:scale(1) translateY(0)}}
.lp-auth-close{position:absolute;top:14px;right:14px;width:28px;height:28px;border-radius:50%;background:rgba(255,255,255,0.06);border:none;color:var(--grey);cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;transition:all .2s}
.lp-auth-close:hover{background:rgba(255,255,255,0.1);color:var(--white)}
.lp-auth-eyebrow{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:500;text-transform:uppercase;letter-spacing:0.16em;color:var(--grey);margin-bottom:6px}
.lp-auth-headline{font-family:'Fraunces',serif;font-size:26px;font-weight:600;color:var(--white);margin-bottom:4px;letter-spacing:-0.01em}
.lp-auth-headline em{color:var(--gold);font-style:italic;text-shadow:0 0 30px rgba(212,168,74,0.45)}
.lp-auth-sub{font-size:13px;color:var(--grey);margin-bottom:26px}
.lp-auth-tabs{display:grid;grid-template-columns:1fr 1fr;background:rgba(255,255,255,0.04);border-radius:10px;padding:4px;margin-bottom:22px;gap:4px}
.lp-auth-tab{padding:9px;text-align:center;font-size:13px;font-weight:700;border-radius:7px;cursor:pointer;transition:all .2s;color:var(--grey);border:none;background:transparent;font-family:inherit}
.lp-auth-tab.active{background:var(--navy-3);color:var(--white);box-shadow:0 2px 8px rgba(0,0,0,0.4)}
.lp-auth-form{display:flex;flex-direction:column;gap:13px}
.lp-form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.lp-field-group{display:flex;flex-direction:column;gap:6px}
.lp-field-label{font-size:10.5px;font-weight:600;color:rgba(255,255,255,0.45);letter-spacing:0.08em;text-transform:uppercase}
.lp-field-label .optional{color:var(--grey);font-weight:400;text-transform:none;letter-spacing:0;font-size:10px;margin-left:4px}
.lp-field-input{width:100%;padding:11px 13px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:9px;color:var(--white);font-family:inherit;font-size:13.5px;transition:all .2s;outline:none}
.lp-field-input::placeholder{color:rgba(255,255,255,0.18)}
.lp-field-input:focus{border-color:rgba(212,168,74,0.45);background:rgba(212,168,74,0.03);box-shadow:0 0 0 3px rgba(212,168,74,0.07)}
.lp-submit-btn{width:100%;padding:13px;background:var(--gold);color:var(--navy);border:none;border-radius:10px;font-family:inherit;font-size:14px;font-weight:800;cursor:pointer;transition:all .2s;margin-top:4px;box-shadow:0 6px 24px rgba(212,168,74,0.25)}
.lp-submit-btn:hover:not(:disabled){background:var(--gold-light);transform:translateY(-1px);box-shadow:0 10px 32px rgba(212,168,74,0.4)}
.lp-submit-btn:disabled{opacity:0.6;cursor:not-allowed}
.lp-auth-toggle{text-align:center;font-size:12.5px;color:var(--grey);margin-top:4px}
.lp-auth-toggle a{color:var(--gold-light);text-decoration:none;font-weight:600;cursor:pointer}
.lp-auth-toggle a:hover{text-decoration:underline}
.lp-auth-err{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:10px 13px;font-size:12.5px;color:#f87171;margin-bottom:4px}
.lp-security-row{display:flex;align-items:center;justify-content:center;gap:16px;margin-top:18px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.05)}
.lp-security-item{display:flex;align-items:center;gap:5px;font-size:10px;color:rgba(255,255,255,0.25);font-family:'JetBrains Mono',monospace}
/* DIVIDER */
.lp-divider{height:1px;background:linear-gradient(90deg,transparent,rgba(212,168,74,0.25),transparent)}
/* STATS */
.lp-stats{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.lp-stat-item{padding:44px 32px;background:var(--navy);text-align:center;border-right:1px solid var(--line);transition:background .3s}
.lp-stat-item:hover{background:var(--navy-3)}
.lp-stat-item:last-child{border-right:none}
.lp-stat-num{font-family:'Fraunces',serif;font-size:54px;font-weight:600;color:var(--gold);letter-spacing:-0.03em;line-height:1;margin-bottom:8px;text-shadow:0 0 40px rgba(212,168,74,0.45)}
.lp-stat-label{font-size:13px;color:var(--grey)}
/* HOW */
.lp-how{padding:110px 64px;max-width:1240px;margin:0 auto}
.lp-eyebrow{font-family:'JetBrains Mono',monospace;font-size:10.5px;font-weight:500;text-transform:uppercase;letter-spacing:0.2em;color:var(--gold);margin-bottom:18px}
.lp-section-title{font-family:'Fraunces',serif;font-size:54px;font-weight:600;letter-spacing:-0.022em;line-height:1.08;margin-bottom:16px}
.lp-section-title em{font-style:italic;color:var(--gold);text-shadow:0 0 50px rgba(212,168,74,0.5),0 0 100px rgba(212,168,74,0.2)}
.lp-section-sub{font-size:17px;color:var(--grey);max-width:480px;line-height:1.65;margin-bottom:64px}
.lp-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line)}
.lp-step{background:var(--navy);padding:52px 44px;position:relative;overflow:hidden;transition:background .25s}
.lp-step:hover{background:var(--navy-3)}
.lp-step::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--gold),transparent);transform:scaleX(0);transform-origin:left;transition:transform .4s ease}
.lp-step:hover::before{transform:scaleX(1)}
.lp-step-num{font-family:'Fraunces',serif;font-size:96px;font-weight:600;color:rgba(212,168,74,0.06);line-height:1;position:absolute;top:16px;right:28px;letter-spacing:-0.04em}
.lp-step-icon{width:54px;height:54px;background:rgba(212,168,74,0.08);border-radius:15px;display:flex;align-items:center;justify-content:center;margin-bottom:22px;font-size:24px}
.lp-step h3{font-family:'Fraunces',serif;font-size:23px;font-weight:600;margin-bottom:12px;letter-spacing:-0.01em}
.lp-step p{font-size:14px;color:var(--grey);line-height:1.7}
/* FEATURES */
.lp-features-sec{padding:110px 64px;background:var(--navy-2)}
.lp-features-inner{max-width:1240px;margin:0 auto}
.lp-features-list{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);margin-top:64px}
.lp-feature-card{background:var(--navy-2);padding:44px 40px;transition:background .25s}
.lp-feature-card:hover{background:var(--navy-3)}
.lp-feature-icon{width:50px;height:50px;background:rgba(212,168,74,0.07);border-radius:13px;display:flex;align-items:center;justify-content:center;font-size:22px;margin-bottom:20px}
.lp-feature-card h4{font-family:'Fraunces',serif;font-size:20px;font-weight:600;margin-bottom:10px;letter-spacing:-0.01em}
.lp-feature-card p{font-size:13.5px;color:var(--grey);line-height:1.65}
.lp-feature-tag{display:inline-block;margin-top:14px;font-size:10px;font-weight:700;color:var(--gold);background:rgba(212,168,74,0.07);padding:3px 10px;border-radius:999px;font-family:'JetBrains Mono',monospace;letter-spacing:0.1em;text-transform:uppercase}
/* INTL */
.lp-intl{padding:110px 64px;max-width:1240px;margin:0 auto}
.lp-intl-inner{display:grid;grid-template-columns:1fr 1fr;gap:80px;align-items:center}
.lp-countries-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.lp-country-card{background:var(--navy-3);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:flex;align-items:center;gap:12px;transition:all .2s}
.lp-country-card:hover{border-color:rgba(212,168,74,0.25);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.3)}
.lp-country-flag{font-size:26px}
.lp-country-info .name{font-size:13px;font-weight:600;margin-bottom:2px}
.lp-country-info .currency{font-size:11px;color:var(--grey);font-family:'JetBrains Mono',monospace}
/* CTA SECTION */
.lp-cta-section{padding:130px 64px;text-align:center;position:relative;overflow:hidden;background:var(--navy-2)}
.lp-cta-section::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 65% 85% at 50% 50%, rgba(212,168,74,0.07) 0%, transparent 70%)}
.lp-cta-group{display:flex;align-items:center;justify-content:center;gap:16px;flex-wrap:wrap}
/* FOOTER */
.lp-footer{padding:44px 64px;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.lp-footer-copy{font-size:12.5px;color:var(--grey)}
.lp-footer-links{display:flex;gap:20px;align-items:center}
.lp-footer-link{font-size:12.5px;color:var(--grey);text-decoration:none;background:none;border:none;cursor:pointer;font-family:inherit;transition:color .2s}
.lp-footer-link:hover{color:var(--white)}
/* PWA badge */
.lp-pwa-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(212,168,74,0.07);border:1px solid rgba(212,168,74,0.18);border-radius:10px;padding:10px 16px;font-size:13px;color:rgba(255,255,255,0.65);cursor:pointer;transition:all .2s;margin-top:16px}
.lp-pwa-badge:hover{background:rgba(212,168,74,0.12);border-color:rgba(212,168,74,0.35);color:var(--white)}
/* PWA INSTALL SECTION */
.lp-install-sec{padding:80px 64px;background:var(--navy-3);border-top:1px solid var(--line);border-bottom:1px solid var(--line);text-align:center}
.lp-install-inner{max-width:560px;margin:0 auto}
.lp-install-headline{font-family:'Fraunces',serif;font-size:38px;font-weight:600;letter-spacing:-0.02em;margin-bottom:12px}
.lp-install-headline em{font-style:italic;color:var(--gold);text-shadow:0 0 40px rgba(212,168,74,0.5)}
.lp-install-sub{font-size:15px;color:var(--grey);line-height:1.65;margin-bottom:32px}
.lp-install-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:18px}
.lp-install-btn{padding:13px 26px;border-radius:10px;font-family:inherit;font-size:14px;font-weight:700;cursor:pointer;transition:all .25s;display:inline-flex;align-items:center;gap:8px}
.lp-install-btn.android{background:var(--gold);color:var(--navy);border:none;box-shadow:0 6px 24px rgba(212,168,74,0.3)}
.lp-install-btn.android:hover{background:var(--gold-light);transform:translateY(-2px);box-shadow:0 12px 32px rgba(212,168,74,0.45)}
.lp-install-btn.iphone{background:transparent;color:var(--white);border:1px solid rgba(255,255,255,0.18)}
.lp-install-btn.iphone:hover{border-color:rgba(255,255,255,0.4);transform:translateY(-1px)}
.lp-install-note{font-size:11.5px;color:rgba(255,255,255,0.3);line-height:1.6;font-family:'JetBrains Mono',monospace}
.lp-install-done{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);border-radius:10px;color:rgba(34,197,94,0.9);font-size:14px;font-weight:600}
@media(max-width:960px){.lp-install-sec{padding:60px 24px}.lp-install-headline{font-size:30px}}
@media(max-width:480px){.lp-install-sec{padding:48px 20px}.lp-install-headline{font-size:26px}.lp-install-btns{flex-direction:column;align-items:stretch}.lp-install-btn{justify-content:center}}
/* REVEAL */
.lp-reveal{opacity:0;transform:translateY(32px);transition:opacity .75s ease,transform .75s ease}
.lp-reveal.visible{opacity:1;transform:translateY(0)}
@keyframes lp-fadeUp{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:translateY(0)}}
/* TABLET */
@media(max-width:960px){
  .lp-nav{padding:14px 20px}
  .lp-nav-link{display:none}
  .lp-hero{grid-template-columns:1fr;min-height:auto}
  .lp-hero-left{padding:100px 24px 40px}
  .lp-headline{font-size:52px}
  .lp-hero-right{padding:20px 24px 60px}
  .lp-stats{grid-template-columns:1fr 1fr}
  .lp-stat-item{padding:28px 20px}
  .lp-stat-num{font-size:40px}
  .lp-how,.lp-features-sec,.lp-intl,.lp-cta-section{padding:70px 24px}
  .lp-section-title{font-size:40px}
  .lp-steps,.lp-features-list{grid-template-columns:1fr}
  .lp-intl-inner{grid-template-columns:1fr;gap:40px}
  .lp-footer{flex-direction:column;gap:16px;padding:28px 24px;text-align:center}
  .lp-features-grid{grid-template-columns:1fr}
  .lp-auth-trigger-headline{font-size:28px}
  .lp-form-row{grid-template-columns:1fr}
}
/* PHONE */
@media(max-width:480px){
  /* Nav — logo + one CTA only */
  .lp-nav{padding:12px 16px}
  .lp-nav-btn.ghost{display:none}
  .lp-nav-btn.gold{padding:8px 14px;font-size:12px}
  /* Hero — single column, full width, no right panel */
  .lp-hero{grid-template-columns:1fr;min-height:100svh}
  .lp-hero-bg{background:radial-gradient(ellipse 90% 60% at 50% 30%, rgba(212,168,74,0.1) 0%, transparent 65%),var(--navy)}
  .lp-hero-left{padding:88px 20px 36px;text-align:center;align-items:center}
  .lp-badge{margin-bottom:24px;font-size:10px}
  .lp-headline{font-size:42px;letter-spacing:-0.02em;margin-bottom:18px;text-align:center}
  .lp-sub{font-size:15px;margin-bottom:28px;text-align:center;max-width:100%}
  /* Bullet grid — 1 column, left-aligned */
  .lp-features-grid{grid-template-columns:1fr;gap:8px;margin-bottom:32px;width:100%;text-align:left}
  .lp-feature-item{font-size:13px}
  /* CTA buttons — stacked, full width */
  .lp-hero-cta{flex-direction:column;align-items:stretch;gap:10px;width:100%}
  .lp-cta-btn{width:100%;justify-content:center;padding:14px 20px;font-size:15px}
  .lp-beta-note{justify-content:center;font-size:11px}
  /* Hide the right panel (auth trigger/card) on phone — auth is in-page via CTA */
  .lp-hero-right{display:none}
  /* Stats — 2×2 grid */
  .lp-stats{grid-template-columns:1fr 1fr}
  .lp-stat-item{padding:24px 12px;border-right:1px solid var(--line)}
  .lp-stat-item:nth-child(2n){border-right:none}
  .lp-stat-item:nth-child(n+3){border-top:1px solid var(--line)}
  .lp-stat-item:nth-child(5){border-right:1px solid var(--line)}
  .lp-stat-num{font-size:36px}
  .lp-stat-label{font-size:11px}
  /* Sections */
  .lp-how,.lp-features-sec,.lp-intl,.lp-cta-section{padding:56px 20px}
  .lp-section-title{font-size:34px;line-height:1.1}
  .lp-section-sub{font-size:15px;margin-bottom:40px}
  .lp-eyebrow{font-size:9.5px;margin-bottom:12px}
  /* Steps */
  .lp-steps{grid-template-columns:1fr;gap:1px}
  .lp-step{padding:36px 24px}
  .lp-step-num{font-size:72px;top:10px;right:16px}
  .lp-step h3{font-size:20px}
  /* Feature cards */
  .lp-features-list{grid-template-columns:1fr}
  .lp-feature-card{padding:28px 24px}
  .lp-feature-card h4{font-size:18px}
  /* International */
  .lp-intl-inner{grid-template-columns:1fr;gap:32px}
  .lp-countries-grid{grid-template-columns:1fr 1fr;gap:8px}
  .lp-country-card{padding:12px 14px;gap:10px}
  .lp-country-flag{font-size:22px}
  .lp-country-info .name{font-size:12px}
  .lp-country-info .currency{font-size:10px}
  /* CTA section */
  .lp-cta-section .lp-section-sub{font-size:14px;margin-bottom:32px}
  .lp-cta-group{flex-direction:column;align-items:stretch;gap:10px;width:100%;max-width:320px;margin:0 auto}
  .lp-cta-group .lp-cta-btn{width:100%;justify-content:center}
  /* Footer */
  .lp-footer{flex-direction:column;gap:12px;padding:24px 20px;text-align:center}
  /* Auth card — full screen overlay on mobile */
  .lp-mobile-auth-overlay{display:flex!important;position:fixed;inset:0;z-index:300;background:rgba(5,14,30,0.97);padding:20px;align-items:center;justify-content:center;overflow-y:auto}
  .lp-auth-card-wrap{max-width:100%;width:100%}
  .lp-auth-card{padding:28px 22px}
  .lp-form-row{grid-template-columns:1fr}
  .lp-field-input{font-size:16px}
}
`;

const FEATURES = [
  ["Auto-matches by ", "area, type & budget"],
  ["Primary Sales, Resales", " and Commercial categories"],
  ["Sales & Rentals", " in separate divisions"],
  ["Stretch matches up to ", "25% above budget"],
  ["Lead labels — ", "Hot, Active, Warm, Cold"],
  ["One-tap ", "WhatsApp & call", " any client"],
  ["Export matches as ", "branded PDFs"],
  ["Install as app — ", "works offline"],
];

const STEPS = [
  { icon: "🤝", num: "01", title: "Log a buyer brief", body: "Capture what they're looking for — area, property type, budget range. Takes under 30 seconds from any device." },
  { icon: "🏠", num: "02", title: "Add a seller listing", body: "Log the property details — location, type, asking price. DealKnot instantly scans for matching buyers." },
  { icon: "🤜", num: "03", title: "Connect & close", body: "See your match score, tap WhatsApp or call directly, share a branded PDF report. Deal tied." },
];

const FEATURE_CARDS = [
  { icon: "⚡", title: "Smart Auto-Matching", body: "The moment you add a buyer or seller, DealKnot scans your entire book and surfaces matches ranked by fit percentage.", tag: "Core" },
  { icon: "📁", title: "Sales & Rentals Split", body: "Two completely separate divisions. Sales buyers never mix with rental tenants. Each has its own listings and matches.", tag: "Organised" },
  { icon: "🎯", title: "Stretch Matches", body: "Goes up to 25% above a buyer's max budget to surface near-matches. Marked 'Stretch' so you know when to negotiate.", tag: "Smart" },
  { icon: "🏷️", title: "Lead Labels", body: "Tag every contact as Hot, Active, Warm, Cold or Closed. Filter your book. Hot leads always float to the top.", tag: "CRM" },
  { icon: "📄", title: "Branded PDF Reports", body: "Export any match as a professional DealKnot-branded PDF to share with clients. Navy & gold, your name on it.", tag: "Professional" },
  { icon: "💬", title: "One-tap WhatsApp", body: "Every match card has a WhatsApp button with a pre-written message. Call or message any client in one tap.", tag: "Fast" },
  { icon: "🌙", title: "Dark Mode", body: "Full dark mode for late night work. Toggle between light and dark. Your preference saved automatically.", tag: "Comfort" },
  { icon: "📱", title: "Install as App", body: "Add DealKnot to your phone home screen. Auto-detects mobile vs desktop. Works offline too.", tag: "PWA" },
  { icon: "💰", title: "Commission Tracker", body: "Log expected and received commission per deal. Track your total pipeline, received earnings, and pending amounts in one place.", tag: "Finance" },
  { icon: "📊", title: "Analytics Dashboard", body: "Charts showing deals closed over time, top areas, match conversion rate, property type breakdown, and international vs local split.", tag: "Insights" },
  { icon: "📥", title: "Excel Import", body: "Upload your existing Excel spreadsheet and DealKnot automatically imports all contacts. Supports up to 10,000 contacts with duplicate detection.", tag: "Import" },
  { icon: "📤", title: "Excel Export", body: "Download your entire book as a formatted Excel file. One click to export all buyers, sellers, and their details.", tag: "Export" },
  { icon: "📝", title: "Client Notes", body: "Add notes and an activity log to every buyer and seller. Keep track of conversations, viewings, and next steps.", tag: "CRM" },
  { icon: "🔍", title: "Full-Text Search", body: "Search across all buyers, sellers, areas, and phone numbers instantly. Find any contact in your book in seconds.", tag: "Search" },
];

const COUNTRIES = [
  { flag: "🇦🇪", name: "UAE", currency: "AED · Dubai, Abu Dhabi" },
  { flag: "🇮🇳", name: "India", currency: "INR · Chennai, Mumbai, Delhi" },
  { flag: "🇬🇧", name: "United Kingdom", currency: "GBP · London, Manchester" },
  { flag: "🇸🇬", name: "Singapore", currency: "SGD · Orchard, Marina Bay" },
  { flag: "🇺🇸", name: "United States", currency: "USD · New York, Miami" },
  { flag: "🇦🇺", name: "Australia", currency: "AUD · Sydney, Melbourne" },
  { flag: "🇭🇰", name: "Hong Kong", currency: "HKD · Central, The Peak" },
  { flag: "🇨🇦", name: "Canada", currency: "CAD · Toronto, Vancouver" },
];

function AuthCard({ initialTab, onClose }) {
  const { login, register } = useAuth();
  const [tab, setTab] = useState(initialTab || "signup");
  const [form, setForm] = useState({ email: "", name: "", nickname: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const up = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      if (tab === "login") {
        await login(form.email, form.password);
      } else {
        if (!form.name.trim()) { setErr("Please enter your name."); setBusy(false); return; }
        await register(form.email, form.name, form.password, form.nickname);
      }
    } catch (ex) {
      setErr(ex.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lp-auth-card-wrap">
      <div className="lp-auth-card">
        <button className="lp-auth-close" onClick={onClose}>✕</button>
        <div className="lp-auth-eyebrow">// Broker Access</div>
        <h2 className="lp-auth-headline">Tie your <em>first deal.</em></h2>
        <p className="lp-auth-sub">Set up your broker workspace in under a minute.</p>
        <div className="lp-auth-tabs">
          <button className={`lp-auth-tab${tab === "signup" ? " active" : ""}`} onClick={() => { setTab("signup"); setErr(""); }}>Sign Up</button>
          <button className={`lp-auth-tab${tab === "login" ? " active" : ""}`} onClick={() => { setTab("login"); setErr(""); }}>Log In</button>
        </div>
        {err && <div className="lp-auth-err">{err}</div>}
        <form onSubmit={submit} autoComplete="on">
          <div className="lp-auth-form">
            {tab === "signup" && (
              <div className="lp-form-row">
                <div className="lp-field-group">
                  <label className="lp-field-label">Full name</label>
                  <input type="text" className="lp-field-input" placeholder="Your name" autoComplete="name"
                    value={form.name} onChange={(e) => up("name", e.target.value)} required />
                </div>
                <div className="lp-field-group">
                  <label className="lp-field-label">Nickname <span className="optional">optional</span></label>
                  <input type="text" className="lp-field-input" placeholder="What to call you" autoComplete="off"
                    value={form.nickname} onChange={(e) => up("nickname", e.target.value)} />
                </div>
              </div>
            )}
            <div className="lp-field-group">
              <label className="lp-field-label">Work email</label>
              <input type="email" className="lp-field-input" placeholder="you@brokerage.com" autoComplete="email"
                value={form.email} onChange={(e) => up("email", e.target.value)} required />
            </div>
            <div className="lp-field-group">
              <label className="lp-field-label">Password</label>
              <input type="password" className="lp-field-input"
                placeholder={tab === "signup" ? "Min. 8 characters" : "Your password"}
                autoComplete={tab === "login" ? "current-password" : "new-password"}
                value={form.password} onChange={(e) => up("password", e.target.value)} required />
            </div>
            <button className="lp-submit-btn" type="submit" disabled={busy}>
              {busy ? "Please wait…" : tab === "signup" ? "Create account →" : "Sign in →"}
            </button>
            <p className="lp-auth-toggle">
              {tab === "signup"
                ? <><span>Already have an account? </span><a onClick={() => { setTab("login"); setErr(""); }}>Log in</a></>
                : <><span>No account? </span><a onClick={() => { setTab("signup"); setErr(""); }}>Sign up free</a></>
              }
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}

function useIsMobilePhone() {
  const [phone, setPhone] = useState(() => typeof window !== "undefined" && window.innerWidth <= 480);
  useEffect(() => {
    const fn = () => setPhone(window.innerWidth <= 480);
    window.addEventListener("resize", fn);
    return () => window.removeEventListener("resize", fn);
  }, []);
  return phone;
}

export default function LandingPage() {
  const [authState, setAuthState] = useState(null); // null | "signup" | "login"
  const [showInstallGuide, setShowInstallGuide] = useState(false);
  const isPhone = useIsMobilePhone();
  const pwa = usePWAInstall();

  const openAuth = (tab) => setAuthState(tab);
  const closeAuth = () => setAuthState(null);

  const scrollToHow = (e) => {
    e.preventDefault();
    document.getElementById("lp-how")?.scrollIntoView({ behavior: "smooth" });
  };

  const scrollToAuthAndOpen = () => {
    if (isPhone) { openAuth("signup"); return; }
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => openAuth("signup"), 600);
  };

  useEffect(() => {
    const style = document.createElement("style");
    style.id = "lp-styles";
    style.textContent = CSS;
    document.head.appendChild(style);
    document.body.classList.add("lp-active");
    document.documentElement.classList.add("lp-active");
    return () => {
      document.getElementById("lp-styles")?.remove();
      document.body.classList.remove("lp-active");
      document.documentElement.classList.remove("lp-active");
    };
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, i) => {
          if (entry.isIntersecting) setTimeout(() => entry.target.classList.add("visible"), i * 80);
        });
      },
      { threshold: 0.1 }
    );
    document.querySelectorAll(".lp-reveal").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  if (showInstallGuide) {
    return <InstallGuide onClose={() => setShowInstallGuide(false)} />;
  }

  return (
    <div className="lp-root">
      {/* MOBILE AUTH OVERLAY */}
      {authState && isPhone && (
        <div className="lp-mobile-auth-overlay" style={{ display: "flex" }}>
          <AuthCard initialTab={authState} onClose={closeAuth} />
        </div>
      )}

      {/* NAV */}
      <nav className="lp-nav">
        <div className="lp-logo" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
          <div className="lp-logo-mark">D</div>
          <div className="lp-logo-text">Deal<span>Knot</span></div>
        </div>
        <div className="lp-nav-links">
          <button className="lp-nav-link" onClick={scrollToHow}>How it works</button>
          <button className="lp-nav-link" onClick={(e) => { e.preventDefault(); document.getElementById("lp-features")?.scrollIntoView({ behavior: "smooth" }); }}>Features</button>
          <button className="lp-nav-btn ghost" onClick={() => openAuth("login")}>Log in</button>
          <button className="lp-nav-btn gold" onClick={() => openAuth("signup")}>Get started free →</button>
        </div>
      </nav>

      {/* HERO */}
      <section className="lp-hero">
        <div className="lp-hero-bg" />
        <div className="lp-hero-left">
          <div className="lp-badge"><span className="lp-dot" />Broker Matching Platform</div>
          <h1 className="lp-headline">
            <span className="line1">Where Deals</span>
            <span className="line2">Get <em>Tied.</em></span>
          </h1>
          <p className="lp-sub">The smartest matching platform for real estate brokers. <strong>Log buyers and sellers</strong> — DealKnot finds the perfect match automatically.</p>
          <div className="lp-features-grid">
            {FEATURES.map((parts, i) => (
              <div className="lp-feature-item" key={i}>
                <div className="lp-check">✓</div>
                <span>
                  {parts.map((p, j) => j % 2 === 1 ? <strong key={j}>{p}</strong> : <span key={j}>{p}</span>)}
                </span>
              </div>
            ))}
          </div>
          <div className="lp-hero-cta">
            <button className="lp-cta-btn primary" onClick={() => openAuth("signup")}>Start for free →</button>
            <button className="lp-cta-btn secondary" onClick={scrollToHow}>See how it works</button>
            {pwa.isMobileDevice && !pwa.installed && (
              pwa.promptAvailable
                ? <button className="lp-cta-btn secondary" onClick={pwa.triggerInstall}>📲 Install App</button>
                : pwa.isIOS
                  ? <button className="lp-cta-btn secondary" onClick={() => setShowInstallGuide(true)}>📲 Install App</button>
                  : null
            )}
          </div>
        </div>

        <div className="lp-hero-right">
          {authState ? (
            <AuthCard initialTab={authState} onClose={closeAuth} />
          ) : (
            <div className="lp-auth-trigger">
              <p className="lp-auth-trigger-headline">Ready to tie your<br /><em>next deal?</em></p>
              <p className="lp-auth-trigger-sub">Set up your workspace in under a minute.</p>
              <div className="lp-auth-trigger-btns">
                <button className="lp-trigger-btn signup" onClick={() => openAuth("signup")}>Create free account →</button>
                <button className="lp-trigger-btn login" onClick={() => openAuth("login")}>Log in</button>
              </div>
            </div>
          )}
        </div>
      </section>

      <div className="lp-divider" />

      {/* STATS */}
      <div className="lp-stats">
        {[["10","Countries supported"],["9","Currencies"],["500+","Areas & neighbourhoods"],["25%","Stretch match range"],["10,000+","Contacts supported"]].map(([n,l]) => (
          <div className="lp-stat-item lp-reveal" key={l}>
            <div className="lp-stat-num">{n}</div>
            <div className="lp-stat-label">{l}</div>
          </div>
        ))}
      </div>

      {/* HOW IT WORKS */}
      <section className="lp-how" id="lp-how">
        <div className="lp-eyebrow">// How it works</div>
        <h2 className="lp-section-title lp-reveal">Three steps to your<br /><em>next closed deal.</em></h2>
        <p className="lp-section-sub lp-reveal">No complex setup. No training needed. Just log and match.</p>
        <div className="lp-steps">
          {STEPS.map((s) => (
            <div className="lp-step lp-reveal" key={s.num}>
              <div className="lp-step-num">{s.num}</div>
              <div className="lp-step-icon">{s.icon}</div>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section className="lp-features-sec" id="lp-features">
        <div className="lp-features-inner">
          <div className="lp-eyebrow">// Everything you need</div>
          <h2 className="lp-section-title lp-reveal">Built for brokers who<br /><em>move fast.</em></h2>
          <div className="lp-features-list">
            {FEATURE_CARDS.map((f) => (
              <div className="lp-feature-card lp-reveal" key={f.title}>
                <div className="lp-feature-icon">{f.icon}</div>
                <h4>{f.title}</h4>
                <p>{f.body}</p>
                <span className="lp-feature-tag">{f.tag}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* INTERNATIONAL */}
      <section className="lp-intl" id="lp-international">
        <div className="lp-intl-inner">
          <div>
            <div className="lp-eyebrow">// International</div>
            <h2 className="lp-section-title lp-reveal">Built for brokers<br />across <em>the world.</em></h2>
            <p className="lp-section-sub lp-reveal" style={{ marginBottom: 0 }}>Whether you're closing deals in Dubai, London, Chennai or Singapore — DealKnot speaks your currency and knows your areas.</p>
          </div>
          <div className="lp-countries-grid lp-reveal">
            {COUNTRIES.map((c) => (
              <div className="lp-country-card" key={c.name}>
                <span className="lp-country-flag">{c.flag}</span>
                <div className="lp-country-info">
                  <div className="name">{c.name}</div>
                  <div className="currency">{c.currency}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="lp-divider" />

      {/* BOTTOM CTA */}
      <section className="lp-cta-section">
        <div style={{ position: "relative", zIndex: 1 }}>
          <div className="lp-eyebrow">// Get started</div>
          <h2 className="lp-section-title lp-reveal">Ready to tie your<br /><em>next deal?</em></h2>
          <div className="lp-cta-group lp-reveal">
            <button className="lp-cta-btn primary" style={{ fontSize: 15, padding: "15px 36px" }} onClick={scrollToAuthAndOpen}>Get started →</button>
          </div>
          <div className="lp-reveal" style={{ marginTop: 24 }}>
            <button className="lp-pwa-badge" onClick={() => setShowInstallGuide(true)}>
              📲 Available as a mobile app — Install on Android &amp; iOS
            </button>
          </div>
        </div>
      </section>

      {/* PWA INSTALL SECTION — mobile only, hidden if already installed */}
      {pwa.isMobileDevice && !pwa.installed && (
        <section className="lp-install-sec lp-reveal">
          <div className="lp-install-inner">
            <div className="lp-eyebrow">// Mobile App</div>
            <h2 className="lp-install-headline">Take DealKnot <em>everywhere.</em></h2>
            <p className="lp-install-sub">Install on your phone in one tap. Works offline, feels like a native app.</p>
            <div className="lp-install-btns">
              {pwa.promptAvailable && (
                <button className="lp-install-btn android" onClick={pwa.triggerInstall}>
                  📲 Install on Android
                </button>
              )}
              {pwa.isIOS && (
                <button className="lp-install-btn iphone" onClick={() => setShowInstallGuide(true)}>
                  📲 Install on iPhone
                </button>
              )}
              {!pwa.promptAvailable && !pwa.isIOS && (
                <button className="lp-install-btn iphone" onClick={() => setShowInstallGuide(true)}>
                  📲 Install App
                </button>
              )}
            </div>
            <p className="lp-install-note">
              Android: Chrome auto-installs · iPhone: Use Safari → Share → Add to Home Screen
            </p>
          </div>
        </section>
      )}
      {pwa.isMobileDevice && pwa.installed && (
        <section className="lp-install-sec">
          <div className="lp-install-inner">
            <div className="lp-install-done">✅ Already installed</div>
          </div>
        </section>
      )}

      {/* FOOTER */}
      <footer className="lp-footer">
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div className="lp-logo" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            <div className="lp-logo-mark">D</div>
            <div className="lp-logo-text">Deal<span>Knot</span></div>
          </div>
          <span className="lp-footer-copy">© 2026 DealKnot. Where Deals Get Tied.</span>
        </div>
        <div className="lp-footer-links">
          <button className="lp-footer-link" onClick={() => setShowInstallGuide(true)}>📲 Install guide</button>
        </div>
      </footer>
    </div>
  );
}
