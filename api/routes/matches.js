const express = require("express");
const { client } = require("../db");
const { requireAuth } = require("../middleware/auth");
const { checkAreaMatch } = require("../areaCoords");

const router = express.Router();
router.use(requireAuth);

const STRETCH_PCT = 0.25; // up to 25% above buyer's max budget counts as a stretch match

// Types that must match exactly (no cross-matching between groups)
const TYPE_MATCH_GROUPS = {
  villa_primary: "villa_primary",
  apt_primary:   "apt_primary",
  villa_resale:  "villa_resale",
  apt_resale:    "apt_resale",
  com_primary:   "com_primary",
  com_resale:    "com_resale",
  land_res:      "land_res",
  land_com:      "land_com",
  agri:          "agri",
  // Legacy → keep old records matching their own group
  res_primary:   "res_primary",
  res_resale:    "res_resale",
  res:           "res_resale",
  com:           "com_resale",
  // rentals
  rent_res:      "rent_res",
  rent_com:      "rent_com",
};

function typeGroup(type) {
  return TYPE_MATCH_GROUPS[type] || type;
}

// Parse comma-separated areas into trimmed array (preserve original casing for display)
function parseAreas(area) {
  return (area || "").split(",").map((a) => a.trim()).filter(Boolean);
}

// Normalize rental price to monthly so monthly vs yearly listings can match
const monthly = (p, period) => (period === "yearly" ? Number(p) / 12 : Number(p));

function computeMatches(buyers, sellers, connectedSet) {
  const out = [];
  for (const b of buyers) {
    for (const s of sellers) {
      if (b.division !== s.division) continue;
      if (typeGroup(b.type) !== typeGroup(s.type) || b.cur !== s.cur) continue;

      // Proximity-aware area matching:
      // For each (buyerArea, sellerArea) pair, check exact or haversine within buyer's radius
      const bAreas = parseAreas(b.area);
      const sAreas = parseAreas(s.area);
      const radiusKm = b.radius_km || 5;

      let bestAreaMatch = null;
      for (const ba of bAreas) {
        for (const sa of sAreas) {
          const result = checkAreaMatch(ba, sa, radiusKm);
          if (result) {
            // Prefer exact match over proximity; among proximity prefer closest
            if (!bestAreaMatch ||
                (result.type === "exact" && bestAreaMatch.type !== "exact") ||
                (result.type === bestAreaMatch.type && result.distanceKm < bestAreaMatch.distanceKm)) {
              bestAreaMatch = { ...result, buyerArea: ba, sellerArea: sa };
            }
          }
        }
      }
      if (!bestAreaMatch) continue;

      // For rentals, normalize both to monthly before comparing
      const isRental = b.division === "rentals";
      const sPrice = isRental ? monthly(s.price, s.period) : Number(s.price);
      const bMin = isRental ? monthly(b.min, b.period) : Number(b.min);
      const bMax = isRental ? monthly(b.max, b.period) : Number(b.max);

      let kind = null;
      if (sPrice >= bMin && sPrice <= bMax) {
        kind = "exact";
      } else if (sPrice > bMax && sPrice <= bMax * (1 + STRETCH_PCT)) {
        kind = "stretch";
      } else {
        continue;
      }

      const mid = (bMin + bMax) / 2;
      const span = (bMax - bMin) / 2 || 1;
      const baseScore = Math.round(85 + (1 - Math.min(1, Math.abs(sPrice - mid) / span)) * 13);
      // Proximity matches get a small score reduction (closer = less penalty)
      const proximityPenalty = bestAreaMatch.type === "proximity"
        ? Math.round(bestAreaMatch.distanceKm * 0.5)
        : 0;
      const score = kind === "stretch"
        ? Math.max(60, baseScore - 18 - proximityPenalty)
        : Math.max(60, baseScore - proximityPenalty);

      const id = `${b.id}-${s.id}`;
      out.push({
        id, buyer: b, seller: s, score, kind,
        connected: connectedSet.has(id),
        // Area match metadata for UI display
        matchedBuyerArea: bAreas.length > 1 || bestAreaMatch.type === "proximity" ? bestAreaMatch.buyerArea : null,
        matchedSellerArea: bestAreaMatch.type === "proximity" ? bestAreaMatch.sellerArea : null,
        distanceKm: bestAreaMatch.distanceKm > 0 ? bestAreaMatch.distanceKm : null,
        areaMatchType: bestAreaMatch.type,
        // Legacy compat — keep matchedArea for any existing consumers
        matchedArea: bAreas.length > 1 ? bestAreaMatch.buyerArea.toLowerCase() : null,
      });
    }
  }
  return out.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "exact" ? -1 : 1;
    if (a.areaMatchType !== b.areaMatchType) return a.areaMatchType === "exact" ? -1 : 1;
    return b.score - a.score;
  });
}

router.get("/", async (req, res) => {
  const brokerId = req.broker.id;

  const [bRes, sRes, cRes] = await Promise.all([
    client.execute({ sql: "SELECT * FROM buyers  WHERE broker_id = ? ORDER BY created_at DESC", args: [brokerId] }),
    client.execute({ sql: "SELECT * FROM sellers WHERE broker_id = ? ORDER BY created_at DESC", args: [brokerId] }),
    client.execute({ sql: "SELECT match_id FROM connections WHERE broker_id = ? AND connected = 1", args: [brokerId] }),
  ]);

  const mapBuyer = (r) => ({
    id: r.id, name: r.name, phone: r.phone, dial: r.dial,
    country: r.country, area: r.area, type: r.type, cur: r.cur,
    min: r.min_price, max: r.max_price,
    intl: r.intl === 1 || r.intl === true, notes: r.notes,
    division: r.division || "sales",
    period: r.period || "monthly",
    label: r.label || "active",
    radius_km: r.radius_km != null ? Number(r.radius_km) : 5,
  });
  const mapSeller = (r) => ({
    id: r.id, name: r.name, phone: r.phone, dial: r.dial,
    country: r.country, area: r.area, type: r.type, cur: r.cur,
    price: r.price,
    intl: r.intl === 1 || r.intl === true, notes: r.notes,
    division: r.division || "sales",
    period: r.period || "monthly",
    label: r.label || "active",
  });

  const buyers = bRes.rows.map(mapBuyer);
  const sellers = sRes.rows.map(mapSeller);
  const connectedSet = new Set(cRes.rows.map((r) => r.match_id));

  res.json(computeMatches(buyers, sellers, connectedSet));
});

router.patch("/:id/connect", async (req, res) => {
  const matchId = req.params.id;
  const brokerId = req.broker.id;

  const existing = (await client.execute({
    sql: "SELECT * FROM connections WHERE match_id = ? AND broker_id = ?",
    args: [matchId, brokerId],
  })).rows[0];

  if (existing) {
    const newVal = (existing.connected === 1 || existing.connected === true) ? 0 : 1;
    await client.execute({
      sql: "UPDATE connections SET connected = ? WHERE match_id = ? AND broker_id = ?",
      args: [newVal, matchId, brokerId],
    });
    return res.json({ connected: newVal === 1 });
  }

  const dash = matchId.indexOf("-");
  const bId = matchId.slice(0, dash);
  const sId = matchId.slice(dash + 1);

  await client.execute({
    sql: "INSERT INTO connections (match_id, broker_id, buyer_id, seller_id, connected) VALUES (?, ?, ?, ?, 1)",
    args: [matchId, brokerId, bId, sId],
  });
  res.json({ connected: true });
});

module.exports = router;
