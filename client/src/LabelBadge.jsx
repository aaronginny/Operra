import { useState, useRef, useEffect } from "react";
import { LABELS, labelMeta } from "./constants";

// Tap-to-cycle / dropdown label badge. Used on every buyer / seller / tenant / landlord card.
export default function LabelBadge({ label, kind, id, onChange, size = "md" }) {
  const meta = labelMeta(label);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("touchstart", onClick);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("touchstart", onClick);
    };
  }, []);

  const pick = (e, id2) => {
    e.preventDefault();
    e.stopPropagation();
    setOpen(false);
    if (id2 !== label) onChange?.(kind, id, id2);
  };

  return (
    <div className={`label-wrap ${size}`} ref={ref} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`label-badge label-${meta.id} ${size}`}
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        title={meta.desc}
      >
        <span className="lico" aria-hidden>{meta.icon}</span>
        <span className="ltxt">{meta.short}</span>
      </button>
      {open && (
        <ul className="label-menu">
          {LABELS.map((l) => (
            <li key={l.id} className={`label-${l.id} ${l.id === meta.id ? "on" : ""}`}
              onMouseDown={(e) => pick(e, l.id)} onTouchEnd={(e) => pick(e, l.id)}>
              <span className="lico" aria-hidden>{l.icon}</span>
              <span className="lname">{l.name}</span>
              <span className="ldesc">{l.desc}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
