import { useState } from "react";
import { useAuth } from "./AuthContext";

export default function AuthPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", name: "", nickname: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const up = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      if (mode === "login") {
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
    <div className="auth-root">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-brand mk">D</div>
          <div>
            <div className="nm">{"Deal"}<em>{"Knot"}</em></div>
            <div style={{ fontSize: 11, color: "var(--ink-400)", fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.12em" }}>Where deals get tied</div>
          </div>
        </div>

        <div className="auth-title">
          {mode === "login" ? "Welcome back." : "Create your account."}
        </div>
        <div className="auth-sub">
          {mode === "login"
            ? "Sign in to your broker workspace."
            : "Set up your personal broker workspace."}
        </div>

        {err && <div className="auth-err">{err}</div>}

        <form onSubmit={submit} autoComplete="on">
          {mode === "register" && (
            <div className="auth-field">
              <label>Full name</label>
              <input type="text" autoComplete="name" placeholder="Surya Narayanan"
                value={form.name} onChange={(e) => up("name", e.target.value)} required/>
            </div>
          )}
          {mode === "register" && (
            <div className="auth-field">
              <label>Nickname <span style={{ color: "var(--ink-400)", fontWeight: 400 }}>(optional)</span></label>
              <input type="text" autoComplete="off" placeholder="How should we greet you?"
                value={form.nickname} onChange={(e) => up("nickname", e.target.value)} />
            </div>
          )}
          <div className="auth-field">
            <label>Email</label>
            <input type="email" autoComplete="email" placeholder="broker@dealknot.com"
              value={form.email} onChange={(e) => up("email", e.target.value)} required/>
          </div>
          <div className="auth-field">
            <label>Password</label>
            <input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "register" ? "Min 6 characters" : "••••••••"}
              value={form.password} onChange={(e) => up("password", e.target.value)} required/>
          </div>
          <button className="auth-btn" type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in →" : "Create account →"}
          </button>
        </form>

        <div className="auth-switch">
          {mode === "login" ? (
            <>No account? <a onClick={() => { setMode("register"); setErr(""); }}>Create one</a></>
          ) : (
            <>Already have an account? <a onClick={() => { setMode("login"); setErr(""); }}>Sign in</a></>
          )}
        </div>
      </div>
    </div>
  );
}
