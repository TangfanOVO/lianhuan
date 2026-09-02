/*!
 * call.js —— 打电话页。
 * ════════════════════════════════════════════════════════════════
 * 整段照搬原项目 redesign/call.html 的 <script>（405–1257 行）。相位机、逐字落下、打断墨点、
 * 按 age 淡出缩字、贴耳黑屏、换皮、打字条、对外接线口 window.__call —— 名字和值都没动。
 *
 * 三处**减法**（每处都在下面注明，没有一处是重画）：
 *   ① 那条线不在这儿画：它是独立的一块，`<script src="../thread/thread.js">`，
 *      原项目 600–810 行那段 canvas 代码就是它的来源，这儿只喂相位和音量。
 *   ② 麦克风（原项目 576–604）整段拿掉：**这一页不申请麦克风**。
 *      micLevel() 留一个恒返回 -1 的桩，半打断那条路因此不触发；barge() 作为 API 还在。
 *   ③ 真接线 WIRE（1259–1396，WebSocket）、重演（899–1134，要 fetch 录音）、
 *      嵌进宿主的 EMBED（872–897，postMessage）都不搬：预览页不发任何请求。
 *      所以 DEMO 留在 true —— 那正是原项目给「浏览器里看」留的那条分支。
 *
 * 页面上的那通电话是**编的剧本**，不是任何人真说过的话。
 *
 * 用：
 *   <link rel="stylesheet" href="../base/tokens.css">
 *   <link rel="stylesheet" href="../thread/thread.css">
 *   <link rel="stylesheet" href="call.css">
 *   …照 demo.html 那份 DOM…
 *   <script src="../base/crest.js"></script>
 *   <script src="../thread/thread.js"></script>
 *   <script src="call.js"></script>
 *
 * 接自己的后端：界面只吃 window.__call 的调用（方法名见文件末尾），把 DEMO 改成 false。
 */
