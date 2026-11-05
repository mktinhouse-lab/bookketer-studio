/* 북케터 밈 카드뉴스 스튜디오 — 북타쿠 스튜디오 흐름(수집 → 기획 후보 3개 → 캔버스 → 완성본)을 북케터 밈 형식으로 */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const state={mode:'book3',meta:null,posts:[],picks:new Set(),crawlFile:null,project:null};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>typeof v==='number'?v.toLocaleString('ko-KR'):null;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const nl=s=>String(s||'').replace(/\\n/g,'\n');
const hdrH=()=>document.documentElement.style.setProperty('--hdr',$('header').offsetHeight+'px');
try{new ResizeObserver(hdrH).observe($('header'))}catch(e){}hdrH();

async function api(url,opt){const r=await fetch(url,opt);
  if(r.status===401&&state.meta&&state.meta.remote){location.href='/login';throw new Error('공유 비밀번호를 다시 넣어 주세요.')}
  if(!r.ok){const t=await r.text();let m=t;try{const d=JSON.parse(t).detail;if(d)m=typeof d==='string'?d:JSON.stringify(d)}catch(e){}
    const e=new Error(String(m).slice(0,300));e.status=r.status;throw e}
  return r.json()}
const post=(u,b)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
function log(t){const l=$('#logbox');l.textContent+=t+'\n';if(l.textContent.length>300000)l.textContent=l.textContent.slice(-150000)}
const plainErr=m=>String(m||'').replace(/^Error: /,'').replace(/^\w*(Error|Exception): /,'');
function toast(msg,kind='',act){
  const el=document.createElement('div');el.className='toast '+kind;
  el.innerHTML=`<span>${esc(msg)}</span>${act?`<button class="btn sm">${esc(act.label)}</button>`:''}<button class="tx" title="닫기">×</button>`;
  const close=()=>el.remove();el.querySelector('.tx').onclick=close;
  if(act)el.querySelector('.btn').onclick=()=>{close();act.fn()};
  const box=$('#toasts');box.appendChild(el);while(box.children.length>4)box.firstChild.remove();
  setTimeout(close,kind==='bad'?9000:act?8000:4000);log((kind==='bad'?'✖ ':'')+msg);
}
function showErr(e){if(e&&e.job)return;
  toast(e instanceof TypeError?'서버에 연결하지 못했습니다. 검은 서버 창이 꺼졌다면 run.bat 을 다시 실행하세요.':plainErr(e&&e.message||e),'bad')}
function dialog(title,msg,buttons,opt={}){
  $('#dtitle').textContent=title;$('#dmsg').textContent=msg;const b=$('#dbtns');b.innerHTML='';
  $('#dlg .dic').textContent=opt.danger?'!':'✓';$('#dlg .dic').classList.toggle('danger',!!opt.danger);
  buttons.forEach(x=>{const el=document.createElement('button');el.className='btn '+(x.danger?'danger':x.pri?'pri':'');el.textContent=x.label;
    el.onclick=()=>{$('#dlg').classList.remove('open');x.fn&&x.fn()};b.appendChild(el)});
  $('#dlg').classList.add('open');
}

/* ---------- 작업 진행: 머리줄의 진행 원 — '62% 완료 · 약 2분 남음' ---------- */
const RUN={};
const ring=(p,cls='')=>`<span class="ring ${cls}${p==null?' spin':''}" style="--p:${p??0}"><i></i>${p==null||/\bxs\b/.test(cls)?'':`<b>${p}</b>`}</span>`;
function dur(sec){const n=Math.max(0,Math.round(sec));if(n>=90)return Math.round(n/60)+'분';if(n>=50)return '1분';return Math.max(10,Math.round(n/10)*10)+'초'}
const runPct=r=>!r?null:r.status==='done'?100:r.prog&&r.prog.pct!=null?r.prog.pct:null;
const running=id=>!!id&&!!RUN[id]&&RUN[id].status==='running';
function progText(r){
  if(!r)return '';if(r.status==='done')return '완료';if(r.status==='error')return '실패: '+r.error;
  const p=r.prog||{};if(p.pct==null)return (p.label&&r.opt.showLabel?p.label+' · ':'')+(r.opt.idle||`진행 중 · ${dur(r.elapsed)} 지남`);
  return `${p.pct}% 완료 · `+(p.over?'거의 다 됐어요':`약 ${dur(p.remaining)} 남음`);
}
const jobSub=r=>progText(r)+(r.status==='done'&&r.opt.go?' · 보기 →':'');
const jobTip=r=>{const p=r.prog||{};return `${r.label} — ${jobSub(r)}`+(r.status==='error'?' (눌러서 자세히 보기)':r.status==='running'&&p.label?` (지금 단계: ${p.label})`:'')};
function jobsPaint(){
  const box=$('#jobs'),list=Object.values(RUN),sig=list.map(r=>r.id+':'+r.status+':'+(runPct(r)==null?'i':'p')).join('|');
  if(box.dataset.sig===sig){list.forEach(r=>{const el=box.querySelector(`.job[data-id="${CSS.escape(r.id)}"]`);if(!el)return;const p=runPct(r);
      if(r.status==='running'&&p!=null){const rg=el.querySelector('.ring');rg.style.setProperty('--p',p);const b=rg.querySelector('b');if(b)b.textContent=p}
      el.querySelector('small').textContent=jobSub(r);el.title=jobTip(r)});return}
  box.dataset.sig=sig;box.classList.toggle('many',list.length>2);
  box.innerHTML=list.map(r=>{const icon=r.status==='done'?'<span class="ring ok" style="--p:100"><i></i><b>✓</b></span>':r.status==='error'?'<span class="ring bad" style="--p:100"><i></i><b>!</b></span>':ring(runPct(r));
    return `<div class="job ${r.status==='error'?'err':r.status==='done'?'ok':'run'}" data-id="${esc(r.id)}" title="${esc(jobTip(r))}">${icon}
      <div class="jt"><b>${esc(r.label)}</b><small>${esc(jobSub(r))}</small></div>${r.status!=='running'?'<button class="jx" title="닫기">×</button>':''}</div>`}).join('');
  $$('#jobs .job').forEach(el=>el.onclick=e=>{const r=RUN[el.dataset.id];if(!r)return;
    if(e.target.closest('.jx')){delete RUN[r.id];return jobsPaint()}
    if(r.status==='error')return dialog(r.label+' — 실패했습니다',r.error+(r.log.length?'\n\n[마지막 기록]\n'+r.log.slice(-6).join('\n'):''),[{label:'확인',pri:true}],{danger:true});
    if(r.opt.go)r.opt.go()});
}
async function runJob(start,label,opt={}){
  const id=typeof start==='string'?start:(await start).job;
  const r=RUN[id]={id,label,opt,prog:null,status:'running',elapsed:0,log:[],miss:0};
  const tick=()=>{jobsPaint();try{opt.onTick&&opt.onTick(r)}catch(e){}};
  const fail=m=>{r.status='error';r.error=plainErr(m);log('✖ 실패: '+r.error);const e=new Error(r.error);e.job=true;return e};
  log('▶ '+label);tick();
  try{while(true){let j;
      try{j=await api('/api/jobs/'+encodeURIComponent(id));r.miss=0}
      catch(e){if(e.status===404)throw fail('서버가 다시 시작되어 작업이 끊겼습니다. 다시 시도해 주세요.');
        if(++r.miss>=8)throw fail('서버와 연결이 끊겼습니다. 검은 서버 창이 켜져 있는지 확인하세요.');await sleep(2000);continue}
      (j.log||[]).slice(r.log.length).forEach(l=>{r.log.push(l);log(l)});
      r.prog=j.progress||null;r.elapsed=j.elapsed||0;
      if(j.status==='error')throw fail(j.error||'알 수 없는 오류');
      if(j.status==='done'){r.status='done';log('✔ '+label+' 완료');return j.result}
      tick();await sleep(1200)}}
  finally{tick();if(r.status==='done')setTimeout(()=>{if(RUN[id]===r){delete RUN[id];jobsPaint()}},opt.go?8000:3500)}
}
function btnRun(btn,r,word){
  if(!btn)return;
  if(r&&r.status==='running'){if(btn.dataset.label==null)btn.dataset.label=btn.innerHTML;
    const p=runPct(r);btn.disabled=true;btn.classList.add('running');btn.innerHTML=`${ring(p,'xs')}<span>${esc(word)}${p!=null?' '+p+'%':''}</span>`}
  else if(btn.dataset.label!=null){btn.innerHTML=btn.dataset.label;delete btn.dataset.label;btn.disabled=false;btn.classList.remove('running')}
}

/* ---------- 마크다운 (이미지 포함) ---------- */
function md(src,kind){
  src=src.replace(/<!--[\s\S]*?-->/g,'');
  const inl=s=>esc(s).replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,(m,a,p)=>`<img alt="${a}" loading="lazy" src="${kind?`/api/img/${kind}/${p.split('/').map(encodeURIComponent).join('/')}`:p}">`)
    .replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>');
  const L=src.split('\n');let h='',i=0;
  while(i<L.length){const l=L[i];let m;
    if(/^```/.test(l)){let b=[];i++;while(i<L.length&&!/^```/.test(L[i]))b.push(L[i++]);i++;h+='<pre>'+esc(b.join('\n'))+'</pre>';continue}
    if(m=l.match(/^(#{1,4})\s+(.*)/)){h+=`<h${m[1].length}>${inl(m[2])}</h${m[1].length}>`;i++;continue}
    if(/^\s*(---|\*\*\*)\s*$/.test(l)){h+='<hr>';i++;continue}
    if(/^\s*>/.test(l)){let b=[];while(i<L.length&&/^\s*>/.test(L[i]))b.push(L[i++].replace(/^\s*>\s?/,''));h+='<blockquote>'+b.map(inl).join('<br>')+'</blockquote>';continue}
    if(/^\s*\|/.test(l)){let rows=[];while(i<L.length&&/^\s*\|/.test(L[i]))rows.push(L[i++]);
      const cells=r=>r.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim());
      const body=rows.filter(r=>/[^\s:|-]/.test(r));
      h+='<table>'+body.map((r,k)=>'<tr>'+cells(r).map(c=>k?`<td>${inl(c)}</td>`:`<th>${inl(c)}</th>`).join('')+'</tr>').join('')+'</table>';continue}
    if(/^\s*([-*]|\d+\.)\s+/.test(l)){const ord=/^\s*\d+\./.test(l);let b=[];
      while(i<L.length&&/^\s*([-*]|\d+\.)\s+/.test(L[i]))b.push('<li>'+inl(L[i++].replace(/^\s*([-*]|\d+\.)\s+/,''))+'</li>');
      h+=(ord?'<ol>':'<ul>')+b.join('')+(ord?'</ol>':'</ul>');continue}
    if(!l.trim()){i++;continue}
    let b=[];while(i<L.length&&L[i].trim()&&!/^(#{1,4}\s|```|\s*>|\s*\||\s*([-*]|\d+\.)\s)/.test(L[i]))b.push(L[i++]);
    h+='<p>'+b.map(inl).join('<br>')+'</p>';
  }
  return '<div class="md">'+h+'</div>';
}

/* ---------- 게시물 카드 ---------- */
const imgUrl=(kind,folder,name)=>`/api/img/${kind}/${encodeURIComponent(folder)}/${encodeURIComponent(name)}`;
const folderOf=(n,suf='_assets')=>n.replace(/\.md$/,'')+suf;
function stat(label,v,icon){const f=fmt(v);return `<div class="stat ${f?'':'na'}"><b>${icon} ${f??'—'}</b><small>${label}</small></div>`}
function pcard(p,i,folder,opt={}){
  const cover=p.images&&p.images[0]?`<img loading="lazy" src="${imgUrl('crawl',folder,p.images[0])}">`
    :`<div class="fake">${esc((p.slides_text||[])[0]||p.caption||'')}</div>`;
  return `<div class="pcard" data-i="${i}">
    <div class="cover">${cover}<span class="rank">#${i}</span><span class="type">${esc(p.type||'게시물')} · ${p.slides||p.images.length}장${p.source==='샘플'?' · 더미':''}</span>
      ${opt.pick?'<button class="pick">선택</button>':''}</div>
    <div class="pb"><div class="who"><b>@${esc(p.author||'알 수 없음')}</b> · ${esc(p.date||'')}</div>
      <div class="stats">${stat('좋아요',p.likes,'♥')}${stat('댓글',p.comments,'💬')}${p.views!=null?stat('조회수',p.views,'▶'):stat('공유',p.shares,'↗')}</div>
      <div class="cap">${esc(p.caption||'(캡션 없음)')}</div>
      <div class="acts"><button class="btn sm detail">상세 보기</button>${opt.pick?'<button class="btn sm var">카피 베리에이션</button>':''}${p.url?`<a href="${esc(p.url)}" target="_blank">원본 ↗</a>`:''}</div></div></div>`;
}
const grid=(posts,folder,opt)=>posts.map((p,i)=>pcard(p,i+1,folder,opt)).join('');
function openModal(p,folder){
  const imgs=(p.images||[]).map(n=>`<img src="${imgUrl('crawl',folder,n)}">`).join('')
    ||`<div class="hint" style="color:#fff;padding:20px">${(p.slides_text||[]).map(esc).join('<br>')||'이미지 없음'}</div>`;
  $('#mbox').innerHTML=`<div class="gal"><div class="strip">${imgs}</div><div class="cnt">좌우로 넘겨 슬라이드 확인</div></div>
   <div class="minfo"><div class="who"><b>@${esc(p.author)}</b> · ${esc(p.date||'')} · ${esc(p.type||'')}</div>
    <div class="stats">${stat('좋아요',p.likes,'♥')}${stat('댓글',p.comments,'💬')}${stat('조회수',p.views,'▶')}</div>
    <div><h3>캡션</h3><div class="cap" style="-webkit-line-clamp:unset;display:block;margin-top:6px">${esc(p.caption||'(없음)')}</div></div>
    <div><h3>댓글 (${(p.top_comments||[]).length})</h3>${(p.top_comments||[]).map(c=>`<div class="cmt">${esc(c)}</div>`).join('')||'<div class="hint">수집된 댓글이 없습니다.</div>'}</div>
    ${p.url?`<a href="${esc(p.url)}" target="_blank">인스타그램에서 원본 열기 ↗</a>`:''}</div>`;
  $('#modal').classList.add('open');
}
const closeModal=()=>$('#modal').classList.remove('open');
$('#mx').onclick=closeModal;$('#modal').onclick=e=>{if(e.target.id==='modal')closeModal()};
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});

