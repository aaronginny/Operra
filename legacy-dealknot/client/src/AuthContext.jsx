import { createContext, useContext, useState, useEffect } from "react";
import { api } from "./api";

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [broker, setBroker] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("pt_token");
    if (!token) { setLoading(false); return; }
    api.me()
      .then((b) => setBroker(b))
      .catch(() => localStorage.removeItem("pt_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const { broker: b, token } = await api.login(email, password);
    localStorage.setItem("pt_token", token);
    setBroker(b);
    return b;
  };

  const register = async (email, name, password, nickname) => {
    const { broker: b, token } = await api.register(email, name, password, nickname);
    localStorage.setItem("pt_token", token);
    setBroker(b);
    return b;
  };

  const logout = () => {
    localStorage.removeItem("pt_token");
    setBroker(null);
  };

  return (
    <Ctx.Provider value={{ broker, loading, login, register, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
