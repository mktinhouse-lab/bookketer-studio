// 카드뉴스 작업 화면: 첫 화면(새로 만들기) · 작업 목록 · 1단계 레퍼런스. studio.js 의 $, esc, num, api, toast, md 를 쓴다.
const VIEWS = ['home', 'works', 'work', 'learn'];
function show(view) {
  VIEWS.forEach(v => { $('#view-' + v).hidden = v !== view; });
  window.scrollTo(0, 0);
}
const fileToDataUrl = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(f); });
const imgUrl = (wid, sub, name) => `/api/works/${encodeURIComponent(wid)}/img/${encodeURIComponent(sub)}/${encodeURIComponent(name)}`;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------------- 길 찾기 ----------------
async function route() {
  const h = location.hash.replace(/^#\/?/, '');
  const [a, b, c] = h.split('/');
  try {
    if (a === 'learn') { drawSteps(0); show('learn'); return; }
    if (a === 'works') { drawSteps(0); show('works'); await drawWorks(); return; }
    if (a === 'w' && b) { await openWork(decodeURIComponent(b), Number(c) || 0); return; }
    drawSteps(0); show('home'); await drawHome();
  } catch (e) { toast(e.message); }
}
window.addEventListener('hashchange', route);

// ---------------- 첫 화면 ----------------
async function drawHome() {
  const list = await api('/api/works');
  const todo = list.filter(w => !w.done);
  $('#recent').innerHTML = todo.length ? todo.slice(0, 6).map(w => workCard(w, true)).join('') : '<div class="empty">이어서 할 작업이 없어요. 위에서 새로 만들어 보세요.</div>';
  HOME_LIST = list;
  drawHomeWorks();
  try {
    const o = await api('/api/learn');
    $('#guide-applied').innerHTML = o.applied ? `적용 가이드: <code>${esc(o.applied.replace('스타일가이드_', '').replace('.md', ''))}</code>` : '스타일 가이드 없음(학습·연결 메뉴)';
  } catch (_) {}
}
let HOME_LIST = [];
function drawHomeWorks() {
  const q = ($('#w-search').value || '').trim();
  const list = HOME_LIST.filter(w => !q || (w.title || '').includes(q) || w.id.includes(q));
  $('#works-n').textContent = q ? `${list.length}/${HOME_LIST.length}개` : `${HOME_LIST.length}개`;
  $('#home-works').innerHTML = list.length ? list.map(w => workCard(w, false)).join('') : `<div class="empty">${q ? '찾는 작업이 없어요.' : '아직 만든 카드뉴스가 없습니다.'}</div>`;
}
$('#w-search').oninput = drawHomeWorks;

// 선택 모드: [선택] → 체크 → [선택 삭제(n)] (휴지통으로 옮김)
document.querySelectorAll('[data-sel]').forEach(btn => btn.onclick = () => toggleSelect(btn.dataset.sel, btn));
function toggleSelect(gridId, btn) {
  const grid = $('#' + gridId), on = !grid.classList.contains('selecting');
  grid.classList.toggle('selecting', on);
  grid.querySelectorAll('.pick').forEach(p => { p.hidden = !on; p.checked = false; });
  grid.querySelectorAll('.wc').forEach(c => c.classList.remove('on'));
  const bar = btn.parentElement;
  bar.querySelector('.del-sel')?.remove();
  btn.textContent = on ? '선택 취소' : '선택';
  if (on) {
    btn.insertAdjacentHTML('afterend', '<button class="btn sm danger del-sel" disabled>선택 삭제</button>');
    const del = bar.querySelector('.del-sel');
    const count = () => { const n = grid.querySelectorAll('.pick:checked').length; del.disabled = !n; del.textContent = n ? `선택 삭제 (${n})` : '선택 삭제'; };
    grid.onclick = e => {
      const card = e.target.closest('.wc'); if (!card || !grid.classList.contains('selecting')) return;
      e.preventDefault();
      const pk = card.querySelector('.pick'); if (e.target !== pk) pk.checked = !pk.checked;
      card.classList.toggle('on', pk.checked); count();
    };
    del.onclick = async () => {
      const ids = [...grid.querySelectorAll('.pick:checked')].map(p => p.closest('.wc').dataset.wid);
      if (!ids.length || !confirm(`${ids.length}개 작업을 휴지통으로 옮길까요? (휴지통에서 되살릴 수 있어요)`)) return;
      await api('/api/works/delete', {ids}); toast(`${ids.length}개를 휴지통으로 옮겼어요`);
      toggleSelect(gridId, btn); await drawHome();
    };
  } else grid.onclick = null;
}
$('#b-trash').onclick = async () => {
  const box = $('#trash-box');
  if (!box.hidden) { box.hidden = true; return; }
  const t = await api('/api/trash');
  box.hidden = false;
  box.innerHTML = `<h3 style="margin:16px 0 4px;font-size:15px">휴지통 <span class="hint">${t.length}개 · 되살리면 작업 목록으로 돌아가요 (완전히 지우려면 작업/_휴지통 폴더를 직접 비워 주세요)</span></h3>
    <div class="trash-list">${t.length ? t.map(x => `<div class="wl"><div><b>${esc(x.title)}</b> <span class="hint">${esc(x.id)} · ${x.done ? '완성' : `${x.step}단계`}</span></div>
      <button class="btn sm" data-restore="${esc(x.id)}">되살리기</button></div>`).join('') : '<div class="hint">비어 있어요.</div>'}</div>`;
  box.querySelectorAll('[data-restore]').forEach(b => b.onclick = async () => {
    await api('/api/trash/restore', {id: b.dataset.restore}); toast('되살렸어요'); await drawHome(); $('#b-trash').click(); $('#b-trash').click();
  });
};

// 작업 화면 위쪽 버튼
$('#b-open-folder').onclick = async () => { try { await api(`/api/works/${encodeURIComponent(W.id)}/open-folder`, {}); } catch (e) { toast(e.message); } };
$('#b-dup').onclick = async () => {
  if (!confirm('이 작업을 복제할까요? 레퍼런스·카피·책·카드가 그대로 복사돼요. 다른 버전을 만들 때 쓰세요.')) return;
  const r = await api(`/api/works/${encodeURIComponent(W.id)}/duplicate`, {}); toast('복제했어요'); location.hash = `#/w/${encodeURIComponent(r.id)}/${W.step}`;
};
$('#b-del-work').onclick = async () => {
  if (!confirm('이 작업을 휴지통으로 옮길까요? (첫 화면 → 작업 목록 → 휴지통에서 되살릴 수 있어요)')) return;
  await api('/api/works/delete', {ids: [W.id]}); toast('휴지통으로 옮겼어요'); location.hash = '#/';
};

// 작업 카드: 4:5 썸네일(완성 PNG / 배경+카피 / 레퍼런스 첫 장) + 제목 + 진행 상태
function workCard(w, big) {
  const t = w.thumb, c = w.copy || [];
  const img = t ? `<img src="${imgUrl(w.id, t.sub, t.name)}" alt="" loading="lazy">` : '';
  const overlay = t && !t.final && c.length ? `<div class="wc-copy"><span style="color:${esc(c[2])}">${esc(c[0])}</span><span style="color:${esc(c[3])}">${esc(c[1])}</span></div>`
    : (!t && c.length ? `<div class="wc-copy"><span>${esc(c[0])}</span><span style="color:#D4FEBE">${esc(c[1])}</span></div>` : '');
  const badge = w.done ? '<span class="wc-badge done">완성</span>' : `<span class="wc-badge">${w.step}단계 · ${esc(STEPS[w.step] || '')}</span>`;
  const u = w.updated || w.id;  // 2026-10-15_15-20-17 → 10/15 15:20
  const when = `${u.slice(5, 7)}/${u.slice(8, 10)} ${u.slice(11, 13)}:${u.slice(14, 16)}`;
  return `<div class="wc ${big ? 'big' : ''}" data-wid="${esc(w.id)}"><input type="checkbox" class="pick" hidden>
    <a class="wc-img ${t && t.ref ? 'ref' : ''}" href="#/w/${encodeURIComponent(w.id)}/${w.done ? 4 : w.step}">${img}${t && t.ref ? '<span class="wc-ref">레퍼런스</span>' : ''}${overlay}${badge}</a>
    <div class="wc-body"><a class="wc-title" href="#/w/${encodeURIComponent(w.id)}/${w.done ? 4 : w.step}">${esc(w.title || '(카피 고르기 전)')}</a>
      <div class="hint">${esc(when)} · ${w.count ? `책 ${w.count}권` : '권수 미정'}</div>
      ${big ? '' : `<details class="wc-files"><summary>파일 ${w.files.length}개</summary>${w.files.map(f => `<button class="btn sm" data-w="${esc(w.id)}" data-f="${esc(f)}">${esc(f)}</button>`).join('')}</details>`}
    </div></div>`;
}
function workRow(w) {
  const title = w.title || '(카피 고르기 전)';
  return `<div class="wl"><div><a href="#/w/${encodeURIComponent(w.id)}/${w.step}">${esc(title)}</a>
    <div class="hint">${esc(w.id)} · ${w.count ? `책 ${w.count}권` : '권수 미정'} · ${w.step}단계 ${esc(STEPS[w.step] || '')} 진행 중 · 레퍼런스 ${w.refs}개</div></div>
    <div class="files">${w.files.map(f => `<button class="btn sm" data-w="${esc(w.id)}" data-f="${esc(f)}">${esc(f)}</button>`).join('')}</div></div>`;
}
async function drawWorks() {
  const list = await api('/api/works');
  $('#works').innerHTML = list.length ? list.map(w => workCard(w, false)).join('') : '<div class="empty">아직 만든 카드뉴스가 없습니다.</div>';
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-f]');
  if (!b) return;
  const f = await api(`/api/works/${encodeURIComponent(b.dataset.w)}/file/${encodeURIComponent(b.dataset.f)}`);
  $('#dlg-t').textContent = f.name; $('#dlg-b').innerHTML = `<div class="md">${md(f.text)}</div>`; $('#dlg').showModal();
});