/* ---------- 레퍼런스 썸네일 카피 베리에이션 ---------- */
async function variations(i,folder,btn){
  const p=state.posts[i-1];if(!p)return;
  if(needClaude('카피 베리에이션은 AI가 만들어요. [Claude 로그인 창 열기]로 먼저 로그인해 주세요.'))return;
  const topic=($('#pj-thumb').value||$('#pj-name').value||$('#pj-message').value||'').trim();
  let res=null;
  try{res=await runJob(post('/api/variations',{crawl_file:state.crawlFile,n:i,topic,mode:state.mode}),`카피 베리에이션 · @${p.author||'레퍼런스'}`,
      {onTick:rr=>btnRun(btn,rr,'만드는 중'),go:()=>showVariations(res)});showVariations(res)}
  catch(e){showErr(e)}
}
function showVariations(r){
  if(!r)return;const img=(r.ref.images||[])[0];
  $('#vx-body').innerHTML=`<div class="vxhead">${img?`<img src="${imgUrl('crawl',folderOf(r.crawl_file),img)}">`:''}<div>
      <div class="hint">@${esc(r.ref.author||'')} · ♥ ${fmt(r.ref.likes)??'—'} ${r.ref.url?`· <a href="${esc(r.ref.url)}" target="_blank">원본 ↗</a>`:''}</div>
      <div class="vxo">${mk(r.original)}</div><div style="margin-top:6px"><b>공식</b> ${esc(r.formula)}</div>
      ${r.topic?`<div class="hint">우리 주제: ${esc(r.topic)}</div>`:''}</div></div>
    <ol class="vxl">${r.variations.map((v,k)=>`<li class="${k+1===r.recommend?'rec':''}"><div><div class="vc">${mk(v.copy)}</div><div class="vw">${k+1===r.recommend?'<b>추천</b> · ':''}${esc(v.why)}</div></div>
      <button class="btn sm vcp" data-k="${k}">복사</button><button class="btn sm pri vuse" data-k="${k}">이 카피로</button></li>`).join('')}</ol>
    <div class="hint">[이 카피로]를 누르면 1번의 썸네일 카피 칸에 들어가고, 책 찾기·기획에 그대로 쓰입니다. 결과는 결과 보기 › 기획 칸에 md로도 저장돼 있어요.</div>`;
  const plain=s=>nl(s).replace(/\[\[|\]\]|\{\{|\}\}/g,'');
  $$('#vx-body .vcp').forEach(b=>b.onclick=()=>{navigator.clipboard.writeText(plain(r.variations[+b.dataset.k].copy));toast('복사했습니다.','ok')});
  $$('#vx-body .vuse').forEach(b=>b.onclick=()=>{const c=nl(r.variations[+b.dataset.k].copy);
    $('#pj-thumb').value=c.replace(/\n/g,' ');if(!$('#pj-name').value.trim())$('#pj-name').value=plain(c).replace(/\n/g,' ').slice(0,30);
    $('#vx').classList.remove('open');tab('work');
    if(fkind()!=='books'){state.mode='book3';renderFormats();renderReady()}
    $('#pj-thumb').scrollIntoView({behavior:'smooth',block:'center'});toast('썸네일 카피 칸에 넣었어요. 이제 [AI로 책 찾기]를 눌러 보세요.','ok')});
  $('#vx').classList.add('open');
}
$('#vx-close').onclick=()=>$('#vx').classList.remove('open');
$('#vx').onclick=e=>{if(e.target.id==='vx')$('#vx').classList.remove('open')};

/* ---------- 1. 알릴 내용(프로젝트) · 형식 ---------- */
const PJ=['name','message','details','cta','proof','books','book_title','book_author','kw_count','thumb'];
function radio(name,items,cur,on){const box=$('#'+name);box.innerHTML='';
  Object.entries(items).forEach(([k,v])=>{const l=document.createElement('label');l.className='opt';
    l.innerHTML=`<input type="radio" name="${name}" value="${k}" ${k===cur?'checked':''}> ${esc(v)}`;l.querySelector('input').onchange=()=>on(k);box.appendChild(l)})}
state.sumType='keyword';state.copyStyle='auto';
const projectNow=()=>({...Object.fromEntries(PJ.map(k=>[k,$('#pj-'+k).value.trim()])),kw_count:+$('#pj-kw_count').value||10,summary_type:state.sumType,copy_style:state.copyStyle,fmt:state.mode});
function projFill(p){PJ.forEach(k=>$('#pj-'+k).value=(p&&p[k]!=null?p[k]:'')||(k==='kw_count'?10:''));state.project=p&&p.id?p.id:null;
  state.sumType=(p&&p.summary_type)||'keyword';state.copyStyle=(p&&p.copy_style)||'auto';if(p&&p.fmt&&state.meta&&state.meta.formats[p.fmt])state.mode=p.fmt;
  if(state.meta){renderFormats();renderReady()}}
const fkind=()=>((state.meta&&state.meta.formats[state.mode])||{}).kind||'free';
const ftags=mode=>((state.meta&&state.meta.formats[mode||state.mode])||{}).tags||[];
const COPY_STYLES={auto:'자동 (기존 게시물처럼)',story:'줄거리 훅 (설정 → 근데 → 드러나요)',personal:'개인 감상 (읽고 나서 남은 것)',persona:'성격 진단 (이런 사람에게)',prescribe:'처방 순서 (이 순서로 읽어요)'};
function renderFormats(){
  const F=state.meta.formats;if(!F[state.mode])state.mode='book3';
  $('#formats').innerHTML=Object.entries(F).map(([k,f])=>`<div class="fmt ${k===state.mode?'on':''}" data-k="${k}"><span class="fk ${f.kind==='free'?'free':''}">${f.kind==='free'?'자유 형식':'북케터 밈 형식'}</span>
    <b>${esc(f.name)}</b><small>${esc(f.desc)}</small>${f.ref?`<a href="${esc(f.ref)}" target="_blank">기준 게시물 보기 ↗</a>`:''}</div>`).join('');
  $$('#formats .fmt').forEach(el=>el.onclick=e=>{if(e.target.closest('a'))return;state.mode=el.dataset.k;try{localStorage.setItem('bk-mode',state.mode)}catch(_){}renderFormats();renderReady()});
  const k=fkind();
  $('#fmt-books').classList.toggle('hidden',k!=='books');$('#fmt-summary').classList.toggle('hidden',k!=='summary');
  $('#fmt-assets').classList.toggle('hidden',k==='free');$('#btn-fmt-plan').classList.toggle('hidden',k==='free');
  radio('copy-style',COPY_STYLES,state.copyStyle,v=>state.copyStyle=v);
  radio('sum-type',{keyword:'키워드 요약 (트렌드·개념서)',selfhelp:'자기계발 핵심 요약'},state.sumType,v=>state.sumType=v);
  const f=F[state.mode];
  $('#fmt-hint').innerHTML=k==='free'?`구성: ${esc(f.desc)}. 첫 장 = 썸네일(사진 + 연두 라벨 + 흰 헤드라인), 마지막 장 = 팔로우·댓글 유도 장. <code>assets/cta.png</code>를 넣어 두면 마지막 장으로 그 이미지를 씁니다. 2번에서 레퍼런스를 골라야 기획할 수 있어요.`
    :`구성: ${esc(f.desc)}. 표지는 왼쪽 위 흰 라벨(${f.tags.map(esc).join(' · ')}) + 아래 큰 헤드라인. ${k==='books'?'<b>책 목록을 비워 두고 2번에서 레퍼런스를 고른 뒤 [선택한 레퍼런스로 기획하기]</b>를 누르면 썸네일 카피 베리에이션 → 책 찾기(교보문고 확인) → 책 소개 작성까지 AI가 한 번에 해요.':'2번에서 레퍼런스를 고르면 그 훅도 참고하고, 안 골라도 <b>[이 형식으로 바로 기획하기]</b>로 만들 수 있어요.'}`;
  const r=state.meta.ready,v=Date.now();
  $$('.asset').forEach(a=>{const key=a.dataset.key;a.querySelector('.aimg').style.backgroundImage=r[key]?`url('/api/assets/${key}?v=${v}')`:'';
    const del=a.querySelector('.adel');if(del)del.classList.toggle('hidden',!r[key])});
}
/* 책 찾기: 썸네일 카피·장르 → AI 후보 + 교보문고 확인 → 체크하면 책 목록에 */
const bookLine=b=>`${b.title} / ${b.author}${b.memo?' / '+b.memo:''}`;
const bookKey=s=>s.split('/')[0].replace(/\s+/g,'').toLowerCase();
function bfListed(){return $('#pj-books').value.split('\n').map(s=>s.trim()).filter(Boolean)}
function bfToggle(b,on){let L=bfListed();const key=bookKey(b.title);L=L.filter(l=>bookKey(l)!==key);if(on)L.push(bookLine(b));$('#pj-books').value=L.join('\n')}
function bfPaint(r){
  const want=(state.meta.formats[state.mode]||{}).count||3,have=new Set(bfListed().map(bookKey));
  const kt=b=>bookKey(b.title);
  $('#bf-list').innerHTML=`<div class="bsum"><b>AI가 고른 기준</b> ${esc(r.summary)} <span class="hint">· ${want}권을 체크하세요 (지금 ${have.size}권) · <a href="#" class="bf-md">md 기록 보기</a></span></div>`+
    r.books.map((b,i)=>{const k=b.kyobo||{},ok=k.verified&&!k.outofprint&&k.author_ok!==false,on=have.has(kt(b));
      return `<label class="bk ${on?'on':''} ${ok?'':'warn'}" data-i="${i}">${k.img?`<img loading="lazy" src="${esc(k.img)}">`:'<div class="noc"></div>'}
        <div><b>${esc(b.title)}</b><div class="hint">${esc(b.author)}${b.translator?' · '+esc(b.translator)+' 옮김':''}</div>
        <div class="chips"><span class="badge ${ok?'ok':'no'}">교보 ${esc(k.note||'확인 못 함')}</span>${k.rating?`<span class="badge">★ ${esc(k.rating)} (${esc(k.reviews)})</span>`:''}${b.tone?`<span class="badge">${esc(b.tone)}</span>`:''}</div>
        <div>${esc(b.why)}</div><div class="hint">훅: ${esc(b.hook)}</div><div class="hint">${esc((b.tags||[]).join(' '))}</div>
        ${k.link?`<a href="${esc(k.link)}" target="_blank" class="hint">교보문고 ↗</a>`:''}</div>
        <input type="checkbox" ${on?'checked':''}></label>`}).join('');
  $$('#bf-list .bk').forEach(el=>{const b=r.books[+el.dataset.i],cb=el.querySelector('input');
    el.querySelectorAll('a').forEach(a=>a.onclick=e=>e.stopPropagation());
    cb.onchange=()=>{const k=b.kyobo||{};
      if(cb.checked&&!(k.verified&&!k.outofprint))toast(`'${b.title}'은(는) 교보문고에서 ${k.note||'확인되지 않았어요'}. 실제 책인지 꼭 확인하세요.`,'bad');
      bfToggle({title:b.title,author:b.author,memo:b.hook},cb.checked);bfPaint(r)}});
  const m=$('#bf-list .bf-md');if(m)m.onclick=e=>{e.preventDefault();tab('files');openFile('analysis',r.file)};
}
$('#btn-bfind').onclick=async()=>{
  const topic=$('#pj-thumb').value.trim();if(!topic)return toast('썸네일 카피나 장르를 먼저 적어 주세요.','bad');
  if(needClaude('책 찾기는 AI가 웹을 검색해서 해요. [Claude 로그인 창 열기]로 먼저 로그인해 주세요.'))return;
  const want=(state.meta.formats[state.mode]||{}).count||3;
  try{const r=await runJob(post('/api/books/find',{topic,count:want,prefs:$('#bf-prefs').value.trim(),exclude:bfListed().map(l=>l.split('/')[0].trim())}),
      `책 찾기 · ${topic.slice(0,16)}`,{onTick:rr=>btnRun($('#btn-bfind'),rr,'책 찾는 중')});
    state.bfind=r;bfPaint(r);if(!$('#pj-name').value.trim())$('#pj-name').value=topic.slice(0,30);
    toast(`후보 ${r.books.length}권을 찾았어요. 마음에 드는 ${want}권을 체크하세요.`,'ok')}
  catch(e){showErr(e)}
};

$$('.asset').forEach(a=>{const key=a.dataset.key;
  a.querySelector('input[type=file]').onchange=async e=>{const f=e.target.files[0];if(!f)return;
    try{await post('/api/assets/'+key,{data:await readFile(f)});await loadMeta(true);toast('저장했습니다. 다음 완성본부터 이 사진을 씁니다.','ok')}catch(err){showErr(err)}e.target.value=''};
  const del=a.querySelector('.adel');if(del)del.onclick=async()=>{await api('/api/assets/'+key,{method:'DELETE'});await loadMeta(true)}});
function projSelect(){
  const ps=state.meta.projects,sel=$('#proj-sel');
  sel.innerHTML='<option value="">— 저장한 프로젝트 불러오기 —</option>'+Object.values(ps).map(p=>`<option value="${esc(p.id)}" ${p.id===state.project?'selected':''}>${esc(p.name)}</option>`).join('');
}
$('#proj-sel').onchange=e=>{const p=state.meta.projects[e.target.value];if(p){projFill(p);try{localStorage.setItem('bk-proj',p.id)}catch(_){}}};
$('#proj-new').onclick=()=>{projFill(null);$('#proj-sel').value='';$('#pj-name').focus()};
$('#proj-save').onclick=async()=>{const p=projectNow();if(!p.name)return toast('주제(이름)를 입력하세요.','bad');
  try{const r=await post('/api/projects',{...p,id:state.project});state.meta.projects[r.id]=r;state.project=r.id;projSelect();
    try{localStorage.setItem('bk-proj',r.id)}catch(_){}$('#proj-msg').textContent='저장했습니다 ✓';setTimeout(()=>$('#proj-msg').textContent='',2000)}catch(e){showErr(e)}};
$('#proj-del').onclick=()=>{if(!state.project)return toast('지울 프로젝트를 먼저 고르세요.','bad');
  dialog('이 프로젝트를 지울까요?','저장한 입력값만 지워집니다. 이미 만든 기획·완성본은 그대로 남습니다.',[{label:'삭제',danger:true,fn:async()=>{
    await api('/api/projects/'+state.project,{method:'DELETE'});delete state.meta.projects[state.project];projFill(null);projSelect()}},{label:'취소'}],{danger:true})};
function renderReady(){
  $('#fmt-lbl').innerHTML=`지금 고른 형식만 찾기: <b>${state.mode==='single'?'단일 카드뉴스 (2장 이하)':'캐러셀 카드뉴스 (3장 이상)'}</b> <span style="opacity:.75">(끄면 구분 없이, 릴스 2개까지)</span>`;
  const m=state.meta,r=m.ready,b=(ok,t)=>`<span class="badge ${ok?'ok':'no'}">${ok?'✔':'✖'} ${t}</span>`;
  $('#ready').innerHTML=b(m.claude.logged_in,m.claude.logged_in?`Claude 연결${m.claude.email?' · '+esc(m.claude.email):''} (구독)`:'Claude 로그인 필요')
    +(m.claude.logged_in||m.remote?'':'<button class="btn sm pri" id="btn-clogin">Claude 로그인 창 열기</button>')
    +b(r.prompts[state.mode],`지침 prompts/${state.mode}.md`)+b(r.brand,'브랜드 가이드 brand_guide.md')
    +`<span class="badge ${r.cta?'ok':''}">${r.cta?'✔ 마지막 장 이미지 assets/cta.png':'마지막 장: 자동 생성 (assets/cta.png 없음)'}</span>`;
  const bl=$('#btn-clogin');if(bl)bl.onclick=claudeLogin;
  const off=!m.claude.logged_in;
  $('#btn-claude-top').classList.toggle('hidden',!off||!!m.remote);$('#claude-remote').classList.toggle('hidden',!off||!m.remote);
}
let cloginBusy=false;
async function claudeLogin(){
  if(cloginBusy)return toast('로그인 창이 이미 열려 있어요. 작업 표시줄에서 검은 창을 찾아 주세요.');
  try{cloginBusy=true;await post('/api/claude/login',{});
    dialog('로그인 창을 열었습니다','작업 표시줄에 새로 뜬 검은 창(Claude 로그인)을 열어 안내대로 진행하세요.\n브라우저가 열리면 Claude 구독 계정으로 로그인하고 [승인]을 누르면 끝나요. 끝나면 이 화면이 자동으로 바뀝니다.',[{label:'확인',pri:true}]);
    for(let k=0;k<72;k++){await sleep(5000);await loadMeta(true);if(state.meta.claude.logged_in){toast('Claude 에 연결됐습니다. 이제 AI 기능을 쓸 수 있어요.','ok');break}}}
  catch(e){showErr(e)}finally{cloginBusy=false}
}
const needClaude=msg=>{if(state.meta.claude.logged_in)return false;
  dialog('Claude 로그인이 필요합니다',state.meta.remote?msg.replace(/\[Claude 로그인 창 열기\]로 /,'')+'\n\n로그인 창은 서버가 켜진 PC 에 떠서, 그 PC 에서 한 번 로그인해야 해요.':msg,
    state.meta.remote?[{label:'확인',pri:true}]:[{label:'Claude 로그인 창 열기',pri:true,fn:claudeLogin},{label:'닫기'}]);return true};
