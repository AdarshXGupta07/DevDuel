// Token handling.
//
// The access token lives in memory only — a token in localStorage is readable by any
// XSS that ever lands on the page. The refresh token has to survive a page reload, so
// it does live in localStorage; that is a deliberate, documented tradeoff (a real
// hardening pass moves it to an httpOnly cookie, which needs a server-side session
// endpoint we have not built yet).
//
// Refresh is *rotating*: every call returns a new refresh token and invalidates the old
// one, so the stored value must be replaced on every refresh or the next call fails.

let accessToken = null;
let refreshing = null;

const REFRESH_KEY = 'devduel.refresh';

export function setTokens({ access_token, refresh_token }) {
  accessToken = access_token || null;
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}

export function clearTokens() {
  accessToken = null;
  localStorage.removeItem(REFRESH_KEY);
}

export function getAccessToken() {
  return accessToken;
}

export function hasSession() {
  return Boolean(localStorage.getItem(REFRESH_KEY));
}

async function refreshTokens() {
  const stored = localStorage.getItem(REFRESH_KEY);
  if (!stored) throw new Error('no session');

  // Collapse concurrent refreshes: two parallel 401s must not both spend the token,
  // because the second one would look like reuse and revoke the whole family.
  if (!refreshing) {
    refreshing = fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: stored }),
    })
      .then(async (res) => {
        if (!res.ok) {
          clearTokens();
          throw new Error('session expired');
        }
        const data = await res.json();
        setTokens(data);
        return data;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

export async function api(path, { method = 'GET', body, retry = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && retry && hasSession()) {
    await refreshTokens();
    return api(path, { method, body, retry: false });
  }

  if (res.status === 204) return null;

  const text = await res.text();

  // Not every response is JSON. A 500 from the server, a 502 from a proxy, or an HTML
  // error page all arrive as plain text, and parsing them blindly produced the useless
  // "Unexpected token 'I'" — which hid the actual problem behind a JSON parser error.
  let data = null;
  let parseFailed = false;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      parseFailed = true;
    }
  }

  if (!res.ok) {
    const detail =
      data?.detail ||
      (parseFailed && text.trim().slice(0, 140)) ||
      `Request failed (${res.status})`;
    const error = new Error(detail);
    error.status = res.status;
    error.data = data;
    throw error;
  }

  if (parseFailed) {
    throw new Error('The server returned an unexpected response.');
  }
  return data;
}

export async function ensureAccessToken() {
  if (accessToken) return accessToken;
  if (!hasSession()) return null;
  const data = await refreshTokens();
  return data.access_token;
}

export const auth = {
  register: (name, email, password) =>
    api('/auth/register', { method: 'POST', body: { name, email, password } }),
  login: async (email, password) => {
    const tokens = await api('/auth/login', { method: 'POST', body: { email, password } });
    setTokens(tokens);
    return tokens;
  },
  logout: async () => {
    const stored = localStorage.getItem(REFRESH_KEY);
    if (stored) {
      try {
        await api('/auth/logout', { method: 'POST', body: { refresh_token: stored } });
      } catch {
        /* logging out locally matters more than the server's opinion */
      }
    }
    clearTokens();
  },
  me: () => api('/auth/me'),
};
