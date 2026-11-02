"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useConnections } from "@/components/ConnectionContext";
import { Alert, Button, inputClass } from "@/components/ui";

const empty = {
  name: "",
  db_type: "postgresql",
  host: "localhost",
  port: "",
  database: "",
  username: "",
  password: "",
};

export default function ConnectionsPage() {
  const { connections, refresh, setActiveId } = useConnections();
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const isSqlite = form.db_type === "sqlite";

  async function add(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setOk("");
    try {
      const body = {
        name: form.name,
        db_type: form.db_type,
        database: form.database,
        host: isSqlite ? null : form.host || null,
        port: !isSqlite && form.port ? Number(form.port) : null,
        username: isSqlite ? null : form.username || null,
        password: isSqlite ? null : form.password || null,
      };
      const created = await api("/api/connections", { method: "POST", body });
      await refresh();
      setActiveId(created.id);
      setForm(empty);
      setOk(
        `Connected to "${created.name}" (${created.tables?.length ?? 0} tables).`,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(c) {
    if (!confirm(`Remove "${c.name}" and its cached answers?`)) return;
    try {
      await api(`/api/connections/${c.id}`, { method: "DELETE" });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">Connections</h1>

      <form
        onSubmit={add}
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2"
      >
        <label className="text-sm">
          Name
          <input
            className={inputClass}
            value={form.name}
            onChange={set("name")}
            required
          />
        </label>
        <label className="text-sm">
          Database type
          <select
            className={inputClass}
            value={form.db_type}
            onChange={set("db_type")}
          >
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
        </label>

        {!isSqlite && (
          <>
            <label className="text-sm">
              Host
              <input
                className={inputClass}
                value={form.host}
                onChange={set("host")}
                required
              />
            </label>
            <label className="text-sm">
              Port
              <input
                className={inputClass}
                type="number"
                value={form.port}
                onChange={set("port")}
                placeholder="default"
              />
            </label>
          </>
        )}

        <label className="text-sm sm:col-span-2">
          {isSqlite ? "File path" : "Database name"}
          <input
            className={inputClass}
            value={form.database}
            onChange={set("database")}
            required
          />
        </label>

        {!isSqlite && (
          <>
            <label className="text-sm">
              Username
              <input
                className={inputClass}
                value={form.username}
                onChange={set("username")}
              />
            </label>
            <label className="text-sm">
              Password
              <input
                className={inputClass}
                type="password"
                value={form.password}
                onChange={set("password")}
              />
            </label>
          </>
        )}

        <div className="space-y-2 sm:col-span-2">
          <Alert>{error}</Alert>
          <Alert kind="ok">{ok}</Alert>
          <Button disabled={busy}>
            {busy ? "Connecting…" : "Add connection"}
          </Button>
        </div>
      </form>

      <div className="space-y-2">
        {connections.length === 0 && (
          <p className="text-sm text-slate-500">No connections yet.</p>
        )}
        {connections.map((c) => (
          <div
            key={c.id}
            className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3"
          >
            <div>
              <p className="font-medium">{c.name}</p>
              <p className="text-xs text-slate-500">
                {c.db_type} ·{" "}
                {c.host ? `${c.host}${c.port ? ":" + c.port : ""}/` : ""}
                {c.database}
              </p>
            </div>
            <Button variant="danger" onClick={() => remove(c)}>
              Remove
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