async function loadMeta(quiet){
  state.meta=await api('/api/meta');
  if(!quiet){try{state.mode=localStorage.getItem('bk-mode')||state.mode}catch(_){}
    let pid=null;try{pid=localStorage.getItem('bk-proj')}catch(_){}if(pid&&state.meta.projects[pid])projFill(state.meta.projects[pid])}
  projSelect();renderFormats();
  const rm=!!state.meta.remote;   // 공유 링크로 들어온 사람: 이 PC 에 창이 뜨는 기능은 숨김
  $('#remote-badge').classList.toggle('hidden',!rm);$('#btn-share').classList.toggle('hidden',rm);
  ['#btn-login','#pub-open'].forEach(x=>$(x).classList.toggle('hidden',rm));
  if(!rm)sharePaint(state.meta.share);
  const s=state.meta.session;$('#sess').textContent=s.logged_in?`● 인스타그램 세션 저장됨 (${s.saved_at})`:s.expired?'● 인스타그램 세션 만료':'● 인스타그램 세션 없음';
  $('#sess').className='badge '+(s.logged_in?'ok':'no');$('#headless').checked=!!state.meta.settings.headless;
  renderReady();
}
$('#headless').onchange=e=>post('/api/settings',{headless:e.target.checked}).catch(showErr);

/* ---------- 공유 링크 (Cloudflare 빠른 터널 + 비밀번호) — 이 PC 에서만 켜고 끈다 ---------- */
function sharePaint(st){
  if(!st)return;state.share=st;
  const b=$('#btn-share');b.classList.toggle('on',!!st.on);b.textContent=st.on?'🔗 공유 중':'🔗 공유';
  $('#sh-pwnote').textContent=st.has_password?'비밀번호가 정해져 있어요. 바꾸면 팀원은 새 비밀번호로 다시 들어와야 해요.':'처음이면 비밀번호부터 정해 주세요. 링크와 함께 팀원에게 알려 주면 됩니다.';
  $('#sh-state').innerHTML=st.on?(st.url?`<b style="color:var(--ok)">● 공유 중</b> — 아래 링크를 팀원에게 보내 주세요. (${esc(st.since)}부터 같은 주소)`:'링크를 만드는 중…')
    :st.error?`<span style="color:var(--bad)">${esc(st.error)}</span>`:!st.tool?'<span style="color:var(--bad)">공유 도구(tools/cloudflared.exe)가 아직 없습니다.</span>':'지금은 공유가 꺼져 있습니다.';
  $('#sh-urlrow').classList.toggle('hidden',!(st.on&&st.url));$('#sh-url').value=st.url||'';
  $('#sh-start').classList.toggle('hidden',!!st.on);$('#sh-stop').classList.toggle('hidden',!st.on);
  $('#sh-start').disabled=!st.has_password||!st.tool;
}
$('#btn-claude-top').onclick=claudeLogin;
$('#btn-share').onclick=async()=>{$('#shx').classList.add('open');try{sharePaint(await api('/api/share'))}catch(e){showErr(e)}};
$('#sh-close').onclick=()=>$('#shx').classList.remove('open');
$('#shx').onclick=e=>{if(e.target.id==='shx')$('#shx').classList.remove('open')};
$('#sh-pwsave').onclick=async()=>{const pw=$('#sh-pw').value;if(pw.trim().length<4)return toast('비밀번호는 4글자 이상으로 정해 주세요.','bad');
  try{sharePaint(await post('/api/share/password',{password:pw}));$('#sh-pw').value='';toast('공유 비밀번호를 저장했습니다.','ok')}catch(e){showErr(e)}};
$('#sh-start').onclick=async()=>{const b=$('#sh-start');b.disabled=true;b.textContent='링크 만드는 중…';
  try{const st=await post('/api/share/start',{});sharePaint(st);if(st.url)toast('공유 링크를 만들었습니다. [링크 복사]로 팀원에게 보내 주세요.','ok')}
  catch(e){showErr(e)}finally{b.textContent='공유 시작';sharePaint(state.share)}};
$('#sh-stop').onclick=()=>dialog('공유를 끌까요?','지금 링크로 들어와 있는 팀원은 더 이상 쓸 수 없게 됩니다. 다시 켜면 새 주소가 만들어져요.',
  [{label:'공유 끄기',danger:true,fn:async()=>{try{sharePaint(await post('/api/share/stop',{}));toast('공유를 껐습니다.','ok')}catch(e){showErr(e)}}},{label:'취소'}],{danger:true});
$('#sh-copy').onclick=()=>{navigator.clipboard.writeText($('#sh-url').value);$('#sh-copy').textContent='복사됨 ✓';setTimeout(()=>$('#sh-copy').textContent='링크 복사',1500)};
setInterval(()=>{if(state.meta&&!state.meta.remote&&document.visibilityState==='visible')api('/api/share').then(sharePaint).catch(()=>{})},60000);

/* ---------- 2. 수집 ---------- */
async function fillSelect(kind,sel,keep){
  const f=await api('/api/files/'+kind);const s=$(sel);
  s.innerHTML=f.length?f.map(x=>`<option>${esc(x.name)}</option>`).join(''):'<option value="">(파일 없음)</option>';
  if(keep&&f.some(x=>x.name===keep))s.value=keep;return f;
}
async function loadPosts(){
  const name=$('#crawl-sel').value;state.picks=new Set();$('#npick').textContent=0;$('#crawl-sum').textContent='';
  if(!name){$('#posts').innerHTML='<div class="empty" style="grid-column:1/-1">아직 수집한 결과가 없습니다. 위에서 검색어나 링크로 수집해 보세요.</div>';return}
  const d=(await api('/api/file/crawl/'+encodeURIComponent(name))).data||{};
  state.crawlFile=name;state.posts=d.posts||[];
  $('#crawl-sum').textContent=`${d.source||''} · ${state.posts.length}개`+(d.params&&d.params['최소 좋아요']!=null?` · 최소 좋아요 ${fmt(d.params['최소 좋아요'])}`:'');
  const folder=folderOf(name),sample=state.posts.length&&state.posts.every(p=>p.source==='샘플');
  const note=sample?`<div class="empty" style="grid-column:1/-1;text-align:left;border-color:var(--warn)"><b>지금 보이는 건 화면 확인용 샘플(더미)이라 사진이 없어요.</b><br>
    실제 레퍼런스 사진·댓글은 ① 위의 <b>[로그인 세션 저장]</b>으로 인스타그램에 로그인하고 ② 검색어를 넣어 <b>[검색해서 수집]</b>을 누르면 들어옵니다.
    ${state.meta.session.logged_in?'':'<div style="margin-top:10px"><button class="btn sm pri" id="sample-login">지금 인스타 로그인하기</button></div>'}</div>`:'';
  $('#posts').innerHTML=note+grid(state.posts,folder,{pick:true})||'<div class="empty" style="grid-column:1/-1">조건에 맞는 게시물이 없습니다. 최소 좋아요를 낮추거나 [새로 찾기]를 눌러 보세요.</div>';
  $$('#posts .pcard').forEach(el=>{const i=+el.dataset.i;
    el.querySelector('.pick').onclick=()=>{
      if(state.picks.has(i))state.picks.delete(i);else if(state.picks.size<3)state.picks.add(i);else return toast('레퍼런스는 최대 3개까지 선택할 수 있습니다.','bad');
      el.classList.toggle('sel',state.picks.has(i));el.querySelector('.pick').textContent=state.picks.has(i)?'✓ 선택됨':'선택';$('#npick').textContent=state.picks.size};
    el.querySelector('.detail').onclick=()=>openModal(state.posts[i-1],folder);
    el.querySelector('.var').onclick=()=>variations(i,folder,el.querySelector('.var'));
    el.querySelector('.cover').ondblclick=()=>openModal(state.posts[i-1],folder)});
  const sl=$('#sample-login');if(sl)sl.onclick=()=>$('#btn-login').click();
}
function showResults(){$('#results-top').scrollIntoView({behavior:'smooth',block:'start'});
  $$('#posts .pcard').forEach((c,k)=>c.animate([{opacity:0,transform:'translateY(14px)'},{opacity:1,transform:'none'}],{duration:350,delay:k*40,fill:'backwards'}))}
const needSession=()=>{if(!state.meta.session.logged_in){toast('먼저 [로그인 세션 저장]을 눌러 인스타그램에 로그인하세요.','bad');return true}return false};
async function crawlJob(start,label,btn){
  const btns=[$('#btn-tag'),$('#btn-tag-new'),$('#btn-urls')];
  try{const r=await runJob(start,label,{go:()=>{tab('work');showResults()},onTick:rr=>btns.forEach(b=>b===btn?btnRun(b,rr,'수집 중'):(b.disabled=rr.status==='running'))});
    if(state.picks.size&&btn!==$('#btn-urls')){await fillSelect('crawl','#crawl-sel',state.crawlFile);
      return toast(`${label} 완료 · ${r.count}개. 지금 고른 레퍼런스는 그대로 둡니다.`,'ok',{label:'새 결과 보기',fn:async()=>{$('#crawl-sel').value=r.file;await loadPosts();tab('work');showResults()}})}
    await fillSelect('crawl','#crawl-sel',r.file);await loadPosts();
    if(!$('#v-work').classList.contains('hidden'))showResults();toast(`${label} 완료 · ${r.count}개`,'ok');return r;
  }catch(e){showErr(e)}finally{btns.forEach(b=>{if(!b.dataset.label)b.disabled=false})}
}
async function loginJob(start){
  try{await runJob(start,'인스타그램 로그인',{idle:'열린 크롬 창에서 로그인한 뒤 그 창을 닫아 주세요',showLabel:false,onTick:r=>btnRun($('#btn-login'),r,'로그인 창 기다리는 중')});
    await loadMeta(true);toast('인스타그램 로그인 세션을 저장했습니다.','ok')}catch(e){showErr(e)}
}
$('#btn-login').onclick=async()=>{await loadMeta(true);
  const go=()=>loginJob(post('/api/session/login',{}));
  if(state.meta.session.logged_in)return dialog('이미 로그인되었습니다','로그인 세션이 저장되어 있어 바로 수집할 수 있습니다.',[{label:'확인',pri:true},{label:'다른 계정으로 다시 로그인',fn:go}]);
  go()};
const tagCrawl=fresh=>()=>{
  const kw=$('#kw').value.trim();if(!kw)return toast('검색어를 입력하세요.','bad');if(needSession())return;
  const fmtv=$('#fmt-only').checked?(state.mode==='single'?'single':'long'):null;
  crawlJob(post('/api/crawl/search',{keyword:kw,min_likes:+$('#minl').value||0,recent_days:+$('#days').value||0,fresh,fmt:fmtv}),
    `${kw} ${fresh?'새로 찾기':'수집'}${fmtv?(fmtv==='long'?' (롱폼)':' (단일)'):''}`,fresh?$('#btn-tag-new'):$('#btn-tag'))};
$('#btn-tag').onclick=tagCrawl(false);$('#btn-tag-new').onclick=tagCrawl(true);
$('#kw').onkeydown=e=>{if(e.key==='Enter')tagCrawl(false)()};
$('#btn-urls').onclick=async()=>{
  const urls=$('#urls').value.split('\n').map(s=>s.trim()).filter(Boolean);if(!urls.length)return toast('레퍼런스 게시물 링크를 붙여넣어 주세요.','bad');
  const go=$('#urls-plan').checked;
  if(go&&needClaude('바로 기획하려면 Claude 로그인이 필요해요. [바로 기획] 체크를 끄면 가져오기만 할 수 있어요.'))return;
  const r=await crawlJob(post('/api/crawl/urls',{urls}),`링크 ${urls.length}개 가져오기`,$('#btn-urls'));
  if(!r||!go)return;
  if(!r.count)return toast('가져온 게시물이 없어 기획하지 않았어요. 비공개·삭제된 게시물인지 확인하세요.','bad');
  const n=Math.min(3,r.count);
  $$('#posts .pcard').forEach(el=>{const i=+el.dataset.i;if(i<=n){state.picks.add(i);el.classList.add('sel');el.querySelector('.pick').textContent='✓ 선택됨'}});
  $('#npick').textContent=state.picks.size;
  if(r.count>3)toast('레퍼런스는 3개까지라 좋아요 높은 3개로 기획해요.','bad');
  $('#btn-plan').onclick(true)};
$('#crawl-sel').onchange=loadPosts;
$('#crawl-reload').onclick=async()=>{await fillSelect('crawl','#crawl-sel');loadPosts()};

/* ---------- 캔버스: 북케터 밈 썸네일 틀 (1080×1350) ----------
   사진 전체 + 아래쪽 어둡게 + 연두 라벨 + 흰 헤드라인(가운데, [[강조]]는 연두) + 흰 말풍선(검정 테두리) */
const CW=1080,CH=1350,CZ=0.5;
const T={font:'Pretendard',fb:'Malgun Gothic',white:'#ffffff',mint:'#b9f6a8',red:'#ff3b30',pill:'#c8f6c2',shadeA:90,bottom:130,width:960,min:64,max:104,lh:1.2};
const CPROPS=['name','raw','editable','selectable','evented','lockRotation','shadeDir','shadeA','pin','rel'];
const EDITABLE=['text','pill','callout','free','tagbox'];
const CV={c:null,meta:{},cands:[],dirty:false,token:0,card:null};
const byName=n=>CV.c.getObjects().filter(o=>o.name===n);
const hex=c=>{try{return '#'+new fabric.Color(typeof c==='string'?c:'#ffffff').toHex()}catch(e){return '#ffffff'}};
let fontsReady=null;
const cvFonts=()=>fontsReady||(fontsReady=Promise.all(['800','600','500'].map(w=>document.fonts.load(`${w} 40px Pretendard`))).catch(()=>{}));
const cvFont=(w='800')=>({fontFamily:`${T.font}, ${T.fb}`,fontWeight:w});
function cvTidy(o){o.setControlsVisibility&&o.setControlsVisibility({mtr:false});o.set({lockRotation:true})}
function parseMarkup(raw){   // [[강조]] → Fabric 글자별 스타일
  const lines=nl(raw).split('\n'),styles={},out=[];
  lines.forEach((line,li)=>{const ch=Array.from(line);let txt=[],hl=false,st={};
    let red=false;
    for(let i=0;i<ch.length;i++){if(ch[i]==='['&&ch[i+1]==='['){hl=true;i++;continue}if(ch[i]===']'&&ch[i+1]===']'){hl=false;i++;continue}
      if(ch[i]==='{'&&ch[i+1]==='{'){red=true;i++;continue}if(ch[i]==='}'&&ch[i+1]==='}'){red=false;i++;continue}
      if(hl)st[txt.length]={fill:T.mint};else if(red)st[txt.length]={fill:T.red};txt.push(ch[i])}
    out.push(txt.join(''));if(Object.keys(st).length)styles[li]=st});
  return {text:out.join('\n'),styles};
}
function shadeFill(dir,a){const al=a/100;if(dir==='all')return `rgba(0,0,0,${(al*.7).toFixed(2)})`;
  let stops=[{offset:0,color:'rgba(0,0,0,0)'},{offset:.4,color:'rgba(0,0,0,0)'},{offset:.62,color:`rgba(0,0,0,${al*.5})`},{offset:.92,color:`rgba(0,0,0,${al})`},{offset:1,color:`rgba(0,0,0,${al})`}];
  if(dir==='top')stops=stops.map(s=>({offset:1-s.offset,color:s.color})).reverse();
  return new fabric.Gradient({type:'linear',gradientUnits:'pixels',coords:{x1:0,y1:0,x2:0,y2:CH},colorStops:stops})}
