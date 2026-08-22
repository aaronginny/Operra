const express = require("express");
const bcrypt = require("bcryptjs");
const { client } = require("../db");
const { sign, requireAuth } = require("../middleware/auth");

const router = express.Router();

router.post("/register", async (req, res) => {
  const { email, name, nickname, password } = req.body || {};
  if (!email || !name || !password)
    return res.status(400).json({ error: "email, name and password are required" });
  if (password.length < 6)
    return res.status(400).json({ error: "Password must be at least 6 characters" });

  const hash = bcrypt.hashSync(password, 10);
  const nick = (nickname || "").trim();
  try {
    const result = await client.execute({
      sql: "INSERT INTO brokers (email, name, nickname, password) VALUES (?, ?, ?, ?)",
      args: [email.toLowerCase().trim(), name.trim(), nick, hash],
    });
    const broker = { id: Number(result.lastInsertRowid), email: email.toLowerCase().trim(), name: name.trim(), nickname: nick };
    res.status(201).json({ broker, token: sign(broker) });
  } catch (err) {
    if (String(err.message).includes("UNIQUE"))
      return res.status(409).json({ error: "An account with that email already exists" });
    throw err;
  }
});

router.post("/login", async (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password)
    return res.status(400).json({ error: "email and password are required" });

  const result = await client.execute({
    sql: "SELECT * FROM brokers WHERE email = ?",
    args: [email.toLowerCase().trim()],
  });
  const broker = result.rows[0];

  if (!broker || !bcrypt.compareSync(password, broker.password))
    return res.status(401).json({ error: "Invalid email or password" });

  const payload = { id: Number(broker.id), email: broker.email, name: broker.name, nickname: broker.nickname || "" };
  res.json({ broker: payload, token: sign(payload) });
});

router.get("/me", requireAuth, async (req, res) => {
  const result = await client.execute({
    sql: "SELECT id, email, name, nickname, created_at FROM brokers WHERE id = ?",
    args: [req.broker.id],
  });
  const broker = result.rows[0];
  if (!broker) return res.status(404).json({ error: "Broker not found" });
  res.json({ id: Number(broker.id), email: broker.email, name: broker.name, nickname: broker.nickname || "" });
});

module.exports = router;
