/* Advscaned Telecaller console — no build step, no framework, no bundler. */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const STAGES = ['OPENING', 'DISCOVERY', 'PITCH', 'CLOSE', 'WRAP'];
const STAGE_LABEL = {
  OPENING: 'Open', DISCOVERY: 'Discover', PITCH: 'Pitch', CLOSE: 'Close', WRAP: 'Wrap',
};
const LANG_BCP47 = { en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN' };

const state = {
  callId: null,
  lead: null,
  stage: 'OPENING',
  lang: 'en',
  voiceOn: localStorage.getItem('voiceOn') !== 'false',
  micOn: false,
  recognition: null,
  interim: '',
  speaking: false,
  leads: [],
  settings: {},
  agentWords: 0,
  leadWords: 0,
};

/* ------------------------------------------------------------------ helpers */
async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  if (form) opts.body = form;
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  const type = res.headers.get('content-type') || '';
  return type.includes('json') ? res.json() : res.text();
}

let toastTimer;
function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* -------------------------------------------------------------------- speech */
const synth = window.speechSynthesis || null;
let voices = [];

function loadVoices() {
  if (!synth) return;
  voices = synth.getVoices() || [];
  const sel = $('#voice-select');
  const usable = voices.filter(v => /en|hi|bn/i.test(v.lang));
  sel.innerHTML = '<option value="">Auto voice</option>' + usable.map((v, i) =>
    `<option value="${v.voiceURI}">${esc(v.name)} · ${v.lang}</option>`).join('');
  const saved = localStorage.getItem('voiceURI');
  if (saved) sel.value = saved;
}
if (synth) {
  loadVoices();
  synth.onvoiceschanged = loadVoices;
}

function pickVoice(lang) {
  const wanted = (LANG_BCP47[lang] || 'en-IN').toLowerCase();
  const base = wanted.split('-')[0];
  const chosen = $('#voice-select')?.value;
  if (chosen) {
    const v = voices.find(x => x.voiceURI === chosen);
    if (v) return v;
  }
  return voices.find(v => v.lang.toLowerCase() === wanted)
    || voices.find(v => v.lang.toLowerCase().replace('_', '-') === wanted)
    || voices.find(v => v.lang.toLowerCase().startsWith(base) && /google|natural|neural/i.test(v.name))
    || voices.find(v => v.lang.toLowerCase().startsWith(base))
    || null;
}

function speak(text, lang, onDone) {
  state.speaking = false;
  if (!synth) { onDone && onDone(); return; }
  synth.cancel();
  if (!state.voiceOn) { onDone && onDone(); return; }
  const u = new SpeechSynthesisUtterance(text);
  const v = pickVoice(lang);
  if (v) u.voice = v;
  u.lang = (v && v.lang) || LANG_BCP47[lang] || 'en-IN';
  u.rate = 1.03;
  u.pitch = 1.03;
  u.onstart = () => { state.speaking = true; markSpeaking(true); };
  u.onend = () => { state.speaking = false; markSpeaking(false); onDone && onDone(); };
  u.onerror = () => { state.speaking = false; markSpeaking(false); onDone && onDone(); };
  synth.speak(u);
}

function markSpeaking(on) {
  $$('.msg.agent').forEach(m => m.classList.remove('speaking'));
  if (on) {
    const last = $$('.msg.agent').at(-1);
    if (last) last.classList.add('speaking');
  }
}

/* --------------------------------------------------------- speech recognition */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function startMic() {
  if (!SR) { toast('This browser has no speech recognition — Chrome or Edge works best.'); return; }
  if (state.micOn) return;
  const rec = new SR();
  rec.lang = LANG_BCP47[state.lang] || 'en-IN';
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  rec.onstart = () => {
    state.micOn = true;
    $('#mic-btn').classList.add('listening');
    $('#mic-hint').textContent = 'Listening… speak normally, then pause.';
  };
  rec.onresult = (ev) => {
    let finalText = '';
    let interim = '';
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const r = ev.results[i];
      if (r.isFinal) finalText += r[0].transcript;
      else interim += r[0].transcript;
    }
    state.interim = interim;
    $('#interim').textContent = interim;
    if (finalText.trim()) {
      // barge-in: the lead started talking while the agent was speaking
      const interrupted = state.speaking;
      if (interrupted && synth) synth.cancel();
      state.interim = '';
      $('#interim').textContent = '';
      sendTurn(finalText.trim(), interrupted);
    }
  };
  rec.onerror = (e) => {
    if (e.error === 'not-allowed') {
      toast('Microphone blocked — allow mic access, or open the console in its own tab. Typing works too.');
    }
    else if (e.error === 'no-speech') { /* stay quiet */ }
    else if (e.error !== 'aborted') toast(`Mic: ${e.error}`);
  };
  rec.onend = () => {
    state.micOn = false;
    $('#mic-btn').classList.remove('listening');
    $('#mic-hint').textContent = 'Voice input uses the browser\'s speech engine — no key, no cost.';
    // keep the conversation hands-free while the call is live
    if (state.callId && state.micOn === false && localStorage.getItem('handsFree') === 'true') {
      setTimeout(() => { if (state.callId) startMic(); }, 350);
    }
  };
  try { rec.start(); } catch { /* already started */ }
  state.recognition = rec;
}