function headline(raw,o={}){
  const {bottom=T.bottom,max=T.max,...rest}=o,{text,styles}=parseMarkup(raw),f=cvFont();
  const w100=Math.max(...text.split('\n').map(l=>new fabric.Text(l||' ',{fontSize:100,...f}).width));
  const size=rest.fontSize||Math.round(Math.min(max,Math.max(T.min,T.width/w100*100)));
  const t=new fabric.Textbox(text,{name:'text',raw,left:CW/2,originX:'center',top:0,width:T.width+60,fontSize:size,...f,fill:T.white,textAlign:'center',
    lineHeight:T.lh,styles,editable:false,shadow:new fabric.Shadow({color:'rgba(0,0,0,0.35)',blur:18,offsetX:0,offsetY:2}),...rest});
  if(rest.top==null)t.set({top:CH-bottom-t.height});cvTidy(t);return t}
function box(kind,raw,o={}){
  const pill=kind==='pill',tag=kind==='tagbox';
  const txt=new fabric.Text(nl(raw),{fontSize:pill?36:tag?28:34,...cvFont(pill?'600':tag?'700':'500'),fill:'#1a1a1a',textAlign:'center',lineHeight:1.3,originX:'center',originY:'center',left:0,top:0});
  const px=pill?16:tag?26:30,py=pill?8:tag?10:20;
  const rect=new fabric.Rect({width:txt.width+px*2,height:txt.height+py*2,fill:pill?T.pill:'#ffffff',stroke:pill?null:'#1a1a1a',strokeWidth:pill?0:tag?1.5:2,originX:'center',originY:'center',left:0,top:0});
  const g=new fabric.Group([rect,txt],{name:kind,raw,originX:o.originX||'center',originY:'top',left:o.left??CW/2,top:o.top??600});
  cvTidy(g);return g}
function layoutCover(c,{copy,label,callouts,tags}){
  const fixed=tags&&tags.length;   // 북케터 밈 형식(책추천·30초 요약) 표지: 왼쪽 위 흰 라벨 상자 + 더 큰 헤드라인
  const h=headline(copy||'카피를 입력하세요',fixed?{bottom:190,max:116}:{});c.add(h);
  (tags||[]).forEach((t,i)=>c.add(box('tagbox',t,{originX:'left',left:55,top:62+i*68})));
  if(label){const p=box('pill',label);p.set({top:h.top-24-p.height});c.add(p)}
  (callouts||[]).filter(Boolean).slice(0,2).forEach((t,i)=>{const b=box('callout',t,{originX:'left'});
    b.set(i===0?{left:CW-122-b.width,top:120}:{left:86,top:340});c.add(b)});
}
const loadImg=url=>new Promise(r=>fabric.Image.fromURL(url,(im,err)=>r(err||!im||!im.width?null:im)));
function coverImg(img){const s=Math.max(CW/img.width,CH/img.height);img.set({originX:'center',originY:'center',left:CW/2,top:CH/2,scaleX:s,scaleY:s});return s}
async function drawPreview(x){   // 기획 후보·보관함 미리보기 (캔버스와 같은 틀)
  await cvFonts();const Z=.3;
  const c=new fabric.StaticCanvas(document.createElement('canvas'),{backgroundColor:'#2b2621'});c.setDimensions({width:CW*Z,height:CH*Z});c.setZoom(Z);
  if(x.bg){const img=await loadImg(x.bg);if(img){coverImg(img);c.add(img)}}
  c.add(new fabric.Rect({left:0,top:0,width:CW,height:CH,fill:shadeFill('bottom',T.shadeA)}));
  layoutCover(c,x);c.renderAll();const url=c.toDataURL({format:'jpeg',quality:.88});c.dispose();return url}
const PREV=new Map();
function thumbPreview(x){const k=[x.copy,x.label,(x.callouts||[]).join('|'),(x.tags||[]).join('|'),x.bg].join('¦');
  if(!PREV.has(k))PREV.set(k,drawPreview(x).catch(e=>{PREV.delete(k);throw e}));return PREV.get(k)}

function cvInit(){if(CV.c)return CV.c;
  const c=new fabric.Canvas('cv',{preserveObjectStacking:true,backgroundColor:'#2b2621'});
  c.setDimensions({width:CW*CZ,height:CH*CZ});c.setZoom(CZ);
  ['selection:created','selection:updated','selection:cleared'].forEach(ev=>c.on(ev,cvSync));
  c.on('object:modified',()=>{CV.dirty=true;cvLayers()});return CV.c=c}
function cvShade(){const s=byName('shade')[0];if(!s)return;const dir=$('#cv-shade-dir').value,a=+$('#cv-shade').value;
  s.set({fill:shadeFill(dir,a),shadeDir:dir,shadeA:a});CV.dirty=true;CV.c.requestRenderAll()}
function cvSetBg(url,pin,rel){return new Promise((res,rej)=>fabric.Image.fromURL(url,(img,err)=>{
  if(err||!img||!img.width)return rej(new Error('이미지를 불러오지 못했습니다: '+url));
  byName('bg').forEach(o=>CV.c.remove(o));
  img.set({name:'bg',pin:pin||'',rel:rel||''});cvTidy(img);CV.base=coverImg(img);$('#cv-zoom').value=100;
  CV.c.insertAt(img,0);CV.dirty=true;CV.c.requestRenderAll();cvStrip();res(img)}))}
async function openCanvas(o){
  $('#cvx').classList.add('open');const c=cvInit();await cvFonts();
  Object.assign(CV,{copy:o.copy||'',meta:{...(o.meta||{})},cands:o.cands||[],fresh:null,token:CV.token+1,card:o.card||null});
  moreReset();$('#cv-msg').textContent='';c.discardActiveObject();c.clear();c.backgroundColor='#2b2621';
  $('#cv-save').textContent=CV.card?`${CV.card.index+1}번째 장 저장`:'저장 → 완성본 만들기';
  if(!CV.meta.plan_round&&!CV.card)$('#cv-save').textContent='저장';
  try{
    if(o.state){
      await new Promise(r=>c.loadFromJSON(o.state,r));c.setZoom(CZ);c.getObjects().forEach(cvTidy);
      const bg=byName('bg')[0];if(bg){CV.base=Math.max(CW/bg.width,CH/bg.height);$('#cv-zoom').value=Math.round(bg.scaleX/CV.base*100)}
      const sh=byName('shade')[0];if(sh){$('#cv-shade-dir').value=sh.shadeDir||'bottom';$('#cv-shade').value=sh.shadeA??T.shadeA}
    }else{
      c.add(new fabric.Rect({name:'shade',left:0,top:0,width:CW,height:CH,selectable:false,evented:false}));
      $('#cv-shade-dir').value='bottom';$('#cv-shade').value=T.shadeA;cvShade();
      layoutCover(c,o);
      if(o.bg&&o.bg.url)await cvSetBg(o.bg.url,o.bg.pin,o.bg.rel).catch(showErr);
    }
  }catch(e){showErr(e)}
  CV.dirty=false;cvStrip();cvSync();c.requestRenderAll();
}
function cvStrip(){
  const cur=(byName('bg')[0]||{}).rel;
  $('#cv-strip').innerHTML=CV.cands.length?CV.cands.map((x,k)=>`<img src="${x.url}" data-k="${k}" class="${x.rel===cur?'on':''} ${CV.fresh&&CV.fresh.has(x.file)?'new':''}" title="${esc(x.pin||'')} — 이 이미지로 바꾸기">`).join('')
    :'<span class="hint">다른 후보가 없습니다. 내 사진을 올릴 수 있습니다.</span>';
  $$('#cv-strip img').forEach(im=>im.onclick=()=>{const x=CV.cands[+im.dataset.k];cvSetBg(x.url,x.pin,x.rel).catch(showErr)});
}
const cvSel=()=>{const a=CV.c&&CV.c.getActiveObject();return a&&EDITABLE.includes(a.name)?a:null};
const isTB=o=>o&&(o.name==='text'||o.name==='free');
const LAYER={text:'헤드라인',pill:'라벨',callout:'말풍선',free:'글자',tagbox:'라벨 상자'};
function cvLayers(){
  const a=CV.c.getActiveObject(),ts=CV.c.getObjects().filter(o=>EDITABLE.includes(o.name));
  $('#cv-layers').innerHTML=ts.map((t,i)=>`<button class="lay ${t===a?'on':''}" data-i="${i}"><small>${LAYER[t.name]}</small>${esc(nl(t.raw??t.text).split('\n')[0].replace(/\[\[|\]\]|\{\{|\}\}/g,'').slice(0,14)||'(빈 글자)')}</button>`).join('')
    ||'<span class="hint">글자 상자가 없습니다. [글자 상자 추가]를 누르세요.</span>';
  $$('#cv-layers .lay').forEach(b=>b.onclick=()=>{CV.c.setActiveObject(ts[+b.dataset.i]);CV.c.requestRenderAll();cvSync()});
}
function cvSync(){
  const t=cvSel(),tb=isTB(t);
  $$('#cv-text,#cv-del,#cv-fwd,#cv-back').forEach(x=>x.disabled=!t);
  $$('#cv-size,#cv-color,#cv-bold,#cv-shadow,#cvx .sw,#cvx [data-al]').forEach(x=>x.disabled=!tb);
  $('#cv-text').value=t?nl(t.raw??t.text):'';
  if(tb){$('#cv-size').value=Math.round(t.fontSize);$('#cv-color').value=hex(t.fill);$('#cv-bold').checked=(+t.fontWeight||400)>=700;$('#cv-shadow').checked=!!t.shadow}
  cvLayers();
}
function cvSetText(v){
  const t=cvSel();if(!t)return;
  if(isTB(t)){const oldTop=t.top,bottom=t.top+t.height,{text,styles}=parseMarkup(v);t.set({text,styles,raw:v});t.initDimensions();
    if(t.name==='text'){t.set({top:bottom-t.height});const dy=t.top-oldTop;   // 헤드라인 줄 수가 바뀌면 바로 위 연두 라벨도 같이 움직인다
      byName('pill').forEach(p=>{if(p.top+p.height<=oldTop+4&&oldTop-(p.top+p.height)<120){p.set({top:p.top+dy});p.setCoords()}})}
    t.setCoords()}
  else{const i=CV.c.getObjects().indexOf(t),nb=box(t.name,v,{originX:t.originX,left:t.left,top:t.top});
    if(t.originX==='center')nb.set({left:t.left});CV.c.remove(t);CV.c.insertAt(nb,i);CV.c.setActiveObject(nb)}
  CV.dirty=true;CV.c.requestRenderAll();cvLayers();
}
function cvSet(k,v){const t=cvSel();if(!isTB(t))return;t.set(k,v);t.initDimensions&&t.initDimensions();t.setCoords();CV.dirty=true;CV.c.requestRenderAll()}
$('#cv-text').oninput=e=>cvSetText(e.target.value);
$('#cv-size').oninput=e=>cvSet('fontSize',Math.max(10,+e.target.value||10));
$('#cv-color').oninput=e=>cvSet('fill',e.target.value);
$$('#cvx .sw').forEach(b=>b.onclick=()=>{cvSet('fill',b.dataset.c);$('#cv-color').value=b.dataset.c});
$('#cv-bold').onchange=e=>cvSet('fontWeight',e.target.checked?'800':'500');
$$('#cvx [data-al]').forEach(b=>b.onclick=()=>cvSet('textAlign',b.dataset.al));
$('#cv-shadow').onchange=e=>cvSet('shadow',e.target.checked?new fabric.Shadow({color:'rgba(0,0,0,0.55)',blur:18,offsetX:0,offsetY:4}):null);
const cvAdd=o=>{CV.c.add(o);CV.c.setActiveObject(o);CV.dirty=true;cvSync()};
$('#cv-add').onclick=()=>{const t=headline('새 글자',{fontSize:64,top:560});t.set({name:'free'});cvAdd(t)};
$('#cv-add-pill').onclick=()=>cvAdd(box('pill','라벨 문구',{top:520}));
$('#cv-add-call').onclick=()=>cvAdd(box('callout','말풍선',{originX:'left',left:86,top:200}));
$('#cv-del').onclick=()=>{const t=cvSel();if(!t)return;CV.c.remove(t);CV.c.discardActiveObject();CV.dirty=true;CV.c.requestRenderAll();cvSync()};
$('#cv-fwd').onclick=()=>{const t=cvSel();if(t){t.bringForward();CV.dirty=true;CV.c.requestRenderAll();cvLayers()}};
$('#cv-back').onclick=()=>{const t=cvSel();if(!t)return;const i=CV.c.getObjects().indexOf(t),floor=byName('bg').length+byName('shade').length;
  if(i>floor){t.sendBackwards();CV.dirty=true;CV.c.requestRenderAll();cvLayers()}};
