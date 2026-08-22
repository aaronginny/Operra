const BASE = "/api";

function getToken() {
  return localStorage.getItem("pt_token");
}

async function request(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body != null ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "Request failed"), { status: res.status, data });
  return data;
}

export const api = {
  // auth
  register: (email, name, password, nickname) =>
    request("POST", "/auth/register", { email, name, password, nickname }),
  login: (email, password) =>
    request("POST", "/auth/login", { email, password }),
  me: () => request("GET", "/auth/me"),

  // buyers
  getBuyers: () => request("GET", "/buyers"),
  addBuyer: (buyer) => request("POST", "/buyers", buyer),
  bulkAddBuyers: (buyers) => request("POST", "/buyers/bulk", buyers),
  updateBuyer: (id, buyer) => request("PUT", `/buyers/${id}`, buyer),
  setBuyerLabel: (id, label) => request("PATCH", `/buyers/${id}/label`, { label }),
  bumpBuyerBudget: (id, delta) => request("PATCH", `/buyers/${id}/budget-bump`, { delta }),
  deleteBuyer: (id) => request("DELETE", `/buyers/${id}`),

  // sellers
  getSellers: () => request("GET", "/sellers"),
  addSeller: (seller) => request("POST", "/sellers", seller),
  bulkAddSellers: (sellers) => request("POST", "/sellers/bulk", sellers),
  updateSeller: (id, seller) => request("PUT", `/sellers/${id}`, seller),
  setSellerLabel: (id, label) => request("PATCH", `/sellers/${id}/label`, { label }),
  deleteSeller: (id) => request("DELETE", `/sellers/${id}`),

  // matches
  getMatches: () => request("GET", "/matches"),
  toggleConnect: (matchId) => request("PATCH", `/matches/${encodeURIComponent(matchId)}/connect`),

  // contacts search (name autocomplete)
  searchContacts: (q) => request("GET", `/contacts/search?q=${encodeURIComponent(q)}`),

  // notes
  getNotes: (clientType, clientId) => request("GET", `/notes/${clientType}/${clientId}`),
  addNote: (clientType, clientId, body) => request("POST", `/notes/${clientType}/${clientId}`, { body }),
  deleteNote: (noteId) => request("DELETE", `/notes/${noteId}`),

  // commissions
  getCommissions: () => request("GET", "/commissions"),
  addCommission: (data) => request("POST", "/commissions", data),
  updateCommission: (id, data) => request("PUT", `/commissions/${id}`, data),
  deleteCommission: (id) => request("DELETE", `/commissions/${id}`),
};
