const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth);

const VALID_TYPES = new Set(["buyer", "seller"]);

function rowToNote(r) {
  return {
    id: r.id,
    clientId: r.client_id,
    clientType: r.client_type,
    body: r.body,
    createdAt: Number(r.created_at) * 1000,
  };
}

router.get("/:clientType/:clientId", async (req, res) => {
  const { clientType, clientId } = req.params;
  if (!VALID_TYPES.has(clientType)) return res.status(400).json({ error: "Invalid type" });
  const result = await client.execute({
    sql: "SELECT * FROM client_notes WHERE broker_id=? AND client_id=? AND client_type=? ORDER BY created_at DESC LIMIT 10",
    args: [req.broker.id, clientId, clientType],
  });
  res.json(result.rows.map(rowToNote));
});

router.post("/:clientType/:clientId", async (req, res) => {
  const { clientType, clientId } = req.params;
  if (!VALID_TYPES.has(clientType)) return res.status(400).json({ error: "Invalid type" });
  const { body } = req.body || {};
  if (!body?.trim()) return res.status(400).json({ error: "Note body required" });

  // Enforce max 10 notes per client — delete oldest if over limit
  const existing = await client.execute({
    sql: "SELECT id FROM client_notes WHERE broker_id=? AND client_id=? AND client_type=? ORDER BY created_at DESC",
    args: [req.broker.id, clientId, clientType],
  });
  if (existing.rows.length >= 10) {
    const oldest = existing.rows[existing.rows.length - 1];
    await client.execute({ sql: "DELETE FROM client_notes WHERE id=?", args: [oldest.id] });
  }

  const id = `n${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  await client.execute({
    sql: "INSERT INTO client_notes (id, broker_id, client_id, client_type, body) VALUES (?,?,?,?,?)",
    args: [id, req.broker.id, clientId, clientType, body.trim()],
  });
  const row = (await client.execute({ sql: "SELECT * FROM client_notes WHERE id=?", args: [id] })).rows[0];
  if (!row) return res.status(500).json({ error: "Failed to retrieve saved note" });
  res.status(201).json(rowToNote(row));
});

router.delete("/:noteId", async (req, res) => {
  const result = await client.execute({
    sql: "DELETE FROM client_notes WHERE id=? AND broker_id=?",
    args: [req.params.noteId, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  res.json({ ok: true });
});

module.exports = router;
