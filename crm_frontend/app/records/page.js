"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useConnections } from "@/components/ConnectionContext";
import { Alert, Button, NoConnection, inputClass } from "@/components/ui";

const LIMIT = 20;

export default function RecordsPage() {
  const { activeId } = useConnections();
  const [schema, setSchema] = useState({});
  const [table, setTable] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });
  const [offset, setOffset] = useState(0);
  const [editor, setEditor] = useState(null); // { id: string | null, text: string }
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const columns = schema[table] || [];
  const pkName = columns.find((c) => c.primary_key)?.name;
  const base = `/api/connections/${activeId}/tables/${table}/records`;

  // Load tables when the connection changes
  useEffect(() => {
    if (!activeId) return;
    setTable("");
    setData({ total: 0, items: [] });
    api(`/api/connections/${activeId}/schema`)
      .then((s) => {
        setSchema(s);
        setTable(Object.keys(s)[0] || "");
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [activeId]);

  const load = useCallback(async () => {
    if (!activeId || !table) return;
    try {
      setData(await api(`${base}?limit=${LIMIT}&offset=${offset}`));
      setError("");
    } catch (e) {
      setError(e.message);
      setData({ total: 0, items: [] });
    }
  }, [activeId, table, offset, base]);

  useEffect(() => {
    load();
  }, [load]);

  function openNew() {
    const blank = {};
    columns
      .filter((c) => !c.primary_key)
      .forEach((c) => (blank[c.name] = null));
    setEditor({ id: null, text: JSON.stringify(blank, null, 2) });
  }

  function openEdit(row) {
    const { [pkName]: id, ...rest } = row;
    setEditor({ id: String(id), text: JSON.stringify(rest, null, 2) });
  }

  async function save() {
    setError("");
    setOk("");
    let body;
    try {
      body = JSON.parse(editor.text);
    } catch {
      return setError("That is not valid JSON.");
    }
    try {
      const res = editor.id
        ? await api(`${base}/${editor.id}`, { method: "PUT", body })
        : await api(base, { method: "POST", body });
      setOk(
        `Saved. ${res.cache_entries_invalidated ?? 0} cached answer(s) cleared.`,
      );
      setEditor(null);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove(row) {
    if (!confirm("Delete this record?")) return;
    setError("");
    setOk("");
    try {
      const res = await api(`${base}/${row[pkName]}`, { method: "DELETE" });
      setOk(
        `Deleted. ${res.cache_entries_invalidated ?? 0} cached answer(s) cleared.`,
      );
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!activeId) return <NoConnection />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Records</h1>
        <select
          className={`${inputClass} !w-auto`}
          value={table}
          onChange={(e) => {
            setTable(e.target.value);
            setOffset(0);
            setEditor(null);
          }}
        >
          {Object.keys(schema).map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <Button className="ml-auto" onClick={openNew} disabled={!table}>
          New record
        </Button>
      </div>

      <p className="text-sm text-slate-500">
        Changes made here clear any cached answers that depend on the table.
      </p>

      <Alert>{error}</Alert>
      <Alert kind="ok">{ok}</Alert>

      {editor && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-sm font-medium">
            {editor.id ? `Edit ${pkName} = ${editor.id}` : "New record"}
          </p>
          <textarea
            className={`${inputClass} h-48 font-mono`}
            value={editor.text}
            onChange={(e) => setEditor({ ...editor, text: e.target.value })}
          />
          <div className="flex gap-2">
            <Button onClick={save}>Save</Button>
            <Button variant="secondary" onClick={() => setEditor(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.name}
                  className="whitespace-nowrap px-3 py-2 font-medium"
                >
                  {c.name}
                </th>
              ))}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {data.items.map((row, i) => (
              <tr key={i} className="border-b border-slate-100 last:border-0">
                {columns.map((c) => (
                  <td key={c.name} className="max-w-xs truncate px-3 py-2">
                    {row[c.name] === null || row[c.name] === undefined ? (
                      <span className="text-slate-300">null</span>
                    ) : (
                      String(row[c.name])
                    )}
                  </td>
                ))}
                <td className="whitespace-nowrap px-3 py-2 text-right">
                  <button
                    className="mr-3 text-indigo-600 hover:underline"
                    onClick={() => openEdit(row)}
                  >
                    Edit
                  </button>
                  <button
                    className="text-red-600 hover:underline"
                    onClick={() => remove(row)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length + 1}
                  className="px-3 py-6 text-center text-slate-500"
                >
                  No records.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>
          {data.total === 0 ? 0 : offset + 1}–
          {Math.min(offset + LIMIT, data.total)} of {data.total}
        </span>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - LIMIT))}
          >
            Previous
          </Button>
          <Button
            variant="secondary"
            disabled={offset + LIMIT >= data.total}
            onClick={() => setOffset(offset + LIMIT)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