$('#b-start').onclick = async () => {
  const urls = [...document.querySelectorAll('.ref-url')].map(i => i.value.trim()).filter(Boolean);
  if (!urls.length) { toast('레퍼런스 링크를 하나 이상 넣어 주세요. 링크가 없으면 옆의 [직접 넣기]를 쓰세요.'); return; }
  let w, r;
  try { w = await api('/api/works', {}); } catch (e) { toast('새 작업을 만들지 못했어요: ' + e.message); return; }
  try { r = await api(`/api/works/${encodeURIComponent(w.id)}/refs/fetch`, {urls}); } catch (e) { toast('레퍼런스를 가져오지 못했어요: ' + e.message); location.hash = `#/w/${encodeURIComponent(w.id)}/1`; return; }
  document.querySelectorAll('.ref-url').forEach(i => i.value = '');
  location.hash = `#/w/${encodeURIComponent(w.id)}/1`;
  watchRefJob(w.id, r.job);
};
$('#b-start-upload').onclick = async () => {
  let w;
  try { w = await api('/api/works', {}); } catch (e) { toast('새 작업을 만들지 못했어요: ' + e.message); return; }
  location.hash = `#/w/${encodeURIComponent(w.id)}/1`;
  setTimeout(() => { $('#addref').open = true; $('#up-files').scrollIntoView({block: 'center'}); }, 400);
};

// ---------------- 작업 열기 ----------------
let W = null;
async function openWork(wid, step) {
  W = await api(`/api/works/${encodeURIComponent(wid)}`);
  step = step || W.step || 1;
  if (step > W.step) step = W.step;
  drawSteps(step, W.step, W.id);
  show('work');
  $('#w-title').textContent = W.title || '새 카드뉴스';
  $('#w-meta').textContent = `· ${W.count ? `책 ${W.count}권` : '권수는 3단계에서 정해요'} · 최종 ${W.step}단계`;
  $('#w-folder').innerHTML = `폴더 <code>작업/${esc(W.id)}</code>`;
  $('#step1').hidden = step !== 1; $('#step2').hidden = step !== 2; $('#step3').hidden = step !== 3; $('#step4').hidden = step !== 4; $('#stepN').hidden = step <= 4;
  if (step === 1) drawRefs();
  else if (step === 2) drawCopies();
  else if (step === 3) drawBooks3();
  else if (step === 4) drawCards();
  else {
    $('#stepN-title').textContent = `${step}단계 · ${STEPS[step]}`;
    $('#stepN-body').textContent = '없는 단계입니다.';
  }
}

