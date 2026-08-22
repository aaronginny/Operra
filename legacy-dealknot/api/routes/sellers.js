const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth);

const VALID_LABELS = new Set(["hot", "active", "warm", "cold", "closed"]);
const VALID_DIVISIONS = new Set(["sales", "rentals"]);
const VALID_PERIODS = new Set(["monthly", "yearly"]);

function rowToSeller(r) {
  return {
    id: r.id, name: r.name, phone: r.phone, dial: r.dial,
    country: r.country, area: r.area, type: r.type, cur: r.cur,
    price: r.price,
    intl: r.intl === 1 || r.intl === true,
    notes: r.notes,
    division: r.division || "sales",
    period: r.period || "monthly",
    label: r.label || "active",
    referredBy: r.referred_by || "",
    createdAt: Number(r.created_at) * 1000,
  };
}

router.get("/", async (req, res) => {
  const result = await client.execute({
    sql: "SELECT * FROM sellers WHERE broker_id = ? ORDER BY created_at DESC",
    args: [req.broker.id],
  });
  res.json(result.rows.map(rowToSeller));
});

router.post("/", async (req, res) => {
  const { name, phone, dial, country, area, type, cur, price, intl, notes, division, period, label, referredBy } = req.body || {};
  if (!name || !phone || !country || !area || !type || !cur || price == null)
    return res.status(400).json({ error: "Missing required fields" });

  const div = VALID_DIVISIONS.has(division) ? division : "sales";
  const per = VALID_PERIODS.has(period) ? period : "monthly";
  const lab = VALID_LABELS.has(label) ? label : "active";

  const id = `s${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  await client.execute({
    sql: `INSERT INTO sellers (id, broker_id, name, phone, dial, country, area, type, cur, price, intl, notes, division, period, label, referred_by)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [id, req.broker.id, name, phone, dial || "+1", country, area, type, cur,
           Number(price), intl ? 1 : 0, notes || "", div, per, lab, referredBy || ""],
  });
  const row = (await client.execute({ sql: "SELECT * FROM sellers WHERE id = ?", args: [id] })).rows[0];
  res.status(201).json(rowToSeller(row));
});

router.put("/:id", async (req, res) => {
  const { name, phone, dial, country, area, type, cur, price, intl, notes, division, period, label, referredBy } = req.body || {};
  if (!name || !phone || !country || !area || !type || !cur || price == null)
    return res.status(400).json({ error: "Missing required fields" });

  const div = VALID_DIVISIONS.has(division) ? division : "sales";
  const per = VALID_PERIODS.has(period) ? period : "monthly";
  const lab = VALID_LABELS.has(label) ? label : "active";

  const result = await client.execute({
    sql: `UPDATE sellers SET name=?, phone=?, dial=?, country=?, area=?, type=?, cur=?,
          price=?, intl=?, notes=?, division=?, period=?, label=?, referred_by=?
          WHERE id=? AND broker_id=?`,
    args: [name, phone, dial || "+1", country, area, type, cur,
           Number(price), intl ? 1 : 0, notes || "", div, per, lab, referredBy || "",
           req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  const row = (await client.execute({ sql: "SELECT * FROM sellers WHERE id = ?", args: [req.params.id] })).rows[0];
  res.json(rowToSeller(row));
});

router.patch("/:id/label", async (req, res) => {
  const { label } = req.body || {};
  if (!VALID_LABELS.has(label)) return res.status(400).json({ error: "Invalid label" });
  const result = await client.execute({
    sql: "UPDATE sellers SET label=? WHERE id=? AND broker_id=?",
    args: [label, req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  const row = (await client.execute({ sql: "SELECT * FROM sellers WHERE id = ?", args: [req.params.id] })).rows[0];
  res.json(rowToSeller(row));
});

router.delete("/:id", async (req, res) => {
  const result = await client.execute({
    sql: "DELETE FROM sellers WHERE id = ? AND broker_id = ?",
    args: [req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  res.json({ ok: true });
});

// Bulk insert — accepts array of seller objects, deduplicates by phone
router.post("/bulk", async (req, res) => {
  const rows = req.body;
  if (!Array.isArray(rows) || rows.length === 0)
    return res.status(400).json({ error: "Expected non-empty array" });
  if (rows.length > 10000)
    return res.status(400).json({ error: "Max 10,000 rows per bulk import" });

  const existingRes = await client.execute({
    sql: "SELECT phone, dial FROM sellers WHERE broker_id = ?",
    args: [req.broker.id],
  });
  const existingPhones = new Set(
    existingRes.rows.map((r) => `${r.dial || ""}${r.phone}`.replace(/\D/g, ""))
  );

  let inserted = 0, duplicates = 0, failed = 0;
  const errors = [];

  for (const rec of rows) {
    const { name, phone, dial, country, area, type, cur, price, intl, notes, division, period, label, referredBy } = rec;
    if (!name || !phone || !country || !area || !type || !cur || price == null) {
      failed++;
      errors.push(`Skipped "${name || "?"}" — missing required fields`);
      continue;
    }

    const normalised = `${dial || ""}${phone}`.replace(/\D/g, "");
    if (existingPhones.has(normalised)) {
      duplicates++;
      continue;
    }

    const div = VALID_DIVISIONS.has(division) ? division : "sales";
    const per = VALID_PERIODS.has(period) ? period : "monthly";
    const lab = VALID_LABELS.has(label) ? label : "active";
    const id = `s${Date.now()}${Math.random().toString(36).slice(2, 6)}`;

    try {
      await client.execute({
        sql: `INSERT INTO sellers (id, broker_id, name, phone, dial, country, area, type, cur, price, intl, notes, division, period, label, referred_by)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        args: [id, req.broker.id, name, phone, dial || "+1", country, area, type, cur,
               Number(price), intl ? 1 : 0, notes || "", div, per, lab, referredBy || ""],
      });
      existingPhones.add(normalised);
      inserted++;
    } catch (e) {
      failed++;
      errors.push(`Failed "${name}": ${e.message}`);
    }
  }

  res.json({ inserted, duplicates, failed, errors });
});

module.exports = router;
