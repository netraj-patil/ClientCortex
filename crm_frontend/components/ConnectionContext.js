"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "@/lib/api";

const Ctx = createContext(null);

export function ConnectionProvider({ children }) {
  const [connections, setConnections] = useState([]);
  const [activeId, setActiveIdState] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const list = await api("/api/connections");
      setConnections(list);
      setActiveIdState((current) => {
        const saved = current || localStorage.getItem("activeConnection") || "";
        return list.some((c) => c.id === saved) ? saved : list[0]?.id || "";
      });
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActiveId = (id) => {
    localStorage.setItem("activeConnection", id);
    setActiveIdState(id);
  };

  return (
    <Ctx.Provider
      value={{ connections, activeId, setActiveId, refresh, error }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useConnections = () => useContext(Ctx);
