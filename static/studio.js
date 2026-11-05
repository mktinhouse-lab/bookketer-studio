// 북케터밈 카드뉴스 스튜디오 — 단계형 화면 (지금은 0단계 학습)
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = v => v == null ? '–' : Number(v).toLocaleString('ko-KR');

async function api(path, body, method) {
  const r = await fetch(path, body === undefined && !method ? {} : {
    method: method || 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body ?? {})});
  let d = null;
  try { d = await r.json(); } catch (_) {}
  if (!r.ok) {
    const det = d && d.detail; const msg = Array.isArray(det) ? det.map(x => x.msg || JSON.stringify(x)).join(', ') : det;
    const e = new Error(msg || `요청 실패 (${r.status})`); e.status = r.status; throw e;
  }
  return d;
}
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('on'), 3200);
}

// ---------------- 단계 표시 ----------------
const STEPS = ['', '레퍼런스', '썸네일 카피', '책 추천', '카드 완성'];
function drawSteps(active = 0, reached = 0, wid = '') {
  $('#steps').hidden = !wid;  // 작업을 열었을 때만 단계 표시
  $('#steps').innerHTML = STEPS.map((s, i) => !i ? '' :
    `<button data-step="${i}" class="${i === active ? 'on' : ''}" ${wid && i <= reached ? '' : 'disabled'}><b>${i}</b>${s}</button>`).join('');
  document.querySelectorAll('#steps button[data-step]').forEach(b => b.onclick = () => { location.hash = `#/w/${wid}/${b.dataset.step}`; });
}

// ---------------- 작은 마크다운 표시 ----------------
function inline(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(text) {
  const lines = text.split('\n'); const out = []; let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith('```')) { const buf = []; i++; while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++]); i++; out.push(`<pre>${esc(buf.join('\n'))}</pre>`); continue; }
    if (/^<!--.*-->$/.test(l.trim())) { i++; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)/); if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
    if (l.trim().startsWith('|')) {
      const rows = []; while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      const cells = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const body = rows.filter(r => !/^\|?\s*:?-{2,}/.test(r.trim().replace(/^\|/, '')));
      out.push('<table>' + body.map((r, k) => `<tr>${cells(r).map(c => k ? `<td>${inline(c)}</td>` : `<th>${inline(c)}</th>`).join('')}</tr>`).join('') + '</table>');
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      const ordered = /^\s*\d+\./.test(l); const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ''));
      out.push(`<${ordered ? 'ol' : 'ul'}>${items.map(x => `<li>${inline(x)}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`); continue;
    }
    if (l.startsWith('>')) { const buf = []; while (i < lines.length && lines[i].startsWith('>')) buf.push(inline(lines[i++].replace(/^>\s?/, ''))); out.push(`<blockquote>${buf.join('<br>')}</blockquote>`); continue; }
    if (!l.trim()) { i++; continue; }
    const buf = []; while (i < lines.length && lines[i].trim() && !/^(#|\||>|```|\s*([-*]|\d+\.)\s)/.test(lines[i])) buf.push(inline(lines[i++]));
    out.push(`<p>${buf.join('<br>')}</p>`);
  }
  return out.join('');
}

// ---------------- 연결 ----------------
let O = null;
function drawConn(o, claude) {
  const set = (id, ok, text) => { $(id).classList.toggle('ok', !!ok); $(id + '-t').innerHTML = text; };
  if (claude) set('#c-claude', claude.logged_in, claude.logged_in ? `로그인됨 ${esc(claude.email || '')}` : '로그인이 필요합니다. 버튼을 누르면 로그인 페이지가 열리고, 받은 코드를 여기에 붙여 넣으면 끝나요.');
  if (claude && !claude.logged_in && !$('#i-code')) {
    // 로그인 페이지에서 받은 코드를 언제든 넣을 수 있게(버튼을 다시 누르면 로그인이 처음부터 시작돼 코드가 무효가 됨)
    $('#b-claude').insertAdjacentHTML('afterend', ' <input type="text" id="i-code" placeholder="받은 코드 붙여넣기"><button class="btn sm pri" id="b-code">확인</button>');
    $('#b-code').onclick = async () => {
      const b = $('#b-code'); b.disabled = true; b.textContent = '확인 중…';
      try { const s = await api('/api/claude/code', {code: $('#i-code').value}); toast(`Claude 로그인됨 ${s.email || ''}`); refresh(true); }
      catch (e) { toast(e.message); }
      finally { b.disabled = false; b.textContent = '확인'; }
    };
  }
  const pills = [['Claude', claude?.logged_in]];
  $('#pills').innerHTML = pills.map(([n, ok]) => `<span class="pill ${ok ? 'ok' : ''}"><i></i>${n}</span>`).join('');
}