$('#cv-shade').oninput=cvShade;$('#cv-shade-dir').onchange=cvShade;
$('#cv-zoom').oninput=e=>{const bg=byName('bg')[0];if(!bg)return;const s=CV.base*e.target.value/100;bg.set({scaleX:s,scaleY:s});bg.setCoords();CV.dirty=true;CV.c.requestRenderAll()};
$('#cv-fit').onclick=()=>{const bg=byName('bg')[0];if(bg){CV.base=coverImg(bg);$('#cv-zoom').value=100;bg.setCoords();CV.dirty=true;CV.c.requestRenderAll()}};
const readFile=f=>new Promise(r=>{const x=new FileReader();x.onload=()=>r(x.result);x.readAsDataURL(f)});
async function uploadImage(f){return post('/api/upload',{data:await readFile(f)})}
$('#cv-upfile').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const u=await uploadImage(f);await cvSetBg(u.url,'직접 올린 사진: '+f.name,u.rel)}catch(err){showErr(err)}e.target.value=''};
$('#cv-close').onclick=()=>{if(CV.dirty&&!confirm('저장하지 않은 편집이 있습니다. 닫을까요?'))return;$('#cvx').classList.remove('open')};
$('#cv-save').onclick=async()=>{
  const c=CV.c;c.discardActiveObject();c.requestRenderAll();cvSync();
  const png=c.toDataURL({format:'png',multiplier:1/CZ});
  const st=c.toJSON(CPROPS);st.objects.forEach(o=>{if(o.src&&o.src.startsWith(location.origin))o.src=o.src.slice(location.origin.length)});
  const bg=byName('bg')[0],h=byName('text')[0],b=$('#cv-save');b.disabled=true;$('#cv-msg').textContent='저장 중…';
  try{
    if(CV.card){const card=CV.card;await post('/api/pub/card/save',{file:card.file,index:card.index,png,state:st});CV.dirty=false;
      $('#cvx').classList.remove('open');toast(`${card.index+1}번째 장을 고쳤습니다.`,'ok');tab('work');
      const t=deskFind('pub',card.file);if(t)deskShow(t.id);await pubReload(card.file);return}
    const r=await post('/api/canvas/save',{png,state:st,copy_text:h?h.raw:CV.copy,meta:{...CV.meta,pin:bg?bg.pin:'',bg_rel:bg?bg.rel:''}});
    CV.dirty=false;log('썸네일 저장: '+r.file);
    if(CV.meta.plan_round){$('#cvx').classList.remove('open');tab('work');makePublish(CV.meta.analysis_file,CV.meta.plan_round,CV.meta.plan_cand,r.file);return}
    $('#cv-msg').innerHTML=`저장됨 ✓ <a href="${r.url}" target="_blank">${esc(r.file)}</a>`;
  }catch(e){showErr(e);$('#cv-msg').textContent='저장하지 못했습니다: '+plainErr(e.message)}finally{b.disabled=false}
};
/* 이미지 더 찾기 */
const MORE_HINT='마음에 드는 이미지가 없으면 원하는 방향을 적고 [이 방향으로 찾기], 그냥 더 보려면 [추가 이미지]. 1~2분 걸리고, 그동안 편집은 계속할 수 있습니다.';
function moreReset(){
  $('#cv-morebox').classList.toggle('hidden',!CV.meta.cand_file);
  const r=CV.moreJob&&RUN[CV.moreJob.id],run=CV.moreJob&&CV.moreJob.token===CV.token&&running(CV.moreJob.id);
  btnRun($('#cv-more-dir'),run&&CV.moreJob.dir?r:null,'찾는 중');btnRun($('#cv-more'),run&&!CV.moreJob.dir?r:null,'찾는 중');
  if(!run){$('#cv-more-dir').disabled=$('#cv-more').disabled=false}
  const msg=$('#cv-more-msg');msg.classList.toggle('run',!!run);msg.textContent=run?progText(r):MORE_HINT;
}
async function candStrip(file){
  if(!file)return [];
  try{const d=(await api('/api/file/generate/'+encodeURIComponent(file))).data;if(!d||!d.candidates)return [];
    const by=Object.fromEntries(d.candidates.map(x=>[x.file,x]));
    return [...(d.ranking||[]).map(x=>x.file),...d.candidates.map(x=>x.file)].filter((f,i,a)=>by[f]&&a.indexOf(f)===i)
      .map(f=>({url:imgUrl('generate',d.assets,f),pin:by[f].pin,file:f,rel:`generate/${d.assets}/${f}`}))}catch(e){return []}
}
async function moreImages(withDir){
  const dir=$('#cv-imgdir').value.trim();
  if(withDir&&!dir)return toast('원하는 이미지 방향을 적어 주세요. 그냥 더 보려면 [추가 이미지]를 누르세요.','bad');
  if(CV.moreJob&&running(CV.moreJob.id))return toast('이미지를 찾는 중입니다. 끝나면 다시 눌러 주세요.');
  const token=CV.token,job={token,dir:withDir};CV.moreJob=job;
  try{const r=await runJob(post('/api/images/more',{cand_file:CV.meta.cand_file,direction:withDir?dir:''}),'이미지 더 찾기'+(withDir?' · '+dir.slice(0,14):''),
      {onTick:rr=>{job.id=rr.id;if(CV.token===token)moreReset()}});
    if(CV.token!==token||!$('#cvx').classList.contains('open'))return toast(`새 이미지 ${r.new.length}장을 찾았습니다. 캔버스를 다시 열면 맨 앞에 있습니다.`,'ok');
    CV.fresh=new Set(r.new);const list=await candStrip(r.file);
    CV.cands=[...list.filter(x=>CV.fresh.has(x.file)),...list.filter(x=>!CV.fresh.has(x.file))];
    cvStrip();$('#cv-strip').scrollLeft=0;if(withDir)$('#cv-imgdir').value='';moreReset();
    $('#cv-more-msg').textContent=`새 이미지 ${r.new.length}장을 맨 앞에 붙였습니다(초록 테두리). 검색어: ${(r.queries||[]).join(' · ')}`;
  }catch(e){if(CV.token===token){moreReset();$('#cv-more-msg').textContent='찾지 못했습니다: '+plainErr(e.message)}showErr(e)}
}
$('#cv-more-dir').onclick=()=>moreImages(true);$('#cv-more').onclick=()=>moreImages(false);
$('#cv-imgdir').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();moreImages(true)}};

/* ---------- 3. 작업대: 기획·완성본 탭 ---------- */
const DESK={tabs:[],cur:null,seq:0};
const dtab=id=>DESK.tabs.find(t=>t.id===id);
const deskFind=(kind,file)=>file?DESK.tabs.find(t=>t.kind===kind&&t.file===file):null;
const isCur=t=>!!t&&DESK.cur===t.id;
const first=s=>nl(s).split('\n')[0].replace(/\[\[|\]\]|\{\{|\}\}/g,'');
function tabTitle(t){const d=t.data;
  if(t.kind==='plan'&&d){const R=d.rounds||[],c=((R[R.length-1]||{}).candidates||[])[0]||{};return first(c.copy||'기획')}
  if(t.kind==='pub'&&d)return first(d.copy||'완성본');return t.title||'작업'}
const tabState=t=>running(t.job)?(runPct(RUN[t.job])==null?'ri':'rp'):t.err?'err':t.fresh?'new':'';
const tabTip=t=>(t.kind==='plan'?'기획':'완성본')+' · '+tabTitle(t)+(running(t.job)?' · '+progText(RUN[t.job]):t.err?' · 실패':t.fresh?' · 새 결과':'');
function deskPaint(){
  $('#desk').classList.toggle('hidden',!DESK.tabs.length);
  const box=$('#dtabs'),sig=DESK.tabs.map(t=>[t.id,isCur(t)?1:0,t.kind,t.file||'',tabTitle(t),tabState(t)].join('\u0001')).join('\u0002');
  if(box.dataset.sig===sig){DESK.tabs.forEach(t=>{const el=box.querySelector(`.dtab[data-id="${t.id}"]`);if(!el)return;el.title=tabTip(t);
      if(tabState(t)==='rp'){const p=runPct(RUN[t.job]);el.querySelector('.ring').style.setProperty('--p',p);el.querySelector('.tp').textContent=p+'%'}});return}
  box.dataset.sig=sig;
  box.innerHTML=DESK.tabs.map(t=>{const st=tabState(t),p=st==='rp'?runPct(RUN[t.job]):null;
    const dot=st==='rp'||st==='ri'?ring(p,'xs')+(p!=null?`<span class="tp">${p}%</span>`:''):st==='err'?'<span class="dot err" title="실패"></span>':st==='new'?'<span class="dot new" title="새 결과"></span>':'';
    return `<div class="dtab ${isCur(t)?'on':''}" data-id="${t.id}" title="${esc(tabTip(t))}"><span class="dk ${t.kind}">${t.kind==='plan'?'기획':'완성본'}</span><span class="dn">${esc(tabTitle(t))}</span>${dot}<button class="dx" title="탭 닫기">×</button></div>`}).join('')
    +'<button class="dadd" id="desk-add">+ 새 기획</button>';
  $$('#dtabs .dtab').forEach(el=>el.onclick=e=>{const t=dtab(el.dataset.id);if(!t)return;if(e.target.closest('.dx'))return deskClose(t);deskShow(t.id)});
  $('#desk-add').onclick=()=>{tab('work');$('#results-top').scrollIntoView({behavior:'smooth',block:'start'});toast('레퍼런스를 1~3개 고른 뒤 [선택한 레퍼런스로 기획하기]를 누르면 새 탭으로 열립니다.')};
}
function deskKeep(){const t=dtab(DESK.cur);if(!t||!t.data)return;
  if(t.kind==='plan'){t.fb=$('#fb').value;t.target=+$('#fb-target').value||0}else{t.cap=$('#pub-cap').value;t.cmt=$('#pub-cmt').value}}
function deskShow(id,scroll){const t=dtab(id);if(!t)return;if(DESK.cur!==id)deskKeep();
  DESK.cur=id;t.fresh=false;deskRenderCur();deskPaint();deskSave();if(scroll)deskScroll()}
function deskScroll(){setTimeout(()=>$('#desk').scrollIntoView({behavior:'smooth',block:'start'}),120)}
function deskRenderCur(){
  const t=dtab(DESK.cur),k=t&&t.data?t.kind:null;
  $('#plan-step').classList.toggle('hidden',k!=='plan');$('#pub-step').classList.toggle('hidden',k!=='pub');
  $('#desk-wait').classList.toggle('hidden',!t||!!t.data);
  if(!t)return;if(!t.data)waitPaint(t);else if(t.kind==='plan')renderPlan(t);else renderPublish(t);
}
function deskRefresh(t){if(isCur(t)){deskKeep();deskRenderCur()}deskPaint()}
function deskTick(t){deskPaint();if(!isCur(t))return;if(!t.data)waitPaint(t);else if(t.kind==='plan')planBusy(t)}
function deskAdd(t,focus=true){t.id='t'+(++DESK.seq);DESK.tabs.push(t);if(focus)deskShow(t.id);else deskPaint();return t}
function deskOpen(kind,data,focus=true){
  let t=deskFind(kind,data.file);
  if(t){if(!running(t.job)){t.data=data;if(kind==='plan')t.ri=null;else t.cap=t.cmt=null}}else t=deskAdd({kind,file:data.file,data},false);
  if(focus)deskShow(t.id);else deskRefresh(t);deskSave();return t}
function deskClose(t){
  if(running(t.job))return toast('이 탭의 작업이 끝난 뒤에 닫을 수 있어요. 진행 상황은 맨 위 머리줄에 보입니다.');
  const i=DESK.tabs.indexOf(t);if(i<0)return;if(isCur(t))deskKeep();DESK.tabs.splice(i,1);
  if(isCur(t)){DESK.cur=null;const n=DESK.tabs[i]||DESK.tabs[i-1];if(n)deskShow(n.id);else deskRenderCur()}
  deskPaint();deskSave();
}
function deskSave(){try{localStorage.setItem('bk-desk',JSON.stringify({tabs:DESK.tabs.filter(t=>t.file).slice(-10).map(t=>({kind:t.kind,file:t.file})),cur:(dtab(DESK.cur)||{}).file||''}))}catch(e){}}
async function deskRestore(){
  let s=null;try{s=JSON.parse(localStorage.getItem('bk-desk')||'null')}catch(e){}
  for(const x of (s&&s.tabs)||[]){try{if(deskFind(x.kind,x.file))continue;
    const d=(await api(`/api/file/${x.kind==='plan'?'analysis':'generate'}/`+encodeURIComponent(x.file))).data;
    if(d&&(x.kind==='plan'?d.rounds:d.type==='발행'))deskAdd({kind:x.kind,file:x.file,data:{...d,file:x.file}},false)}catch(e){}}
  const c=DESK.tabs.find(t=>t.file&&s&&t.file===s.cur)||DESK.tabs[0];if(c)deskShow(c.id);
}
function waitPaint(t){
  const W=$('#desk-wait');
  if(t.err){W.innerHTML=`<span class="ring lg bad" style="--p:100"><i></i><b>!</b></span><div class="dwt"><b>${esc(t.title||'작업')} — 실패했습니다</b>
      <div class="hint">${esc(t.err)}</div><div class="row" style="margin:12px 0 0">${t.body?'<button class="btn pri" id="dw-retry">다시 시도</button>':''}<button class="btn" id="dw-close">이 탭 닫기</button></div></div>`;
    const rb=$('#dw-retry');if(rb)rb.onclick=()=>startPlan(t.body,t.title,t);$('#dw-close').onclick=()=>deskClose(t);return}
  const r=t.job&&RUN[t.job],p=r&&r.prog||{};
  W.innerHTML=`${ring(runPct(r),'lg')}<div class="dwt"><b>${esc(t.title||'작업 중')}</b><div class="dwp">${esc(progText(r)||'시작하는 중…')}</div>
    <div class="hint">${p.label?`지금 단계: ${esc(p.label)}`:''}</div>
    <div class="hint" style="margin-top:8px">${esc(t.note||'기다리는 동안 위에서 레퍼런스를 더 모으거나 다른 탭을 편집·저장해도 됩니다. 끝나면 이 탭에 결과가 들어옵니다.')}</div></div>`;
}