function stopMic() {
  if (state.recognition) {
    try { state.recognition.abort(); } catch { /* ignore */ }
  }
  state.micOn = false;
  $('#mic-btn').classList.remove('listening');
}

/* ------------------------------------------------------------------ rendering */
function renderStagebar(stage) {
  state.stage = stage;
  const idx = stage ? STAGES.indexOf(stage) : -1;
  $('#stagebar').innerHTML = STAGES.map((s, i) => {
    const cls = i === idx ? 'active' : (i < idx ? 'done' : '');
    return `<div class="stage ${cls}"><i></i><span>${STAGE_LABEL[s]}</span></div>`;
  }).join('');
  const pill = $('#stage-pill');
  pill.textContent = stage || 'IDLE';
  pill.className = 'pill' + (stage === 'CLOSE' ? ' ok' : stage === 'WRAP' ? ' warn' : '');
}

function addMessage(role, text, meta = {}) {
  const wrap = $('#transcript');
  const empty = $('.empty', wrap);
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const tags = [];
  if (meta.intent) tags.push(`<span class="tag intent">${esc(meta.intent)}${meta.confidence != null ? ` · ${Math.round(meta.confidence * 100)}%` : ''}</span>`);
  if (meta.sentiment != null && Math.abs(meta.sentiment) >= 0.2) {
    tags.push(`<span class="tag ${meta.sentiment > 0 ? 'pos' : 'neg'}">${meta.sentiment > 0 ? 'positive' : 'negative'} ${meta.sentiment.toFixed(1)}</span>`);
  }
  if (meta.policy) tags.push(`<span class="tag">${esc(meta.policy)}</span>`);
  if (meta.interruption) tags.push('<span class="tag neg">barge-in</span>');
  if (meta.stage) tags.push(`<span class="tag">${esc(meta.stage)}</span>`);

  div.innerHTML = `
    <div class="who">${role === 'agent' ? 'AI' : 'L'}</div>
    <div>
      <div class="bubble">${esc(text)}${role === 'agent' && state.speaking ? '<span class="wave"><i></i><i></i><i></i></span>' : ''}</div>
      ${tags.length ? `<div class="meta">${tags.join('')}</div>` : ''}
    </div>`;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function renderChips(chips = []) {
  const box = $('#chips');
  box.innerHTML = '';
  chips.forEach(t => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = t;
    b.onclick = () => sendTurn(t, false);
    box.appendChild(b);
  });
}

function renderSlots(slots = {}) {
  const dl = $('#slots');
  const entries = Object.entries(slots).filter(([, v]) => v !== '' && v != null);
  $('#slot-count').textContent = entries.length;
  if (!entries.length) { dl.innerHTML = '<dd class="muted">Nothing captured yet</dd>'; return; }
  dl.innerHTML = entries.map(([k, v]) =>
    `<dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${esc(v)}</dd>`).join('');
}

function updateUnderstanding(u) {
  const conf = u?.confidence || 0;
  $('#conf-bar').style.width = `${Math.round(conf * 100)}%`;
  $('#conf-label').textContent = u?.intent ? `${u.intent} · ${Math.round(conf * 100)}%` : '—';
  const s = u?.sentiment || 0;
  const bar = $('#senti-bar');
  bar.style.width = `${Math.round(((s + 1) / 2) * 100)}%`;
  bar.className = s < -0.15 ? 'neg' : '';
  $('#senti-label').textContent = s > 0.2 ? 'positive' : s < -0.2 ? 'negative' : 'neutral';
  $('#intent-tags').innerHTML = (u?.ranked || []).slice(0, 4)
    .map(([name, score]) => `<span class="tag intent">${esc(name)} {${score.toFixed(1)}}</span>`).join('');
}