$('#b-claude').onclick = async () => {
  try {
    const r = await api('/api/claude/login', {});
    $('#c-claude-t').innerHTML = `① <a href="${esc(r.url)}" target="_blank" rel="noopener"><b>로그인 페이지 열기</b></a> → 구독 계정으로 로그인<br>② 마지막 화면에 나온 코드를 복사해 아래에 붙여 넣기`;
    $('#b-claude').parentElement.innerHTML = '<input type="text" id="i-code" placeholder="코드 붙여넣기"><button class="btn sm pri" id="b-code">확인</button>';
    $('#b-code').onclick = async () => {
      try { const s = await api('/api/claude/code', {code: $('#i-code').value}); toast(`Claude 로그인됨 ${s.email || ''}`); refresh(true); }
      catch (e) { toast(e.message); }
    };
  } catch (e) { toast(e.message); }
};
// ---------------- 현황 · 작업 ----------------
function drawStats(o) {
  const sk = Object.entries(o.skipped || {}).map(([k, v]) => `${k} ${v}`).join(' · ');
  const box = (n, label) => `<div class="stat"><b>${n}</b><span>${label}</span></div>`;
  $('#stats').innerHTML = [
    box(num(o.total), `캐러셀 수집${o.feed_total ? ` (전체 게시물 ${num(o.feed_total)})` : ''}${o.index_done ? '' : ' · 목록 수집 중'}`),
    box(`${num(o.with_images)}`, '이미지 저장'),
    box(`${num(o.analyzed)}<small style="font-size:14px;color:var(--mut)"> / ${num(o.total)}</small>`, 'AI 분석 완료'),
    box(num(o.with_insights), '인사이트 있음'),
    box(num(o.books), '사용한 책'),
  ].join('');
  $('#folder').innerHTML = `${sk ? `제외: ${esc(sk)} · ` : ''}저장 위치 <code>${esc(o.folder)}</code>${o.last_collect ? ` · 마지막 수집 ${esc(o.last_collect)} (${esc(o.last_source || '')})` : ''}`;
}

let watching = null;
async function watchJob(id, quiet) {
  watching = id;
  $('#jobbox').hidden = false; $('#b-stop').hidden = false;
  $('#b-stop').onclick = async () => { await api(`/api/jobs/${id}/stop`, {}); toast('지금 하던 게시물까지 저장하고 멈춥니다'); };
  setRunning(true);
  while (watching === id) {
    let j;
    try { j = await api(`/api/jobs/${id}`); } catch (_) { break; }
    $('#job-label').textContent = j.label + (j.progress?.label ? ` — ${j.progress.label}` : '');
    const m = Math.floor(j.elapsed / 60), s = j.elapsed % 60;
    $('#job-time').textContent = `${m}분 ${s}초 경과` + (j.progress?.pct ? ` · ${j.progress.pct}%` : '');
    $('#job-bar').style.width = (j.status === 'done' ? 100 : j.progress?.pct || 2) + '%';
    const log = $('#job-log'); const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
    log.textContent = j.log.slice(-80).join('\n'); if (atBottom) log.scrollTop = log.scrollHeight;
    if (j.status !== 'running') {
      setRunning(false); $('#b-stop').hidden = true;
      if (!quiet || j.status !== 'done') toast(j.status === 'done' ? `${j.label} 완료` : j.status === 'stopped' ? '멈췄습니다. [이어서]로 계속할 수 있어요' : `오류: ${j.error}`);
      watching = null; refresh(true); break;
    }
    if (Math.random() < .25) refresh();
    await new Promise(r => setTimeout(r, 1500));
  }
}
function setRunning(on) {
  for (const b of ['#b-run', '#b-update', ...[...document.querySelectorAll('[data-act]')].map(x => x)]) {
    const el = typeof b === 'string' ? $(b) : b; el.disabled = on;
  }
}
async function startLearn(path, body) {
  try { const r = await api(path, body || {}); watchJob(r.job); } catch (e) { toast(e.message); }
}
$('#b-run').onclick = () => startLearn('/api/learn/run', {update: false});
$('#b-update').onclick = () => startLearn('/api/learn/run', {update: true});
document.querySelectorAll('[data-act]').forEach(b => b.onclick = () => startLearn('/api/learn/' + b.dataset.act, {}));

