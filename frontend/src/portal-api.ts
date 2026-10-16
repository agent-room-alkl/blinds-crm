const KEY = "vera-portal-token";

export const portalSession = {
  get token() {
    return sessionStorage.getItem(KEY) || "";
  },
  set token(value: string) {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  },
};

export async function portalRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/portal/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      ...(portalSession.token ? { Authorization: `Bearer ${portalSession.token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: unknown };
    if (response.status === 401) portalSession.token = "";
    if (response.status === 404) throw new Error("PORTAL_UNAVAILABLE");
    const detail = typeof data.detail === "string" ? data.detail : "";
    throw new Error(detail || response.statusText);
  }
  return (await response.json()) as T;
}
