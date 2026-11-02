"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useConnections } from "@/components/ConnectionContext";
import { Alert, Button, NoConnection, inputClass } from "@/components/ui";

export default function AskPage() {
  const { activeId, error: connError } = useConnections();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]); // newest first

  async function submit(e) {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3) return;
    setLoading(true);
    setError("");
    try {
      const res = await api("/api/ask", {
        method: "POST",
        body: { question: q, connection_id: activeId },
      });
      setHistory((h) => [{ question: q, ...res }, ...h]);
      setQuestion("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Ask your CRM</h1>
        <p className="mt-1 text-sm text-slate-500">
          Ask in plain English. Repeated or similar questions are answered
          instantly from the cache.
        </p>
      </div>

      <Alert>{connError}</Alert>

      {!activeId ? (
        <NoConnection />
      ) : (
        <form onSubmit={submit} className="flex gap-2">
          <input
            className={inputClass}
            placeholder="e.g. Which deals closed last month?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
          />
          <Button disabled={loading || question.trim().length < 3}>
            {loading ? "Thinking…" : "Ask"}
          </Button>
        </form>
      )}

      <Alert>{error}</Alert>

      <div className="space-y-4">
        {history.map((item, i) => (
          <div
            key={i}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <p className="text-sm font-medium text-slate-500">
              {item.question}
            </p>
            <p className="mt-2 whitespace-pre-wrap">{item.answer}</p>

            <div className="mt-3 flex items-center gap-3 text-xs">
              <span
                className={`rounded-full px-2 py-0.5 font-medium ${
                  item.source === "cache"
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                {item.source === "cache" ? "From cache" : "From database"}
              </span>
              <span className="text-slate-500">{item.latency_ms} ms</span>
            </div>

            {item.sql && (
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-slate-500">
                  Show SQL
                </summary>
                <pre className="mt-2 overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                  {item.sql}
                </pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