// ---------------- 스타일 가이드 ----------------
let G = {name: null, text: ''};
async function drawGuides(o) {
  const sel = $('#g-sel'); const cur = sel.value;
  if (!o.guides.length) { sel.innerHTML = '<option>가이드 없음</option>'; sel.disabled = true; $('#g-applied').innerHTML = ''; return; }
  sel.disabled = false;
  sel.innerHTML = o.guides.map(n => `<option value="${esc(n)}">${esc(n.replace('스타일가이드_', '').replace('.md', ''))}${n === o.applied ? ' · 적용 중' : ''}</option>`).join('');
  const pick = o.guides.includes(cur) ? cur : o.applied || o.guides[0];
  sel.value = pick;
  if (G.name !== pick && $('#g-text').hidden) await loadGuide(pick);
  $('#g-applied').innerHTML = pick === o.applied ? '<span class="tag">적용 중</span>' : '<span class="tag gray">미적용</span>';
}
async function loadGuide(name) {
  const g = await api(`/api/learn/guide/${encodeURIComponent(name)}`);
  G = {name, text: g.text};
  $('#g-view').innerHTML = md(g.text);
}
$('#g-sel').onchange = async () => { await loadGuide($('#g-sel').value); $('#g-applied').innerHTML = $('#g-sel').value === O.applied ? '<span class="tag">적용 중</span>' : '<span class="tag gray">미적용</span>'; };
function editMode(on) {
  $('#g-text').hidden = !on; $('#g-view').hidden = on; $('#g-save').hidden = !on; $('#g-cancel').hidden = !on; $('#g-edit').hidden = on;
  if (on) $('#g-text').value = G.text;
}
$('#g-edit').onclick = () => G.name && editMode(true);
$('#g-cancel').onclick = () => editMode(false);
$('#g-save').onclick = async () => {
  const r = await api('/api/learn/guide/save', {base: G.name, text: $('#g-text').value});
  editMode(false); toast(`새 버전으로 저장: ${r.name}`); await refresh(); $('#g-sel').value = r.name; await loadGuide(r.name);
};
$('#g-pin').onclick = async () => { await api('/api/learn/guide/pin', {name: $('#g-sel').value}); toast('이 버전을 고정 적용합니다'); refresh(); };
$('#g-unpin').onclick = async () => { await api('/api/learn/guide/pin', {name: null}); toast('항상 최신 버전을 적용합니다'); refresh(); };

