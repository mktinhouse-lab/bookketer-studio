// 북케터밈 카드 템플릿(1080×1350). 편집기 미리보기와 /render(PNG 내보내기)가 같은 함수를 쓴다.
// renderCard(slide, index, cards, img) → { el, ready: Promise }   img(sub, name) → 이미지 주소
(function () {
  const MINT = '#D4FEBE';
  const COLOR = {흰색: '#FFFFFF', 민트: MINT};
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // 사진을 상자(box)에 꽉 차게(cover) + 확대(zoom) + 위치(px,py %) 로 놓는다
  function placeBg(card, src, box, zoom, px, py, opacity) {
    if (!src) return Promise.resolve();
    const im = h('img', 'bgimg'); im.src = src; im.style.opacity = opacity ?? 1;
    card.appendChild(im);
    return new Promise(ok => {
      const fit = () => {
        const s = Math.max(box.w / im.naturalWidth, box.h / im.naturalHeight) * (zoom || 1);
        const W = im.naturalWidth * s, H = im.naturalHeight * s;
        im.style.width = W + 'px'; im.style.height = H + 'px';
        im.style.left = box.x + (box.w - W) * (px ?? 50) / 100 + 'px';
        im.style.top = box.y + (box.h - H) * (py ?? 50) / 100 + 'px';
        ok();
      };
      if (im.complete && im.naturalWidth) fit(); else { im.onload = fit; im.onerror = ok; }
    });
  }
  function grad(card, strength) {
    const g = h('div', 'grad');
    const a = Math.max(0, Math.min(1, strength ?? 1));
    g.style.background = `linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,${0.72 * a}) 48%, rgba(0,0,0,${0.96 * a}) 100%)`;
    card.appendChild(g);
  }
  // 한 줄이 1000px 를 넘으면 줄여서 맞춘다(글자 크기 비율 유지)
  function fitLine(span, max) {
    requestAnimationFrame(() => { const w = span.scrollWidth; if (w > max) span.style.transform = `scale(${max / w})`; });
  }

  window.renderCard = function (s, i, cards, img) {
    const card = h('div', 'card');
    const waits = [];
    const bodyBg = () => waits.push(placeBg(card, cards.body_bg && img('04_배경', cards.body_bg), {x: 0, y: -56, w: 1097, h: 1462},
      cards.body_zoom, cards.body_px, cards.body_py, cards.body_opacity ?? 0.27));
    if (s.type === 'thumb') {
      waits.push(placeBg(card, s.bg && img('04_배경', s.bg), {x: 0, y: 0, w: 1080, h: 1350}, s.zoom, s.px, s.py, 1));
      grad(card, s.shade);
      [[s.chip1, 49], [s.chip2, 116]].forEach(([t, y]) => { if (!t) return; const c = h('div', 'chip lab', t); c.style.top = y + 'px'; card.appendChild(c); });
      const size = 105.7 * (s.size || 1), dy = s.dy || 0;
      [[s.line1, s.c1 || '#FFFFFF', 922], [s.line2, s.c2 || MINT, 1046]].forEach(([t, c, y]) => {
        const row = h('div', 'copy'); row.style.top = y + dy + 'px';
        const sp = h('span', null, t || ''); sp.style.color = c; sp.style.fontSize = size + 'px';
        row.appendChild(sp); card.appendChild(row); fitLine(sp, 1010);
      });
    } else if (s.type === 'book') {
      bodyBg();
      // 하단 검정 그라데이션은 썸네일에만(사용자 지시 10/15). 책 소개 장에는 넣지 않는다.
      const t = h('div', 'chip bchip t', s.title || ''); card.appendChild(t);
      if ((s.tags || '').trim()) card.appendChild(h('div', 'chip bchip h', s.tags.trim()));
      const cv = h('div', 'cover');
      if (s.cover) { const im = h('img'); im.src = img('03_책표지', s.cover); cv.appendChild(im); waits.push(new Promise(ok => { im.onload = ok; im.onerror = ok; })); }
      card.appendChild(cv);
      const d = h('div', 'desc'); d.style.top = 908 + (s.dy || 0) + 'px';
      d.style.fontSize = 36.4 * (s.size || 1) + 'px'; d.style.lineHeight = 50 * (s.size || 1) + 'px';
      (s.lines || []).forEach(l => { const r = h('div', null, l.text); r.style.color = COLOR[l.color] || l.color || '#fff'; d.appendChild(r); fitLine(r, 1000); });
      card.appendChild(d);
    } else {
      bodyBg();
      card.appendChild(h('div', 'cta-main', s.main || ''));
      card.appendChild(h('div', 'cta-sub', s.sub || ''));
      card.appendChild(h('div', 'pill'));
      // 프로필 사진(assets/profile.jpg)을 바꾸면 새로고침만으로 반영되게 주소에 시각을 붙인다
      const pf = h('div', 'pf'); const pim = h('img'); pim.src = '/api/brand/profile?v=' + (window.__pv || (window.__pv = Date.now())); pf.appendChild(pim); card.appendChild(pf);
      waits.push(new Promise(ok => { pim.onload = ok; pim.onerror = ok; }));
      card.appendChild(h('div', 'pid', 'bookketer_mim'));
      card.appendChild(h('div', 'fbtn', '팔로우'));
      const cur = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      cur.setAttribute('viewBox', '0 0 70 84'); cur.setAttribute('class', 'cursor');
      cur.innerHTML = '<path d="M6 4 L6 64 L22 50 L33 76 L44 71 L33 46 L54 46 Z" fill="#000" stroke="#fff" stroke-width="4" stroke-linejoin="round"/>';
      card.appendChild(cur);
    }
    const ready = Promise.all([document.fonts ? document.fonts.ready : Promise.resolve(), ...waits]);
    return {el: card, ready};
  };
})();
