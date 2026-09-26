import { api, ApiError, auth } from './api.js';
import {
  ago, card, count, cover, esc, formatScore, installCoverFallback, legend, loading, names, rating, releaseDate,
  releaseYear, reviewsLabel, score, SCORE_WORDS, table, tier, today,
} from './ui.js';

const view = document.getElementById('view');
const dialog = document.getElementById('auth-dialog');
const toastEl = document.getElementById('toast');

const SORTS = [
  ['rating', 'оценке'],
  ['reviews', 'числу рецензий'],
  ['newest', 'новизне'],
  ['oldest', 'году, старые'],
  ['title', 'названию'],
];
const RATING_STEPS = [['', 'Все'], ['6', '6+'], ['7', '7+'], ['8', '8+'], ['9', '9+']];
const PLATFORMS_COLLAPSED = 6;

const store = {
  screen: null,
  meta: null,
  lead: null,
  saved: new Set(),
  layout: readPref('kritik:layout', 'grid'),
  showAllPlatforms: false,
  catalog: { query: null, items: [], count: 0, page: 1, next: null },
  pending: null,
  seq: 0,
  reviewSort: 'new',
};

function readPref(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}
function writePref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* приватный режим — просто не запоминаем */
  }
}

// ——— Уведомления ———
let toastTimer;
function toast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, 3800);
}

// ——— Шапка ———
async function refreshStats() {
  try {
    const stats = await api.stats();
    document.getElementById('stats').innerHTML = [
      ['Игр', stats.games],
      ['Рецензий', stats.reviews],
      ['Критиков', stats.critics],
    ]
      .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
      .join('');
  } catch {
    document.getElementById('stats').innerHTML = '';
  }
}

function renderAccount() {
  const user = auth.user;
  document.getElementById('account').innerHTML = user
    ? `<span>Вы вошли как <strong>${esc(user.public_name)}</strong></span><button type="button" data-action="logout">Выйти</button>`
    : `<button type="button" data-action="login">Войти</button><button type="button" data-action="register">Регистрация</button>`;
  document.getElementById('saved-count').textContent = user && store.saved.size ? store.saved.size : '';
}

