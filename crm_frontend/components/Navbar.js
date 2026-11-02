"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useConnections } from "./ConnectionContext";

const links = [
  { href: "/", label: "Ask" },
  { href: "/records", label: "Records" },
  { href: "/cache", label: "Cache" },
  { href: "/connections", label: "Connections" },
];

export default function Navbar() {
  const pathname = usePathname();
  const { connections, activeId, setActiveId } = useConnections();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-4 py-3">
        <span className="font-semibold text-slate-900">ClientCortex</span>

        <nav className="flex gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-md px-3 py-1.5 text-sm ${
                pathname === l.href
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <select
          value={activeId}
          onChange={(e) => setActiveId(e.target.value)}
          className="ml-auto rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          {connections.length === 0 && <option value="">No connections</option>}
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.db_type})
            </option>
          ))}
        </select>
      </div>
    </header>
  );
}