// ---------------- 게시물 ----------------
let P = [];
async function loadPosts() {
  P = await api('/api/learn/posts');
  const kinds = [...new Set(P.map(p => p.kind).filter(Boolean))];
  const ks = $('#p-kind'); const cur = ks.value;
  ks.innerHTML = '<option value="">모든 종류</option>' + kinds.map(k => `<option>${esc(k)}</option>`).join(''); ks.value = cur;
  drawPosts();
}
function drawPosts() {
  const q = $('#p-q').value.trim(); const kind = $('#p-kind').value; const sort = $('#p-sort').value;
  let list = P.filter(p => (!kind || p.kind === kind) && (!q || (p.copy + ' ' + p.books.join(' ')).includes(q)));
  const key = {likes: p => p.likes || 0, saved: p => p.insights.saved || 0, shares: p => p.insights.shares || 0}[sort];
  if (key) list = [...list].sort((a, b) => key(b) - key(a));
  $('#p-count').textContent = `${list.length}개`;
  $('#posts').innerHTML = list.length ? list.map(p => `<button class="pc" data-code="${esc(p.code)}">
    ${p.thumb ? `<img loading="lazy" src="/api/learn/img/${encodeURIComponent(p.folder)}/${p.thumb}" alt="">` : '<img alt="">'}
    <div><div class="c">${esc(p.copy || (p.analyzed ? '' : '분석 전'))}</div>
    <div class="m">${esc(p.date)} · ♥${num(p.likes)} 💬${num(p.comments)}${p.insights.saved != null ? ` · 저장 ${num(p.insights.saved)}` : ''}${p.insights.shares != null ? ` · 공유 ${num(p.insights.shares)}` : ''}</div>
    <div class="m">${esc(p.kind || '')}${p.books.length ? ` · 책 ${p.books.length}권` : ''}</div></div></button>`).join('')
    : '<div class="empty">아직 수집한 게시물이 없습니다.</div>';
  document.querySelectorAll('.pc').forEach(b => b.onclick = () => openPost(b.dataset.code));
}
$('#p-q').oninput = drawPosts; $('#p-sort').onchange = drawPosts; $('#p-kind').onchange = drawPosts;

async function openPost(code) {
  const d = await api(`/api/learn/post/${code}`);
  const p = d.post, a = d.analysis, ins = p.insights || {};
  $('#dlg-t').innerHTML = `${esc(p.date)} · <a href="${esc(p.url)}" target="_blank" rel="noopener">게시물 열기</a>`;
  let h = `<div class="strip">${d.images.map(n => `<img src="/api/learn/img/${encodeURIComponent(d.folder)}/${n}" alt="">`).join('')}</div>
    <p class="hint">좋아요 ${num(p.likes)} · 댓글 ${num(p.comments)} · 장 ${p.slides}${Object.keys(ins).length ? ` · 저장 ${num(ins.saved)} · 공유 ${num(ins.shares)} · 도달 ${num(ins.reach)} · 조회 ${num(ins.views)}` : ' · 인사이트 없음'}</p>`;
  if (a) {
    h += `<h3>썸네일 카피 <span class="tag gray">${esc(a.post_kind)}</span></h3>` + a.thumbnail.copy_lines.map(x => `<div>(${esc(x.color)}) <b>${esc(x.text)}</b></div>`).join('');
    if (a.books.length) h += '<h3>소개한 책</h3>' + a.books.map(b => `<div style="margin-bottom:12px"><b>${b.slide}p · ${esc(b.title)}</b> ${esc(b.author)} <span class="hint">${esc(b.hashtags.join(' '))}</span>
      <blockquote style="margin:4px 0;padding:4px 12px;border-left:3px solid var(--mint)">${b.description_lines.map(x => `${esc(x.text)} <span class="hint">(${esc(x.color)})</span>`).join('<br>')}</blockquote>
      <span class="hint">${b.count?.chars}자 (공백 제외 ${b.count?.chars_no_space}) · ${b.count?.lines}줄</span></div>`).join('');
    h += `<h3>장 구성</h3><ol>${a.slides.map(s => `<li>[${esc(s.role)}] ${esc(s.text).replace(/\n/g, ' / ')}</li>`).join('')}</ol>`;
    if (a.notes) h += `<p class="hint">확인 필요: ${esc(a.notes)}</p>`;
    h += `<div class="row"><button class="btn sm" id="re-an">이 게시물 다시 분석</button></div>`;
  } else h += '<div class="empty">아직 분석 전입니다.</div>';
  h += `<h3>캡션</h3><div style="white-space:pre-wrap;font-size:13.5px">${esc(p.caption)}</div>`;
  $('#dlg-b').innerHTML = h; $('#dlg').showModal();
  const re = $('#re-an'); if (re) re.onclick = () => { $('#dlg').close(); startLearn('/api/learn/analyze', {codes: [code], redo: true}); };
}
$('#dlg-x').onclick = () => $('#dlg').close();

