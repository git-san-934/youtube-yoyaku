// チャンネル管理 — data/channels.json を GitHub API 経由で編集する
// トークンはこの端末の localStorage にのみ保存する

const REPO = 'git-san-934/youtube-yoyaku'
const FILE = 'data/channels.json'
const TOKEN_KEY = 'yy-gh-token'
const API = 'https://api.github.com'

const state = {
  token: '',
  list: [], // channels.json の中身（配列）
  sha: '', // 取得した channels.json の blob SHA
  busy: false,
}

const els = {
  setup: document.getElementById('setup'),
  manager: document.getElementById('manager'),
  error: document.getElementById('error'),
  tokenForm: document.getElementById('token-form'),
  tokenInput: document.getElementById('token-input'),
  tokenSave: document.getElementById('token-save'),
  setupMsg: document.getElementById('setup-msg'),
  addForm: document.getElementById('add-form'),
  addInput: document.getElementById('add-input'),
  addBtn: document.getElementById('add-btn'),
  msg: document.getElementById('msg'),
  list: document.getElementById('channel-list'),
  reload: document.getElementById('reload'),
  forget: document.getElementById('forget'),
}

// --- localStorage（使えなくても動く） -------------------------------------
function loadToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}
function saveToken(v) {
  try {
    localStorage.setItem(TOKEN_KEY, v)
  } catch {
    /* 保存できなくてもこのセッションでは使える */
  }
}
function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* no-op */
  }
}

