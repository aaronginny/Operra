const jwt = require("jsonwebtoken");

const SECRET = process.env.JWT_SECRET || "dealknot-dev-secret-change-in-prod";

function sign(payload) {
  return jwt.sign(payload, SECRET, { expiresIn: "30d" });
}

function requireAuth(req, res, next) {
  const header = req.headers.authorization || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: "Not authenticated" });
  try {
    req.broker = jwt.verify(token, SECRET);
    next();
  } catch {
    res.status(401).json({ error: "Invalid or expired token" });
  }
}

module.exports = { sign, requireAuth };