// ---------------- 1단계 레퍼런스 ----------------
function drawRefs() {
  const refs = W.refs || [];
  $('#addref').hidden = refs.length >= 3;
  if (!refs.length) { $('#refs').innerHTML = '<div class="empty">레퍼런스를 가져오는 중이거나 아직 없습니다. 아래에서 추가하세요.</div>'; $('#addref').open = true; return; }
  $('#refs').innerHTML = refs.map(r => `<div class="ref" data-no="${r.no}">
    <h3>레퍼런스 ${r.no} ${r.author ? `· @${esc(r.author)}` : ''} ${r.url ? `<a class="hint" href="${esc(r.url)}" target="_blank" rel="noopener">원본 열기</a>` : ''}
      <span class="hint">${esc(r.date || '')} · ♥${num(r.likes)} · 💬${num(r.comments)} · ${r.slides}장 · ${esc(r.source)}</span>
      <button class="btn sm danger" data-del="${r.no}" style="margin-left:auto">빼기</button></h3>
    <div class="strip">${r.images.map(n => `<img src="${imgUrl(W.id, '01_레퍼런스_이미지', n)}" alt="" data-zoom>`).join('')}</div>
    <div class="cols">
      <label>썸네일 카피 (AI가 읽음 · 고칠 수 있어요)<textarea class="copy" data-k="copy">${esc(r.copy)}</textarea></label>
      <label>장별 구성<textarea data-k="structure">${esc(r.structure)}</textarea></label>
    </div>
    <div class="cols">
      <label>댓글 내용 (로그인 없이 가져오면 비어 있어요 · 반응 좋은 댓글을 붙여 넣으면 2단계 분석에 씁니다)<textarea data-k="top_comments">${esc(r.top_comments)}</textarea></label>
      <label>좋아요 · 댓글 수 · 계정 · 날짜 (비었거나 틀리면 고치기)<span class="row" style="margin:0"><input type="text" data-k="likes" value="${r.likes ?? ''}" placeholder="좋아요" style="width:110px"><input type="text" data-k="comments" value="${r.comments ?? ''}" placeholder="댓글 수" style="width:110px"><input type="text" data-k="author" value="${esc(r.author || '')}" placeholder="계정명" style="width:150px"><input type="text" data-k="date" value="${esc(r.date || '')}" placeholder="업로드 날짜 2026-10-01" style="width:170px"></span></label>
    </div>
    <details><summary>캡션 보기·고치기</summary><textarea data-k="caption" style="min-height:120px">${esc(r.caption)}</textarea></details>
    ${r.analysis?.notes ? `<p class="hint">AI 확인 필요: ${esc(r.analysis.notes)}</p>` : ''}
  </div>`).join('');
  document.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => {
    if (!confirm('이 레퍼런스를 뺄까요?')) return;
    W = await api(`/api/works/${encodeURIComponent(W.id)}/refs/save`, {refs: collectRefs().filter(r => r.no !== Number(b.dataset.del))});
    drawRefs();
  });
  document.querySelectorAll('[data-zoom]').forEach(i => i.onclick = () => { $('#dlg-t').textContent = '레퍼런스'; $('#dlg-b').innerHTML = `<img src="${i.src}" style="max-width:100%;display:block;margin:auto">`; $('#dlg').showModal(); });
}
function collectRefs() {
  return [...document.querySelectorAll('.ref')].map(el => {
    const r = {no: Number(el.dataset.no)};
    el.querySelectorAll('[data-k]').forEach(f => {
      let v = f.value;
      if (f.dataset.k === 'likes' || f.dataset.k === 'comments') v = v.replace(/[^\d]/g, '') === '' ? null : Number(v.replace(/[^\d]/g, ''));
      r[f.dataset.k] = v;
    });
    return r;
  });
}
$('#b-refs-save').onclick = async () => { W = await api(`/api/works/${encodeURIComponent(W.id)}/refs/save`, {refs: collectRefs()}); toast('저장했어요'); };
$('#b-refs-next').onclick = async () => {
  try {
    const hadCopies = !!(W.copy && W.copy.items && W.copy.items.length);
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/refs/confirm`, {refs: collectRefs()});
    toast(`${r.file} 저장`);
    if (hadCopies && confirm('레퍼런스를 고쳤어요. 2단계 썸네일 카피를 새 레퍼런스로 다시 뽑을까요? (📌고정한 카피는 남겨요)')) {
      const pinned = W.copy.items.filter(c => c.pinned).map(c => c.id);
      const g = await api(`/api/works/${encodeURIComponent(W.id)}/copies/gen`, {keep_ids: pinned});
      location.hash = `#/w/${encodeURIComponent(W.id)}/2`; watchBar('copyjob', g.job, j => j.status === 'done' && openWork(W.id, 2));
      return;
    }
    location.hash = `#/w/${encodeURIComponent(W.id)}/2`;
  } catch (e) { toast(e.message); }
};
$('#b-add-url').onclick = async () => {
  const u = $('#add-url').value.trim(); if (!u) return;
  await api(`/api/works/${encodeURIComponent(W.id)}/refs/save`, {refs: collectRefs()});
  const r = await api(`/api/works/${encodeURIComponent(W.id)}/refs/fetch`, {urls: [u]});
  $('#add-url').value = ''; watchRefJob(W.id, r.job);
};
$('#b-upload').onclick = async () => {
  const files = [...$('#up-files').files];
  const images = await Promise.all(files.map(fileToDataUrl));
  try {
    await api(`/api/works/${encodeURIComponent(W.id)}/refs/save`, {refs: collectRefs()});
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/refs/upload`, {images, thumb_copy: $('#up-copy').value, caption: $('#up-caption').value, url: $('#up-url').value});
    ['#up-copy', '#up-caption', '#up-url'].forEach(s => $(s).value = ''); $('#up-files').value = '';
    if (r.job) watchRefJob(W.id, r.job); else { await openWork(W.id, 1); toast('올렸어요'); }
  } catch (e) { toast(e.message); }
};

async function watchRefJob(wid, id) {
  $('#refjob').hidden = false;
  while (true) {
    let j; try { j = await api(`/api/jobs/${id}`); } catch (_) { break; }
    $('#refjob-label').textContent = j.label + (j.progress?.label ? ` — ${j.progress.label}` : '');
    $('#refjob-time').textContent = `${j.elapsed}초`;
    $('#refjob-bar').style.width = (j.status === 'done' ? 100 : j.progress?.pct || 3) + '%';
    if (j.status !== 'running') {
      $('#refjob').hidden = true;
      if (j.status === 'error') toast(`오류: ${j.error}`);
      else if (j.result?.failed?.length) toast(`못 읽은 링크 ${j.result.failed.length}개 — 직접 올리기를 써 주세요`);
      else toast('레퍼런스를 읽었어요. 틀린 곳을 고쳐 주세요');
      if (W && W.id === wid) await openWork(wid, 1);
      break;
    }
    await sleep(1500);
  }
}

// ---------------- 공통: 진행 막대 ----------------
async function watchBar(prefix, id, onDone) {
  $('#' + prefix).hidden = false;
  while (true) {
    let j; try { j = await api(`/api/jobs/${id}`); } catch (_) { break; }
    $(`#${prefix}-label`).textContent = j.label + (j.progress?.label ? ` — ${j.progress.label}` : '');
    $(`#${prefix}-time`).textContent = `${j.elapsed}초`;
    $(`#${prefix}-bar`).style.width = (j.status === 'done' ? 100 : j.progress?.pct || 3) + '%';
    if (j.status !== 'running') {
      $('#' + prefix).hidden = true;
      if (j.status === 'error') toast(`오류: ${j.error}`);
      if (onDone) await onDone(j);
      return j;
    }
    await sleep(1500);
  }
}