// --- base64（UTF-8） ------------------------------------------------------
function encodeBase64(text) {
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin)
}
function decodeBase64(b64) {
  const bin = atob(b64.replace(/\s/g, ''))
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

// --- GitHub API --------------------------------------------------------
async function gh(path, options = {}) {
  const res = await fetch(API + path, {
    ...options,
    headers: {
      Authorization: `Bearer ${state.token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  return res
}

function apiErrorMessage(status) {
  if (status === 401) return 'トークンが使えません（無効か期限切れ）。設定し直してください。'
  if (status === 403) return '権限が足りません。トークンの「Contents: Read and write」を確認してください。'
  if (status === 404) return 'ファイルが見つかりません。リポジトリの指定を確認してください。'
  return `保存できませんでした（エラー ${status}）。`
}

// --- 入力の解析 --------------------------------------------------------
// 返り値: { handle: '@name' } / { channel_id: 'UC…' } / null
function parseInput(raw) {
  let s = (raw || '').trim()
  if (!s) return null
  s = s.replace(/^https?:\/\//i, '').replace(/^www\./i, '')

  // チャンネルIDのURL
  let m = s.match(/^(?:m\.|music\.)?youtube\.com\/channel\/(UC[0-9A-Za-z_-]{20,})/i)
  if (m) return { channel_id: m[1] }

  // ハンドルのURL
  m = s.match(/^(?:m\.|music\.)?youtube\.com\/@([^/?#\s]+)/i)
  if (m) return { handle: '@' + decodeURIComponent(m[1]) }

  // youtube.com のその他の形（/c/ や /user/ は handle と一致しないので受け付けない）
  if (/youtube\.com/i.test(s)) return null

  // @name / name
  m = s.match(/^@?([^/?#\s@]+)$/)
  if (m) return { handle: '@' + m[1] }

  return null
}

function entryLabel(e) {
  return e.name || e.handle || e.channel_id || '(不明)'
}

function isDuplicate(parsed) {
  return state.list.some((e) => {
    if (parsed.channel_id && e.channel_id) return e.channel_id === parsed.channel_id
    if (parsed.handle && e.handle) {
      return e.handle.toLowerCase() === parsed.handle.toLowerCase()
    }
    return false
  })
}

// --- 描画 -------------------------------------------------------------
function setMsg(text, kind) {
  els.msg.textContent = text || ''
  els.msg.className = 'msg' + (kind ? ` is-${kind}` : '')
}
function setSetupMsg(text, kind) {
  els.setupMsg.textContent = text || ''
  els.setupMsg.className = 'msg' + (kind ? ` is-${kind}` : '')
}

function showSetup() {
  els.setup.hidden = false
  els.manager.hidden = true
}
function showManager() {
  els.setup.hidden = true
  els.manager.hidden = false
}

function renderList() {
  els.list.replaceChildren()
  if (state.list.length === 0) {
    const p = document.createElement('p')
    p.className = 'empty-note'
    p.textContent = '登録チャンネルがありません。上の欄から追加してください。'
    els.list.appendChild(p)
    return
  }

  state.list.forEach((entry, i) => {
    const row = document.createElement('div')
    row.className = 'ch'

    const main = document.createElement('div')
    main.className = 'ch__main'

    const name = document.createElement('div')
    name.className = 'ch__name'
    name.textContent = entryLabel(entry)
    if (!entry.channel_id) {
      const badge = document.createElement('span')
      badge.className = 'ch__pending'
      badge.textContent = '変換待ち'
      name.appendChild(badge)
    }
    main.appendChild(name)

    const handle = document.createElement('div')
    handle.className = 'ch__handle'
    handle.textContent = entry.handle || entry.channel_id || ''
    main.appendChild(handle)

    row.appendChild(main)
    row.appendChild(delControl(entry, i))
    els.list.appendChild(row)
  })
}

// 「削除」→「削除しますか？ 削除／やめる」
function delControl(entry, i) {
  const wrap = document.createElement('div')
  wrap.className = 'ch__del-wrap'

  const showButton = () => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'ch__del'
    btn.textContent = '削除'
    btn.addEventListener('click', showConfirm)
    wrap.replaceChildren(btn)
  }
  const showConfirm = () => {
    const box = document.createElement('div')
    box.className = 'ch__confirm'
    const label = document.createElement('span')
    label.className = 'ch__confirm-label'
    label.textContent = '削除しますか？'
    const yes = document.createElement('button')
    yes.type = 'button'
    yes.className = 'ch__confirm-yes'
    yes.textContent = '削除'
    yes.addEventListener('click', () => removeAt(i, entry))
    const no = document.createElement('button')
    no.type = 'button'
    no.className = 'ch__confirm-no'
    no.textContent = 'やめる'
    no.addEventListener('click', showButton)
    box.append(label, yes, no)
    wrap.replaceChildren(box)
  }
  showButton()
  return wrap
}

// --- データ取得・保存 --------------------------------------------------
async function fetchList() {
  const res = await gh(`/repos/${REPO}/contents/${FILE}?ref=main`)
  if (!res.ok) {
    if (res.status === 401) {
      setMsg(apiErrorMessage(401), 'error')
      state.token = ''
      clearToken()
      showSetup()
      return false
    }
    setMsg(apiErrorMessage(res.status), 'error')
    return false
  }
  const data = await res.json()
  let parsed
  try {
    parsed = JSON.parse(decodeBase64(data.content))
  } catch {
    setMsg('channels.json を読み取れませんでした。', 'error')
    return false
  }
  state.list = Array.isArray(parsed) ? parsed : []
  state.sha = data.sha
  return true
}

// list を channels.json のフォーマットで書き戻す
async function save(summary) {
  if (state.busy) return
  state.busy = true
  setBusy(true)
  setMsg('保存しています…')

  const body = (retrySha) =>
    JSON.stringify({
      message: `chore: チャンネル変更 (${summary})`,
      content: encodeBase64(JSON.stringify(state.list, null, 2) + '\n'),
      sha: retrySha ?? state.sha,
      branch: 'main',
    })

  try {
    let res = await gh(`/repos/${REPO}/contents/${FILE}`, { method: 'PUT', body: body() })

    if (res.status === 409) {
      // 取得後に Actions などがコミットした。最新を取り直して 1 回だけやり直す
      const fresh = await gh(`/repos/${REPO}/contents/${FILE}?ref=main`)
      if (fresh.ok) {
        const d = await fresh.json()
        res = await gh(`/repos/${REPO}/contents/${FILE}`, { method: 'PUT', body: body(d.sha) })
      }
    }

    if (!res.ok) {
      setMsg(apiErrorMessage(res.status), 'error')
      return
    }
    const out = await res.json()
    state.sha = out.content?.sha || state.sha
    renderList()
    setMsg(
      summary.startsWith('追加')
        ? '追加しました。1〜2分後に正式なチャンネルIDへ変換され、次回の更新から要約対象になります。'
        : '保存しました。反映まで1〜2分ほどかかることがあります。',
      'ok',
    )
  } catch {
    setMsg('保存できませんでした。通信状況を確認して、もう一度お試しください。', 'error')
    await fetchList().then(renderList)
  } finally {
    state.busy = false
    setBusy(false)
  }
}

function setBusy(b) {
  els.addBtn.disabled = b
  els.reload.disabled = b
  for (const btn of els.list.querySelectorAll('button')) btn.disabled = b
}

async function addChannel(rawValue) {
  const parsed = parseInput(rawValue)
  if (!parsed) {
    setMsg('チャンネルのURL または @名 を入力してください。', 'error')
    return
  }
  if (isDuplicate(parsed)) {
    setMsg('そのチャンネルはすでに登録されています。', 'error')
    return
  }
  state.list.push(parsed)
  els.addInput.value = ''
  await save('追加: ' + (parsed.handle || parsed.channel_id))
}

async function removeAt(i, entry) {
  if (state.list[i] !== entry) {
    // 一覧が変わっている可能性。取り直してからにする
    setMsg('一覧が更新されました。もう一度お試しください。', 'error')
    if (await fetchList()) renderList()
    return
  }
  state.list.splice(i, 1)
  await save('削除: ' + (entry.handle || entry.channel_id || entryLabel(entry)))
}

// --- トークン設定 ----------------------------------------------------
async function verifyAndSaveToken(value) {
  const token = value.trim()
  if (!token) {
    setSetupMsg('トークンを貼り付けてください。', 'error')
    return
  }
  els.tokenSave.disabled = true
  setSetupMsg('確認しています…')
  state.token = token
  try {
    const res = await gh(`/repos/${REPO}`)
    if (!res.ok) {
      state.token = ''
      setSetupMsg(
        res.status === 401
          ? 'トークンが使えません。コピーし直すか、作成手順を見直してください。'
          : `確認に失敗しました（エラー ${res.status}）。`,
        'error',
      )
      return
    }
    saveToken(token)
    setSetupMsg('')
    showManager()
    setMsg('読み込んでいます…')
    if (await fetchList()) {
      renderList()
      setMsg('')
    }
  } catch {
    state.token = ''
    setSetupMsg('通信できませんでした。時間をおいてお試しください。', 'error')
  } finally {
    els.tokenSave.disabled = false
  }
}

// --- 初期化 --------------------------------------------------------
function setupControls() {
  els.tokenForm.addEventListener('submit', (e) => {
    e.preventDefault()
    verifyAndSaveToken(els.tokenInput.value)
  })
  els.addForm.addEventListener('submit', (e) => {
    e.preventDefault()
    addChannel(els.addInput.value)
  })
  els.reload.addEventListener('click', async () => {
    setMsg('更新しています…')
    if (await fetchList()) {
      renderList()
      setMsg('最新の状態にしました。', 'ok')
    }
  })
  els.forget.addEventListener('click', () => {
    clearToken()
    state.token = ''
    state.list = []
    state.sha = ''
    els.tokenInput.value = ''
    setSetupMsg('トークンを削除しました。', 'ok')
    showSetup()
  })
}

async function main() {
  setupControls()
  state.token = loadToken()
  if (!state.token) {
    showSetup()
    return
  }
  showManager()
  setMsg('読み込んでいます…')
  try {
    if (await fetchList()) {
      renderList()
      setMsg('')
    }
  } catch {
    els.error.hidden = false
  }
}

main()