function updateLive(payload) {
  renderStagebar(payload.stage);
  if (payload.goal) $('#goal').textContent = payload.goal;
  if (payload.coach) $('#coach').textContent = payload.coach.suggestion || payload.coach.objective;
  if (payload.understanding) updateUnderstanding(payload.understanding);
  if (payload.slots) renderSlots(payload.slots);
  const total = state.agentWords + state.leadWords || 1;
  $('#talk-agent').style.width = `${Math.round((state.agentWords / total) * 100)}%`;
  $('#dnc-pill').textContent = payload.dnc ? 'DNC' : 'OK';
  $('#dnc-pill').className = 'pill ' + (payload.dnc ? 'bad' : 'ok');
}

/* --------------------------------------------------------------------- calls */
async function loadLeads() {
  state.leads = await api('/api/leads');
  const sel = $('#lead-select');
  sel.innerHTML = state.leads.map(l =>
    `<option value="${l.id}">${esc(l.name)}${l.company ? ' · ' + esc(l.company) : ''}${l.dnc ? ' (DNC)' : ''}</option>`
  ).join('') || '<option value="">No leads yet — add one in Leads</option>';

  const tbody = $('#leads-table tbody');
  tbody.innerHTML = state.leads.map(l => `
    <tr data-id="${l.id}">
      <td><b>${esc(l.name)}</b><br><small class="muted">${esc(l.role || '')}</small></td>
      <td>${esc(l.company || '—')}</td>
      <td class="muted">${esc(l.phone || '—')}</td>
      <td>${({ en: 'EN', hi: 'हिं', bn: 'বাং' })[l.language] || l.language}</td>
      <td><span class="status ${esc(l.status)}">${esc(l.status)}</span></td>
      <td class="score">${l.score || 0}</td>
      <td><div class="pin ${l.dnc ? 'on' : ''}" data-dnc="${l.id}" title="Do not call"></div></td>
      <td><button class="btn ghost" data-call="${l.id}">Call</button></td>
    </tr>`).join('') || '<tr><td colspan="8" class="muted">No leads yet.</td></tr>';

  $$('[data-dnc]').forEach(el => el.onclick = async () => {
    const lead = state.leads.find(l => l.id === el.dataset.dnc);
    await api(`/api/leads/${lead.id}`, { method: 'PATCH', body: { dnc: !lead.dnc, status: !lead.dnc ? 'dnc' : 'new' } });
    await loadLeads();
  });
  $$('[data-call]').forEach(el => el.onclick = () => {
    switchView('call');
    $('#lead-select').value = el.dataset.call;
    startCall();
  });
}

async function startCall() {
  const leadId = $('#lead-select').value;
  if (!leadId) { toast('Add a lead first.'); return; }
  try {
    stopMic();
    if (synth) synth.cancel();
    $('#transcript').innerHTML = '';
    state.agentWords = 0;
    state.leadWords = 0;
    const payload = await api('/api/calls/start', { method: 'POST', body: { lead_id: leadId } });
    state.callId = payload.call_id;
    state.lang = payload.language || 'en';
    state.lead = payload.lead;
    $('#start-btn').disabled = true;
    $('#end-btn').disabled = false;
    $('#send-btn').disabled = false;
    $('#say-input').focus();

    renderChips(payload.chips);
    updateLive(payload);
    state.agentWords += payload.text.split(/\s+/).length;
    state.speaking = state.voiceOn;
    addMessage('agent', payload.text, { stage: payload.stage });
    speak(payload.text, state.lang, () => {
      if (localStorage.getItem('handsFree') === 'true') startMic();
    });
    if (payload.compliance?.recording_notice) {
      toast(payload.compliance.recording_notice);
    }
  } catch (err) {
    toast(`Could not start the call: ${err.message}`);
  }
}

async function sendTurn(text, interrupted = false) {
  if (!state.callId || !text) return;
  addMessage('lead', text, { interruption: interrupted, stage: state.stage });
  state.leadWords += text.split(/\s+/).length;
  $('#interim').textContent = '';
  try {
    const payload = await api(`/api/calls/${state.callId}/turn`, {
      method: 'POST', body: { text, interrupted },
    });
    state.lang = payload.language || state.lang;
    updateLive(payload);
    renderChips(payload.chips);
    state.agentWords += payload.text.split(/\s+/).length;
    addMessage('agent', payload.text, {
      stage: payload.stage, policy: payload.debug?.policy,
    });
    speak(payload.text, state.lang);

    if (payload.end_call) {
      endCallUI();
      const outcome = payload.final?.outcome || 'connected';
      toast(`Call ended — ${outcome.replace(/_/g, ' ')}. Next: ${payload.final?.next_action || 'n/a'}`);
      loadDashboard();
      loadLeads();
    }
  } catch (err) {
    toast(`Turn failed: ${err.message}`);
  }
}