/* 기획 탭 */
const TPL_KO={paper_title:'타이포',photo_box:'사진+박스',paper_box:'모눈+박스',dark_cta:'마지막 장',book:'책 장',follow_cta:'팔로우 장',summary_index:'목차 장',keyword_pair:'키워드 장',self_check:'셀프체크 장'};
const slideLi=s=>`<li><b>${esc(TPL_KO[s.template]||s.template)} · ${esc(s.label||'')}</b> ${esc(nl(s.headline||'')).replace(/\n/g,' ')} ${esc(nl(s.body||'')).replace(/\n/g,' ')}${(s.bullets||[]).length?' · '+s.bullets.map(esc).join(' / '):''}</li>`;
const bgOf=c=>c.img&&c.img.bg?imgUrl('generate',c.img.assets,c.img.bg):'';
const mk=s=>esc(nl(s)).replace(/\[\[(.+?)\]\]/g,'<span class="ml">$1</span>').replace(/\{\{(.+?)\}\}/g,'<b style="color:#e5484d">$1</b>');
function contentPreview(ct){   // 형식 후보의 본문 미리보기 (책 목록 · 키워드)
  if(ct.books)return `<details class="cprev" open><summary>책 ${ct.books.length}권</summary>${ct.books.map((b,i)=>`<div><b>${i+1}. ${esc(b.title)}</b> — ${esc(b.author)} <span class="hint">${esc(b.tags.join(' '))}</span><br>${b.lines.map(mk).join('<br>')}</div>`).join('<hr style="border:0;border-top:1px dashed var(--line)">')}</details>`;
  if(ct.keywords)return `<details class="cprev"><summary>목차 · 키워드 ${ct.keywords.length}개 · 셀프체크</summary><div><b>${esc(ct.book_title)}</b> <span class="hint">${esc(ct.subtitle)}</span></div>
    ${ct.keywords.map((k,i)=>`<div><b>${String(i+1).padStart(2,'0')} ${esc(k.title)}</b> <span class="hint">${esc(k.en)}</span><br>${mk(k.line1)}<br><span class="ml">${mk(k.line2)}</span></div>`).join('')}
    <div><b>${esc(ct.check.title)}</b><br>${ct.check.items.map(x=>'☐ '+esc(x)).join('<br>')}</div></details>`;
  return '';
}
let planSeq=0;
function renderPlan(t){
  const d=t.data;const R=d.rounds||[];if(!R.length)return;
  const ri=t.ri==null||t.ri>=R.length?R.length-1:t.ri,r=R[ri],my=++planSeq;
  $('#plan-file').textContent=`${(d.project||{}).name||''} · ${state.meta.modes[d.mode]||''} · 레퍼런스 ${(d.picks||[]).map(n=>'#'+n).join(' ')}${R.length>1?` · 라운드 ${R.length}`:''}`;
  $('#rtabs').innerHTML=R.length>1?R.map((x,i)=>`<button data-i="${i}" class="${i===ri?'on':''}">라운드 ${x.n}${i===R.length-1?' (최신)':''}</button>`).join(''):'';
  $$('#rtabs button').forEach(b=>b.onclick=()=>{deskKeep();t.ri=+b.dataset.i;renderPlan(t)});
  const A=d.auto,autoHtml=A&&ri===0?`<div class="chk"><b>자동 준비</b>${A.variations?` · 레퍼런스 카피 "${esc(nl(A.variations.original).replace(/\n/g,' '))}" → 공식: ${esc(A.variations.formula)}
      <ol style="margin:6px 0 6px 18px;padding:0">${A.variations.variations.map((v,i)=>`<li>${mk(v.copy).replace(/<br>/g,' ')}${i+1===A.variations.recommend?' <b>← 후보 1 표지</b>':''}</li>`).join('')}</ol>`:''}
      <div><b>AI가 고른 책</b> ${(A.books||[]).map(b=>`${esc(b.title)} — ${esc(b.author)} <span class="badge ${(b.kyobo||{}).verified&&!(b.kyobo||{}).outofprint?'ok':'no'}">교보 ${esc((b.kyobo||{}).note||'확인 못 함')}</span>`).join(' · ')}</div></div>`:'';
  $('#plan-sum').innerHTML=autoHtml+(r.feedback?`<b>반영한 피드백${r.target?` (후보 ${r.target} 기준)`:''}</b> ${esc(r.feedback)}<br>`:'')+(r.summary?`<b>${r.n>1?'바꾼 점':'레퍼런스에서 가져온 핵심'}</b> ${esc(r.summary)}`:'')
    +(r.check?`<div class="chk"><b>팩트체크 결과</b> (후보 1에 반영)<table><tr><th>책</th><th>판정</th><th>교보문고</th><th>확인한 점</th></tr>${r.check.books.map(b=>`<tr><td>${esc(b.title)}</td><td><span class="badge ${b.status==='정확'?'ok':'no'}">${esc(b.status)}</span></td><td>${esc(b.kyobo||'')}</td><td>${b.issues.map(esc).join('<br>')||'-'}</td></tr>`).join('')}</table></div>`:'');
  const long=d.mode==='long';
  $('#pcands').innerHTML=r.candidates.map((c,k)=>`<div class="pc" data-k="${k}">
    <div class="pv" title="이 후보로 편집"><img alt=""><span class="no">후보 ${k+1}</span>${c.img&&c.img.bg?'':'<span class="noimg">이미지 없음</span>'}</div>
    <div class="pcb"><div class="pangle">${esc(c.angle||'')}</div>
      <div class="chips"><span class="badge">${esc(c.pattern||'')}</span></div>
      ${c.share?`<div class="why"><b>공유 명분</b> ${esc(c.share)}</div>`:''}${c.from_ref?`<div class="why"><b>레퍼런스에서</b> ${esc(c.from_ref)}</div>`:''}
      ${c.img&&c.img.reason?`<div class="why"><b>이미지</b> ${esc(c.img.reason)}</div>`:`<div class="why"><b>이미지 가이드</b> ${esc(c.image||'')}</div>`}
      ${c.content?contentPreview(c.content):''}
      ${long&&(c.slides||[]).length?`<details><summary>본문 ${c.slides.length}장 보기</summary><ol start="2">${c.slides.map(slideLi).join('')}<li><b>마지막 장</b> ${esc(nl(c.cta.headline))} ${esc(nl(c.cta.body))}</li></ol></details>`:''}
      <details><summary>캡션 · 고정댓글 보기</summary><pre>${esc(c.caption||'')}</pre><pre>${esc(c.comment||'')}</pre></details>
      <div class="acts"><button class="btn sm pri pick-cand">이 후보로 편집 →</button><button class="btn sm fb-this">이 후보 기준 수정</button>${c.content&&c.content.books?'<button class="btn sm fcheck" title="책 제목·저자·절판은 교보문고에서, 줄거리·인용·숫자는 웹에서 확인하고 틀린 곳을 고친 후보를 새 라운드로 만들어요">팩트체크</button>':''}</div>
    </div></div>`).join('');
  $('#fb-target').innerHTML='<option value="0">후보 3개 전체에 대해</option>'+r.candidates.map((c,k)=>`<option value="${k+1}">후보 ${k+1} 기준으로 고치기</option>`).join('');
  $('#fb-target').value=String(t.target||0);$('#fb').value=t.fb||'';
  $('#fbbox').classList.toggle('hidden',ri!==R.length-1);
  $$('#pcands .pc').forEach(el=>{const k=+el.dataset.k,c=r.candidates[k];
    el.querySelector('.pick-cand').onclick=el.querySelector('.pv').onclick=()=>pickCand(t,ri,k);
    const fc=el.querySelector('.fcheck');if(fc)fc.onclick=()=>{if(running(t.job))return;
      if(needClaude('팩트체크는 AI가 웹을 검색해서 해요.'))return;
      if(ri!==R.length-1){deskKeep();t.ri=null}
      planJob(t,post('/api/factcheck',{plan_file:t.file,round:ri+1,cand:k+1}),`팩트체크 · 후보 ${k+1}`)};
    el.querySelector('.fb-this').onclick=()=>{if(ri!==R.length-1){deskKeep();t.ri=null;renderPlan(t)}if(running(t.job))return;
      $('#fb-target').value=k+1;$('#fb').focus();$('#fbbox').scrollIntoView({behavior:'smooth',block:'center'})};
    thumbPreview({copy:c.copy,label:c.label,callouts:c.callouts,tags:ftags(d.mode),bg:bgOf(c)}).then(u=>{if(my===planSeq)el.querySelector('.pv img').src=u}).catch(()=>{})});
  planBusy(t);
}
function planBusy(t){
  const r=t.job&&RUN[t.job],on=running(t.job);
  $('#fb').disabled=$('#fb-target').disabled=on;btnRun($('#btn-replan'),on?r:null,'다시 기획 중');
  const m=$('#fb-run');m.classList.toggle('bad',!on&&!!t.err);m.classList.toggle('hidden',!on&&!t.err);
  m.textContent=on?`${progText(r)} — 그동안 위 후보를 편집·저장하거나 다른 탭에서 작업해도 됩니다.`:t.err?`다시 기획하지 못했습니다: ${t.err}`:'';
}
async function planJob(t,start,label){
  t.err=null;if(isCur(t))deskRenderCur();
  try{const d=await runJob(start,label,{go:()=>{tab('work');deskShow(t.id,true)},onTick:r=>{t.job=r.id;deskTick(t)}});
    if(isCur(t))deskKeep();Object.assign(t,{job:null,data:d,file:d.file,ri:null,fb:'',target:0});
    if(isCur(t))deskRenderCur();else t.fresh=true;deskPaint();deskSave()}
  catch(e){t.job=null;t.err=plainErr(e.message);if(isCur(t))deskRenderCur();deskPaint();showErr(e)}
}
function startPlan(body,label,t){if(!t)t=deskAdd({kind:'plan',file:null,data:null,title:label},true);t.body=body;return planJob(t,post('/api/plan',body),label)}
$('#btn-fmt-plan').onclick=()=>$('#btn-plan').onclick(true);
$('#btn-plan').onclick=(fromFormat)=>{
  const k=fkind(),fname=state.meta.formats[state.mode].name;
  if(!state.picks.size&&k==='free')return toast('자유 형식은 2번에서 레퍼런스를 1~3개 선택해야 기획할 수 있어요.','bad');
  const project=projectNow();
  if(k==='books'&&!state.picks.size&&!project.books&&!project.message&&!project.thumb&&!project.name)return dialog('레퍼런스나 주제가 필요해요',`${fname}은 2번에서 레퍼런스를 고르면 썸네일 카피 → 책 찾기 → 책 소개까지 AI가 알아서 해요. 레퍼런스 없이 하려면 1번에 썸네일 카피나 장르를 적어 주세요.`,[{label:'확인',pri:true,fn:()=>$('#pj-books').focus()}]);
  if(k==='summary'&&!project.book_title)return dialog('요약할 책을 적어 주세요','30초 요약은 1번 칸에 책 제목과 내용 메모(사실 정보)를 넣어 주세요.',[{label:'확인',pri:true,fn:()=>$('#pj-book_title').focus()}]);
  if(!project.name&&k!=='books')project.name=project.book_title||fname;
  if(k==='free'&&!(project.message||project.details))return dialog('알릴 내용을 먼저 적어 주세요',
    '1번 칸에 주제와 핵심 메시지(또는 사실 정보)를 넣어야 AI가 레퍼런스 공식에 우리 내용을 얹을 수 있어요.',[{label:'확인',pri:true,fn:()=>$('#pj-name').focus()}]);
  if(needClaude('1번 칸의 [Claude 로그인 창 열기]를 눌러 구독 계정으로 로그인해 주세요.'))return;
  const b=$('#btn-plan');b.disabled=true;setTimeout(()=>b.disabled=false,1500);
  const picks=[...state.picks].sort((a,b)=>a-b);
  const auto=k==='books'&&!project.books;
  startPlan({crawl_file:picks.length?state.crawlFile:'',picks,mode:state.mode,project},`${auto?'자동 기획':'새 기획'} · ${fname} · ${(project.name||project.thumb||'레퍼런스').slice(0,12)}${picks.length?' · 레퍼런스 '+picks.map(n=>'#'+n).join(' '):''}`);
  deskScroll();
};
$('#btn-replan').onclick=()=>{
  const t=dtab(DESK.cur);if(!t||t.kind!=='plan'||!t.data||running(t.job))return;
  const fb=$('#fb').value.trim();if(!fb)return toast('수정하고 싶은 내용을 입력하세요.','bad');deskKeep();
  planJob(t,post('/api/plan',{plan_file:t.file,feedback:fb,target:+$('#fb-target').value}),`다시 기획 · ${tabTitle(t)}`);
};
async function refineCand(o,fb){
  fb=(fb||'').trim();if(!fb){toast('어떻게 바꿀지 입력하세요.','bad');return false}
  const d=(await api('/api/file/analysis/'+encodeURIComponent(o.plan_file))).data;if(!d||!d.rounds){toast('기획 파일을 찾지 못했습니다.','bad');return false}
  tab('work');const t=deskOpen('plan',{...d,file:o.plan_file});
  if(running(t.job)){toast('이 기획은 지금 다시 기획 중이에요. 끝난 뒤에 다시 눌러 주세요.','bad');return false}
  planJob(t,post('/api/plan',{plan_file:o.plan_file,feedback:fb,target:o.cand,target_round:o.round}),`다시 기획 · ${tabTitle(t)}`);deskScroll();return true;
}
async function editCandidate(o){   // o = {plan_file, round, cand, c(후보), mode}
  const c=o.c,img=c.img||{};
  openCanvas({copy:c.copy,label:c.label,callouts:c.callouts,tags:ftags(o.mode),cands:await candStrip(img.file),
    bg:img.bg?{url:imgUrl('generate',img.assets,img.bg),pin:img.pin,rel:`generate/${img.assets}/${img.bg}`}:null,
    meta:{analysis_file:o.plan_file,cand_file:img.file||'',plan_round:o.round,plan_cand:o.cand}});
}
function pickCand(t,ri,k){$$('#pcands .pc').forEach((el,i)=>el.classList.toggle('chosen',i===k));
  editCandidate({plan_file:t.data.file,round:ri+1,cand:k+1,c:t.data.rounds[ri].candidates[k],mode:t.data.mode})}

/* 완성본 탭 */
async function pubJob(t,start){
  t.err=null;
  try{const r=await runJob(start,'저장 · 카드 이미지 만들기',{go:()=>{tab('work');deskShow(t.id,true)},onTick:rr=>{t.job=rr.id;deskTick(t)}});
    Object.assign(t,{job:null,data:r,file:r.file});if(isCur(t))deskRenderCur();else t.fresh=true;deskPaint();deskSave();
    if(!$('#v-lib').classList.contains('hidden'))loadLib()}
  catch(e){t.job=null;t.err=plainErr(e.message);if(isCur(t))deskRenderCur();deskPaint();showErr(e)}
}
function makePublish(planFile,round,cand,thumb){
  const t=deskAdd({kind:'pub',file:null,data:null,title:'저장 중 · 카드 이미지 만들기',note:'카드 이미지를 만들어 바탕화면 › 카드뉴스 완성본 폴더에 저장하고 있어요. 다른 탭에서 계속 작업해도 됩니다.'},true);
  tab('work');deskScroll();return pubJob(t,post('/api/publish',{plan_file:planFile,round,cand,thumb_file:thumb}));
}
const KIND_LABEL={thumb:'썸네일',body:'본문',cta:'마지막 장',image:'이미지'};
function renderPublish(t){
  const p=t.data;state.pub=p;
  $('#pub-file').textContent=`카드 ${p.cards.length}장 · ${p.file}`;renderCardMgr(p);
  $('#pub-cap').value=t.cap??(p.caption||'');$('#pub-cmt').value=t.cmt??(p.comment||'');
  $('#pub-caplen').textContent=` ${$('#pub-cap').value.length.toLocaleString()}자`;
  $('#pub-note').textContent=p.pin&&p.pin.startsWith('http')?'썸네일 배경 출처: '+p.pin:'';
  const d=p.desktop;$('#pub-desk').innerHTML=d&&d.folder?`✔ 카드 ${d.files.filter(x=>x.endsWith('.png')).length}장 + 캡션 파일이 <b>${esc(d.folder.split(/[\\/]/).slice(-3).join(' › '))}</b> 에 저장됐습니다 (파일명 끝 번호 = 올릴 순서)`:'';
  $('#pub-zip').href='/api/pub/zip?file='+encodeURIComponent(p.file);
}
function renderCardMgr(p){
  const v=Date.now(),last=p.cards.length-1,hasCta=p.cards[last]&&p.cards[last].kind==='cta';
  $('#pub-cards').innerHTML=p.cards.map((c,i)=>{const url=imgUrl('generate',p.folder,c.file)+'?v='+v;
    return `<div class="ctile" data-i="${i}"><a class="cimg" href="${url}" target="_blank" title="크게 보기"><img src="${url}"><span class="cnum">${i+1} · ${KIND_LABEL[c.kind]||''}</span></a>
      <div class="cbtns">${c.kind==='thumb'||c.slide?'<button class="btn sm pri c-edit">편집</button>':''}<label class="btn sm">내 이미지로<input type="file" accept="image/*" class="c-rep" hidden></label>
        ${i>0?`<button class="btn sm c-left" ${i<=1?'disabled':''} title="앞으로">◀</button><button class="btn sm c-right" ${i>=last?'disabled':''} title="뒤로">▶</button><button class="btn sm c-del">빼기</button>`:''}</div></div>`}).join('')
    +`<div class="ctile add"><label class="cimg">+ 이미지 장 추가<br><small style="font-weight:500">${hasCta?'마지막 장 앞에':'맨 뒤에'} 들어갑니다</small><input type="file" accept="image/*" id="c-add" hidden></label></div>`;
  $$('#pub-cards .ctile[data-i]').forEach(el=>{const i=+el.dataset.i;const E=el.querySelector('.c-edit');if(E)E.onclick=()=>editCard(i).catch(showErr);
    el.querySelector('.c-rep').onchange=e=>{const f=e.target.files[0];if(f)cardImage(i,f,'replace')};
    const L=el.querySelector('.c-left'),R=el.querySelector('.c-right'),D=el.querySelector('.c-del');
    if(L)L.onclick=()=>cardOp('/api/pub/card/move',{index:i,step:-1});if(R)R.onclick=()=>cardOp('/api/pub/card/move',{index:i,step:1});
    if(D)D.onclick=()=>dialog(`${i+1}번째 장을 뺄까요?`,'이 완성본과 바탕화면 폴더에서 이 장이 빠지고 뒤 장들의 번호가 당겨집니다.',[{label:'빼기',danger:true,fn:()=>cardOp('/api/pub/card/remove',{index:i})},{label:'취소'}],{danger:true})});
  $('#c-add').onchange=e=>{const f=e.target.files[0];if(f)cardImage(hasCta?last:p.cards.length,f,'insert')};
}
async function pubReload(file){
  const d=(await api('/api/file/generate/'+encodeURIComponent(file))).data;
  const t=deskFind('pub',file);if(t){t.data={...d,file};deskRefresh(t)}if(!$('#v-lib').classList.contains('hidden'))loadLib();return d}
