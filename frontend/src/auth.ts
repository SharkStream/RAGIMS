/**
 * Auth store (K5): token + current user persistence + a tiny React hook.
 *
 * Token/user live in localStorage so a refresh keeps the session; `/auth/me`
 * revalidates lazily (App shell) — role always comes from the backend.
 */

export interface StoredUser {
  id: string;
  tenant_id: string;
  username: string;
  role: "admin" | "editor" | "viewer" | string;
}

const TOKEN_KEY = "ragims_token";
const USER_KEY = "ragims_user";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string, user: StoredUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser(): StoredUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    return null;
  }
}

/** Write-role check used by pages to hide mutation controls. */
export function canWrite(user: StoredUser | null): boolean {
  return user?.role === "admin" || user?.role === "editor";
}
