// Клиент API «Критика». Access-токен живёт только в памяти, refresh — в httpOnly-cookie,
// поэтому после перезагрузки страницы сессия восстанавливается запросом /auth/refresh/.

export class ApiError extends Error {
  constructor(status, data) {
    super(ApiError.describe(status, data));
    this.status = status;
    this.data = data || {};
  }

  static describe(status, data) {
    if (data && typeof data.detail === 'string') return data.detail;
    if (data && typeof data === 'object') {
      const first = Object.values(data).flat()[0];
      if (typeof first === 'string') return first;
    }
    if (status === 0) return 'Сервер не отвечает. Проверьте, что он запущен.';
    return `Ошибка сервера (${status}).`;
  }
}

const session = { access: null, user: null };
// Флаг «в этом браузере входили» (без токена): гостю не нужен заведомо неудачный запрос refresh.
const SESSION_HINT = 'kritik:session';

function hint(on) {
  try {
    if (on) localStorage.setItem(SESSION_HINT, '1');
    else localStorage.removeItem(SESSION_HINT);
  } catch {
    /* хранилище недоступно — просто всегда пробуем refresh */
  }
}

function hasHint() {
  try {
    return localStorage.getItem(SESSION_HINT) !== null;
  } catch {
    return true;
  }
}
const listeners = new Set();
let refreshing = null;

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function notify() {
  listeners.forEach((fn) => fn(session.user));
}

async function send(path, { method = 'GET', body, token } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, null);
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

function refresh() {
  refreshing ??= send('/auth/refresh/', { method: 'POST' })
    .then((data) => {
      session.access = data.access;
      return true;
    })
    .catch(() => {
      hint(false);
      const hadUser = session.user !== null;
      session.access = null;
      session.user = null;
      if (hadUser) notify();
      return false;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

export async function request(path, options = {}) {
  try {
    return await send(path, { ...options, token: session.access });
  } catch (error) {
    // Access-токен истёк: пробуем продлить сессию один раз и повторяем запрос.
    if (error.status === 401 && session.access) {
      await refresh();
      return send(path, { ...options, token: session.access });
    }
    throw error;
  }
}

export const auth = {
  get user() {
    return session.user;
  },
  onChange(fn) {
    listeners.add(fn);
  },
  async restore() {
    if (!hasHint() || !(await refresh())) return null;
    try {
      session.user = await request('/auth/me/');
    } catch {
      session.user = null;
    }
    notify();
    return session.user;
  },
  async login(username, password) {
    return this.accept(await send('/auth/login/', { method: 'POST', body: { username, password } }));
  },
  async register(payload) {
    return this.accept(await send('/auth/register/', { method: 'POST', body: payload }));
  },
  accept(data) {
    hint(true);
    session.access = data.access;
    session.user = data.user;
    notify();
    return data.user;
  },
  async logout() {
    try {
      await send('/auth/logout/', { method: 'POST' });
    } finally {
      hint(false);
      session.access = null;
      session.user = null;
      notify();
    }
  },
};

export const api = {
  stats: () => request('/games/stats/'),
  filters: () => request('/games/filters/'),
  games: (params) => request(`/games/?${params}`),
  game: (id) => request(`/games/${id}/`),
  gameReviews: (id) => request(`/games/${id}/reviews/`),
  createReview: (body) => request('/reviews/', { method: 'POST', body }),
  updateReview: (id, body) => request(`/reviews/${id}/`, { method: 'PATCH', body }),
  deleteReview: (id) => request(`/reviews/${id}/`, { method: 'DELETE' }),
  myReviews: () => request('/me/reviews/'),
  saved: () => request('/me/saved-games/'),
  save: (gameId) => request('/me/saved-games/', { method: 'POST', body: { game_id: gameId } }),
  unsave: (gameId) => request(`/me/saved-games/${gameId}/`, { method: 'DELETE' }),
};