async function cardOp(url,body){const file=state.pub.file;try{await post(url,{file,...body});toast('카드를 고쳤습니다.','ok');await pubReload(file)}catch(e){showErr(e)}}
async function cardImage(i,f,mode){const file=state.pub.file;
  try{await post('/api/pub/card/image',{file,index:i,mode,data:await readFile(f)});toast(mode==='insert'?`이미지 장을 ${i+1}번째에 넣었습니다.`:`${i+1}번째 장을 내 이미지로 바꿨습니다.`,'ok');await pubReload(file)}catch(e){showErr(e)}}
async function editCard(i){
  const p=state.pub,c=p.cards[i],card={file:p.file,index:i};
  if(c.kind==='thumb'){const r=await api(`/api/pub/card?file=${encodeURIComponent(p.file)}&index=${i}`);
    return openCanvas({copy:p.copy,state:r.state,card,cands:await candStrip(p.cand_file),meta:{cand_file:p.cand_file}})}
  if(c.slide)return openSlide(p,i);
}
$('#pub-cap').oninput=()=>$('#pub-caplen').textContent=` ${$('#pub-cap').value.length.toLocaleString()}자`;
$('#pub-capsave').onclick=async()=>{const p=state.pub;if(!p)return;try{await post('/api/pub/caption',{file:p.file,caption:$('#pub-cap').value,comment:$('#pub-cmt').value});
  const t=dtab(DESK.cur);if(t){t.cap=t.cmt=null}await pubReload(p.file);toast('캡션·고정댓글을 저장했습니다(바탕화면 캡션 파일도 바뀜).','ok')}catch(e){showErr(e)}};
const copyBtn=(btn,area,word)=>$(btn).onclick=()=>{navigator.clipboard.writeText($(area).value);$(btn).textContent='복사됨 ✓';setTimeout(()=>$(btn).textContent=word,1500)};
copyBtn('#pub-capcopy','#pub-cap','캡션 복사');copyBtn('#pub-cmtcopy','#pub-cmt','고정댓글 복사');
$('#pub-open').onclick=async()=>{const p=state.pub;if(!p)return;try{const d=await post('/api/desktop',{file:p.file});toast('바탕화면 폴더를 열었습니다: '+d.folder,'ok')}catch(e){showErr(e)}};
$('#pub-rf-go').onclick=async()=>{const t=dtab(DESK.cur);if(!t||t.kind!=='pub'||!t.data)return;const p=t.data;
  try{if(await refineCand({plan_file:p.plan_file,round:p.round,cand:p.cand},$('#pub-rf').value))$('#pub-rf').value=''}catch(e){showErr(e)}};

/* 본문 장 편집 — 템플릿마다 칸을 자동으로 만들고 HTML 템플릿으로 다시 렌더링 */
const SLF={   // [키, 이름, 종류(text|ta|lines|words|img|kw)]
  paper_title:[['label','눈썹 문구'],['headline','헤드라인','ta'],['body','본문','ta']],
  photo_box:[['label','제목 박스'],['body','본문','ta'],['image','배경 사진','img']],
  paper_box:[['label','박스 제목'],['body','본문','ta'],['bullets','불릿 (줄마다 하나)','lines']],
  dark_cta:[['headline','헤드라인','ta'],['body','본문','ta'],['image','배경 사진','img']],
  book:[['title','책 제목'],['tags','해시태그 (띄어쓰기로 구분)','words'],['cover','책 표지','img'],['lines','소개 (줄마다 하나)','lines'],['image','배경 사진','img']],
  follow_cta:[['headline','헤드라인','ta'],['body','본문','ta'],['image','배경 사진','img'],['avatar','프로필 사진','img']],
  summary_index:[['tag','태그'],['title','제목'],['subtitle','부제'],['items','목록 (줄마다 하나)','lines'],['footer','아래 안내'],['image','배경 사진','img']],
  self_check:[['tag','태그'],['title','제목'],['subtitle','부제'],['items','체크 문항 (줄마다 하나)','lines'],['footer','아래 안내'],['image','배경 사진','img']],
  keyword_pair:[['items','키워드 2개','kw']],
};
const KWF=[['no','태그'],['title','키워드'],['en','영문 부제'],['line1','설명 1줄 (흰색)'],['line2','설명 2줄 (연두)'],['image','배경 사진','img']];
const FREE_TPL=['paper_title','photo_box','paper_box','dark_cta'];
const SL={p:null,i:0,slide:null};
const relUrl=rel=>{if(!rel)return '';const m=rel.match(/^(crawl|analysis|generate)\/(.+)\/([^/]+)$/);return m?imgUrl(m[1],m[2],m[3]):''};
function fieldHtml([k,name,type],v,path){
  const id=`slf-${path}`;
  if(type==='img')return `<div class="imgf" data-path="${path}">${v?`<img src="${relUrl(v)}">`:'<span class="hint">없음</span>'}<b style="font-size:12.5px">${name}</b>
    <label class="btn sm">바꾸기<input type="file" accept="image/*" hidden></label>${v?'<button class="btn sm ghost imgx">빼기</button>':''}</div>`;
  const val=type==='lines'?(v||[]).join('\n'):type==='words'?(v||[]).join(' '):nl(v||'');
  const big=type==='ta'||type==='lines';
  return `<label class="fl">${name}${big?`<textarea id="${id}" data-path="${path}" data-type="${type}" style="min-height:${type==='lines'?90:70}px">${esc(val)}</textarea>`
    :`<input type="text" id="${id}" data-path="${path}" data-type="${type||'text'}" value="${esc(val)}">`}</label>`;
}
function slideForm(){
  const s=SL.slide,box=$('#sl-fields');let h='';
  if(FREE_TPL.includes(s.template))h+=`<label class="fl">템플릿 <select id="sl-template">${FREE_TPL.map(k=>`<option value="${k}" ${k===s.template?'selected':''}>${TPL_KO[k]}</option>`).join('')}</select></label>`;
  for(const f of SLF[s.template]||[]){
    if(f[2]==='kw')h+=(s.items||[]).map((it,j)=>`<div class="sub"><b>키워드 ${j+1}</b>${KWF.map(g=>fieldHtml(g,it[g[0]],`items.${j}.${g[0]}`)).join('')}</div>`).join('');
    else h+=fieldHtml(f,s[f[0]],f[0]);
  }
  box.innerHTML=h;
  const tsel=$('#sl-template');if(tsel)tsel.onchange=()=>{collectSlide();SL.slide.template=tsel.value;slideForm()};
  $$('#sl-fields .imgf').forEach(el=>{const path=el.dataset.path;
    el.querySelector('input').onchange=async e=>{const f=e.target.files[0];if(!f)return;collectSlide();try{const u=await uploadImage(f);setPath(SL.slide,path,u.rel);slideForm()}catch(err){showErr(err)}};
    const x=el.querySelector('.imgx');if(x)x.onclick=()=>{collectSlide();setPath(SL.slide,path,'');slideForm()}});
}
function setPath(o,path,v){const ks=path.split('.');let t=o;ks.slice(0,-1).forEach(k=>t=t[k]);t[ks[ks.length-1]]=v}
function collectSlide(){
  $$('#sl-fields [data-type]').forEach(el=>{const tp=el.dataset.type,v=el.value;
    setPath(SL.slide,el.dataset.path,tp==='lines'?v.split('\n').map(x=>x.trim()).filter(Boolean):tp==='words'?v.split(/\s+/).filter(Boolean):v)});
}
function openSlide(p,i){
  const s=JSON.parse(JSON.stringify({template:'photo_box',...p.cards[i].slide}));Object.assign(SL,{p,i,slide:s});
  $('#sl-title').textContent=`${i+1}번째 장 편집 · ${TPL_KO[s.template]||KIND_LABEL[p.cards[i].kind]}`;
  slideForm();$('#sl-preview').src=imgUrl('generate',p.folder,p.cards[i].file)+'?v='+Date.now();$('#sl-msg').textContent='';$('#slx').classList.add('open');
}
$('#sl-close').onclick=()=>$('#slx').classList.remove('open');
$('#sl-save').onclick=async()=>{
  collectSlide();const s=SL.slide;
  const b=$('#sl-save');b.disabled=true;$('#sl-msg').textContent='만드는 중…';
  try{await post('/api/pub/card/slide',{file:SL.p.file,index:SL.i,slide:s});const d=await pubReload(SL.p.file);SL.p={...d,file:SL.p.file};
    $('#sl-preview').src=imgUrl('generate',d.folder,d.cards[SL.i].file)+'?v='+Date.now();$('#sl-msg').textContent='다시 만들었습니다 ✓'}
  catch(e){showErr(e);$('#sl-msg').textContent=''}finally{b.disabled=false}
};

/* 새로 고침해도 서버에서 아직 도는 작업을 다시 붙인다 */
async function jobsRecover(){
  let list=[];try{list=await api('/api/jobs')}catch(e){return}
  for(const j of list){if(RUN[j.id])continue;const m=j.meta||{},title=m.title||j.label||'작업';
    try{if(m.kind==='plan'){const t=deskFind('plan',m.plan_file)||deskAdd({kind:'plan',file:null,data:null,title},false);planJob(t,j.id,title)}
      else if(m.kind==='publish')pubJob(deskAdd({kind:'pub',file:null,data:null,title},false),j.id);
      else if(m.kind==='crawl')crawlJob(j.id,title,/새로 찾기/.test(title)?$('#btn-tag-new'):$('#btn-tag'));
      else if(m.kind==='login')loginJob(j.id);
      else runJob(j.id,title).catch(()=>{})}catch(e){}}
}

/* ---------- 결과 보기: 수집 → 기획 → 생성 ---------- */
let rawCur='';
const OV={data:null,sel:null};
const KIND_NAME={crawl:'수집',analysis:'기획',generate:'생성'};
const day=w=>w?w.slice(5).replace('-','/'):'';
const ovFind=(k,n)=>OV.data&&OV.data[k].find(x=>x.name===n);
const ovTitle=(k,x)=>k==='crawl'?x.title:first(x.title||x.type);
const genShown=g=>g.group==='완성본'||g.group==='편집본';
function ovLinks(k,n){
  const D=OV.data,s=new Set([k+'|'+n]),add=(kk,nn)=>nn&&s.add(kk+'|'+nn),gensOf=a=>D.generate.filter(g=>g.parent===a);
  if(k==='crawl')D.analysis.filter(a=>a.parent===n).forEach(a=>{add('analysis',a.name);gensOf(a.name).forEach(g=>add('generate',g.name))});
  if(k==='analysis'){const a=ovFind(k,n);add('crawl',a&&a.parent);gensOf(n).forEach(g=>add('generate',g.name))}
  if(k==='generate'){const g=ovFind(k,n),a=g&&ovFind('analysis',g.parent);add('analysis',g&&g.parent);add('crawl',a&&a.parent);(g&&g.parts||[]).forEach(x=>add('generate',x))}
  return s;
}
function ovThumb(x,k){const pg=x.pages>1?`<span class="pg">${x.pages}장</span>`:'';
  if(x.thumb)return `<div class="oth"><img loading="lazy" src="${esc(x.thumb)}">${pg}</div>`;
  return `<div class="oth txt">${nl(ovTitle(k,x)).split('\n').slice(-3).map(l=>`<span>${esc(l)}</span>`).join('')}</div>`}
function ovCard(k,x){
  const D=OV.data;let sub='',tags='';
  if(k==='crawl'){const na=D.analysis.filter(a=>a.parent===x.name).length;sub=`${x.count}개 · 최고 ♥ ${fmt(x.top)??'—'}`;tags=na?`<span class="tag next">기획 ${na} →</span>`:''}
  if(k==='analysis'){const ng=D.generate.filter(g=>g.parent===x.name&&g.type==='발행').length;
    sub=[x.project,x.mode,`레퍼런스 ${x.picks.map(n=>'#'+n).join(' ')}`].filter(Boolean).join(' · ');
    tags=x.type?`<span class="tag">${esc(x.type)}</span>`:`<span class="tag t-plan">${x.rounds>1?`라운드 ${x.rounds}`:'기획'}</span>`+(ng?`<span class="tag next">완성본 ${ng} →</span>`:'')}
  if(k==='generate'){sub=[x.mode,x.pages?`카드 ${x.pages}장`:''].filter(Boolean).join(' · ');
    tags=x.type==='발행'?'<span class="tag t-pub">완성본</span>':'<span class="tag" title="캔버스에서 저장만 하고 완성본은 안 만든 것">편집본</span>'}
  return `<button class="ocard" data-k="${k}" data-n="${esc(x.name)}" title="${esc(x.name)}">${ovThumb(x,k)}<div class="ot">
    <div class="otitle">${esc(ovTitle(k,x))}</div><div class="osub">${esc(sub)}</div><div class="ometa"><time>${esc(day(x.when))}</time>${tags}</div></div></button>`;
}
function ovRender(){
  const D=OV.data;const EMPTY={crawl:'아직 수집한 결과가 없습니다.',analysis:'아직 기획한 결과가 없습니다.<br>수집 결과에서 레퍼런스를 골라 기획해 보세요.',generate:'아직 저장한 완성본이 없습니다.'};
  for(const k of ['crawl','analysis','generate']){const list=D[k].filter(x=>k!=='generate'||genShown(x));
    if(k==='generate')list.sort((a,b)=>(a.group==='편집본')-(b.group==='편집본'));
    $('#n-'+k).textContent=k==='generate'?list.filter(x=>x.group==='완성본').length:list.length;
    $('#c-'+k).innerHTML=list.map((x,i)=>(k==='generate'&&x.group==='편집본'&&(i===0||list[i-1].group!=='편집본')?'<div class="colsep">저장 전 편집본</div>':'')+ovCard(k,x)).join('')||`<div class="empty">${EMPTY[k]}</div>`}
  $$('#board .ocard').forEach(b=>b.onclick=()=>SEL.on?selToggle(b):openFile(b.dataset.k,b.dataset.n));selPaint();ovMark();
}
function ovMark(){
  const s=OV.sel,links=s?ovLinks(s.k,s.n):new Set();$('#board').classList.toggle('focus',!!s);
  $$('#board .ocard').forEach(b=>{const key=b.dataset.k+'|'+b.dataset.n;b.classList.toggle('on',!!s&&b.dataset.k===s.k&&b.dataset.n===s.n);b.classList.toggle('link',links.has(key))});
  if(!s){$('#trail').innerHTML='';return}
  const step=(k,x)=>x?`<button data-k="${k}" data-n="${esc(x.name)}" class="${k===s.k&&x.name===s.n?'on':''}">${KIND_NAME[k]} · ${esc(ovTitle(k,x))}</button>`:'';
  let c,a,g;if(s.k==='crawl')c=ovFind('crawl',s.n);if(s.k==='analysis'){a=ovFind('analysis',s.n);c=a&&ovFind('crawl',a.parent)}
  if(s.k==='generate'){g=ovFind('generate',s.n);a=g&&ovFind('analysis',g.parent);c=a&&ovFind('crawl',a.parent)}
  const parts=[step('crawl',c),step('analysis',a),step('generate',g)].filter(Boolean);
  $('#trail').innerHTML=parts.length>1?'<span class="hint">이 결과의 흐름</span> '+parts.join('<span class="sep">›</span>'):'';
  $$('#trail button').forEach(b=>b.onclick=()=>openFile(b.dataset.k,b.dataset.n));
}
const SEL={on:false,keys:new Set()};const selKey=b=>b.dataset.k+'|'+b.dataset.n;
function selMode(on){SEL.on=on;if(!on)SEL.keys.clear();$('#board').classList.toggle('selmode',on);$('#selbar').classList.toggle('hidden',!on);
  $$('#board .colall').forEach(l=>l.classList.toggle('hidden',!on));$('#sel-mode').classList.toggle('hidden',on);selPaint()}
