const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");

const router = express.Router();
router.use(requireAuth);

router.get("/search", async (req, res) => {
  const brokerId = req.broker.id;
  const q = (req.query.q || "").trim();
  if (!q || q.length < 1) return res.json([]);

  const pattern = `%${q}%`;
  const [bRes, sRes] = await Promise.all([
    client.execute({
      sql: "SELECT id, name, phone, dial FROM buyers WHERE broker_id = ? AND name LIKE ? LIMIT 6",
      args: [brokerId, pattern],
    }),
    client.execute({
      sql: "SELECT id, name, phone, dial FROM sellers WHERE broker_id = ? AND name LIKE ? LIMIT 6",
      args: [brokerId, pattern],
    }),
  ]);

  const results = [
    ...bRes.rows.map((r) => ({ id: r.id, name: r.name, phone: r.phone, dial: r.dial, type: "buyer" })),
    ...sRes.rows.map((r) => ({ id: r.id, name: r.name, phone: r.phone, dial: r.dial, type: "seller" })),
  ].slice(0, 12);

  res.json(results);
});

module.exports = router;