// ---------------- 책 DB ----------------
let B = {};
async function loadBooks() { B = (await api('/api/learn/books')).books || {}; drawBooks(); }
function drawBooks() {
  const q = $('#b-q').value.trim();
  const rows = Object.values(B).filter(b => !q || (b.title + ' ' + (b.author || '')).includes(q))
    .sort((a, b) => (b.last_used || '').localeCompare(a.last_used || ''));
  $('#b-count').textContent = `${rows.length}권`;
  $('#books').innerHTML = rows.length ? `<table class="books"><tr><th>책 제목</th><th>저자</th><th>횟수</th><th>마지막 소개</th><th>게시물</th></tr>${rows.map(b => `<tr><td><b>${esc(b.title)}</b></td><td>${esc(b.author || '')}</td><td>${b.times}</td><td>${esc(b.last_used || '')}</td>
    <td>${b.posts.map(x => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.date)}</a>`).join(' ')}</td></tr>`).join('')}</table>`
    : '<div class="empty">분석이 끝나면 소개했던 책이 여기에 쌓입니다.</div>';
}
$('#b-q').oninput = drawBooks;

// ---------------- 새로고침 ----------------
let claudeChecked = null;
async function refresh(full) {
  O = await api('/api/learn');
  if (full || !claudeChecked) claudeChecked = (await api('/api/status')).claude;
  drawConn(O, claudeChecked); drawStats(O); await drawGuides(O);
  if (full || !P.length || Math.random() < .5) { await loadPosts(); await loadBooks(); }
  if (O.job && !watching) watchJob(O.job);
}
refresh(true).catch(e => toast(e.message));

// ---------------- 팀 공유 링크 ----------------
async function drawShare() {
  let s; try { s = await api('/api/share'); } catch (_) { $('#c-share').hidden = true; return; }  // 공유 링크로 들어온 사람에겐 숨김
  $('#c-share').classList.toggle('ok', s.on);
  $('#c-share-t').innerHTML = s.on ? `켜짐 · <a href="${esc(s.url)}" target="_blank" rel="noopener"><b>${esc(s.url)}</b></a> <button class="btn sm" id="b-share-copy">복사</button><br>이 PC와 프로그램이 켜져 있는 동안만 열려요. 끄거나 PC를 다시 켜면 주소가 바뀌어요.`
    : (s.error ? esc(s.error) + '<br>' : '') + (s.has_password ? '비밀번호가 정해져 있어요. [공유 켜기]를 누르면 링크가 생겨요.' : '먼저 공유 비밀번호를 정해 주세요.');
  const cp = $('#b-share-copy'); if (cp) cp.onclick = () => { navigator.clipboard.writeText(s.url); toast('링크를 복사했어요'); };
  $('#ngrok-box').hidden = !s.ngrok;
  if (s.fixed) $('#i-ngrok-domain').placeholder = `지금 고정 도메인: ${s.fixed}`;
  if (s.fixed && !s.on) $('#c-share-t').insertAdjacentHTML('beforeend', `<br>고정 주소: <b>https://${esc(s.fixed)}</b> (프로그램을 켜면 자동으로 열려요)`);
}
$('#b-ngrok').onclick = async () => {
  try {
    await api('/api/share/ngrok', {token: $('#i-ngrok-token').value, domain: $('#i-ngrok-domain').value});
    $('#i-ngrok-token').value = ''; toast('저장했어요. [공유 끄기] → [공유 켜기]를 누르면 고정 주소로 열려요'); drawShare();
  } catch (e) { toast(e.message); }
};
$('#b-sharepw').onclick = async () => { try { await api('/api/share/password', {password: $('#i-sharepw').value}); $('#i-sharepw').value = ''; toast('공유 비밀번호를 정했어요'); drawShare(); } catch (e) { toast(e.message); } };
$('#b-share-on').onclick = async () => { $('#c-share-t').textContent = '링크 만드는 중(최대 30초)…'; try { await api('/api/share/start', {}); } catch (e) { toast(e.message); } drawShare(); };
$('#b-share-off').onclick = async () => { await api('/api/share/stop', {}); toast('공유를 껐어요'); drawShare(); };
drawShare();
// 놓친 오류도 화면에 알린다(버튼이 반응 없는 것처럼 보이지 않게)
window.addEventListener('unhandledrejection', e => toast('오류: ' + (e.reason && e.reason.message || e.reason)));
