// Разметка и форматирование, общие для всех экранов.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);

export function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
export const count = (n, one, few, many) => `${n} ${plural(n, one, few, many)}`;

const longDate = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
const shortDate = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
const todayLine = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

export const releaseDate = (iso) => (iso ? longDate.format(new Date(`${iso}T00:00:00`)) : 'Дата не объявлена');
export const releaseYear = (game) => (game.release_date ? game.release_date.slice(0, 4) : '');
export const today = () => todayLine.format(new Date());

export function ago(iso) {
  const date = new Date(iso);
  const days = Math.floor((Date.now() - date.getTime()) / 86400000);
  if (days <= 0) return 'сегодня';
  if (days === 1) return 'вчера';
  if (days < 7) return `${count(days, 'день', 'дня', 'дней')} назад`;
  return shortDate.format(date);
}

// ——— Оценки ———
export const rating = (game) => (game.average_rating == null ? null : Number(game.average_rating));
export const formatScore = (value, integer = false) =>
  value == null ? '—' : integer ? String(value) : value.toFixed(1).replace('.', ',');

export function tier(value) {
  if (value == null) return 'none';
  if (value >= 9) return 'top';
  if (value >= 7) return 'good';
  if (value >= 5) return 'mixed';
  return 'low';
}

export const TIER_LABELS = {
  top: 'выбор сообщества',
  good: 'хорошо',
  mixed: 'спорно',
  low: 'слабо',
  none: 'нет оценок',
};

export function score(value, { size = '', integer = false } = {}) {
  const t = tier(value);
  const label = value == null ? 'Нет оценок' : `Оценка ${formatScore(value, integer)} из 10`;
  return `<span class="score score--${t}${size ? ` score--${size}` : ''}" role="img" aria-label="${label}">${formatScore(value, integer)}</span>`;
}

export const SCORE_WORDS = [
  '', 'Провал', 'Ужасно', 'Очень плохо', 'Плохо', 'Посредственно',
  'Нормально', 'Хорошо', 'Очень хорошо', 'Отлично', 'Шедевр',
];

// ——— Обложки ———
const THEMES = ['oxblood', 'indigo', 'slate', 'mustard', 'bottle', 'plum', 'rust', 'ink', 'teal', 'sand'];

function themeFor(game) {
  if (THEMES.includes(game.poster_theme)) return game.poster_theme;
  let hash = 0;
  for (const char of game.title || '') hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return THEMES[hash % THEMES.length];
}

// Для игр без картинки рисуем типографскую обложку — как у книжной серии.
export function typeCover(game) {
  const title = game.title || '';
  const longest = Math.max(...title.split(/\s+/).map((word) => word.length));
  const size = title.length > 26 || longest > 13 ? ' cover--xlong' : title.length > 14 || longest > 9 ? ' cover--long' : '';
  return `<div class="cover cover--type cover--${themeFor(game)}${size}" aria-hidden="true">
    <div class="cover__meta"><span></span><span>${esc(releaseYear(game))}</span></div>
    <div><div class="cover__rule"></div><div class="cover__title" lang="en">${esc(title)}</div></div>
  </div>`;
}

export function cover(game) {
  if (!game.cover_url) return typeCover(game);
  return `<div class="cover"><img src="${esc(game.cover_url)}" alt="" loading="lazy" decoding="async"
    data-fallback="${esc(JSON.stringify({ title: game.title, poster_theme: game.poster_theme, release_date: game.release_date }))}"></div>`;
}

// Картинка с RAWG не загрузилась — подменяем типографской обложкой.
export function installCoverFallback(root) {
  root.addEventListener(
    'error',
    (event) => {
      const img = event.target;
      if (!(img instanceof HTMLImageElement) || !img.dataset.fallback) return;
      img.closest('.cover').outerHTML = typeCover(JSON.parse(img.dataset.fallback));
    },
    true,
  );
}

export const names = (items, limit = Infinity) => {
  const list = (items || []).map((item) => item.name);
  if (list.length <= limit) return list.join(', ');
  return `${list.slice(0, limit).join(', ')} и ещё ${list.length - limit}`;
};

export const reviewsLabel = (n) => (n ? count(n, 'рецензия', 'рецензии', 'рецензий') : 'Нет рецензий');

export function saveButton(game, saved) {
  return `<button class="save" type="button" data-save="${game.id}" aria-pressed="${saved}">${saved ? 'В списке' : 'В список'}</button>`;
}

export function card(game, saved) {
  const meta = [releaseYear(game), names(game.genres, 2)].filter(Boolean).join(' · ');
  return `<article class="card">
    <a class="card__cover" href="#/game/${game.id}" tabindex="-1" aria-hidden="true">
      ${cover(game)}<span class="card__score">${score(rating(game))}</span>
    </a>
    <div class="card__body">
      <div class="card__meta mono">${esc(meta) || '&nbsp;'}</div>
      <h3 class="card__title"><a href="#/game/${game.id}">${esc(game.title)}</a></h3>
      <p class="card__platforms">${esc(names(game.platforms, 3)) || 'Платформы не указаны'}</p>
      <div class="card__foot mono"><span>${reviewsLabel(game.review_count)}</span>${saveButton(game, saved)}</div>
    </div>
  </article>`;
}

export function table(games, saved, offset = 0) {
  const rows = games
    .map(
      (game, index) => `<tr>
      <td class="table__rank">${String(offset + index + 1).padStart(2, '0')}</td>
      <td><div class="table__game"><a class="table__thumb" href="#/game/${game.id}" tabindex="-1" aria-hidden="true">${cover(game)}</a>
        <a class="table__title" href="#/game/${game.id}">${esc(game.title)}</a></div></td>
      <td class="table__muted hide-sm">${esc(names(game.genres, 2))}</td>
      <td class="table__muted hide-md">${esc(names(game.platforms, 2))}</td>
      <td class="num hide-sm">${esc(releaseYear(game)) || '—'}</td>
      <td class="num hide-sm">${game.review_count}</td>
      <td class="num">${score(rating(game), { size: 'sm' })}</td>
      <td>${saveButton(game, saved.has(game.id))}</td>
    </tr>`,
    )
    .join('');
  return `<table class="table">
    <thead><tr><th>№</th><th>Игра</th><th class="hide-sm">Жанр</th><th class="hide-md">Платформы</th>
    <th class="num hide-sm">Год</th><th class="num hide-sm">Рец.</th><th class="num">Оценка</th><th><span class="visually-hidden">Список</span></th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

export const loading = (text = 'Загрузка') => `<div class="loading mono">${esc(text)}</div>`;

export function legend() {
  const items = [
    [9.5, '9 и выше — выбор сообщества'],
    [8, '7–8,9 — хорошо'],
    [6, '5–6,9 — спорно'],
    [3, 'ниже 5 — слабо'],
    [null, 'нет оценок'],
  ];
  return `<ul class="legend mono">${items.map(([value, text]) => `<li>${score(value)}${esc(text)}</li>`).join('')}</ul>`;
}
