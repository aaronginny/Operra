const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth);

const VALID_LABELS = new Set(["hot", "active", "warm", "cold", "closed"]);
const VALID_DIVISIONS = new Set(["sales", "rentals"]);
const VALID_PERIODS = new Set(["monthly", "yearly"]);

function rowToBuyer(r) {
  return {
    id: r.id, name: r.name, phone: r.phone, dial: r.dial,
    country: r.country, area: r.area, type: r.type, cur: r.cur,
    min: r.min_price, max: r.max_price,
    intl: r.intl === 1 || r.intl === true,
    notes: r.notes,
    division: r.division || "sales",
    period: r.period || "monthly",
    label: r.label || "active",
    radiusKm: r.radius_km != null ? Number(r.radius_km) : 5,
    createdAt: Number(r.created_at) * 1000,
  };
}

router.get("/", async (req, res) => {
  const result = await client.execute({
    sql: "SELECT * FROM buyers WHERE broker_id = ? ORDER BY created_at DESC",
    args: [req.broker.id],
  });
  res.json(result.rows.map(rowToBuyer));
});

router.post("/", async (req, res) => {
  const { name, phone, dial, country, area, type, cur, min, max, intl, notes, division, period, label, radiusKm } = req.body || {};
  if (!name || !phone || !country || !area || !type || !cur || min == null || max == null)
    return res.status(400).json({ error: "Missing required fields" });
  if (Number(max) < Number(min))
    return res.status(400).json({ error: "max must be >= min" });

  const div = VALID_DIVISIONS.has(division) ? division : "sales";
  const per = VALID_PERIODS.has(period) ? period : "monthly";
  const lab = VALID_LABELS.has(label) ? label : "active";
  const rkm = Math.max(1, Math.min(50, Number(radiusKm) || 5));

  const id = `b${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  await client.execute({
    sql: `INSERT INTO buyers (id, broker_id, name, phone, dial, country, area, type, cur, min_price, max_price, intl, notes, division, period, label, radius_km)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [id, req.broker.id, name, phone, dial || "+1", country, area, type, cur,
           Number(min), Number(max), intl ? 1 : 0, notes || "", div, per, lab, rkm],
  });
  const row = (await client.execute({ sql: "SELECT * FROM buyers WHERE id = ?", args: [id] })).rows[0];
  res.status(201).json(rowToBuyer(row));
});

router.put("/:id", async (req, res) => {
  const { name, phone, dial, country, area, type, cur, min, max, intl, notes, division, period, label, radiusKm } = req.body || {};
  if (!name || !phone || !country || !area || !type || !cur || min == null || max == null)
    return res.status(400).json({ error: "Missing required fields" });
  if (Number(max) < Number(min))
    return res.status(400).json({ error: "max must be >= min" });

  const div = VALID_DIVISIONS.has(division) ? division : "sales";
  const per = VALID_PERIODS.has(period) ? period : "monthly";
  const lab = VALID_LABELS.has(label) ? label : "active";
  const rkm = Math.max(1, Math.min(50, Number(radiusKm) || 5));

  const result = await client.execute({
    sql: `UPDATE buyers SET name=?, phone=?, dial=?, country=?, area=?, type=?, cur=?,
          min_price=?, max_price=?, intl=?, notes=?, division=?, period=?, label=?, radius_km=?
          WHERE id=? AND broker_id=?`,
    args: [name, phone, dial || "+1", country, area, type, cur,
           Number(min), Number(max), intl ? 1 : 0, notes || "", div, per, lab, rkm,
           req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  const row = (await client.execute({ sql: "SELECT * FROM buyers WHERE id = ?", args: [req.params.id] })).rows[0];
  res.json(rowToBuyer(row));
});

router.patch("/:id/label", async (req, res) => {
  const { label } = req.body || {};
  if (!VALID_LABELS.has(label)) return res.status(400).json({ error: "Invalid label" });
  const result = await client.execute({
    sql: "UPDATE buyers SET label=? WHERE id=? AND broker_id=?",
    args: [label, req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  const row = (await client.execute({ sql: "SELECT * FROM buyers WHERE id = ?", args: [req.params.id] })).rows[0];
  res.json(rowToBuyer(row));
});

router.patch("/:id/budget-bump", async (req, res) => {
  const { delta } = req.body || {};
  const d = Number(delta);
  if (!Number.isFinite(d) || d === 0) return res.status(400).json({ error: "Invalid delta" });
  const existing = (await client.execute({
    sql: "SELECT * FROM buyers WHERE id=? AND broker_id=?",
    args: [req.params.id, req.broker.id],
  })).rows[0];
  if (!existing) return res.status(404).json({ error: "Not found" });
  const newMax = Number(existing.max_price) + d;
  const newMin = Math.min(Number(existing.min_price), newMax);
  await client.execute({
    sql: "UPDATE buyers SET min_price=?, max_price=? WHERE id=? AND broker_id=?",
    args: [newMin, newMax, req.params.id, req.broker.id],
  });
  const row = (await client.execute({ sql: "SELECT * FROM buyers WHERE id = ?", args: [req.params.id] })).rows[0];
  res.json(rowToBuyer(row));
});

router.delete("/:id", async (req, res) => {
  const result = await client.execute({
    sql: "DELETE FROM buyers WHERE id = ? AND broker_id = ?",
    args: [req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  res.json({ ok: true });
});

// Bulk insert — accepts array of buyer objects, deduplicates by phone
router.post("/bulk", async (req, res) => {
  const rows = req.body;
  if (!Array.isArray(rows) || rows.length === 0)
    return res.status(400).json({ error: "Expected non-empty array" });
  if (rows.length > 10000)
    return res.status(400).json({ error: "Max 10,000 rows per bulk import" });

  // Fetch existing phone numbers for this broker to detect duplicates
  const existingRes = await client.execute({
    sql: "SELECT phone, dial FROM buyers WHERE broker_id = ?",
    args: [req.broker.id],
  });
  const existingPhones = new Set(
    existingRes.rows.map((r) => `${r.dial || ""}${r.phone}`.replace(/\D/g, ""))
  );

  let inserted = 0, duplicates = 0, failed = 0;
  const errors = [];

  for (const rec of rows) {
    const { name, phone, dial, country, area, type, cur, min, max, intl, notes, division, period, label } = rec;
    if (!name || !phone || !country || !area || !type || !cur || min == null || max == null) {
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
    const id = `b${Date.now()}${Math.random().toString(36).slice(2, 6)}`;

    try {
      await client.execute({
        sql: `INSERT INTO buyers (id, broker_id, name, phone, dial, country, area, type, cur, min_price, max_price, intl, notes, division, period, label)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        args: [id, req.broker.id, name, phone, dial || "+1", country, area, type, cur,
               Number(min), Number(max), intl ? 1 : 0, notes || "", div, per, lab],
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
