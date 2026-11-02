"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useConnections } from "@/components/ConnectionContext";
import { Alert, Button, NoConnection } from "@/components/ui";

export default function CachePage() {
  const { activeId } = useConnections();
  const [stats, setStats] = useState(null);
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!activeId) return;
    try {
      const [s, e] = await Promise.all([
        api(`/api/cache/stats?connection_id=${activeId}`),
        api(`/api/cache/entries?connection_id=${activeId}`),
      ]);
      setStats(s);
      setEntries(e.entries);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, [activeId]);

  // Load now, then refresh every 5s so invalidations show up on their own.
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  async function clearAll() {
    if (!confirm("Delete every cached answer for this connection?")) return;
    try {
      await api(`/api/cache?connection_id=${activeId}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!activeId) return <NoConnection />;

  const cards = stats
    ? [
        ["Cached answers", stats.entries],
        ["Hits", stats.hits],
        ["Misses", stats.misses],
        ["Hit rate", `${Math.round(stats.hit_rate * 100)}%`],
        ["Invalidated", stats.invalidations],
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Cache</h1>
        <Button variant="danger" onClick={clearAll}>
          Clear cache
        </Button>
      </div>

      <Alert>{error}</Alert>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {cards.map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-slate-200 bg-white p-3"
          >
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold">{value}</p>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {entries.length === 0 && (
          <p className="text-sm text-slate-500">
            Nothing cached yet. Ask a question first.
          </p>
        )}
        {entries.map((e, i) => (
          <div
            key={i}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <p className="font-medium">{e.question}</p>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
              {e.answer}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {e.tables?.map((t) => (
                <span key={t} className="rounded-full bg-slate-100 px-2 py-0.5">
                  {t}
                </span>
              ))}
              <span className="ml-auto">
                {new Date(e.created_at).toLocaleString()}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
