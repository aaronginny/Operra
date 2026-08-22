import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "./api";

export default function NameAutocomplete({ value, onChange, onSelect, placeholder, className }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const timerRef = useRef(null);
  const containerRef = useRef(null);

  const search = useCallback(async (q) => {
    if (!q || q.length < 1) { setResults([]); setOpen(false); return; }
    try {
      const data = await api.searchContacts(q);
      setResults(data);
      setOpen(true);
      setActiveIdx(-1);
    } catch {
      setResults([]); setOpen(true);
    }
  }, []);

  const handleChange = (e) => {
    const v = e.target.value;
    onChange(v);
    clearTimeout(timerRef.current);
    if (!v) { setOpen(false); setResults([]); return; }
    timerRef.current = setTimeout(() => search(v), 150);
  };

  const handleSelect = (contact) => {
    onChange(contact.name);
    onSelect?.(contact);
    setOpen(false);
    setResults([]);
  };

  const handleKeyDown = (e) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault();
      handleSelect(results[activeIdx]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  useEffect(() => {
    const onClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const initials = (name) =>
    name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div ref={containerRef} className="name-ac-wrap">
      <input
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => { if (results.length > 0) setOpen(true); }}
        placeholder={placeholder}
        className={className}
        autoComplete="off"
      />
      {open && (
        <ul className="name-ac-dropdown">
          {results.length === 0
            ? <li className="name-ac-empty">No contacts found</li>
            : results.map((c, i) => (
              <li key={c.id}
                className={i === activeIdx ? "active" : ""}
                onMouseDown={(e) => { e.preventDefault(); handleSelect(c); }}>
                <div className={`name-ac-av ${c.type === "buyer" ? "b" : "s"}`}>
                  {initials(c.name)}
                </div>
                <div className="name-ac-info">
                  <div className="name-ac-name">{c.name}</div>
                  <div className="name-ac-phone">{c.dial} {c.phone}</div>
                </div>
              </li>
            ))
          }
        </ul>
      )}
    </div>
  );
}
