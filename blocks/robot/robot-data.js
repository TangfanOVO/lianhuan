// 机器人页 · 数据层
//
// 规矩：**fetch 只出现在这个文件里**，渲染层一行都没有。
// 想换后端就只改这一个文件，`robot.js` 一个字都不用动。
//
// ★ 这块积木**只有前端**。后端要你自己接 —— 每个人的机器人都不一样，
//   接口形状照下面 EP 那三条来，返回什么形状看 normalize()。

export const EP = {
  robot: '/api/robot',      // GET {online,why,engine,...} · POST {volume}|{brightness}|{head}|{reboot}
  timeline: '/api/timeline', // GET {items:[{kind,content,date,time}]} —— 它身上发生过的事
  shots: '/api/shots'       // 要自己实现：GET {items:[{file,url,text,time,yaw,pitch}]}
};

// 没有后端时拿来占位的一份。★ 界面上会**明说这是占位**，不冒充实时数据。
// 数值取自一台真机的 get_device_status 返回，形状是真的，具体的数你自己接了就变。
export const MEASURED = {
  online: false,
  why: '',
  engine: '豆包',
  volume: 25,
  brightness: 75,
  theme: 'light',
  battery: { level: 100, charging: false },
  network: { type: 'wifi', ssid: 'your-wifi', signal: 'strong' },
  head: { yaw: -3, pitch: -8 },   // 「正面」—— 掰正之后记下来的那个角度，开机回这里
  keep_awake: false
};

// 舵机的物理量程 ＋ 回正点。★ 换一台机器人先改这里。
export const LIMITS = { yaw: [-85, 85], pitch: [-20, 88], home: { yaw: -3, pitch: -8 } };

// 摄像头视场角（度）。俯视/侧视那两张示意图的扇形就是照这个画的。
export const FOV = { h: 66, v: 49.5 };

async function j(url, init) {
  const r = await fetch(url, Object.assign({ headers: { Accept: 'application/json' } }, init || {}));
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

// 把 get_device_status 的嵌套形状和扁平形状都收成一种
function normalize(d) {
  const s = d || {};
  const scr = s.screen || {};
  const spk = s.audio_speaker || {};
  return {
    online: !!s.online,
    why: s.why || '',
    engine: s.engine || MEASURED.engine,
    volume: spk.volume ?? s.volume ?? MEASURED.volume,
    brightness: scr.brightness ?? s.brightness ?? MEASURED.brightness,
    theme: scr.theme ?? s.theme ?? MEASURED.theme,
    battery: s.battery || MEASURED.battery,
    network: s.network || MEASURED.network,
    head: s.head || MEASURED.head,
    keep_awake: s.keep_awake ?? MEASURED.keep_awake
  };
}

export async function loadRobot(base) {
  try { return { live: true, d: normalize(await j((base || '') + EP.robot)) }; }
  catch (e) { return { live: false, d: MEASURED, why: String((e && e.message) || e) }; }
}

export async function loadTimeline(base) {
  try {
    const d = await j((base || '') + EP.timeline);
    return { live: true, items: (d.items || []).filter(i => !i.kind || i.kind === '装修') };
  } catch (e) { return { live: false, items: [] }; }
}

export async function loadShots(base) {
  try {
    const d = await j((base || '') + EP.shots + '?limit=12');
    return { live: true, items: d.items || [] };
  } catch (e) { return { live: false, items: [] }; }
}

// 一个 POST 一件事。回 {ok, awake, why} 时前端才好说人话。
export async function send(base, body) {
  try {
    const d = await j((base || '') + EP.robot, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body)
    });
    return { ok: d.ok !== false, awake: d.awake, why: d.why || '' };
  } catch (e) { return { ok: false, awake: null, why: '' }; }
}