// ---------------- 2단계 썸네일 카피 ----------------
let copySel = null, copyGenRunning = false;
async function drawCopies() {
  const c = W.copy;
  if (!c || !c.items?.length) {
    $('#copy-analysis').innerHTML = ''; $('#copy-var').innerHTML = ''; $('#copy-dev').innerHTML = ''; $('#copy-edit').hidden = true;
    if (!copyGenRunning) startCopyGen([]);
    return;
  }
  const a = c.analysis;
  $('#copy-analysis').innerHTML = `<div class="anal"><div><b>후킹 구조</b>${esc(a.hook)}</div><div><b>타깃</b>${esc(a.target)}</div>
    <div><b>건드리는 감정</b>${esc(a.emotion)}</div><div><b>반응 근거</b>${esc(a.evidence)}</div><div class="wide"><b>레퍼런스 공식</b>${esc(a.formula)}</div></div>`;
  const card = x => `<div class="cc ${copySel === x.id ? 'on' : ''}" data-cid="${esc(x.id)}">
    <input type="radio" name="copypick" ${copySel === x.id ? 'checked' : ''}>
    <div class="t"><div class="a">${esc(x.line1)}</div><div class="b">${esc(x.line2)}${x.recommended ? '<span class="rec">추천</span>' : ''}</div><div class="d">${esc(x.device)}</div></div>
    <button class="pin ${x.pinned ? 'on' : ''}" data-pin="${esc(x.id)}" title="고정">📌</button></div>`;
  $('#copy-var').innerHTML = c.items.filter(x => x.kind === '베리에이션').map(card).join('');
  $('#copy-dev').innerHTML = c.items.filter(x => x.kind === '디벨롭').map(card).join('');
  $('#copy-reco').textContent = c.recommend ? `추천 이유: ${c.recommend}` : '';
  document.querySelectorAll('.cc').forEach(el => el.onclick = e => { if (e.target.closest('.pin')) return; pickCopy(el.dataset.cid); });
  document.querySelectorAll('[data-pin]').forEach(b => b.onclick = async () => {
    const x = W.copy.items.find(i => i.id === b.dataset.pin); x.pinned = !x.pinned;
    W = await api(`/api/works/${encodeURIComponent(W.id)}/copies/save`, {items: [{id: x.id, pinned: x.pinned}]}); drawCopies();
  });
  if (!copySel) { const ch = c.chosen?.id && c.items.find(i => i.id === c.chosen.id); const rec = ch || c.items.find(i => i.recommended); if (rec) pickCopy(rec.id); }
}
function pickCopy(id) {
  copySel = id;
  const x = W.copy.items.find(i => i.id === id); if (!x) return;
  document.querySelectorAll('.cc').forEach(el => el.classList.toggle('on', el.dataset.cid === id));
  document.querySelectorAll('.cc input').forEach(r => r.checked = r.closest('.cc').dataset.cid === id);
  $('#copy-edit').hidden = false; $('#ed1').value = x.line1; $('#ed2').value = x.line2; $('#ed-device').textContent = `${x.kind} · ${x.device}`;
  previewCopy();
}
function previewCopy() { $('#pv1').textContent = $('#ed1').value; $('#pv2').textContent = $('#ed2').value; }
$('#ed1').oninput = previewCopy; $('#ed2').oninput = previewCopy;
async function startCopyGen(keep) {
  copyGenRunning = true;
  try {
    const g = await api(`/api/works/${encodeURIComponent(W.id)}/copies/gen`, {keep_ids: keep});
    await watchBar('copyjob', g.job, async j => { if (j.status === 'done') { copySel = null; await openWork(W.id, 2); } else $('#copy-analysis').innerHTML = '<div class="empty">카피를 뽑지 못했어요. [다시 뽑기]를 눌러 주세요.</div>'; });
  } catch (e) { toast(e.message); }
  copyGenRunning = false;
}
$('#b-copy-regen').onclick = () => startCopyGen(W.copy.items.filter(c => c.pinned).map(c => c.id));
$('#b-copy-next').onclick = async () => {
  const x = W.copy.items.find(i => i.id === copySel) || {};
  try {
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/copies/confirm`, {chosen: {...x, line1: $('#ed1').value.trim(), line2: $('#ed2').value.trim()}});
    toast(`카피 확정 · 폴더 이름: ${r.id}`); copySel = null;
    location.hash = `#/w/${encodeURIComponent(r.id)}/3`;
  } catch (e) { toast(e.message); }
};

