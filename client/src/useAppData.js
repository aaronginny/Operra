import { useState, useEffect, useCallback } from "react";
import { api } from "./api";

async function withRetry(fn, attempts = 3, delayMs = 800) {
  for (let i = 0; i < attempts; i++) {
    try { return await fn(); }
    catch (e) {
      if (i === attempts - 1) throw e;
      await new Promise((r) => setTimeout(r, delayMs * (i + 1)));
    }
  }
}

export function useAppData(enabled = true) {
  const [buyers, setBuyers] = useState([]);
  const [sellers, setSellers] = useState([]);
  const [matches, setMatches] = useState([]);
  const [connectedSet, setConnectedSet] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [b, s, m] = await withRetry(() =>
        Promise.all([api.getBuyers(), api.getSellers(), api.getMatches()])
      );
      setBuyers(b);
      setSellers(s);
      setMatches(m);
      setConnectedSet(new Set(m.filter((x) => x.connected).map((x) => x.id)));
    } catch (e) {
      setError(e.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (enabled) reload(); }, [reload, enabled]);

  const refreshMatches = async () => {
    const m = await withRetry(() => api.getMatches());
    setMatches(m);
    setConnectedSet(new Set(m.filter((x) => x.connected).map((x) => x.id)));
  };

  const addBuyer = async (data) => {
    const b = await api.addBuyer(data);
    setBuyers((prev) => [b, ...prev]);
    await refreshMatches();
    return b;
  };

  const addSeller = async (data) => {
    const s = await api.addSeller(data);
    setSellers((prev) => [s, ...prev]);
    await refreshMatches();
    return s;
  };

  // Bulk import — sends a batch to the server and refreshes state once when done.
  // Returns { inserted, duplicates, failed, errors } from the server.
  const bulkAddBuyers = async (records) => {
    const result = await api.bulkAddBuyers(records);
    if (result.inserted > 0) {
      const fresh = await api.getBuyers();
      setBuyers(fresh);
      await refreshMatches();
    }
    return result;
  };

  const bulkAddSellers = async (records) => {
    const result = await api.bulkAddSellers(records);
    if (result.inserted > 0) {
      const fresh = await api.getSellers();
      setSellers(fresh);
      await refreshMatches();
    }
    return result;
  };

  const updateBuyer = async (id, data) => {
    const b = await api.updateBuyer(id, data);
    setBuyers((prev) => prev.map((x) => x.id === id ? b : x));
    await refreshMatches();
    return b;
  };

  const updateSeller = async (id, data) => {
    const s = await api.updateSeller(id, data);
    setSellers((prev) => prev.map((x) => x.id === id ? s : x));
    await refreshMatches();
    return s;
  };

  const setBuyerLabel = async (id, label) => {
    const b = await api.setBuyerLabel(id, label);
    setBuyers((prev) => prev.map((x) => x.id === id ? b : x));
    return b;
  };

  const setSellerLabel = async (id, label) => {
    const s = await api.setSellerLabel(id, label);
    setSellers((prev) => prev.map((x) => x.id === id ? s : x));
    return s;
  };

  const bumpBuyerBudget = async (id, delta) => {
    const b = await api.bumpBuyerBudget(id, delta);
    setBuyers((prev) => prev.map((x) => x.id === id ? b : x));
    await refreshMatches();
    return b;
  };

  const deleteBuyer = async (id) => {
    await api.deleteBuyer(id);
    setBuyers((prev) => prev.filter((x) => x.id !== id));
    setMatches((prev) => prev.filter((m) => m.buyer.id !== id));
  };

  const deleteSeller = async (id) => {
    await api.deleteSeller(id);
    setSellers((prev) => prev.filter((x) => x.id !== id));
    setMatches((prev) => prev.filter((m) => m.seller.id !== id));
  };

  const toggleConnect = async (matchId) => {
    const result = await api.toggleConnect(matchId);
    setConnectedSet((prev) => {
      const next = new Set(prev);
      if (result.connected) next.add(matchId);
      else next.delete(matchId);
      return next;
    });
    return result;
  };

  return {
    buyers, sellers, matches, connectedSet, loading, error, reload,
    addBuyer, addSeller, bulkAddBuyers, bulkAddSellers,
    updateBuyer, updateSeller,
    setBuyerLabel, setSellerLabel, bumpBuyerBudget,
    deleteBuyer, deleteSeller, toggleConnect,
  };
}
