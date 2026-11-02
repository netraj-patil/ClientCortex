const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Small fetch wrapper: sends/receives JSON and throws a readable Error on failure.
export async function api(path, { method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Cannot reach the backend. Is it running on " + BASE + "?");
  }

  let data = null;
  try {
    data = await res.json();
  } catch {}

  if (!res.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}
