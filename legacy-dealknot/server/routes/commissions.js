const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth);

const VALID_STATUSES = new Set(["Pending", "Partial", "Received"]);

function rowToCommission(r) {
  return {
    id: r.id,
    broker_id: r.broker_id,
    buyer_name: r.buyer_name,
    seller_name: r.seller_name,
    area: r.area,
    property_type: r.property_type,
    deal_value: r.deal_value,
    commission_percent: r.commission_percent,
    commission_amount: r.commission_amount,
    currency: r.currency,
    status: r.status,
    expected_date: r.expected_date,
    received_date: r.received_date,
    notes: r.notes,
    createdAt: Number(r.created_at) * 1000,
  };
}

router.get("/", async (req, res) => {
  const result = await client.execute({
    sql: "SELECT * FROM commissions WHERE broker_id = ? ORDER BY created_at DESC",
    args: [req.broker.id],
  });
  res.json(result.rows.map(rowToCommission));
});

router.post("/", async (req, res) => {
  const {
    buyer_name, seller_name, area, property_type,
    deal_value, commission_percent, commission_amount,
    currency, status, expected_date, received_date, notes,
  } = req.body || {};

  const stat = VALID_STATUSES.has(status) ? status : "Pending";
  const id = `c${Date.now()}${Math.random().toString(36).slice(2, 6)}`;

  await client.execute({
    sql: `INSERT INTO commissions
          (id, broker_id, buyer_name, seller_name, area, property_type,
           deal_value, commission_percent, commission_amount, currency,
           status, expected_date, received_date, notes)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      id, req.broker.id,
      buyer_name || "", seller_name || "", area || "", property_type || "",
      Number(deal_value) || 0, Number(commission_percent) || 0, Number(commission_amount) || 0,
      currency || "AED", stat,
      expected_date || "", received_date || "", notes || "",
    ],
  });
  const row = (await client.execute({ sql: "SELECT * FROM commissions WHERE id = ?", args: [id] })).rows[0];
  if (!row) return res.status(500).json({ error: "Failed to retrieve saved commission" });
  res.status(201).json(rowToCommission(row));
});

router.put("/:id", async (req, res) => {
  const {
    buyer_name, seller_name, area, property_type,
    deal_value, commission_percent, commission_amount,
    currency, status, expected_date, received_date, notes,
  } = req.body || {};

  const stat = VALID_STATUSES.has(status) ? status : "Pending";

  const result = await client.execute({
    sql: `UPDATE commissions SET
          buyer_name=?, seller_name=?, area=?, property_type=?,
          deal_value=?, commission_percent=?, commission_amount=?,
          currency=?, status=?, expected_date=?, received_date=?, notes=?
          WHERE id=? AND broker_id=?`,
    args: [
      buyer_name || "", seller_name || "", area || "", property_type || "",
      Number(deal_value) || 0, Number(commission_percent) || 0, Number(commission_amount) || 0,
      currency || "AED", stat,
      expected_date || "", received_date || "", notes || "",
      req.params.id, req.broker.id,
    ],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  const row = (await client.execute({ sql: "SELECT * FROM commissions WHERE id = ?", args: [req.params.id] })).rows[0];
  if (!row) return res.status(500).json({ error: "Failed to retrieve updated commission" });
  res.json(rowToCommission(row));
});

router.delete("/:id", async (req, res) => {
  const result = await client.execute({
    sql: "DELETE FROM commissions WHERE id = ? AND broker_id = ?",
    args: [req.params.id, req.broker.id],
  });
  if (result.rowsAffected === 0) return res.status(404).json({ error: "Not found" });
  res.json({ ok: true });
});

module.exports = router;