function endCallUI() {
  stopMic();
  state.callId = null;
  $('#start-btn').disabled = false;
  $('#end-btn').disabled = true;
  $('#send-btn').disabled = true;
  renderChips([]);
}

async function hangup() {
  if (!state.callId) return;
  const id = state.callId;
  endCallUI();
  try {
    await api(`/api/calls/${id}/hangup`, { method: 'POST', body: { outcome: 'connected' } });
    toast('Call ended by agent.');
    loadDashboard();
    loadLeads();
  } catch (err) { toast(err.message); }
}

/* ----------------------------------------------------------------- dashboard */
async function loadDashboard() {
  try {
    const data = await api('/api/dashboard');
    const k = data.kpis;
    $('#kpis').innerHTML = [
      ['Calls', k.calls], ['Connected', `${k.connect_rate}%`], ['Appointments', k.appointments],
      ['Booking rate', `${k.booking_rate}%`], ['Avg score', k.avg_score],
      ['Avg duration', `${k.avg_duration_s}s`], ['Sentiment', k.avg_sentiment],
      ['DNC flagged', k.dnc],
    ].map(([label, val]) => `<div class="kpi"><b>${esc(val)}</b><span>${esc(label)}</span></div>`).join('');

    $('#recent-calls').innerHTML = data.recent_calls.map(c => `
      <div class="call-row">
        <div>
          <b>${esc(c.lead_name)}</b>
          <small>${esc(c.company || '')} · ${esc(c.language.toUpperCase())} · ${esc(c.duration_s)}s</small>
        </div>
        <div class="right">
          <span class="status ${esc(c.outcome)}">${esc(c.outcome.replace(/_/g, ' '))}</span>
          <small class="score">score ${c.score}</small>
        </div>
        <div class="summary">${esc(c.summary || (c.appointment ? 'Demo booked for ' + c.appointment.slot : '—'))}</div>
      </div>`).join('') || '<p class="muted small">No calls yet.</p>';

    const total = Object.values(k.by_outcome).reduce((a, b) => a + b, 0) || 1;
    $('#outcomes').innerHTML = Object.entries(k.by_outcome)
      .sort((a, b) => b[1] - a[1])
      .map(([name, n]) => bar(name, n, total)).join('') || '<p class="muted small">—</p>';
    const ltotal = Object.values(k.by_language).reduce((a, b) => a + b, 0) || 1;
    $('#languages').innerHTML = Object.entries(k.by_language)
      .map(([name, n]) => bar(LANG_BCP47[name] ? name.toUpperCase() : name, n, ltotal)).join('')
      || '<p class="muted small">—</p>';

    if (!state.leads.length) state.leads = data.leads;
  } catch (err) { toast(err.message); }
}

function bar(name, n, total) {
  const pct = Math.round((n / total) * 100);
  return `<div class="bar-row"><span>${esc(name.replace(/_/g, ' '))}</span>
    <span class="track"><i style="width:${pct}%"></i></span><b>${n}</b></div>`;
}

/* ------------------------------------------------------------------ knowledge */
async function loadKB() {
  const rows = await api('/api/kb');
  $('#kb-list').innerHTML = rows.map((r, i) => `
    <div class="kb-row" data-i="${i}">
      <input class="kb-q" value="${esc(r.question)}" placeholder="Question" />
      <textarea class="kb-a" rows="2" placeholder="Answer the agent may give">${esc(r.answer)}</textarea>
      <button class="btn ghost kb-del">✕</button>
    </div>`).join('');
  $$('.kb-del').forEach(b => b.onclick = () => b.closest('.kb-row').remove());
}

async function saveKB() {
  const rows = $$('.kb-row').map((el, i) => ({
    id: `kb${i + 1}`,
    question: $('.kb-q', el).value.trim(),
    answer: $('.kb-a', el).value.trim(),
  })).filter(r => r.question);
  await api('/api/kb', { method: 'PUT', body: rows });
  toast('Knowledge saved — the agent will use it on the next call.');
}

/* ------------------------------------------------------------------- settings */
async function loadSettings() {
  const s = await api('/api/settings');
  state.settings = s;
  const form = $('#settings-form');
  for (const [k, v] of Object.entries(s)) {
    const field = form.elements[k];
    if (!field) continue;
    field.value = Array.isArray(v) ? v.join(', ') : v ?? '';
  }
  $('#llm-pill').textContent = (s.llm_provider || 'off').toUpperCase();
  $('#llm-pill').className = 'pill' + (s.llm_provider === 'off' ? '' : ' ok');
  $('#engine-name').textContent = s.llm_provider === 'off' ? 'Local engine' : `LLM · ${s.llm_model}`;
  $('#engine-sub').textContent = s.llm_provider === 'off' ? 'zero cost · no API key' : s.llm_provider;
  $('#hook-url').textContent = `${location.origin}/twilio/voice`;
}