function setNav(section) {
  document.querySelectorAll('[data-nav]').forEach((link) => {
    if (link.dataset.nav === section) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

// ——— Роутер ———
function parseHash() {
  const raw = location.hash.slice(1) || '/';
  const [path, query = ''] = raw.split('?');
  return { path: path || '/', params: new URLSearchParams(query) };
}

async function route() {
  const { path, params } = parseHash();
  const match = path.match(/^\/game\/(\d+)\/?$/);
  try {
    if (path === '/') return await showCatalog(params);
    if (match) return await showGame(Number(match[1]), params);
    if (path === '/saved') return await showSaved();
    if (path === '/reviews') return await showMyReviews();
    return showMessage('Не найдено.', 'Такой страницы нет. Возможно, ссылка устарела.', null);
  } catch (error) {
    console.error(error);
    showMessage('Сбой.', error instanceof ApiError ? error.message : 'Что-то пошло не так. Обновите страницу.', null);
  }
}

function enterScreen(name, title, section = name) {
  const changed = store.screen !== name;
  store.screen = name;
  document.title = title ? `${title} — Критик` : 'Критик — оценки игр от игроков';
  setNav(section);
  return changed;
}

function showMessage(big, text, section, actions = '<a class="btn" href="#/">В каталог</a>') {
  enterScreen(`message:${big}`, big.replace(/\.$/, ''), section);
  view.innerHTML = `<div class="state"><h1 class="state__big">${esc(big)}</h1><p>${esc(text)}</p>${actions}</div>`;
}

function requireLogin(section, title, text) {
  showMessage(
    title,
    text,
    section,
    `<button class="btn" type="button" data-action="login">Войти</button>
     <button class="btn btn--ghost" type="button" data-action="register">Создать аккаунт</button>`,
  );
}

// ——— Каталог: состояние фильтров живёт в адресе, поэтому ссылкой можно поделиться ———
const splitList = (value) => (value ? value.split(',').filter(Boolean) : []);

function readFilters(params) {
  return {
    search: params.get('search') || '',
    genre: splitList(params.get('genre')),
    platform: splitList(params.get('platform')),
    year_from: params.get('year_from') || '',
    year_to: params.get('year_to') || '',
    rating_min: params.get('rating_min') || '',
    reviewed: params.get('reviewed') === '1',
    ordering: params.get('ordering') || 'rating',
  };
}

function toQuery(filters) {
  const query = new URLSearchParams();
  if (filters.search) query.set('search', filters.search);
  if (filters.genre.length) query.set('genre', filters.genre.join(','));
  if (filters.platform.length) query.set('platform', filters.platform.join(','));
  if (filters.year_from) query.set('year_from', filters.year_from);
  if (filters.year_to) query.set('year_to', filters.year_to);
  if (filters.rating_min) query.set('rating_min', filters.rating_min);
  if (filters.reviewed) query.set('reviewed', '1');
  if (filters.ordering !== 'rating') query.set('ordering', filters.ordering);
  return query;
}

const activeFilterCount = (f) =>
  f.genre.length + f.platform.length + (f.year_from || f.year_to ? 1 : 0) + (f.rating_min ? 1 : 0) + (f.reviewed ? 1 : 0) + (f.search ? 1 : 0);

function currentFilters() {
  return readFilters(parseHash().params);
}

function goCatalog(filters, { replace = false } = {}) {
  const query = toQuery(filters).toString();
  const hash = `#/${query ? `?${query}` : ''}`;
  if (replace) {
    history.replaceState(null, '', hash);
    route();
  } else if (location.hash !== hash) {
    location.hash = hash;
  }
}

async function showCatalog(params) {
  const filters = readFilters(params);
  if (enterScreen('catalog', null)) {
    store.catalog.query = null;
    renderCatalogShell(filters);
    window.scrollTo(0, 0);
  }
  store.meta ??= await api.filters();
  renderIndex(filters);
  renderSorts(filters);
  const search = document.getElementById('search');
  if (document.activeElement !== search) search.value = filters.search;

  const pristine = activeFilterCount(filters) === 0;
  document.getElementById('lead').hidden = !pristine;
  if (pristine) {
    renderLead().catch(() => {
      document.getElementById('lead').hidden = true;
    });
  }
  await loadResults(filters);
}

function renderCatalogShell() {
  const wide = window.matchMedia('(min-width: 901px)').matches;
  view.innerHTML = `
    <section class="lead" id="lead" hidden></section>
    <div class="section-head">
      <h2>Каталог</h2>
      <span class="mono">Поиск, фильтры и сортировка работают одновременно</span>
    </div>
    <div class="catalog">
      <details class="index" id="index" ${wide ? 'open' : ''}>
        <summary>Фильтры <span class="mono" id="filter-count"></span></summary>
        <div class="index__body" id="index-body"></div>
      </details>
      <section class="results" aria-label="Результаты">
        <label class="search">
          <svg class="search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><circle cx="10" cy="10" r="7"/><path d="m15.5 15.5 6 6"/></svg>
          <span class="visually-hidden">Поиск по названию</span>
          <input id="search" type="search" placeholder="Найти игру по названию" autocomplete="off" spellcheck="false">
        </label>
        <div class="toolbar">
          <div class="sorts" id="sorts"></div>
          <div class="viewtoggle" role="group" aria-label="Вид каталога">
            <button type="button" data-layout="grid" aria-pressed="${store.layout === 'grid'}">Сетка</button>
            <button type="button" data-layout="table" aria-pressed="${store.layout === 'table'}">Таблица</button>
          </div>
        </div>
        <div class="summary" id="summary"></div>
        <div id="results">${loading()}</div>
        <div class="more" id="more"></div>
      </section>
    </div>`;
}

function indexOptions(kind, items, selected) {
  return items
    .map(
      (item) => `<li><button class="index__option" type="button" data-toggle="${kind}" data-slug="${esc(item.slug)}" aria-pressed="${selected.includes(item.slug)}">
        <span class="index__label">${esc(item.name)}</span><span class="index__count">${item.count}</span></button></li>`,
    )
    .join('');
}

function renderIndex(filters) {
  const { genres, platforms, years } = store.meta;
  const shownPlatforms =
    store.showAllPlatforms || platforms.length <= PLATFORMS_COLLAPSED
      ? platforms
      : platforms.filter((p, i) => i < PLATFORMS_COLLAPSED || filters.platform.includes(p.slug));
  const yearOptions = (selected) =>
    `<option value="">—</option>${years
      .slice()
      .reverse()
      .map((y) => `<option value="${y}" ${String(y) === selected ? 'selected' : ''}>${y}</option>`)
      .join('')}`;
  const active = activeFilterCount(filters) - (filters.search ? 1 : 0);

  document.getElementById('filter-count').textContent = active ? `(${active})` : '';
  document.getElementById('index-body').innerHTML = `
    <div class="index__group">
      <h3 class="index__title">Жанр</h3>
      <ul class="index__list">${indexOptions('genre', genres, filters.genre)}</ul>
    </div>
    <div class="index__group">
      <h3 class="index__title">Платформа</h3>
      <ul class="index__list">${indexOptions('platform', shownPlatforms, filters.platform)}</ul>
      ${platforms.length > PLATFORMS_COLLAPSED ? `<button class="linkbtn index__more" type="button" data-action="more-platforms">${store.showAllPlatforms ? 'Свернуть' : `Все платформы (${platforms.length})`}</button>` : ''}
    </div>
    <div class="index__group">
      <h3 class="index__title">Год выпуска</h3>
      <div class="range">
        <label for="year-from">с</label><select class="select" id="year-from" data-year="year_from">${yearOptions(filters.year_from)}</select>
        <label for="year-to">по</label><select class="select" id="year-to" data-year="year_to">${yearOptions(filters.year_to)}</select>
      </div>
    </div>
    <div class="index__group">
      <h3 class="index__title">Оценка сообщества</h3>
      <div class="steps" role="group" aria-label="Минимальная оценка">
        ${RATING_STEPS.map(([value, label]) => `<button type="button" data-rating="${value}" aria-pressed="${filters.rating_min === value}">${label}</button>`).join('')}
      </div>
      <label class="check"><input type="checkbox" id="reviewed" ${filters.reviewed ? 'checked' : ''}> Только с рецензиями</label>
    </div>
    <div class="index__group">
      <h3 class="index__title">Шкала</h3>
      ${legend()}
      ${active ? '<p><button class="linkbtn linkbtn--danger" type="button" data-action="reset">Сбросить все фильтры</button></p>' : ''}
    </div>`;
}

function renderSorts(filters) {
  document.getElementById('sorts').innerHTML = `<span class="mono">Сортировать по</span>${SORTS.map(
    ([value, label]) => `<button type="button" data-sort="${value}" aria-pressed="${filters.ordering === value}">${label}</button>`,
  ).join('')}`;
}

function renderSummary(filters, total) {
  const { genres, platforms } = store.meta;
  const nameOf = (list, slug) => list.find((item) => item.slug === slug)?.name || slug;
  const tokens = [];
  if (filters.search) tokens.push(['search', '', `«${filters.search}»`]);
  filters.genre.forEach((slug) => tokens.push(['genre', slug, nameOf(genres, slug)]));
  filters.platform.forEach((slug) => tokens.push(['platform', slug, nameOf(platforms, slug)]));
  if (filters.year_from || filters.year_to) {
    const label = filters.year_from && filters.year_to
      ? filters.year_from === filters.year_to ? filters.year_from : `${filters.year_from}–${filters.year_to}`
      : filters.year_from ? `с ${filters.year_from}` : `по ${filters.year_to}`;
    tokens.push(['years', '', label]);
  }
  if (filters.rating_min) tokens.push(['rating_min', '', `оценка ${filters.rating_min}+`]);
  if (filters.reviewed) tokens.push(['reviewed', '', 'с рецензиями']);

  document.getElementById('summary').innerHTML = `<span class="summary__count mono">Найдено: ${count(total, 'игра', 'игры', 'игр')}</span>${tokens
    .map(([kind, slug, label]) => `<button class="token" type="button" data-remove="${kind}" data-slug="${esc(slug)}" aria-label="Убрать фильтр ${esc(label)}">${esc(label)}<span aria-hidden="true">×</span></button>`)
    .join('')}`;
}

async function loadResults(filters, { append = false } = {}) {
  const query = toQuery(filters);
  const key = query.toString();
  const state = store.catalog;
  const ticket = ++store.seq;
  const results = document.getElementById('results');
  const page = append ? state.page + 1 : 1;
  if (!append && key === state.query) {
    renderResults(filters);
    return;
  }
  if (!append) results.style.opacity = '.45';
  query.set('page', page);

  let data;
  try {
    data = await api.games(query);
  } catch (error) {
    if (ticket !== store.seq) return;
    results.style.opacity = '';
    if (error.status === 400) {
      results.innerHTML = `<div class="state"><p>${esc(error.message)}</p><button class="btn btn--ghost" type="button" data-action="reset">Сбросить фильтры</button></div>`;
      return;
    }
    throw error;
  }
  if (ticket !== store.seq) return;

  Object.assign(state, {
    query: key,
    items: append ? [...state.items, ...data.results] : data.results,
    count: data.count,
    page,
    next: data.next,
  });
  results.style.opacity = '';
  renderResults(filters);
}

function renderResults(filters) {
  const { items, count: total, next } = store.catalog;
  renderSummary(filters, total);
  const results = document.getElementById('results');
  if (!items.length) {
    results.innerHTML = `<div class="state"><h3 class="state__big">Пусто.</h3>
      <p>Под такие условия не подошла ни одна игра. Уберите часть фильтров или измените запрос.</p>
      <button class="btn btn--ghost" type="button" data-action="reset">Сбросить фильтры</button></div>`;
  } else if (store.layout === 'table') {
    results.innerHTML = table(items, isSavedSet());
  } else {
    results.innerHTML = `<div class="grid">${items.map((g) => card(g, isSaved(g))).join('')}</div>`;
  }
  const rest = total - items.length;
  document.getElementById('more').innerHTML = next
    ? `<button class="btn btn--ghost" type="button" data-action="more">Показать ещё ${Math.min(rest, 24)} из ${rest}</button>`
    : '';
}

async function renderLead() {
  const lead = document.getElementById('lead');
  if (!store.lead) {
    const top = await api.games(new URLSearchParams({ ordering: 'rating', reviewed: '1', page_size: '6' }));
    const [first] = top.results;
    const reviews = first ? await api.gameReviews(first.id) : [];
    const quote = reviews.slice().sort((a, b) => b.score - a.score || b.text.length - a.text.length)[0];
    store.lead = { games: top.results, quote };
  }
  const [first, ...rest] = store.lead.games;
  if (!first || store.screen !== 'catalog') {
    lead.hidden = true;
    return;
  }
  const quote = store.lead.quote;
  lead.innerHTML = `
    <article class="lead__main">
      <span class="kicker">Выше всех в рейтинге сообщества</span>
      <a class="lead__cover" href="#/game/${first.id}" tabindex="-1" aria-hidden="true">${cover(first)}</a>
      <div class="lead__title-row">
        <h2 class="lead__title"><a href="#/game/${first.id}">${esc(first.title)}</a></h2>
        ${score(rating(first), { size: 'lg' })}
      </div>
      <p class="lead__meta mono">${[releaseYear(first), names(first.genres), reviewsLabel(first.review_count)].filter(Boolean).map(esc).join(' · ')}</p>
      ${quote ? `<blockquote class="lead__quote">«${esc(quote.text)}»<cite>${esc(quote.author)}, оценка ${quote.score}</cite></blockquote>` : ''}
    </article>
    <aside class="chart" aria-label="Рейтинг сообщества">
      <span class="kicker">Рейтинг сообщества</span>
      <ol class="chart__list">
        ${rest
          .map(
            (game, index) => `<li class="chart__item">
          <span class="chart__rank" aria-hidden="true">${String(index + 2).padStart(2, '0')}</span>
          <div><a class="chart__title" href="#/game/${game.id}">${esc(game.title)}</a>
            <div class="chart__meta mono">${esc([releaseYear(game), reviewsLabel(game.review_count)].filter(Boolean).join(' · '))}</div></div>
          ${score(rating(game))}
        </li>`,
          )
          .join('')}
      </ol>
      <div class="chart__foot"><button class="linkbtn" type="button" data-action="sort-rating">Весь рейтинг ↓</button></div>
    </aside>`;
  lead.hidden = false;
}

// ——— Личный список ———
const isSaved = (game) => (auth.user ? store.saved.has(game.id) : false);
const isSavedSet = () => (auth.user ? store.saved : new Set());

async function loadSavedIds() {
  if (!auth.user) {
    store.saved = new Set();
    return;
  }
  try {
    store.saved = new Set((await api.saved()).map((item) => item.game.id));
  } catch {
    store.saved = new Set();
  }
}

function paintSaveButtons(id, saved) {
  document.querySelectorAll(`[data-save="${id}"]`).forEach((button) => {
    button.setAttribute('aria-pressed', String(saved));
    if (button.classList.contains('save')) button.textContent = saved ? 'В списке' : 'В список';
    else button.textContent = saved ? 'Убрать из списка' : 'Добавить в мой список';
  });
  document.getElementById('saved-count').textContent = store.saved.size || '';
}

async function toggleSave(id) {
  if (!auth.user) {
    // После входа только добавляем: игра могла уже быть в списке этого аккаунта.
    openAuth('login', 'Войдите, чтобы собирать свой список игр.', () => {
      if (!store.saved.has(id)) toggleSave(id);
    });
    return;
  }
  const wasSaved = store.saved.has(id);
  if (wasSaved) store.saved.delete(id);
  else store.saved.add(id);
  paintSaveButtons(id, !wasSaved);
  try {
    if (wasSaved) await api.unsave(id);
    else await api.save(id);
    toast(wasSaved ? 'Игра убрана из списка.' : 'Игра добавлена в ваш список.');
    if (store.screen === 'saved' && wasSaved) showSaved();
  } catch (error) {
    if (wasSaved) store.saved.add(id);
    else store.saved.delete(id);
    paintSaveButtons(id, wasSaved);
    toast(error.message);
  }
}

async function showSaved() {
  enterScreen('saved', 'Мой список');
  window.scrollTo(0, 0);
  if (!auth.user) {
    requireLogin('saved', 'Ваш список.', 'Отмечайте игры, в которые хотите сыграть, — список сохранится в аккаунте и будет доступен с любого устройства.');
    return;
  }
  view.innerHTML = loading();
  const items = await api.saved();
  store.saved = new Set(items.map((item) => item.game.id));
  renderAccount();
  if (!items.length) {
    view.innerHTML = `<div class="section-head"><h2>Мой список</h2></div>
      <div class="state"><h3 class="state__big">Пока пусто.</h3>
      <p>Нажмите «В список» у любой игры в каталоге — она появится здесь.</p><a class="btn" href="#/">Открыть каталог</a></div>`;
    return;
  }
  view.innerHTML = `<div class="section-head"><h2>Мой список</h2><span class="mono">${count(items.length, 'игра', 'игры', 'игр')} · новые сверху</span></div>
    <div class="grid">${items.map((item) => card(item.game, true)).join('')}</div>`;
}

// ——— Страница игры ———
async function showGame(id, params) {
  if (enterScreen(`game:${id}`, 'Игра', 'catalog')) {
    view.innerHTML = loading();
    window.scrollTo(0, 0);
  }
  let game;
  let reviews;
  try {
    [game, reviews] = await Promise.all([api.game(id), api.gameReviews(id)]);
  } catch (error) {
    if (error.status === 404) return showMessage('Не найдено.', 'Такой игры нет в каталоге.', 'catalog');
    throw error;
  }
  document.title = `${game.title} — Критик`;
  const firstGenre = game.genres[0];
  const related = firstGenre
    ? (await api.games(new URLSearchParams({ genre: firstGenre.slug, page_size: '6' }))).results.filter((g) => g.id !== id).slice(0, 5)
    : [];
  renderGame(game, reviews, related, { editing: params.get('edit') === '1' });
}

function verdict(game) {
  const value = rating(game);
  const dist = game.score_distribution || [];
  const max = Math.max(0, ...dist);
  const bars = dist
    .map((n, i) => {
      const height = max ? Math.max((n / max) * 100, 2) : 2;
      return `<div class="bar${n && n === max ? ' bar--peak' : ''}" title="Оценка ${i + 1}: ${count(n, 'голос', 'голоса', 'голосов')}">
        <span class="bar__n">${n || ''}</span><div class="bar__fill" style="height:${height}%"></div><span class="bar__label">${i + 1}</span></div>`;
    })
    .join('');
  return `<div class="verdict">
    <div class="verdict__score${tier(value) === 'top' ? ' verdict__score--top' : ''}">
      <div class="verdict__number${value == null ? ' verdict__number--none' : ''}">${formatScore(value)}</div>
      <div class="verdict__label">${value == null ? 'Нет оценок' : `Оценка сообщества<br>${reviewsLabel(game.review_count)}`}</div>
    </div>
    <div class="bars" role="img" aria-label="Распределение оценок от 1 до 10">${bars}</div>
  </div>`;
}

function reviewItem(review, { own = false, confirming = false } = {}) {
  const actions = own
    ? confirming
      ? `<div class="review__actions"><span class="mono">Удалить рецензию?</span>
          <button class="btn btn--small" type="button" data-action="delete-review" data-id="${review.id}">Да, удалить</button>
          <button class="linkbtn" type="button" data-action="cancel-delete">Отмена</button></div>`
      : `<div class="review__actions"><button class="linkbtn" type="button" data-action="edit-review">Изменить</button>
          <button class="linkbtn linkbtn--danger" type="button" data-action="ask-delete">Удалить</button></div>`
    : '';
  const edited = review.updated_at && review.updated_at.slice(0, 16) !== review.created_at.slice(0, 16);
  return `<article class="review${own ? ' review--own' : ''}" ${own ? 'id="own-review"' : ''}>
    ${score(review.score, { integer: true, size: 'lg' })}
    <div>
      <div class="review__head">
        <span class="review__author">${esc(review.author)}</span>
        ${own ? '<span class="review__badge mono">Ваша рецензия</span>' : ''}
        <span class="review__date mono">${ago(review.created_at)}${edited ? ' · изменено' : ''}</span>
      </div>
      <p class="review__text">${esc(review.text)}</p>
      ${actions}
    </div>
  </article>`;
}

function reviewForm(existing) {
  const current = existing?.score || 0;
  return `<form class="write" id="review-form" novalidate data-id="${existing?.id || ''}">
    <h3 class="write__title">${existing ? 'Изменить рецензию' : 'Ваша рецензия'}</h3>
    <div class="field__label mono"><span>Оценка</span><span id="score-word">${current ? `${current} — ${SCORE_WORDS[current]}` : 'выберите от 1 до 10'}</span></div>
    <div class="picker" role="radiogroup" aria-label="Оценка от 1 до 10">
      ${Array.from({ length: 10 }, (_, i) => i + 1)
        .map((n) => `<button type="button" role="radio" data-score="${n}" aria-checked="${n === current}" class="${n >= 9 ? 'is-top' : ''}" aria-label="${n} — ${SCORE_WORDS[n]}">${n}</button>`)
        .join('')}
    </div>
    <div class="picker__scale mono"><span>1 — провал</span><span>10 — шедевр</span></div>
    <label class="field">
      <span class="field__label mono"><span>Текст рецензии</span><span id="counter">${(existing?.text || '').length} / 500</span></span>
      <textarea class="textarea" name="text" maxlength="500" placeholder="Что зацепило, что раздражало, кому бы вы её посоветовали?">${esc(existing?.text || '')}</textarea>
    </label>
    <p class="error" id="form-error" hidden></p>
    <div class="form-actions">
      <button class="btn" type="submit">${existing ? 'Сохранить' : 'Опубликовать'}</button>
      ${existing ? '<button class="linkbtn" type="button" data-action="cancel-edit">Отмена</button>' : ''}
    </div>
  </form>`;
}

const REVIEW_SORTS = [['new', 'новые'], ['high', 'высокие'], ['low', 'низкие']];

function sortReviews(list) {
  const sorted = list.slice();
  if (store.reviewSort === 'high') sorted.sort((a, b) => b.score - a.score);
  if (store.reviewSort === 'low') sorted.sort((a, b) => a.score - b.score);
  return sorted;
}

function renderGame(game, reviews, related, { editing = false, confirming = false } = {}) {
  store.gamePage = { game, reviews, related };
  const own = reviews.find((review) => review.is_owner);
  const others = sortReviews(reviews.filter((review) => !review.is_owner));
  const saved = isSaved(game);
  const source = game.data_source === 'rawg' && game.source_url
    ? `<a href="${esc(game.source_url)}" target="_blank" rel="noopener">RAWG.io ↗</a>`
    : 'Редакционный каталог';

  let writeSlot = '';
  if (!auth.user) {
    writeSlot = `<div class="prompt"><p>Играли? Поставьте оценку — она сразу попадёт в рейтинг.</p>
      <button class="btn" type="button" data-action="login-to-review">Войти и написать</button></div>`;
  } else if (!own || editing) {
    writeSlot = reviewForm(editing ? own : null);
  }

  const ownBlock = own && !editing ? reviewItem(own, { own: true, confirming }) : '';
  const list = others.map((review) => reviewItem(review)).join('');
  const empty = !own && !others.length
    ? '<div class="state"><p>Рецензий пока нет. Ваша может стать первой.</p></div>'
    : '';

  view.innerHTML = `
    <nav class="crumbs mono" aria-label="Навигация">
      <a href="#/">Каталог</a><span>/</span>
      ${game.genres[0] ? `<a href="#/?genre=${esc(game.genres[0].slug)}">${esc(game.genres[0].name)}</a><span>/</span>` : ''}
      <span>${esc(game.title)}</span>
    </nav>
    <header class="game-head">
      <div>
        <span class="kicker">${esc(names(game.genres)) || 'Игра'}</span>
        <h1 class="game-head__title">${esc(game.title)}</h1>
        <dl class="facts mono">
          <dt>Выход</dt><dd>${esc(releaseDate(game.release_date))}</dd>
          <dt>Платформы</dt><dd>${esc(names(game.platforms)) || '—'}</dd>
          <dt>Жанры</dt><dd>${esc(names(game.genres)) || '—'}</dd>
          <dt>Источник</dt><dd>${source}</dd>
        </dl>
        <div class="game-head__actions">
          <button class="btn${saved ? ' btn--ghost' : ''}" type="button" data-save="${game.id}" aria-pressed="${saved}">${saved ? 'Убрать из списка' : 'Добавить в мой список'}</button>
          ${!own || !auth.user ? '<button class="btn btn--ghost" type="button" data-action="scroll-write">Написать рецензию</button>' : ''}
        </div>
      </div>
      <div>
        ${cover(game)}
        ${verdict(game)}
      </div>
    </header>
    <div class="game-body">
      <div>
        <p class="lede${game.description ? '' : ' lede--empty'}">${esc(game.description || 'Описание игры пока не добавлено.')}</p>
        <div class="section-head" id="reviews-head">
          <h2>Рецензии <span class="mono">${reviews.length || ''}</span></h2>
          ${others.length > 1 ? `<div class="sorts">${REVIEW_SORTS.map(([value, label]) => `<button type="button" data-review-sort="${value}" aria-pressed="${store.reviewSort === value}">${label}</button>`).join('')}</div>` : ''}
        </div>
        <div id="write-slot">${writeSlot}</div>
        <div class="reviews">${ownBlock}${list}${empty}</div>
      </div>
      <aside>
        <div class="aside-note">
          <span class="kicker">Как считается оценка</span>
          <p>Среднее арифметическое оценок пользователей «Критика». Каждый может оставить одну рецензию на игру и в любой момент изменить или удалить её — оценка пересчитается сразу.</p>
        </div>
        ${related.length ? `<div class="aside-note">
          <span class="kicker">Ещё в жанре «${esc(firstGenreName(game))}»</span>
          <ol class="chart__list">${related
            .map(
              (g) => `<li class="chart__item chart__item--plain">
            <div><a class="chart__title" href="#/game/${g.id}">${esc(g.title)}</a><div class="chart__meta mono">${esc(releaseYear(g))}</div></div>${score(rating(g), { size: 'sm' })}</li>`,
            )
            .join('')}</ol>
        </div>` : ''}
      </aside>
    </div>`;

  if (editing) document.querySelector('#review-form textarea')?.focus();
}

const firstGenreName = (game) => game.genres[0]?.name || '';

async function reloadGame(message) {
  const { game } = store.gamePage;
  const [fresh, reviews] = await Promise.all([api.game(game.id), api.gameReviews(game.id)]);
  renderGame(fresh, reviews, store.gamePage.related);
  store.lead = null;
  store.catalog.query = null;
  refreshStats();
  if (message) toast(message);
  document.getElementById('reviews-head')?.scrollIntoView({ block: 'start' });
}

async function submitReview(form) {
  const picked = form.querySelector('[aria-checked="true"]');
  const text = form.text.value.trim();
  const error = form.querySelector('#form-error');
  const fail = (message) => {
    error.textContent = message;
    error.hidden = false;
  };
  if (!picked) return fail('Выберите оценку от 1 до 10.');
  if (text.length < 10) return fail('Напишите хотя бы 10 символов — пара предложений о впечатлениях.');

  const body = { score: Number(picked.dataset.score), text };
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  try {
    if (form.dataset.id) await api.updateReview(form.dataset.id, body);
    else await api.createReview({ ...body, game_id: store.gamePage.game.id });
    const rounded = form.dataset.id ? 'Рецензия обновлена' : 'Рецензия опубликована';
    await reloadGame(`${rounded}. Оценка игры пересчитана.`);
  } catch (err) {
    button.disabled = false;
    fail(err.message);
  }
}

// ——— Мои рецензии ———
async function showMyReviews() {
  enterScreen('reviews', 'Мои рецензии');
  window.scrollTo(0, 0);
  if (!auth.user) {
    requireLogin('reviews', 'Ваши рецензии.', 'Здесь собраны все ваши оценки и тексты — их можно изменить или удалить в любой момент.');
    return;
  }
  view.innerHTML = loading();
  const reviews = await api.myReviews();
  if (!reviews.length) {
    view.innerHTML = `<div class="section-head"><h2>Мои рецензии</h2></div>
      <div class="state"><h3 class="state__big">Ни строчки.</h3><p>Откройте любую игру в каталоге и поставьте ей оценку.</p><a class="btn" href="#/">Открыть каталог</a></div>`;
    return;
  }
  const avg = reviews.reduce((sum, r) => sum + r.score, 0) / reviews.length;
  view.innerHTML = `<div class="section-head"><h2>Мои рецензии</h2>
      <span class="mono">${count(reviews.length, 'рецензия', 'рецензии', 'рецензий')} · ваша средняя оценка ${formatScore(avg)}</span></div>
    <div class="reviews">${reviews
      .map(
        (review) => `<article class="review">
        <a href="#/game/${review.game.id}" tabindex="-1" aria-hidden="true">${score(review.score, { integer: true, size: 'lg' })}</a>
        <div>
          <div class="review__head"><a class="review__game" href="#/game/${review.game.id}">${esc(review.game.title)}</a>
            <span class="review__date mono">${ago(review.created_at)}</span></div>
          <p class="review__text">${esc(review.text)}</p>
          <div class="review__actions"><a class="linkbtn" href="#/game/${review.game.id}?edit=1">Изменить</a>
            <a class="linkbtn" href="#/game/${review.game.id}">Страница игры</a></div>
        </div>
      </article>`,
      )
      .join('')}</div>`;
}

// ——— Вход и регистрация ———
function openAuth(mode, reason = '', after = null) {
  store.pending = after;
  renderAuth(mode, reason);
  if (!dialog.open) dialog.showModal();
  dialog.querySelector('input')?.focus();
}

function authField(name, label, type = 'text', autocomplete = 'off', hint = '') {
  return `<label class="field"><span class="field__label mono"><span>${label}</span><span>${hint}</span></span>
    <input class="input" name="${name}" type="${type}" autocomplete="${autocomplete}"></label>
    <p class="error" data-error-for="${name}" hidden></p>`;
}

function renderAuth(mode, reason) {
  const login = mode === 'login';
  dialog.innerHTML = `<form class="dialog__inner" id="auth-form" data-mode="${mode}" novalidate>
    <div class="dialog__top">
      <div class="dialog__tabs" role="tablist">
        <button type="button" role="tab" data-auth-tab="login" aria-selected="${login}">Вход</button>
        <button type="button" role="tab" data-auth-tab="register" aria-selected="${!login}">Регистрация</button>
      </div>
      <button class="dialog__close" type="button" data-action="close-dialog" aria-label="Закрыть">×</button>
    </div>
    <p class="dialog__hint" id="auth-title">${esc(reason || (login ? 'С возвращением. Ваш список и рецензии ждут.' : 'Аккаунт нужен, чтобы ставить оценки и вести свой список.'))}</p>
    ${authField('username', 'Логин', 'text', 'username', login ? '' : 'латиница, цифры, @.+-_')}
    ${login ? '' : authField('display_name', 'Имя на сайте', 'text', 'nickname', 'необязательно')}
    ${authField('password', 'Пароль', 'password', login ? 'current-password' : 'new-password', login ? '' : 'от 8 символов')}
    ${login ? '' : authField('password_confirm', 'Пароль ещё раз', 'password', 'new-password')}
    <p class="error" data-error-for="detail" hidden></p>
    <button class="btn" type="submit">${login ? 'Войти' : 'Создать аккаунт'}</button>
  </form>`;
}

async function submitAuth(form) {
  form.querySelectorAll('[data-error-for]').forEach((el) => {
    el.hidden = true;
  });
  const data = Object.fromEntries(new FormData(form));
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  try {
    const user = form.dataset.mode === 'login'
      ? await auth.login(data.username, data.password)
      : await auth.register(data);
    const pending = store.pending;
    dialog.close();
    toast(form.dataset.mode === 'login' ? `С возвращением, ${user.public_name}.` : `Аккаунт создан. Добро пожаловать, ${user.public_name}.`);
    await loadSavedIds();
    renderAccount();
    await rerender();
    if (pending) pending();
  } catch (error) {
    button.disabled = false;
    const fields = error.data && typeof error.data === 'object' ? error.data : {};
    let shown = false;
    for (const [name, messages] of Object.entries(fields)) {
      const target = form.querySelector(`[data-error-for="${name}"]`);
      if (target) {
        target.textContent = [].concat(messages).join(' ');
        target.hidden = false;
        shown = true;
      }
    }
    if (!shown) {
      const target = form.querySelector('[data-error-for="detail"]');
      target.textContent = error.message;
      target.hidden = false;
    }
  }
}

async function rerender() {
  const screen = store.screen;
  store.screen = null;
  if (screen === 'catalog') store.catalog.query = null;
  const y = window.scrollY;
  await route();
  window.scrollTo(0, y);
}

// ——— События ———
let searchTimer;
document.addEventListener('input', (event) => {
  if (event.target.id === 'search') {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => goCatalog({ ...currentFilters(), search: event.target.value.trim() }, { replace: true }), 280);
  }
  if (event.target.name === 'text' && event.target.closest('#review-form')) {
    document.getElementById('counter').textContent = `${event.target.value.length} / 500`;
  }
});

document.addEventListener('change', (event) => {
  const target = event.target;
  if (target.dataset.year) goCatalog({ ...currentFilters(), [target.dataset.year]: target.value });
  if (target.id === 'reviewed') goCatalog({ ...currentFilters(), reviewed: target.checked });
});

document.addEventListener('submit', (event) => {
  if (event.target.id === 'review-form') {
    event.preventDefault();
    submitReview(event.target);
  }
  if (event.target.id === 'auth-form') {
    event.preventDefault();
    submitAuth(event.target);
  }
});

document.addEventListener('click', async (event) => {
  const el = event.target.closest('button, a');
  if (!el) return;
  const { dataset } = el;

  if (dataset.save) return toggleSave(Number(dataset.save));

  if (dataset.toggle) {
    const filters = currentFilters();
    const list = filters[dataset.toggle];
    filters[dataset.toggle] = list.includes(dataset.slug) ? list.filter((s) => s !== dataset.slug) : [...list, dataset.slug];
    return goCatalog(filters);
  }
  if (dataset.rating !== undefined) return goCatalog({ ...currentFilters(), rating_min: dataset.rating });
  if (dataset.sort) return goCatalog({ ...currentFilters(), ordering: dataset.sort });
  if (dataset.remove) {
    const f = currentFilters();
    if (dataset.remove === 'genre' || dataset.remove === 'platform') f[dataset.remove] = f[dataset.remove].filter((s) => s !== dataset.slug);
    else if (dataset.remove === 'years') Object.assign(f, { year_from: '', year_to: '' });
    else if (dataset.remove === 'reviewed') f.reviewed = false;
    else f[dataset.remove] = '';
    return goCatalog(f);
  }
  if (dataset.layout) {
    store.layout = dataset.layout;
    writePref('kritik:layout', store.layout);
    document.querySelectorAll('[data-layout]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.layout === store.layout)));
    return renderResults(currentFilters());
  }
  if (dataset.reviewSort) {
    store.reviewSort = dataset.reviewSort;
    const { game, reviews, related } = store.gamePage;
    renderGame(game, reviews, related);
    return document.getElementById('reviews-head')?.scrollIntoView({ block: 'start' });
  }
  if (dataset.score) {
    const picker = el.closest('.picker');
    picker.querySelectorAll('[data-score]').forEach((b) => b.setAttribute('aria-checked', String(b === el)));
    document.getElementById('score-word').textContent = `${dataset.score} — ${SCORE_WORDS[dataset.score]}`;
    return;
  }
  if (dataset.authTab) {
    return renderAuth(dataset.authTab, '');
  }

  switch (dataset.action) {
    case 'login':
    case 'register':
      return openAuth(dataset.action);
    case 'logout':
      await auth.logout();
      toast('Вы вышли из аккаунта.');
      return;
    case 'close-dialog':
      store.pending = null;
      return dialog.close();
    case 'reset':
      return goCatalog({ ...readFilters(new URLSearchParams()), ordering: currentFilters().ordering });
    case 'more':
      el.disabled = true;
      return loadResults(currentFilters(), { append: true });
    case 'more-platforms':
      store.showAllPlatforms = !store.showAllPlatforms;
      return renderIndex(currentFilters());
    case 'sort-rating':
      return document.querySelector('.catalog')?.scrollIntoView({ block: 'start' });
    case 'login-to-review':
      return openAuth('login', 'Войдите, чтобы написать рецензию.', () => document.getElementById('write-slot')?.scrollIntoView({ block: 'center' }));
    case 'scroll-write': {
      if (!auth.user) return openAuth('login', 'Войдите, чтобы написать рецензию.');
      const slot = document.getElementById('write-slot');
      slot.scrollIntoView({ block: 'center' });
      return slot.querySelector('textarea')?.focus({ preventScroll: true });
    }
    case 'edit-review': {
      const { game, reviews, related } = store.gamePage;
      renderGame(game, reviews, related, { editing: true });
      return document.getElementById('write-slot')?.scrollIntoView({ block: 'center' });
    }
    case 'cancel-edit':
    case 'cancel-delete': {
      const { game, reviews, related } = store.gamePage;
      return renderGame(game, reviews, related);
    }
    case 'ask-delete': {
      const { game, reviews, related } = store.gamePage;
      renderGame(game, reviews, related, { confirming: true });
      return document.getElementById('own-review')?.scrollIntoView({ block: 'center' });
    }
    case 'delete-review':
      el.disabled = true;
      try {
        await api.deleteReview(dataset.id);
        await reloadGame('Рецензия удалена. Оценка игры пересчитана.');
      } catch (error) {
        toast(error.message);
      }
      return;
    default:
  }
});

dialog.addEventListener('close', () => {
  store.pending = null;
});

document.addEventListener('keydown', (event) => {
  if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
    const search = document.getElementById('search');
    if (search) {
      event.preventDefault();
      search.focus();
    }
  }
});

window.addEventListener('hashchange', route);

auth.onChange(async () => {
  renderAccount();
  if (!auth.user && store.screen) {
    store.saved = new Set();
    await rerender();
  }
});

// ——— Запуск ———
async function start() {
  installCoverFallback(document);
  document.getElementById('issue-line').textContent = `${today()} · оценки видеоигр от игроков`;
  renderAccount();
  view.innerHTML = loading();
  refreshStats();
  await auth.restore();
  await loadSavedIds();
  renderAccount();
  await route();
}

start();
