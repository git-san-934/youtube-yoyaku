// ユーチューブ要約 — data/summaries.json を読み込んでカード一覧を描画する

const STORAGE_KEY = 'yy-channel-filter'
const HIDDEN_KEY = 'yy-hidden'
const JST_OFFSET_MIN = 9 * 60

const state = {
  items: [],
  channel: '',
  hidden: new Set(), // 「消す」で非表示にした video_id（この端末のみ）
}

const els = {
  updated: document.getElementById('updated'),
  select: document.getElementById('channel-select'),
  list: document.getElementById('list'),
  empty: document.getElementById('empty'),
  error: document.getElementById('error'),
}

async function loadData() {
  const res = await fetch(`data/summaries.json?ts=${Date.now()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

function pad(n) {
  return String(n).padStart(2, '0')
}

// UTC の Date を JST の年月日時分に変換
function toJstParts(date) {
  const shifted = new Date(date.getTime() + JST_OFFSET_MIN * 60000)
  return {
    y: shifted.getUTCFullYear(),
    mo: shifted.getUTCMonth() + 1,
    d: shifted.getUTCDate(),
    h: shifted.getUTCHours(),
    mi: shifted.getUTCMinutes(),
  }
}

function formatWhen(iso) {
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  const diffMs = Date.now() - dt.getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'たった今'
  if (min < 60) return `${min}分前`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours}時間前`
  const p = toJstParts(dt)
  return `${p.mo}/${p.d}`
}

function formatUpdated(iso) {
  if (!iso) return 'データ取得前'
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return ''
  const p = toJstParts(dt)
  return `最終更新 ${p.y}/${p.mo}/${p.d} ${pad(p.h)}:${pad(p.mi)}`
}

function renderFilter() {
  const names = [...new Set(state.items.map((it) => it.channel).filter(Boolean))]
  names.sort((a, b) => a.localeCompare(b, 'ja'))
  for (const name of names) {
    const opt = document.createElement('option')
    opt.value = name
    opt.textContent = name
    els.select.appendChild(opt)
  }
  const saved = safeGet()
  if (saved && names.includes(saved)) {
    state.channel = saved
    els.select.value = saved
  }
}

// カード右上の「消す」ボタン。押すと「消す／やめる」の確認に差し替わる。
function delControl(cardEl, item) {
  const wrap = document.createElement('div')
  wrap.className = 'card__del-wrap'

  const showButton = () => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'card__del'
    btn.textContent = '消す'
    btn.setAttribute('aria-label', 'この要約を消す')
    btn.addEventListener('click', showConfirm)
    wrap.replaceChildren(btn)
  }

  const showConfirm = () => {
    const box = document.createElement('div')
    box.className = 'card__confirm'

    const label = document.createElement('span')
    label.className = 'card__confirm-label'
    label.textContent = '消しますか？'

    const yes = document.createElement('button')
    yes.type = 'button'
    yes.className = 'card__confirm-yes'
    yes.textContent = '消す'
    yes.addEventListener('click', () => {
      cardEl.classList.add('is-removing')
      setTimeout(() => hideItem(item.video_id), 200)
    })

    const no = document.createElement('button')
    no.type = 'button'
    no.className = 'card__confirm-no'
    no.textContent = 'やめる'
    no.addEventListener('click', showButton)

    box.append(label, yes, no)
    wrap.replaceChildren(box)
  }

  showButton()
  return wrap
}

function card(item) {
  const el = document.createElement('article')
  el.className = 'card'

  const img = document.createElement('img')
  img.className = 'card__thumb'
  img.src = item.thumbnail || `https://i.ytimg.com/vi/${item.video_id}/hqdefault.jpg`
  img.alt = item.title || ''
  img.loading = 'lazy'
  img.referrerPolicy = 'no-referrer'
  el.appendChild(img)

  const body = document.createElement('div')
  body.className = 'card__body'

  body.appendChild(delControl(el, item))

  const a = document.createElement('a')
  a.className = 'card__title'
  a.href = item.url
  a.target = '_blank'
  a.rel = 'noopener'
  a.textContent = item.title || '(無題)'
  body.appendChild(a)

  const meta = document.createElement('p')
  meta.className = 'card__meta'
  const chan = document.createElement('span')
  chan.textContent = item.channel || ''
  const dot = document.createElement('span')
  dot.className = 'dot'
  dot.textContent = '・'
  const when = document.createElement('span')
  when.textContent = formatWhen(item.published_at)
  meta.append(chan, dot, when)
  body.appendChild(meta)

  const summary = document.createElement('p')
  summary.className = 'card__summary'
  if (item.status === 'ok' && item.summary) {
    summary.textContent = item.summary
  } else {
    summary.classList.add('is-pending')
    summary.textContent = '要約準備中'
  }
  body.appendChild(summary)

  el.appendChild(body)
  return el
}

function render() {
  const unread = state.items.filter((it) => !state.hidden.has(it.video_id))
  const items = state.channel
    ? unread.filter((it) => it.channel === state.channel)
    : unread
  const sorted = [...items].sort((a, b) =>
    (b.published_at || '').localeCompare(a.published_at || ''),
  )

  els.list.replaceChildren(...sorted.map(card))
  els.empty.hidden = sorted.length > 0
}

function safeGet() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function safeSet(value) {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* localStorage 不可でも動作は継続 */
  }
}

function loadHidden() {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(arr) ? arr.filter((v) => typeof v === 'string') : [])
  } catch {
    return new Set()
  }
}

function saveHidden() {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...state.hidden]))
  } catch {
    /* localStorage 不可でも動作は継続（再読み込みで元に戻るだけ） */
  }
}

// summaries.json に今ある動画IDだけを残し、古いIDが溜まり続けないようにする
function pruneHidden(validIds) {
  let changed = false
  for (const id of state.hidden) {
    if (!validIds.has(id)) {
      state.hidden.delete(id)
      changed = true
    }
  }
  if (changed) saveHidden()
}

function hideItem(videoId) {
  state.hidden.add(videoId)
  saveHidden()
  render()
}

function setupControls() {
  els.select.addEventListener('change', () => {
    state.channel = els.select.value
    safeSet(state.channel)
    render()
  })
}

async function main() {
  setupControls()
  state.hidden = loadHidden()
  try {
    const data = await loadData()
    state.items = Array.isArray(data.items) ? data.items : []
    pruneHidden(new Set(state.items.map((it) => it.video_id)))
    els.updated.textContent = formatUpdated(data.updated_at)
    renderFilter()
    render()
  } catch (err) {
    console.error(err)
    els.updated.textContent = ''
    els.error.hidden = false
  }
}

main()