// ---------------- 3단계 책 추천 ----------------
let bookGenRunning = false;
const bkSel = () => (W.books?.selected || []);
function drawBooks3() {
  const b = W.books;
  $('#bk-pilotic').checked = !!b?.pilotic;
  if (!b || !b.items?.length) {
    $('#books-grid').innerHTML = '';
    if (!bookGenRunning) startBookGen([]);
    return;
  }
  const sel = bkSel();
  const met = (v, url) => v != null && v !== '' ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(typeof v === 'number' ? num(v) : v)}</a>` : '<span class="na">확인 불가</span>';
  $('#books-grid').innerHTML = b.items.map(x => `<div class="bk ${sel.includes(x.key) ? 'on' : ''}" data-key="${esc(x.key)}">
    <div class="bk-top"><label class="ck"><input type="checkbox" ${sel.includes(x.key) ? 'checked' : ''}> 선택${sel.includes(x.key) ? ` <b>${sel.indexOf(x.key) + 1}</b>` : ''}</label>
      ${x.used ? '<span class="tag gray">사용함</span>' : ''}${x.pilotic ? '<span class="tag">필로틱</span>' : ''}</div>
    <div class="bk-body">
      ${x.cover ? `<img src="${esc(x.cover)}" alt="" referrerpolicy="no-referrer">` : '<div class="nocover">표지 없음</div>'}
      <div class="bk-info"><b class="bk-t">${esc(x.title)}</b>
        <div class="hint">${esc(x.author || '')} · ${esc(x.publisher || '출판사 확인 불가')} · ${esc(x.pub_date || '출간일 확인 불가')}</div>
        <div class="hint">${esc(x.field || '분야 확인 불가')}${x.pages ? ` · ${x.pages}쪽` : ''}</div>
        <p class="bk-sum">${esc(x.summary || '').replace(/\n/g, '<br>')}</p>
        <p class="bk-why">💡 ${esc(x.why || '')}</p>${x.warn ? `<p class="bk-warn">⚠️ ${esc(x.warn)}</p>` : ''}
      </div></div>
    <div class="bk-met"><span>판매지수 ${met(x.sales_point, x.url)}</span><span>현재 순위 ${met(x.rank_now, x.url)}</span><span>최고 순위·기간 ${met(x.best_record, x.url)}</span></div>
  </div>`).join('');
  document.querySelectorAll('.bk').forEach(el => el.onclick = async e => {
    if (e.target.closest('a')) return;
    const k = el.dataset.key; let s = [...bkSel()];
    s = s.includes(k) ? s.filter(x => x !== k) : [...s, k];
    W = await api(`/api/works/${encodeURIComponent(W.id)}/books/select`, {keys: s}); drawBooks3();
  });
  const n = sel.length;
  const ok = n >= 3 && n <= 5;
  $('#bk-count').textContent = `${n}권 선택`;
  $('#bk-need').textContent = ok ? `${n}권으로 만들어요 (썸네일 + 책 ${n}장 + CTA)` : '3~5권을 고르면 고른 권수로 카드뉴스를 만들어요';
  $('#b-books-next').disabled = !ok;
  $('#b-books-next').textContent = ok ? `이 ${n}권으로 4단계 →` : '이 책들로 4단계 →';
}
async function startBookGen(keep) {
  bookGenRunning = true;
  try {
    const g = await api(`/api/works/${encodeURIComponent(W.id)}/books/gen`, {keep_keys: keep, pilotic: $('#bk-pilotic').checked});
    await watchBar('bookjob', g.job, async j => {
      if (j.status === 'done') { if (j.result?.dropped) toast(`알라딘에서 확인 안 된 후보 ${j.result.dropped}권은 뺐어요`); await openWork(W.id, 3); }
      else $('#books-grid').innerHTML = '<div class="empty">추천을 끝내지 못했어요. [다시 추천]을 눌러 주세요.</div>';
    });
  } catch (e) { toast(e.message); }
  bookGenRunning = false;
}
$('#b-book-regen').onclick = () => startBookGen(bkSel());
$('#bk-pilotic').onchange = () => toast($('#bk-pilotic').checked ? '다음 추천부터 필로틱 1권을 넣어요. [다시 추천]을 눌러 주세요' : '필로틱 포함을 껐어요');
$('#b-bk-search').onclick = async () => {
  const q = $('#bk-q').value.trim(); if (!q) return;
  $('#bk-results').innerHTML = '<div class="hint">알라딘에서 찾는 중…</div>';
  const r = await api(`/api/books/search?q=${encodeURIComponent(q)}`);
  $('#bk-results').innerHTML = r.length ? `<div class="bk-search">${r.map(x => `<div class="wl"><div><b>${esc(x.title)}</b> <span class="hint">${esc(x.author_line)} · ${esc(x.publisher)} · ${esc(x.month)} · 판매지수 ${num(x.sales_point)}</span></div>
    <button class="btn sm" data-add="${esc(x.item_id)}">후보에 추가</button></div>`).join('')}</div>` : '<div class="hint">알라딘에서 찾지 못했어요.</div>';
  document.querySelectorAll('[data-add]').forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = '추가 중…';
    const g = await api(`/api/works/${encodeURIComponent(W.id)}/books/add`, {item_id: b.dataset.add});
    await watchBar('bookjob', g.job, async j => { $('#bk-results').innerHTML = ''; if (j.status === 'done') await openWork(W.id, 3); });
  });
};
$('#b-books-next').onclick = async () => {
  try {
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/books/confirm`, {keys: bkSel()});
    toast(`책 ${r.count}권으로 확정했어요` + (r.copy_changed ? ` · 카피 숫자도 맞췄어요: ${r.copy_changed}` : '')); location.hash = `#/w/${encodeURIComponent(r.id)}/4`;
  } catch (e) { toast(e.message); }
};