function selToggle(b){const k=selKey(b);SEL.keys.has(k)?SEL.keys.delete(k):SEL.keys.add(k);selPaint()}
function selPaint(){const vis=$$('#board .ocard');SEL.keys.forEach(k=>{if(!vis.some(b=>selKey(b)===k))SEL.keys.delete(k)});
  vis.forEach(b=>b.classList.toggle('picked',SEL.keys.has(selKey(b))));
  $$('#board [data-colall]').forEach(c=>{const cs=$$(`#c-${c.dataset.colall} .ocard`),n=cs.filter(b=>SEL.keys.has(selKey(b))).length;c.checked=!!cs.length&&n===cs.length;c.indeterminate=n>0&&n<cs.length;c.disabled=!cs.length});
  const n=SEL.keys.size;$('#sel-n').textContent=n+'개 선택';$('#sel-del').disabled=!n;$('#sel-del').textContent=n?`선택한 ${n}개 삭제`:'선택한 결과 삭제'}
$('#sel-mode').onclick=()=>selMode(true);$('#sel-done').onclick=()=>selMode(false);
$('#sel-all').onclick=()=>{$$('#board .ocard').forEach(b=>SEL.keys.add(selKey(b)));selPaint()};$('#sel-none').onclick=()=>{SEL.keys.clear();selPaint()};
$('#board').addEventListener('change',e=>{const k=e.target.dataset&&e.target.dataset.colall;if(!k)return;$$(`#c-${k} .ocard`).forEach(b=>e.target.checked?SEL.keys.add(selKey(b)):SEL.keys.delete(selKey(b)));selPaint()});
$('#sel-del').onclick=()=>{
  const items=[...SEL.keys].map(k=>{const i=k.indexOf('|');return{kind:k.slice(0,i),name:k.slice(i+1)}});if(!items.length)return;
  const D=OV.data,picked=new Set(items.map(x=>x.name));
  const extra=[...new Set(items.filter(x=>x.kind==='generate').flatMap(x=>(ovFind('generate',x.name)||{}).parts||[]))].filter(n=>n&&!picked.has(n));
  const run=async list=>{try{const r=await post('/api/delete',{items:list});log(`결과 ${r.moved.length}개를 휴지통으로 옮겼습니다: ${r.trash}`);
      if(OV.sel&&list.some(x=>x.name===OV.sel.n)){OV.sel=null;$('#fname').textContent='위에서 결과를 선택하세요';$('#fgo').classList.add('hidden');$('#fcopy').classList.add('hidden');$('#fcards').innerHTML='';$('#fview').innerHTML='<div class="empty">삭제했습니다.</div>'}
      selMode(false);await loadFiles();fillSelect('crawl','#crawl-sel').then(loadPosts).catch(()=>{});toast(`${r.moved.length}개를 휴지통으로 옮겼습니다.`,'ok')}catch(e){showErr(e)}};
  const btns=extra.length?[{label:`썸네일·이미지 후보 ${extra.length}개도 함께 삭제`,danger:true,fn:()=>run([...items,...extra.map(n=>({kind:'generate',name:n}))])},{label:'고른 것만 삭제',fn:()=>run(items)},{label:'취소'}]
    :[{label:'삭제',danger:true,fn:()=>run(items)},{label:'취소'}];
  dialog(`${items.length}개를 삭제할까요?`,'md 기록과 이미지 폴더를 data › 휴지통 으로 옮깁니다. 바탕화면 카드뉴스 완성본 폴더의 이미지는 그대로 둡니다.',btns,{danger:true});
};
async function loadFiles(){OV.data=await api('/api/overview');if(OV.sel&&!ovFind(OV.sel.k,OV.sel.n))OV.sel=null;ovRender()}
function renderCands(d,box){
  const by=Object.fromEntries(d.candidates.map(c=>[c.file,c])),rk=Object.fromEntries((d.ranking||[]).map((r,k)=>[r.file,{...r,k:k+1}]));
  const order=[...(d.ranking||[]).map(r=>r.file),...d.candidates.map(c=>c.file)].filter((f,i,a)=>by[f]&&a.indexOf(f)===i);
  box.innerHTML='<div class="cands">'+order.map(f=>{const c=by[f],r=rk[f];return `<div class="cand"><img loading="lazy" src="${imgUrl('generate',d.assets,f)}">
    ${r?`<span class="rank">추천 ${r.k}</span><span class="score">${esc(r.score)}점</span>`:''}<div class="ct">${r?`<b>${esc(r.reason)}</b>`:`<small>${esc(c.alt||'')}</small>`}
    ${c.pin?`<a href="${esc(c.pin)}" target="_blank" class="hint">원본 핀 ↗</a>`:''}</div></div>`}).join('')+'</div>';
}
let openSeq=0;
async function openFile(kind,name){
  const my=++openSeq;OV.sel={k:kind,n:name};ovMark();
  const r=await api(`/api/file/${kind}/${encodeURIComponent(name)}`);if(my!==openSeq)return;rawCur=r.content;const d=r.data||{};
  const it=ovFind(kind,name);$('#fname').textContent=it?`${KIND_NAME[kind]} 결과 · ${ovTitle(kind,it)}`:name;$('#fname').title=name;
  $('#fcopy').classList.remove('hidden');$('#fcards').innerHTML='';
  let GO=null;
  if(kind==='crawl')GO=['이 수집 결과로 기획하기',async()=>{tab('work');await fillSelect('crawl','#crawl-sel',name);$('#crawl-sel').value=name;await loadPosts();showResults()}];
  if(kind==='analysis'&&d.rounds)GO=['이 기획 이어서 하기 (피드백·편집)',async()=>{tab('work');deskOpen('plan',{...d,file:name});deskScroll()}];
  if(kind==='generate'&&d.type==='발행')GO=['카드 편집 · 캡션',async()=>{tab('work');deskOpen('pub',{...d,file:name});deskScroll()}];
  if(kind==='generate'&&d.type==='썸네일')GO=['썸네일 다시 편집',async()=>openCanvas({copy:d.copy,state:d.state,cands:await candStrip(d.cand_file),
    meta:{...d.meta,cand_file:d.cand_file}})];
  $('#fgo').classList.toggle('hidden',!GO);if(GO){$('#fgo').textContent=GO[0]+' →';$('#fgo').onclick=()=>GO[1]().catch(showErr)}
  let html='';
  if(kind==='crawl'){const folder=folderOf(name);html=`<div class="sumbar"><span class="badge">${esc(d.source||'')}</span><span class="badge">${(d.posts||[]).length}개 수집</span>${Object.entries(d.params||{}).map(([k,v])=>`<span class="badge">${esc(k)} ${esc(v)}</span>`).join('')}</div>
      <div class="posts">${grid(d.posts||[],folder,{})}</div><h3>md 기록</h3>`;
    $('#fview').innerHTML=html+'<div class="paper">'+md(r.content,'crawl')+'</div>';
    $$('#fview .pcard').forEach(el=>el.querySelector('.detail').onclick=()=>openModal(d.posts[+el.dataset.i-1],folder));return}
  if(kind==='generate'&&d.type==='발행')$('#fcards').innerHTML=d.cards.map(c=>`<a href="${imgUrl('generate',d.folder,c.file)}" target="_blank"><img src="${imgUrl('generate',d.folder,c.file)}"></a>`).join('');
  $('#fview').innerHTML=(d.type==='이미지후보'?'<div id="fcands"></div>':'')+'<div class="paper">'+md(r.content,kind)+'</div>';
  if(d.type==='이미지후보')renderCands(d,$('#fcands'));
}
$('#fcopy').onclick=()=>{navigator.clipboard.writeText(rawCur);toast('원문을 복사했습니다.','ok')};
$('#files-reload').onclick=()=>loadFiles();

/* ---------- 작업 보관함: 모든 기획 후보 + 저장한 완성본 ---------- */
const LIB={data:null,status:'전체',proj:'all'};
const LIB_ST=['전체','안 쓴 후보','저장됨'];
async function loadLib(){try{LIB.data=await api('/api/library');libRender()}catch(e){showErr(e)}}
$('#lib-reload').onclick=loadLib;
let libSeq=0;const libQueue=[];let libBusy=false;
async function libDrain(){if(libBusy)return;libBusy=true;while(libQueue.length){const f=libQueue.shift();try{await f()}catch(e){}}libBusy=false}
function libRender(){
  const all=LIB.data.items,projs=[...new Set(all.map(x=>x.project).filter(Boolean))];
  $('#lib-status').innerHTML=LIB_ST.map(st=>`<button data-s="${st}" class="${LIB.status===st?'on':''}">${st} ${all.filter(x=>st==='전체'||x.status===st).length}</button>`).join('');
  $('#lib-proj').innerHTML=[['all','모든 프로젝트'],...projs.map(p=>[p,p])].map(([b,l])=>`<button data-b="${esc(b)}" class="${LIB.proj===b?'on':''}">${esc(l)}</button>`).join('');
  $$('#lib-status button').forEach(b=>b.onclick=()=>{LIB.status=b.dataset.s;libRender()});$$('#lib-proj button').forEach(b=>b.onclick=()=>{LIB.proj=b.dataset.b;libRender()});
  const list=all.filter(x=>(LIB.proj==='all'||x.project===LIB.proj)&&(LIB.status==='전체'||x.status===LIB.status));
  const my=++libSeq;libQueue.length=0;
  $('#lib-grid').innerHTML=list.map((x,i)=>{const p=x.pub;
    return `<div class="pc lc" data-i="${i}"><div class="pv">${p?`<img src="${imgUrl('generate',p.folder,p.cards[0].file)}">`:'<img alt="">'}<span class="no">${esc(x.project||'')}</span>${!p&&!x.bg?'<span class="noimg">이미지 없음</span>':''}</div>
      <div class="pcb"><div class="ometa"><span class="tag ${p?'t-pub':''}">${p?'저장됨':'안 쓴 후보'}</span><span class="tag">${x.mode==='long'?'롱폼':'단일'}</span><time style="margin-left:auto">${esc(day(x.when))}</time></div>
        <div class="pangle">${esc(x.angle||'')}</div>
        <details><summary>캡션${x.slides.length?` · 본문 ${x.slides.length}장`:''} 보기</summary>${x.slides.length?`<ol start="2">${x.slides.map(slideLi).join('')}</ol>`:''}<pre>${esc(x.caption)}</pre></details>
        <div class="hint" style="font-size:12px">기획 ${esc(x.plan_file.slice(0,15))} · 라운드 ${x.round} · 후보 ${x.cand}${x.pubs>1?` · 저장 ${x.pubs}번`:''}</div>
        <div class="acts">${p?'<button class="btn sm pri lib-open">열기</button><button class="btn sm lib-edit">다시 편집</button>':'<button class="btn sm pri lib-edit">편집해서 저장 →</button>'}<button class="btn sm lib-rf">✏️ 고치기</button></div>
        <div class="refine hidden lib-rfbox"><textarea placeholder="어떻게 바꿀까요?&#10;예) 첫 줄을 더 세게 / 현장 증언형으로 / 이미지는 그대로"></textarea>
          <div class="row"><button class="btn sm pri lib-rf-go">이 내용으로 다시 기획 (후보 3개)</button></div></div></div></div>`}).join('')
    ||`<div class="empty" style="grid-column:1/-1">${all.length?'조건에 맞는 후보가 없습니다.':'아직 기획한 후보가 없습니다. 작업 탭에서 레퍼런스를 골라 기획해 보세요.'}</div>`;
  $$('#lib-grid .lc').forEach(el=>{const x=list[+el.dataset.i];
    el.querySelector('.lib-edit').onclick=()=>libEdit(x).catch(showErr);
    const bx=el.querySelector('.lib-rfbox');el.querySelector('.lib-rf').onclick=()=>{bx.classList.toggle('hidden');if(!bx.classList.contains('hidden'))bx.querySelector('textarea').focus()};
    el.querySelector('.lib-rf-go').onclick=()=>refineCand(x,bx.querySelector('textarea').value).catch(showErr);
    const o=el.querySelector('.lib-open');if(o)o.onclick=()=>{tab('work');deskOpen('pub',{...x.pub,file:x.pub.file});deskScroll()};
    if(!x.pub)libQueue.push(()=>my!==libSeq?null:thumbPreview({copy:x.copy,label:x.label,callouts:x.callouts,tags:x.tags,bg:x.bg}).then(u=>{if(my===libSeq)el.querySelector('.pv img').src=u}))});
  libDrain();
}
async function libEdit(x){
  const meta={analysis_file:x.plan_file,plan_round:x.round,plan_cand:x.cand,cand_file:(x.img||{}).file||''};
  if(x.pub){const t=(await api('/api/file/generate/'+encodeURIComponent(x.pub.thumb_file)).catch(()=>({}))).data;
    if(t&&t.state)return openCanvas({copy:t.copy,state:t.state,cands:await candStrip(meta.cand_file),meta})}
  const plan=(await api('/api/file/analysis/'+encodeURIComponent(x.plan_file))).data;
  editCandidate({plan_file:x.plan_file,round:x.round,cand:x.cand,c:plan.rounds[x.round-1].candidates[x.cand-1],mode:x.mode});
}

/* ---------- 탭 · 시작 ---------- */
function tab(w,skip){for(const v of ['work','lib','files']){$('#v-'+v).classList.toggle('hidden',w!==v);$('#t-'+v).classList.toggle('on',w===v)}
  if(w==='files'&&!skip)loadFiles();if(w==='lib'&&!skip)loadLib()}
$('#t-work').onclick=()=>tab('work');$('#t-lib').onclick=()=>tab('lib');$('#t-files').onclick=()=>tab('files');
(async()=>{try{await loadMeta();await fillSelect('crawl','#crawl-sel');await loadPosts();await deskRestore();await jobsRecover()}catch(e){showErr(e)}})();