async function saveSettings(e) {
  e.preventDefault();
  const form = $('#settings-form');
  const patch = {};
  for (const [k, v] of Object.entries(state.settings)) {
    const field = form.elements[k];
    if (!field) continue;
    patch[k] = Array.isArray(v)
      ? field.value.split(',').map(x => x.trim()).filter(Boolean)
      : field.value;
  }
  await api('/api/settings', { method: 'PUT', body: patch });
  toast('Settings saved.');
  await loadSettings();
}

/* ----------------------------------------------------------------- navigation */
function switchView(view) {
  $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $$('.view').forEach(v => v.hidden = v.id !== `view-${view}`);
  const titles = {
    call: ['Live call', 'Browser calling — free, no telephony bill.'],
    leads: ['Leads', 'Your calling list, with consent and DNC flags.'],
    dashboard: ['Dashboard', 'Every call is scored, summarised and exportable.'],
    knowledge: ['Knowledge', 'The facts the agent is allowed to quote.'],
    settings: ['Settings', 'Personality, offer, model and telephony.'],
  }[view];
  $('#view-title').textContent = titles[0];
  $('#view-sub').textContent = titles[1];
  if (view === 'dashboard') loadDashboard();
  if (view === 'leads') loadLeads();
  if (view === 'knowledge') loadKB();
  if (view === 'settings') loadSettings();
}

/* ---------------------------------------------------------------------- wire */
function wire() {
  $$('.nav-item').forEach(b => b.onclick = () => switchView(b.dataset.view));

  $('#start-btn').onclick = startCall;
  $('#end-btn').onclick = hangup;
  $('#send-btn').onclick = () => {
    const input = $('#say-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    sendTurn(text, false);
  };
  $('#say-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); $('#send-btn').click(); }
  });

  $('#mic-btn').onclick = () => {
    if (!state.callId) { toast('Start a call first.'); return; }
    if (state.micOn) { stopMic(); localStorage.setItem('handsFree', 'false'); }
    else { localStorage.setItem('handsFree', 'true'); startMic(); }
  };

  const vt = $('#voice-toggle');
  vt.checked = state.voiceOn;
  vt.onchange = () => {
    state.voiceOn = vt.checked;
    localStorage.setItem('voiceOn', String(vt.checked));
    if (!vt.checked && synth) synth.cancel();
  };
  $('#voice-select').onchange = e => localStorage.setItem('voiceURI', e.target.value);

  $('#seed-btn').onclick = async () => {
    const r = await api('/api/seed_demo', { method: 'POST' });
    toast(`${r.added} demo leads ready.`);
    await loadLeads();
  };

  $('#lead-form').onsubmit = async e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (!data.name) return;
    await api('/api/leads', { method: 'POST', body: data });
    e.target.reset();
    await loadLeads();
    toast('Lead added.');
  };

  $('#import-btn').onclick = () => $('#csv-file').click();
  $('#csv-file').onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const rows = await api('/api/leads/import', { method: 'POST', form });
    toast(`${rows.length} leads imported.`);
    await loadLeads();
  };

  $('#kb-add').onclick = () => {
    const row = document.createElement('div');
    row.className = 'kb-row';
    row.innerHTML = `<input class="kb-q" placeholder="Question" />
      <textarea class="kb-a" rows="2" placeholder="Answer"></textarea>
      <button class="btn ghost kb-del">✕</button>`;
    $('.kb-del', row).onclick = () => row.remove();
    $('#kb-list').appendChild(row);
  };
  $('#kb-save').onclick = () => saveKB().catch(e => toast(e.message));
  $('#settings-form').onsubmit = saveSettings;

  // keyboard: space to talk when idle in the call view
  document.addEventListener('keydown', e => {
    if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA'
        && state.callId && !state.micOn) {
      e.preventDefault();
      localStorage.setItem('handsFree', 'false');
      startMic();
    }
  });
}

async function boot() {
  wire();
  renderStagebar(null);
  $('#end-btn').disabled = true;
  $('#send-btn').disabled = true;
  try {
    const h = await api('/api/health');
    $('#engine-sub').textContent = h.llm === 'off' ? 'zero cost · no API key' : h.llm;
    await loadLeads();
    await loadSettings();
  } catch (err) {
    toast(`Backend not reachable: ${err.message}`);
  }
}

boot();