// ---------------- 4단계 카드 완성(편집기) ----------------
// 카드 저장: 서버가 더 새 내용(rev)을 갖고 있으면 덮어쓰지 않고 최신 내용을 다시 불러온다
async function saveCards() {
  try {
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/cards/save`, {cards: C});
    C.rev = r.rev; return true;
  } catch (e) {
    if (e.status !== 409) throw e;
    W = await api(`/api/works/${encodeURIComponent(W.id)}`); C = W.cards; drawCards();
    toast('다른 화면이나 자동 작업이 먼저 바꾼 최신 내용을 불러왔어요. 방금 고친 것은 다시 고쳐 주세요');
    return false;
  }
}
let C = null, cur = 0, cardBuildRunning = false, saveTimer = null;
const cardImg = (sub, name) => imgUrl(W.id, sub, name);
const MINT = '#D4FEBE';
const COPY_COLORS = [['#FFFFFF', '흰색'], [MINT, '민트'], ['#F30505', '빨강']];

async function drawCards() {
  C = W.cards;
  $('#export-result').innerHTML = W.export ? exportHtml(W.export) : '';
  if (!C) {
    $('#editor').hidden = true; $('#ed-bottom').hidden = true;
    $('#cards-empty').hidden = false; $('#cards-empty').textContent = '설명글·캡션을 쓰고 배경을 찾아 카드를 만드는 중이에요(1~2분).';
    if (!cardBuildRunning) startCardBuild();
    return;
  }
  $('#cards-empty').hidden = true; $('#editor').hidden = false; $('#ed-bottom').hidden = false;
  if (cur >= C.slides.length) cur = 0;
  $('#ed-caption').value = C.caption || ''; capCount(); drawFactcheck();
  drawStrip(); drawStage(); drawPanel();
}
async function startCardBuild() {
  cardBuildRunning = true;
  try {
    const g = await api(`/api/works/${encodeURIComponent(W.id)}/cards/build`, {});
    await watchBar('cardjob', g.job, async j => {
      if (j.status === 'done') { cur = 0; await openWork(W.id, 4); }
      else { $('#cards-empty').hidden = false; $('#cards-empty').textContent = '자동 제작을 끝내지 못했어요. [처음부터 다시 자동 제작]을 눌러 주세요.'; $('#ed-bottom').hidden = false; }
    });
  } catch (e) { toast(e.message); }
  cardBuildRunning = false;
}
function slideLabel(s, i) { return s.type === 'thumb' ? '썸네일' : s.type === 'cta' ? 'CTA' : `책 ${i}`; }
function descCount(s) { return (s.lines || []).reduce((n, l) => n + (l.text || '').length, 0); }
function descBad(s) { const [lo, hi] = C.range || [75, 140]; const n = descCount(s); return n < lo || n > hi; }
function mount(target, i, cls) {
  const {el} = renderCard(C.slides[i], i, C, cardImg);
  const wrap = document.createElement('div'); wrap.className = 'sc'; wrap.appendChild(el);
  target.innerHTML = ''; target.appendChild(wrap);
}
function drawStrip() {
  const st = $('#ed-strip'); st.innerHTML = '';
  C.slides.forEach((s, i) => {
    const t = document.createElement('div'); t.className = 'ed-thumb' + (i === cur ? ' on' : '');
    const inner = document.createElement('div'); t.appendChild(inner); mount(inner, i);
    t.insertAdjacentHTML('beforeend', `<span class="no">${i + 1} ${slideLabel(s, i)}</span>${s.type === 'book' && descBad(s) ? '<span class="warn">⚠️</span>' : ''}`);
    t.onclick = () => { cur = i; drawStrip(); drawStage(); drawPanel(); };
    st.appendChild(t);
  });
}
function drawStage() { mount($('#ed-frame'), cur); $('#ed-pos').textContent = `${cur + 1} / ${C.slides.length} · ${slideLabel(C.slides[cur], cur)} · 1080×1350`; }
function changed(redrawPanel) {
  drawStage();
  const th = document.querySelectorAll('.ed-thumb')[cur];
  if (th) { mount(th.firstChild, cur); th.querySelector('.warn')?.remove(); const s = C.slides[cur]; if (s.type === 'book' && descBad(s)) th.insertAdjacentHTML('beforeend', '<span class="warn">⚠️</span>'); }
  if (redrawPanel) drawPanel();
  $('#ed-saved').textContent = '저장 중…';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try { if (await saveCards()) $('#ed-saved').textContent = '자동 저장됨'; else $('#ed-saved').textContent = '최신 내용으로 바꿨어요'; }
    catch (e) { $('#ed-saved').textContent = '저장 실패: ' + e.message; }
  }, 600);
}
function bgPicker(selected, onPick) {
  const bgs = C.bgs || [];
  return `<div class="bgpick">${bgs.map(b => `<img src="${cardImg('04_배경', b.file)}" data-bg="${esc(b.file)}" class="${b.file === selected ? 'on' : ''}" title="${esc(b.query || '')}">`).join('')}</div>
    <div class="row" style="margin:4px 0"><input type="file" accept="image/*" data-upbg><input type="text" placeholder="검색어로 더 찾기 (쉼표로 여러 개)" data-kw style="flex:1" value="${esc((C.keywords || []).join(', '))}"><button class="btn sm" data-morebg>더 찾기</button></div>`;
}
function wireBg(prefix, onPick) {
  document.querySelectorAll('#ed-panel [data-bg]').forEach(im => im.onclick = () => { onPick(im.dataset.bg); changed(true); });
  const up = document.querySelector('#ed-panel [data-upbg]');
  if (up) up.onchange = async () => {
    const f = up.files[0]; if (!f) return;
    const r = await api(`/api/works/${encodeURIComponent(W.id)}/cards/upload`, {data: await fileToDataUrl(f), kind: 'bg'});
    C.bgs = [{file: r.file, query: '직접 올림'}, ...(C.bgs || [])]; onPick(r.file); changed(true);
  };
  const more = document.querySelector('#ed-panel [data-morebg]');
  if (more) more.onclick = async () => {
    const kws = document.querySelector('#ed-panel [data-kw]').value.split(',').map(x => x.trim()).filter(Boolean);
    if (!(await saveCards())) return;
    const g = await api(`/api/works/${encodeURIComponent(W.id)}/cards/bg`, {keywords: kws});
    await watchBar('cardjob', g.job, async j => { if (j.status === 'done') { const w = await api(`/api/works/${encodeURIComponent(W.id)}`); C.bgs = w.cards.bgs; C.keywords = kws; drawPanel(); } });
  };
}
const rng = (k, label, min, max, step, val) => `<label>${label} <input type="range" data-k="${k}" min="${min}" max="${max}" step="${step}" value="${val}"></label>`;
function drawPanel() {
  const s = C.slides[cur], P = $('#ed-panel');
  if (s.type === 'thumb') {
    const opt = v => COPY_COLORS.map(([c, n]) => `<option value="${c}" ${v === c ? 'selected' : ''}>${n}</option>`).join('');
    P.innerHTML = `<h3>썸네일</h3>
      <label>1줄<div class="ed-line"><input type="text" data-k="line1" value="${esc(s.line1)}"><select data-k="c1">${opt(s.c1)}</select></div></label>
      <label>2줄<div class="ed-line"><input type="text" data-k="line2" value="${esc(s.line2)}"><select data-k="c2">${opt(s.c2)}</select></div></label>
      <div class="two"><label>라벨 1<input type="text" data-k="chip1" value="${esc(s.chip1)}"></label><label>라벨 2<input type="text" data-k="chip2" value="${esc(s.chip2)}"></label></div>
      <div class="two">${rng('size', '카피 크기', 0.6, 1.3, 0.01, s.size || 1)}${rng('dy', '카피 위치(위↔아래)', -500, 150, 1, s.dy || 0)}</div>
      <h3>배경</h3>${bgPicker(s.bg)}
      <div class="two">${rng('zoom', '확대', 1, 2.5, 0.01, s.zoom || 1)}${rng('shade', '아래 어둡게', 0, 1.5, 0.01, s.shade ?? 1)}</div>
      <div class="two">${rng('px', '가로 위치', 0, 100, 1, s.px ?? 50)}${rng('py', '세로 위치', 0, 100, 1, s.py ?? 50)}</div>
      <label class="ck" style="flex-direction:row"><input type="checkbox" id="same-body" ${C.body_bg === s.bg ? 'checked' : ''}> 책 소개·CTA 장 배경도 이 사진으로</label>`;
    wireBg('thumb', f => { if ($('#same-body')?.checked || C.body_bg === s.bg) C.body_bg = f; s.bg = f; });
    $('#same-body').onchange = e => { if (e.target.checked) { C.body_bg = s.bg; changed(); } };
  } else if (s.type === 'book') {
    const n = descCount(s), [lo, hi] = C.range || [75, 140];
    P.innerHTML = `<h3>책 ${cur} · ${esc(s.title)}</h3>
      <label>책 제목 칩<input type="text" data-k="title" value="${esc(s.title)}"></label>
      <label>해시태그 칩<input type="text" data-k="tags" value="${esc(s.tags)}"></label>
      <label>설명글 <span>(<span class="cnt ${n < lo || n > hi ? 'bad' : ''}">${n}자</span> · 기준 ${lo}~${hi}자 · 색 칸을 누르면 흰색↔민트)</span></label>
      <div class="ed-lines">${(s.lines || []).map((l, j) => `<div class="ed-line"><button class="clr" data-clr="${j}" style="background:${l.color === '민트' ? MINT : '#fff'}" title="${l.color}"></button>
        <input type="text" data-line="${j}" value="${esc(l.text)}"><button class="x" data-del="${j}" title="줄 빼기">×</button></div>`).join('')}
        <button class="btn sm" id="add-line">+ 줄 추가</button></div>
      <div class="two">${rng('size', '설명 크기', 0.8, 1.2, 0.01, s.size || 1)}${rng('dy', '설명 위치', -120, 120, 1, s.dy || 0)}</div>
      <div class="rw-box" id="rw-box" hidden>
        <textarea id="rw-text" placeholder="어떻게 고칠까요? 예) 주인공 이름을 넣고 첫 장면부터 긴장감 있게 / 마지막 줄은 질문으로 끝내 줘 / 좀 더 짧게 (비워 두면 줄거리 위주로 새로 써요)"></textarea>
        <div class="row end" style="margin:6px 0 0"><button class="btn sm" id="rw-cancel">취소</button><button class="btn sm pri" id="rw-go">이대로 다시 쓰기</button></div>
      </div>
      <div class="row"><button class="btn sm" id="b-rewrite">이 책 설명글 다시 쓰기(AI)</button>
        <label class="btn sm" style="display:inline-block">표지 바꾸기<input type="file" accept="image/*" id="up-cover" hidden></label></div>
      <div class="row"><button class="btn sm" id="mv-up">▲ 앞으로</button><button class="btn sm" id="mv-down">▼ 뒤로</button></div>
      <h3>책 소개·CTA 장 배경 <span class="hint">(모든 책 장 공통)</span></h3>${bgPicker(C.body_bg)}
      <div class="two">${rng('body_opacity', '사진 진하기', 0.1, 0.6, 0.01, C.body_opacity ?? 0.27)}${rng('body_zoom', '확대', 1, 2.5, 0.01, C.body_zoom || 1)}</div>`;
    wireBg('body', f => { C.body_bg = f; });
    P.querySelectorAll('[data-line]').forEach(inp => inp.oninput = () => { s.lines[+inp.dataset.line].text = inp.value; changed(); updateCnt(); });
    P.querySelectorAll('[data-clr]').forEach(b => b.onclick = () => { const l = s.lines[+b.dataset.clr]; l.color = l.color === '민트' ? '흰색' : '민트'; changed(true); });
    P.querySelectorAll('[data-del]').forEach(b => b.onclick = () => { s.lines.splice(+b.dataset.del, 1); changed(true); });
    $('#add-line').onclick = () => { const last = s.lines[s.lines.length - 1]; s.lines.push({text: '', color: last?.color === '민트' ? '흰색' : '민트'}); changed(true); };
    $('#b-rewrite').onclick = () => { $('#rw-box').hidden = false; $('#rw-text').focus(); };
    $('#rw-cancel').onclick = () => { $('#rw-box').hidden = true; };
    $('#rw-go').onclick = async () => {
      const instruction = $('#rw-text').value.trim();
      $('#rw-box').hidden = true;
      if (!(await saveCards())) return;
      const g = await api(`/api/works/${encodeURIComponent(W.id)}/cards/rewrite`, {key: s.key, instruction});
      await watchBar('cardjob', g.job, async j => { if (j.status === 'done') { const w = await api(`/api/works/${encodeURIComponent(W.id)}`); W = w; C = w.cards; drawStrip(); drawStage(); drawPanel(); toast('다시 썼어요'); } });
    };
    $('#up-cover').onchange = async e => { const f = e.target.files[0]; if (!f) return;
      const r = await api(`/api/works/${encodeURIComponent(W.id)}/cards/upload`, {data: await fileToDataUrl(f), kind: 'cover'}); s.cover = r.file; changed(true); };
    const move = d => { const j = cur + d; if (j < 1 || j > C.slides.length - 2) return; [C.slides[cur], C.slides[j]] = [C.slides[j], C.slides[cur]]; cur = j; drawStrip(); changed(true); };
    $('#mv-up').onclick = () => move(-1); $('#mv-down').onclick = () => move(1);
  } else {
    P.innerHTML = `<h3>CTA</h3><label>메인 문구<input type="text" data-k="main" value="${esc(s.main)}"></label>
      <label>서브 문구<input type="text" data-k="sub" value="${esc(s.sub)}"></label>
      <p class="hint">프로필 사진은 assets/profile.jpg, 아이디·팔로우 버튼은 템플릿에 고정돼 있어요.</p>
      <h3>배경 <span class="hint">(책 소개 장과 공통)</span></h3>${bgPicker(C.body_bg)}
      <div class="two">${rng('body_opacity', '사진 진하기', 0.1, 0.6, 0.01, C.body_opacity ?? 0.27)}${rng('body_zoom', '확대', 1, 2.5, 0.01, C.body_zoom || 1)}</div>`;
    wireBg('body', f => { C.body_bg = f; });
  }
  P.querySelectorAll('[data-k]').forEach(inp => {
    const k = inp.dataset.k; const target = k.startsWith('body_') ? C : s;
    inp.oninput = inp.onchange = () => { target[k] = inp.type === 'range' ? Number(inp.value) : inp.value; changed(); };
  });
  function updateCnt() { const n = descCount(s), [lo, hi] = C.range || [75, 140]; const el = P.querySelector('.cnt'); if (el) { el.textContent = n + '자'; el.classList.toggle('bad', n < lo || n > hi); } }
}
function capCount() { const v = $('#ed-caption').value; $('#cap-n').textContent = `${v.length}자${/#\S/.test(v) ? ' · ⚠️ 해시태그가 있어요(규칙: 캡션엔 해시태그 없음)' : ''}`; }
$('#ed-caption').oninput = () => { C.caption = $('#ed-caption').value; capCount(); changed(); };
function drawFactcheck() {
  const f = C.factcheck;
  if (!f) { $('#fc-box').innerHTML = '<h3>사실 검증</h3><span class="hint">아직 검증 전이에요. [사실 검증 다시 하기]를 눌러 주세요.</span>'; return; }
  const items = [];
  (f.copy_fit || []).forEach(x => items.push(`<li class="fix">⚠️ 카피와 안 맞음: ${esc(x)}</li>`));
  (f.books || []).forEach(b => {
    if (!b.issues.length) items.push(`<li class="ok">✅ ${esc(b.title)} — 문제 없음</li>`);
    b.issues.forEach(i => items.push(`<li class="fix">✏️ <b>${esc(b.title)}</b> (${esc(i.where)}) <del>${esc(i.text)}</del> — ${esc(i.problem)}<br><span class="hint">근거: ${esc(i.evidence)}</span></li>`));
  });
  (f.caption || []).forEach(i => items.push(`<li class="fix">✏️ <b>캡션</b> <del>${esc(i.text)}</del> — ${esc(i.problem)}${f.caption_unfixed ? ' <b>(자동으로 못 고쳤어요 — 아래 캡션에서 직접 고쳐 주세요)</b>' : ''}<br><span class="hint">근거: ${esc(i.evidence)}</span></li>`));
  $('#fc-box').innerHTML = `<h3>사실 검증 <span class="hint">${esc(f.at)} · 틀리거나 근거 없는 곳은 고쳐서 카드에 넣었어요</span></h3><ul>${items.join('')}</ul>`;
}
$('#b-factcheck').onclick = async () => {
  if (!(await saveCards())) return;
  const g = await api(`/api/works/${encodeURIComponent(W.id)}/cards/factcheck`, {});
  await watchBar('cardjob', g.job, async j => { if (j.status === 'done') { const w = await api(`/api/works/${encodeURIComponent(W.id)}`); W = w; C = w.cards; drawCards(); toast(`검증 끝: 고친 곳 ${j.result.issues}개`); } });
};
$('#b-rebuild').onclick = async () => { if (!confirm('설명글·캡션·배경을 처음부터 다시 만들까요? 지금 고친 내용은 사라져요.')) return; W.cards = null; C = null; drawCards(); };
function exportHtml(x) {
  return `<div class="exp-actions"><a class="btn pri" href="/api/works/${encodeURIComponent(W.id)}/zip" download>PNG 전체 받기 (zip + 캡션)</a>
      <button class="btn" onclick="navigator.clipboard.writeText(C.caption||'');toast('캡션을 복사했어요')">캡션 복사</button></div>
    <p class="hint">저장 위치: <code>작업/${esc(W.id)}/${esc(x.folder)}</code> · ${x.files.length}장 · ${esc(x.at)} · 그림을 누르면 한 장씩 받을 수 있어요</p>
    <div class="exp-list">${x.files.map(f => `<a href="${cardImg(x.folder, f)}" download="${esc(f)}"><img src="${cardImg(x.folder, f)}?t=${Date.now()}" alt=""></a>`).join('')}</div>`;
}
$('#b-export').onclick = async () => {
  if (!(await saveCards())) return;
  const g = await api(`/api/works/${encodeURIComponent(W.id)}/cards/export`, {});
  await watchBar('cardjob', g.job, async j => {
    if (j.status === 'done') { W.export = j.result; $('#export-result').innerHTML = exportHtml({...j.result, at: '방금'}); toast(`PNG ${j.result.files.length}장 저장했어요. 인스타에는 직접 올려 주세요(보안상 자동 발행 없음)`); }
  });
};

route();
