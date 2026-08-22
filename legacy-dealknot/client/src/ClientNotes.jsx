import { useState, useEffect, useCallback } from "react";
import { api } from "./api";
import { I } from "./icons";

function timeAgo(ts) {
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(ts).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export default function ClientNotes({ clientId, clientType }) {
  const [notes, setNotes] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getNotes(clientType, clientId);
      setNotes(data);
    } catch {}
  }, [clientId, clientType]);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const note = await api.addNote(clientType, clientId, text.trim());
      setNotes((prev) => [note, ...prev].slice(0, 10));
      setText("");
    } catch {}
    setBusy(false);
  };

  const remove = async (noteId) => {
    try {
      await api.deleteNote(noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch {}
  };

  return (
    <div className="client-notes">
      <div className="tl-head">// activity notes</div>
      <div className="notes-input-row">
        <input
          className="notes-input"
          placeholder="Add a note… e.g. Called today, very interested"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          maxLength={300}
        />
        <button className="notes-add-btn" onClick={submit} disabled={!text.trim() || busy}>
          <I.plus width="14" height="14" />
        </button>
      </div>
      {notes.length === 0 && (
        <div className="notes-empty">No notes yet. Log calls, visits, updates.</div>
      )}
      {notes.map((n) => (
        <div key={n.id} className="note-row">
          <div className="note-dot" />
          <div className="note-body">{n.body}</div>
          <div className="note-meta">{timeAgo(n.createdAt)}</div>
          <button className="note-del" onClick={() => remove(n.id)} title="Delete note">
            <I.x width="11" height="11" />
          </button>
        </div>
      ))}
    </div>
  );
}