(function (global) {
'use strict';

/* ══════ 名字只在这一处 ══════
   界面上所有露名字的地方（待机页标题、来电提示、转写标签、瞥一眼那句大字）都引下面这两个
   常量 —— 代码里没有第二处写死的名字，**改这两行就换成你自己的**。
   （demo.html 里另有两处静态文案：顶栏 .who 和打字条 placeholder。那是宿主自己的 DOM，
     换名字时跟着一起改。） */
const NAME = '伙伴';   /* 对面那一侧（AI）在界面上叫什么 */
const ME   = '我';     /* 这一侧（用户）在转写标签里叫什么 */

function boot(){
const $ = s => document.querySelector(s);
const B = document.body;
let reduce = false;
try{ reduce = matchMedia('(prefers-reduced-motion:reduce)').matches; }catch(e){}

/* ★ 演示开关。接后端时改成 false：界面只吃 window.__call 的调用，不自己演。
   ★ 预览版留 true —— 这一页不连任何服务，主键按下去走的就是下面 script() 那段编的剧本。 */
const DEMO = true;
/* 打字机速度（接 TTS 后改由播放进度驱动 bump()） */
const TYPE_MS = 46;   /* 0818：74 太慢，音频播完字还没走完 */

const WORDS = {idle:'待机',incoming:'来电',ringing:'呼叫中',connecting:'接通中',listening:'在听',thinking:'在想',speaking:'在说',ended:'已挂断'};
const BIG   = {idle:'',incoming:NAME+'打过来了',ringing:'正在呼叫',connecting:'接通中',listening:'在听你说',thinking:NAME+'在想',speaking:NAME+'在说',ended:'已挂断'};
/* ★ 原项目这四句是真的聊天记录。开源这份**全换成编的** —— 谁都没说过这几句话。
   句子的形状留着（用户先开口、伙伴说到一半被打断、最后那句是英文带一行中文转录），
   因为要演的就是这几件事。 */
const L1='喂？听得到吗，我这边有点吵。',
      L2='听得到。你先说，我这边安静——',
      L3='那我说啦！今天那个东西我做完了。',
      L4="Then let's call it a day.",
      A4='那今天就到这儿。';           /* L4 的中文转录：说英文时跟在原句下面那行小字 */

const S = {phase:'idle', lines:[], muted:false, ear:false, skin:'talk', typing:false};
let seq = 0, timers = [], runId = 0, tick = null, typer = null, muteBefore = false;

/* ══════ 那条线 ══════
   ★ 不在这儿画。它是独立的一块：../thread/thread.js。
     原项目 call.html 里那段 canvas 代码就是它的来源（叶子的 path 也是同一片枫叶，
     从 ../base/crest.js 的 Crest.def('maple') 取，全仓库只有那一份）。
     这儿只做两件事：把相位转过去，把音量转过去。 */
const leafDef = (global.Crest && global.Crest.def) ? global.Crest.def('maple') : null;
/* 待机页那片家徽也读同一份 path —— 不另贴一份 */
(function(){
  const sv = $('#crest'); if(!sv || !leafDef) return;
  sv.setAttribute('viewBox', leafDef.viewBox);
  const p = sv.querySelector('path'); if(p) p.setAttribute('d', leafDef.path);
})();
const cv = $('#thread');
const th = (cv && global.Thread) ? global.Thread(cv, {leaf: leafDef}) : null;

/* ══════════════════════════════════════════════════
   相位机 —— 六个名字照抄规格；incoming / ringing 是响铃那一下，界面自己多的两段
   idle → (incoming|ringing) → connecting → listening ⇄ thinking → speaking → … → ended
   ══════════════════════════════════════════════════ */
function setPhase(p){
  if(S.phase === p) return;
  S.phase = p;
  global.__phase = p;                 /* (0819) 嵌在宿主里时，宿主靠它兜底知道电话结束没 */
  if(th) th.setPhase(p);              /* 线上的波、叶子、拆线，都归那块管 */
  /* 表由相位机自己管：只调 setPhase 也会走表，不挂在演示上。响铃不计时 */
  if(p === 'idle'){ stopTimer(); $('#timer').textContent = '00:00'; }
  else if(p === 'ended' || p === 'incoming' || p === 'ringing') stopTimer();
  else if(!tick) startTimer();
  paint();
}
function startTimer(){
  const t0 = performance.now();
  stopTimer();
  tick = setInterval(()=>{
    const s = Math.floor((performance.now()-t0)/1000);
    $('#timer').textContent = String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');
  }, 250);
}
function stopTimer(){ clearInterval(tick); tick = null; }
const wait = ms => new Promise(r => timers.push(setTimeout(r, ms)));
function stopRun(){ runId++; timers.forEach(clearTimeout); timers = []; clearInterval(typer); typer = null; }

/* ══════ 话 ══════
   用户的话：整句落上去（识别本来就是说完才回来的）
   伙伴的话：逐字浮现，跟着实际说到哪个字走                                  */
function hers(text, alt){
  S.lines = [...S.lines, {id:++seq, side:'hers', text, alt, shown:text.length, cut:false}].slice(-40);
  paint();
}
function type(text, cutAt, alt){
  return new Promise(resolve=>{
    const id = ++seq, run = runId;
    setPhase('speaking');
    S.lines = [...S.lines, {id, side:'mine', text, alt, shown:0, cut:false}].slice(-40);
    paint();
    if(reduce){ bump(id, text.length); resolve(); return; }
    let i = 0;
    const cut = cutAt ? Math.floor(text.length*cutAt) : -1;
    clearInterval(typer);
    typer = setInterval(()=>{
      if(run !== runId){ clearInterval(typer); resolve(); return; }
      i++;
      /* 打断是真的：字停在那儿不消失，末尾留一个墨点 */
      if(cut > 0 && i >= cut){ clearInterval(typer); bump(id, i, true); setPhase('listening'); resolve('cut'); return; }
      bump(id, i);
      if(i >= text.length){ clearInterval(typer); typer = null; resolve(); }
    }, TYPE_MS);
  });
}
function bump(id, shown, cut){
  const l = S.lines.find(x => x.id === id); if(!l) return;
  l.shown = shown; if(cut) l.cut = true;
  paint();
}
/* 用户一开口：掐掉回放、跳回 listening。★ 接了 TTS 的宿主还要在这儿 abort 掉那条流式请求 */
function barge(){
  if(S.phase !== 'speaking') return;
  const l = S.lines[S.lines.length-1];
  if(l && l.side === 'mine'){ clearInterval(typer); typer = null; l.cut = true; }
  setPhase('listening');
}

/* ══════ 画 DOM ══════ */
function paint(){
  const p = S.phase, pre = p === 'idle' || p === 'incoming' || p === 'ringing';
  B.dataset.phase = p;
  B.dataset.pre = pre ? '1' : '0';
  B.dataset.skin = S.skin;
  B.dataset.typing = S.typing ? '1' : '0';
  B.dataset.ear = S.ear ? '1' : '0';
  $('#word').textContent = S.typing ? '在打字' : WORDS[p];
  $('#big').textContent = BIG[p];
  $('#pretitle').textContent = p === 'idle' ? '给' + NAME + '打电话' : NAME;
  $('#presub').textContent = p === 'incoming' ? NAME + '打过来了'
    : p === 'ringing' ? '正在呼叫…' : '接通之后，外放看着，或者贴到耳边';
  $('#primary').setAttribute('aria-label', p === 'idle' ? '拨号' : p === 'incoming' ? '拒接' : '挂断');
  $('#mute').setAttribute('aria-pressed', String(S.muted));
  $('#earbtn').setAttribute('aria-pressed', String(S.ear));

  const tl = $('#tl');
  const n = S.lines.length;
  let prevSide = null;
  S.lines.forEach((l, i)=>{
    const age = Math.min(3, n-1-i);
    let el = tl.querySelector('[data-id="'+l.id+'"]');
    if(!el){
      el = document.createElement('div');
      el.className = 'ln'; el.dataset.id = l.id; el.dataset.side = l.side;
      el.innerHTML = '<div class="tag"></div><div class="say"></div>';
      el.querySelector('.tag').textContent = (l.side === 'mine' ? NAME : ME)
        + (l.ms ? ' · ' + (l.side === 'mine' ? '想了 ' : '听懂 ') + (l.ms/1000).toFixed(1) + 's' : '');
      tl.appendChild(el);
    }
    /* ★ 0820 逮到的：翻译是**后到**的（说完才翻），
       而 alt 原来只在「元素第一次创建」那一支里渲染 —— 后到的那行永远画不出来。
       挪出来：每次 paint 都对一下，有就补、变了就改。 */
    if(l.alt){
      let a = el.querySelector('.alt');
      if(!a){ a = document.createElement('div'); a.className = 'alt'; el.appendChild(a); }
      if(a.textContent !== l.alt) a.textContent = l.alt;
    }
    if(l.ms){ const tg = el.querySelector('.tag');
      const want = (l.side === 'mine' ? NAME + ' · 想了 ' : ME + ' · 听懂 ') + (l.ms/1000).toFixed(1) + 's';
      if(tg.textContent !== want) tg.textContent = want; }
    el.dataset.age = age;
    el.dataset.tag = l.side === prevSide ? '0' : '1';
    el.style.gridRow = String(i+1);
    prevSide = l.side;
    const say = el.querySelector('.say');
    if(l.side === 'hers'){
      if(say.textContent !== l.text) say.textContent = l.text;
    }else{
      /* 已经落下的字不重画，只补新的那几个 —— 不然每个字都会重播一次落下 */
      const have = say.querySelectorAll('span').length;
      for(let k = have; k < l.shown; k++){
        const sp = document.createElement('span'); sp.textContent = l.text[k]; say.appendChild(sp);
      }
      if(l.cut && !say.querySelector('.caret')){
        const c = document.createElement('span'); c.className = 'caret'; say.appendChild(c);
      }
    }
  });
  const live = new Set(S.lines.map(l => String(l.id)));
  tl.querySelectorAll('.ln').forEach(el =>{ if(!live.has(el.dataset.id)) el.remove(); });
  /* (0820) 新字往下长的时候自己贴着底 —— 除非用户自己往上翻了（那就别抢位置） */
  if(!tl._userScroll){ tl.scrollTop = tl.scrollHeight; }

  const last = S.lines[n-1];
  const gl = $('#glanceline');
  gl.textContent = last ? (last.side === 'mine' ? last.text.slice(0, last.shown) : last.text) : '';
  gl.dataset.side = last ? last.side : '';
}

/* (0820) 通话转写要能上滑看记录：翻上去了就别再抢；翻回底部自动恢复 */
(function(){
  const tl = $('#tl');
  if(!tl) return;
  tl.addEventListener('scroll', ()=>{
    const atEnd = tl.scrollHeight - tl.scrollTop - tl.clientHeight < 40;
    tl._userScroll = !atEnd;
  }, {passive:true});
})();

/* ══════ 控制 ══════ */
async function dial(){
  S.lines = []; S.typing = false;
  const run = ++runId, ok = ()=> run === runId;
  setPhase('ringing');
  await wait(1900); if(!ok()) return;
  await script(ok);
}
function incomingCall(){ stopRun(); S.lines = []; S.typing = false; setPhase('incoming'); }
async function pickUp(){
  const run = ++runId, ok = ()=> run === runId;
  await script(ok);
}
/* 演示脚本 —— 编的。DEMO=false 时整段不跑 */
async function script(ok){
  setPhase('connecting'); await wait(520); if(!ok()) return;
  setPhase('listening'); await wait(1100); if(!ok()) return;
  hers(L1); await wait(820); if(!ok()) return;
  setPhase('thinking'); await wait(2700); if(!ok()) return;
  await type(L2, .58); if(!ok()) return;          /* 说到 58% 被用户打断 */
  await wait(520); if(!ok()) return;
  hers(L3); await wait(760); if(!ok()) return;
  setPhase('thinking'); await wait(3400); if(!ok()) return;
  /* ★ 最后这一句在预览里多带两样东西，好让「想了 x.xs」那个标签和 alt 那行小字
     在剧本里真的露一次面（原项目是接了后端之后由 __call.pushMine / setAlt 喂进来的）。 */
  await type(L4, 0, A4); if(!ok()) return;
  const l4 = S.lines[S.lines.length-1]; if(l4){ l4.ms = 3400; paint(); }
  await wait(1200); if(!ok()) return;
  setPhase('listening');
}
function hangUp(){
  stopRun();
  S.ear = false; S.typing = false; S.muted = false;   /* 打字时自动掐的麦，挂断要还回去 */
  setPhase('ended');
  timers.push(setTimeout(()=>{ S.lines = []; setPhase('idle'); }, 1400));
}

$('#primary').addEventListener('click', ()=>{
  S.phase === 'idle' ? dial() : hangUp();
});
$('#answer').addEventListener('click', ()=> pickUp());
$('#lethim').addEventListener('click', ()=> incomingCall());   /* 原型开关，接线后删 */
$('#mute').addEventListener('click', ()=>{
  S.muted = !S.muted;
  paint();
});
$('#earbtn').addEventListener('click', ()=>{
  S.ear = !S.ear;
  if(S.ear) S.skin = 'glance';   /* 拿开手机那一下要能一眼读完，对话版做不到 */
  paint();
});
$('#ear').addEventListener('click', ()=>{ S.ear = false; paint(); });
$('#toTalk').addEventListener('click', ()=>{ S.skin = 'talk'; paint(); });
$('#toGlance').addEventListener('click', ()=>{ S.skin = 'glance'; paint(); });

/* 换皮也能左右划 */
let px = null, py = null;
$('#field').addEventListener('pointerdown', e =>{ px = e.clientX; py = e.clientY; });
$('#field').addEventListener('pointerup', e =>{
  if(px == null) return;
  const dx = e.clientX - px, dy = e.clientY - py; px = null;
  if(Math.abs(dx) > 46 && Math.abs(dx) > Math.abs(dy)*1.6){ S.skin = dx < 0 ? 'glance' : 'talk'; paint(); }
});

/* ── 打字：不方便说话时的另一张嘴 ── */
$('#typeopen').addEventListener('click', ()=>{
  muteBefore = S.muted; S.muted = true; S.typing = true;
  paint(); $('#draft').focus();
});
$('#typeclose').addEventListener('click', ()=>{
  S.typing = false; S.muted = muteBefore;
  paint();
});
$('#typerow').addEventListener('submit', e =>{
  e.preventDefault();
  const el = $('#draft'), v = (el.value||'').trim(); if(!v) return;
  el.value = '';
  const b = $('#send');   /* 发送键那一下是 0730 钉的：.9 → 1.06 → 1 */
  b.style.animation = 'none'; void b.offsetWidth;
  b.style.animation = 'sendpop .41s cubic-bezier(.34,1.56,.64,1)';
  stopRun();
  hers(v);
  /* ★ 接后端：这里把 v 发出去，回复走 __call.pushMine。下面这段是演示 */
  if(!DEMO){ setPhase('thinking'); return; }
  const run = ++runId, ok = ()=> run === runId;
  (async ()=>{
    setPhase('thinking'); await wait(2400); if(!ok()) return;
    await type(L2); if(!ok()) return;
    await wait(900); if(!ok()) return; setPhase('listening');
  })();
});

/* ★ 中缝那块的高度是被对话内容挤出来的，window resize 根本不触发 —— 必须 ResizeObserver */
if(global.ResizeObserver && th) new ResizeObserver(()=> th.fit()).observe($('.threadwrap'));
if(th && matchMedia('(prefers-color-scheme:dark)').addEventListener)
  matchMedia('(prefers-color-scheme:dark)').addEventListener('change', th.retheme);

paint();

/* ══════════════════════════════════════════════════
   接线口。规格 §7 那四个照抄，多一个 incoming（对面打过来；本机打出去是 setPhase('ringing')）
   ══════════════════════════════════════════════════ */
global.__call = {
  setPhase(name){ stopRun(); setPhase(name); },
  pushMine(text, alt, ms){ stopRun(); type(text, 0, alt); const l = S.lines[S.lines.length-1]; if(l){ l.ms = ms; } },   /* 伙伴那一侧说的（逐字）。alt = 可选第二行小字 */
  pushHers(text, alt){ stopRun(); hers(text, alt); },      /* 用户说的（整句） */
  setLevel(v){ if(th) th.setLevel(v); },
  /* (0818) 用户说话时逐字回屏：识别是滚动重发全句的，所以原地改最后一行，不是往下堆 */
  hersLive(text){
    const last = S.lines[S.lines.length-1];
    if(last && last.side === 'hers' && last.live){ last.text = text; last.shown = text.length; }
    /* 太短的先不开行 —— 静音期它会另起一次识别蹦出一两个字，那不是用户在说话 */
    else if((text||'').length >= 2)
      S.lines = [...S.lines, {id:++seq, side:'hers', text, shown:text.length, cut:false, live:true}].slice(-40);
    else return;
    paint();
  },
  hersDone(text, ms){
    const last = S.lines[S.lines.length-1];
    if(last && last.side === 'hers' && last.live){ last.text = text; last.shown = text.length; last.live = false; last.ms = ms; paint(); }
    else { hers(text); const l = S.lines[S.lines.length-1]; if(l){ l.ms = ms; paint(); } }
  },
  incoming(){ incomingCall(); },
  /* 逐字驱动：接 TTS 后按播放进度调这个，别用文件里那个定速打字机 */
  progress(shown){ const l = S.lines[S.lines.length-1]; if(l && l.side === 'mine') bump(l.id, shown); },
  /* 播完了就把这句补齐，别让它停在半路 */
  finishMine(){ const l = S.lines[S.lines.length-1]; if(l && l.side === 'mine' && !l.cut) bump(l.id, l.text.length); },
  /* (0820) 中文翻译是**后到**的（让小模型在这句说完之后翻，不占说话的时间）。
     到了就补在最后那句英文底下，那行小字本来就有位置。 */
  setAlt(text){
    for(let i = S.lines.length - 1; i >= 0; i--){
      if(S.lines[i].side === 'mine'){ S.lines[i].alt = text; paint(); return; }
    }
  },
  barge,
  setTheme(t){ document.documentElement.dataset.theme = t; if(th) th.retheme(); },
  setLayout(l){ document.body.dataset.layout = l; }        /* stream | columns */
};
}

if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

})(typeof window !== 'undefined' ? window : this);
