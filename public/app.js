'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const examples = {
    canonical: 'I want to organize a charity event at my university in March with a budget of RM2k.',
    bazaar: 'Plan a charity bazaar at Taylor’s Lakeside Campus for 120 attendees between 1 and 30 November 2026 with a RM 5,000 budget. Support student wellbeing, compare dates using local weather climatology, propose a covered venue, student MCs, suitable Malaysian sponsors, outreach drafts and a promotion plan. Treat all bookings and sponsor commitments as unconfirmed.',
    workshop: 'Plan a career skills workshop at Taylor’s Lakeside Campus for 80 students between 1 and 30 November 2026 with a RM 3,000 budget. Compare dates, propose an indoor venue, organisers and MC roles, a practical programme, potential Malaysian sponsors, outreach drafts and a promotion plan.',
    dormathon: 'Plan a Dormathon Track 2 student project showcase at Taylor’s Lakeside Campus for 120 attendees between 1 and 30 November 2026 with a RM 5,000 budget. Compare dates using local weather climatology, propose a covered venue, student MCs, suitable Malaysian sponsors, outreach drafts and a promotion plan. Treat all bookings and sponsor commitments as unconfirmed.'
  };
  const agents = [
    { id: 'goal', label: 'Goal Interpreter', icon: '01', lane: 0, deps: [] },
    { id: 'sources', label: 'Source Librarian', icon: '02', lane: 0, deps: ['goal'] },
    { id: 'date', label: 'Date Scout', icon: '03', lane: 1, deps: ['goal', 'sources'] },
    { id: 'budget', label: 'Budget Architect', icon: '04', lane: 1, deps: ['goal', 'risk (re-plan)'] },
    { id: 'venue', label: 'Venue Liaison', icon: '05', lane: 1, deps: ['goal', 'sources'] },
    { id: 'talent', label: 'Talent Coordinator', icon: '06', lane: 2, deps: ['date', 'roster'] },
    { id: 'sponsor', label: 'Sponsor Matcher', icon: '07', lane: 2, deps: ['sources', 'budget'] },
    { id: 'programme', label: 'Programme Director', icon: '08', lane: 2, deps: ['date', 'risk'] },
    { id: 'risk', label: 'Risk Sentinel', icon: '09', lane: 2, deps: ['date.weather'] },
    { id: 'outreach', label: 'Outreach Drafter', icon: '10', lane: 3, deps: ['date', 'venue', 'talent', 'sponsor'] },
    { id: 'promo', label: 'Promo Studio', icon: '11', lane: 3, deps: ['date', 'venue'] },
    { id: 'validator', label: 'Validator', icon: '12', lane: 3, deps: ['all specialist outputs'] }
  ];
  const tabs = ['Overview', 'Date Decision', 'Timeline', 'Budget', 'Risk / Weather', 'People / MCs', 'Sponsors / Gmail', 'Promo', 'Export'];
  const state = { id: null, status: 'idle', pack: null, trace: [], metrics: null, tab: 'Overview', source: null, demo: false, replay: false, clientId: '', configLoaded: false, gmailBusy: false, gmailResult: null, startedAt: null };
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const array = (value) => Array.isArray(value) ? value.filter((item) => item != null) : value == null ? [] : [value];
  const first = (...values) => values.find((v) => v !== null && v !== undefined && v !== '');
  const number = (value) => value == null || value === '' ? null : Number.isFinite(Number(value)) ? Number(value) : null;
  const rm = (value) => number(value) === null ? 'Not specified' : `RM ${number(value).toLocaleString('en-MY', { maximumFractionDigits: 2 })}`;
  const label = (key) => String(key).replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ').replace(/\bRM\b/g, '(RM)').replace(/^./, (c) => c.toUpperCase());
  const missing = (text = 'Not confirmed') => `<span class="unknown">${esc(text)}</span>`;
  function safeURL(value) {
    if (typeof value !== 'string') return null;
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
  }
  const badge = (text, kind = '') => `<span class="badge ${esc(kind)}">${esc(text)}</span>`;
  function sources(value) {
    const links = [];
    const seen = new Set();
    function collect(v) {
      if (!v) return;
      if (Array.isArray(v)) return v.forEach(collect);
      if (typeof v === 'string') { const url = safeURL(v); if (url && !seen.has(url)) { seen.add(url); links.push({ url, title: new URL(url).hostname }); } return; }
      if (typeof v === 'object') {
        const url = safeURL(first(v.url, v.sourceURL, v.sourceUrl, v.href, v.website, v.link));
        if (url && !seen.has(url)) { seen.add(url); links.push({ url, title: first(v.title, v.name, v.label, new URL(url).hostname) }); }
        ['sources', 'sourceURLs', 'sourceUrls', 'citations', 'source', 'contactPage', 'contactUrl', 'website', 'url', 'evidence'].forEach((key) => { if (v[key] && v[key] !== v) collect(v[key]); });
      }
    }
    collect(value);
    return links.length ? `<div class="source-list">${links.map((item) => `<a class="source-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)} ↗</a>`).join('')}</div>` : '';
  }
  function valueHTML(value, depth = 0) {
    if (value == null || value === '') return missing();
    if (typeof value === 'boolean') return esc(value ? 'Yes' : 'No');
    if (typeof value !== 'object') { const url = safeURL(String(value)); return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(new URL(url).hostname)} ↗</a>` : esc(value); }
    if (depth > 4) return esc(Array.isArray(value) ? value.map((v) => typeof v === 'object' ? first(v.name, v.title, v.description, 'See details') : v).join('; ') : first(value.name, value.title, value.description, value.message, 'See sourced details'));
    if (Array.isArray(value)) return value.length ? `<ul class="rich-list">${value.map((v) => `<li>${valueHTML(v, depth + 1)}</li>`).join('')}</ul>` : missing('No entries supplied');
    const rows = Object.entries(value).filter(([k, v]) => v != null && !['email', 'accessToken', 'token', 'privateRoster', 'body', 'html', 'raw', 'trace', 'budgetCents', 'scenarioDate', 'attendanceAssumed', 'prompt', 'amountCents', 'totalCents', 'limitCents', 'contingencyCents', 'gapCents', 'organiserFundsCents', 'askCents'].includes(k));
    return rows.length ? `<dl class="fact-list">${rows.map(([k, v]) => `<div class="fact-row"><dt>${esc(label(k))}</dt><dd>${valueHTML(v, depth + 1)}</dd></div>`).join('')}</dl>` : missing('No details supplied');
  }
  const card = (title, content, full = false, intro = '') => `<section class="content-card${full ? ' full' : ''}"><h3>${esc(title)}</h3>${intro ? `<p class="card-intro">${esc(intro)}</p>` : ''}${content}</section>`;
  const callout = (title, body, kind = 'warning') => `<div class="callout ${esc(kind)}"><strong>${esc(title)}</strong>${esc(body)}</div>`;
  const empty = (title, message) => `<div class="empty-state"><h3>${esc(title)}</h3>${esc(message)}</div>`;
  function facts(rows) { return `<dl class="fact-list">${rows.map(([key, value]) => `<div class="fact-row"><dt>${esc(key)}</dt><dd>${valueHTML(value)}</dd></div>`).join('')}</dl>`; }
  function table(headers, rows) { return rows.length ? `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : missing('No entries supplied'); }
  function notice(text, error = false) { $('notice').textContent = text; $('notice').className = `notice${error ? ' error' : ''}`; $('notice').hidden = false; }
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    const content = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(typeof content.error === 'string' ? content.error : content.error?.message || `Request failed (${response.status}).`); error.data = content; error.status = response.status; throw error; }
    return content;
  }
  function formOverrides() {
    const result = {};
    for (const [id, key] of [['event-type', 'eventType'], ['cause', 'cause'], ['date-start', 'dateStart'], ['date-end', 'dateEnd'], ['budget', 'budgetRM'], ['organiser-funds', 'organiserFundsRM'], ['attendance', 'attendance'], ['campus', 'campus'], ['location', 'location']]) {
      const value = $(id).value.trim();
      if (value !== '') result[key] = ['budgetRM', 'organiserFundsRM', 'attendance'].includes(key) ? Number(value) : value;
    }
    return result;
  }
  function parseCSV(text) {
    const rows = []; let row = [], field = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') { if (quoted && text[i + 1] === '"') { field += '"'; i++; } else if (quoted || field === '') quoted = !quoted; else throw new Error('Roster CSV has a quote inside an unquoted field.'); }
      else if (c === ',' && !quoted) { row.push(field.trim()); field = ''; }
      else if ((c === '\n' || c === '\r') && !quoted) { if (c === '\r' && text[i + 1] === '\n') i++; row.push(field.trim()); if (row.some(Boolean)) rows.push(row); row = []; field = ''; }
      else field += c;
    }
    if (quoted) throw new Error('Roster CSV has an unclosed quoted field.');
    row.push(field.trim()); if (row.some(Boolean)) rows.push(row);
    if (!rows.length) return [];
    const headers = rows.shift().map((h) => h.toLowerCase().replace(/\s/g, ''));
    const expected = ['name', 'role', 'freedates', 'email'];
    if (expected.some((h) => !headers.includes(h))) throw new Error('Use the roster header: name,role,freeDates,email.');
    if (rows.length > 100) throw new Error('Please limit the roster to 100 authorised participants.');
    return rows.map((cells, index) => {
      if (cells.length !== headers.length) throw new Error(`Roster row ${index + 2} has the wrong number of columns.`);
      const get = (key) => cells[headers.indexOf(key)] || '';
      if (!get('name')) throw new Error(`Roster row ${index + 2} needs a name.`);
      const dates = get('freedates').split(/[;|]/).map((d) => d.trim()).filter(Boolean);
      if (dates.some((d) => !/^\d{4}-\d{2}-\d{2}$/.test(d) || Number.isNaN(Date.parse(`${d}T12:00:00`)))) throw new Error(`Roster row ${index + 2} needs dates formatted YYYY-MM-DD, separated by semicolons.`);
      const email = get('email');
      if (email && !/^[^\s@,]+@[^\s@,]+\.[^\s@,]+$/.test(email)) throw new Error(`Roster row ${index + 2} has an invalid email.`);
      return { name: get('name'), role: get('role'), freeDates: dates, ...(email ? { email } : {}), ...(state.demo ? { demo: true } : {}) };
    });
  }
  function updateRosterStatus() {
    try { const roster = parseCSV($('roster').value); $('roster-status').textContent = roster.length ? `${roster.length} ${state.demo ? 'DEMO ' : ''}participant(s). ${state.demo ? 'Illustrative availability only; not real confirmed people. ' : ''}Email addresses are excluded from public pack sharing.` : 'No roster supplied. People and MC availability will remain unconfirmed.'; } catch (error) { $('roster-status').textContent = error.message; }
  }
  function setBusy(busy) { $('run-button').disabled = busy; $('run-example').disabled = busy; $('replay-button').disabled = busy; $('run-button').textContent = busy ? 'Specialists are working…' : 'Build my event pack ↗'; }
  function normalizedStatus(status) {
    const raw = String(status || 'waiting').toLowerCase();
    if (/^(done|completed|complete|success|succeeded|passed|finished)$/.test(raw)) return 'completed';
    if (/fail|error/.test(raw)) return 'failed';
    if (/re.?plan|retry|warn|blocked/.test(raw)) return 'replan';
    if (/run|start|working|active|progress/.test(raw)) return 'running';
    return 'waiting';
  }
  function resolveAgent(event) {
    const input = String(first(event.agentId, event.agent, event.actor, event.specialist, '')).toLowerCase();
    const matches = [['goal', /intake|brief|intent|goal/], ['sources', /research|source|librarian/], ['risk', /risk|weather|climat/], ['talent', /talent|people|roster|availability/], ['venue', /venue|location/], ['sponsor', /sponsor/], ['date', /date|decision|schedul/], ['budget', /budget|finance/], ['programme', /programme|program|timeline/], ['promo', /promo|marketing/], ['outreach', /outreach|draft|gmail/], ['validator', /valid|re.?plan/]];
    return matches.find(([, pattern]) => pattern.test(input))?.[0] || input;
  }
  function renderDAG() {
    const laneNames = ['01 · FRAME & SOURCE', '02 · PARALLEL DATE / COST / VENUE', '03 · PARALLEL SPECIALIST OUTPUTS', '04 · DRAFT / PROMO → VALIDATE'];
    $('agent-dag').innerHTML = laneNames.map((name, lane) => `<div class="dag-lane"><div class="lane-title">${esc(name)}</div>${agents.filter((a) => a.lane === lane).map((a) => {
      const events = state.trace.filter((e) => resolveAgent(e) === a.id);
      const event = events.slice().reverse().find((e) => normalizedStatus(e.status) !== 'waiting') || events[events.length - 1]; const status = event ? normalizedStatus(event.status) : 'waiting';
      const statusText = event ? String(event.status || 'event received') : 'Not started';
      return `<div class="agent-card ${esc(status)}"><div class="agent-top"><span class="agent-icon">${esc(a.icon)}</span><div><div class="agent-name">${esc(a.label)}</div><div class="agent-number">${esc(a.id)}</div></div></div><div class="agent-state"><span>${esc(statusText)}</span><span>${event ? status === 'completed' ? '✓' : status === 'failed' ? '!' : '↗' : '—'}</span></div><div class="agent-deps">${a.deps.length ? `← ${esc(a.deps.join(' + '))}` : '← event brief'}</div></div>`;
    }).join('')}</div>`).join('');
  }
  function renderTrace() {
    $('trace-count').textContent = `${state.trace.length} real event${state.trace.length === 1 ? '' : 's'}`;
    $('trace-list').innerHTML = state.trace.length ? state.trace.slice(-250).map((event) => {
      const time = first(event.time, event.timestamp, '');
      const parsed = typeof time === 'string' || typeof time === 'number' ? new Date(time) : null;
      const timeText = parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleTimeString('en-GB', { hour12: false }) : String(time || '');
      const kind = normalizedStatus(event.status);
      return `<div class="trace-row"><div class="trace-agent">${esc(first(event.agent, event.agentId, event.actor, 'Runtime'))}<br>${badge(first(event.status, 'event'), kind === 'failed' ? 'error' : kind === 'replan' ? 'warning' : '')}</div><div><div class="trace-tool">${esc(first(event.tool, event.toolName, 'Runtime event'))}</div><div class="trace-message">${esc(first(event.message, event.description, 'Event reported by the runtime.'))}</div>${event.data ? `<details><summary>Inspect returned evidence</summary>${valueHTML(event.data)}</details>` : ''}</div><time class="trace-time">${esc(timeText)}</time></div>`;
    }).join('') : '<p class="empty-trace">No execution yet. Start a plan to see actual specialist and tool events here.</p>';
    const checkpoints = state.trace.filter((event) => /re.?plan|repair|cross_specialist_checks|revalidate/.test(`${event.status || ''} ${event.tool || ''}`));
    $('workflow-checks').hidden = !checkpoints.length;
    $('workflow-checks').innerHTML = checkpoints.slice(-8).map((event) => `<div class="workflow-check"><span>${badge(/re.?plan|repair/.test(`${event.status} ${event.tool}`) ? 'Real re-plan / repair' : 'Real validation', /re.?plan|repair/.test(`${event.status} ${event.tool}`) ? 'warning' : 'info')}</span><div><strong>${esc(event.tool || 'Runtime check')} · ${esc(event.status || 'event')}</strong><p>${esc(event.message || 'Actual runtime event')}</p></div></div>`).join('');
    renderDAG();
  }
  function appendTrace(event) {
    if (!event || typeof event !== 'object') return;
    const time = first(event.time, event.timestamp);
    if (time && state.trace.some((existing) => first(existing.time, existing.timestamp) === time && existing.agent === event.agent && existing.status === event.status && existing.tool === event.tool && existing.message === event.message)) return;
    state.trace.push(event); renderTrace();
  }
  function runStatus(status) {
    state.status = status;
    $('run-status').className = `run-status ${normalizedStatus(status) === 'completed' ? 'complete' : normalizedStatus(status) === 'failed' ? 'failed' : normalizedStatus(status) === 'running' ? 'running' : ''}`;
    $('run-status').textContent = state.replay ? `Recorded replay · ${status}` : label(status);
    $('run-meta').hidden = !state.id;
    $('run-meta').innerHTML = state.id ? `<span>Run <code>${esc(state.id)}</code> · ${state.replay ? '<strong>Replay of a real recorded run</strong>' : 'Actual tool-driven execution'}</span><span>Read-only sharing · no roster emails in pack</span>` : '';
  }
  function closeStream() { if (state.source) { state.source.close(); state.source = null; } }
  function complete(pack) {
    closeStream(); state.pack = pack || state.pack; runStatus('completed'); setBusy(false);
    if (!state.pack) { notice('The run completed but no Event Pack was returned. Reload the saved run to retry.', true); return; }
    $('results').hidden = false; $('empty-results').hidden = true;
    const goal = state.pack.goal || {};
    $('results-title').textContent = first(state.pack.title, goal.eventType ? `${goal.eventType} · Event Pack` : null, 'The Event Pack');
    $('results-subtitle').textContent = `Proposed plan · ${first(goal.campus, 'Taylor’s University')} · commitments and availability require confirmation.`;
    $('pdf-link').href = `/api/runs/${encodeURIComponent(state.id)}/pdf`;
    renderTabs(); renderContent();
    if (state.pack.engine) $('engine-description').textContent = typeof state.pack.engine === 'string' ? state.pack.engine : first(state.pack.engine.description, state.pack.engine.disclosure, state.pack.engine.note, 'WorkBuddy keyless LLM is not activated. Deterministic tool-driven specialist runtime; no fabricated LLM output.');
  }
  function streamRun(id) {
    closeStream();
    const stream = new EventSource(`/api/runs/${encodeURIComponent(id)}/stream`); state.source = stream;
    stream.addEventListener('trace', (event) => { try { appendTrace(JSON.parse(event.data)); } catch { notice('A trace event could not be decoded. The saved run still retains its execution record.', true); } });
    stream.addEventListener('complete', async (event) => {
      try { const data = JSON.parse(event.data); state.metrics = data.metrics || state.metrics; if (data.pack) complete(data.pack); else await loadRun(id); } catch (error) { closeStream(); setBusy(false); notice(error.message, true); }
    });
    stream.addEventListener('failed', (event) => { closeStream(); runStatus('failed'); setBusy(false); try { const data = JSON.parse(event.data); notice(typeof data.error === 'string' ? data.error : data.error?.message || 'The runtime reported a failed run.', true); } catch { notice('The runtime reported a failed run.', true); } });
    stream.onerror = async () => {
      if (state.source !== stream) return;
      closeStream();
      try { const data = await request(`/api/runs/${encodeURIComponent(id)}`); state.trace = array(data.trace); renderTrace(); if (data.pack && normalizedStatus(data.status) === 'completed') complete(data.pack); else if (normalizedStatus(data.status) === 'failed') { runStatus('failed'); setBusy(false); notice('The run failed. See the recorded trace for the real failure.', true); } else { setBusy(false); notice('The live connection was interrupted. Reload this saved run to reconnect; no progress is being invented.', true); } } catch (error) { setBusy(false); notice(`Live connection interrupted. ${error.message}`, true); }
    };
  }
  async function startRun(mode = 'normal') {
    try {
      const prompt = $('prompt').value.trim();
      if (mode !== 'replay' && !prompt) { $('prompt').focus(); notice('Add an event brief first.'); return; }
      if (mode !== 'replay' && prompt.length > 3000) throw new Error('Please keep your event brief within 3,000 characters.');
      const roster = mode === 'replay' ? [] : parseCSV($('roster').value);
      const overrides = mode === 'replay' ? {} : formOverrides();
      if (overrides.dateStart && overrides.dateEnd && overrides.dateStart > overrides.dateEnd) throw new Error('The earliest date must be on or before the latest date.');
      if (overrides.organiserFundsRM != null && overrides.budgetRM != null && overrides.organiserFundsRM > overrides.budgetRM) throw new Error('Organiser funds cannot exceed the planning budget cap.');
      closeStream(); state.trace = []; state.pack = null; state.metrics = null; state.gmailResult = null; state.replay = mode === 'replay'; state.id = null; $('results').hidden = true; $('empty-results').hidden = false; $('notice').hidden = true; setBusy(true); runStatus('running'); renderTrace(); $('trace-details').open = true;
      const data = await request('/api/runs', { method: 'POST', body: JSON.stringify(mode === 'replay' ? { mode: 'replay' } : { prompt, ...(Object.keys(overrides).length ? { overrides } : {}), roster }) });
      if (!data.id) throw new Error('The server did not return a run ID.');
      state.id = data.id; state.replay = !!first(data.replay, state.replay); history.pushState({}, '', `/run/${encodeURIComponent(data.id)}`); runStatus(data.status || 'running');
      $('workflow').scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (data.pack) complete(data.pack); else await loadRun(data.id);
    } catch (error) { setBusy(false); runStatus('failed'); notice(error.message, true); }
  }
  async function loadRun(id) {
    const data = await request(`/api/runs/${encodeURIComponent(id)}`);
    state.id = data.id || id; state.trace = array(data.trace); state.metrics = data.metrics || null; state.replay = !!first(data.replay, data.mode === 'replay' ? true : undefined, data.pack?.replay, state.replay); renderTrace(); runStatus(data.status || 'running');
    if (data.pack && normalizedStatus(data.status) === 'completed') complete(data.pack);
    else if (normalizedStatus(data.status) === 'failed') { setBusy(false); notice(typeof data.error === 'string' ? data.error : 'This run failed. Its real trace is available below.', true); $('trace-details').open = true; }
    else { setBusy(true); $('trace-details').open = true; streamRun(state.id); }
  }
  function renderTabs() {
    $('tabs').innerHTML = tabs.map((tab, index) => `<button class="tab" id="tab-${index}" type="button" role="tab" aria-selected="${state.tab === tab}" aria-controls="tab-content" tabindex="${state.tab === tab ? 0 : -1}" data-tab="${esc(tab)}">${esc(tab)}</button>`).join('');
    $('tab-content').setAttribute('aria-labelledby', `tab-${tabs.indexOf(state.tab)}`);
  }
  function overview() {
    const p = state.pack, g = p.goal || {}, chosen = p.dateDecision?.chosen;
    const date = typeof chosen === 'string' ? chosen : first(chosen?.date, chosen?.label, chosen?.dateISO, p.dateDecision?.chosenDate);
    const budget = p.budget || {};
    const intro = typeof p.summary === 'string' ? callout('A practical starting point', p.summary, 'info') : p.summary ? card('Plan summary', valueHTML(p.summary), true) : '';
    const kpis = [["Preferred date", date || 'Pending', 'Proposed · see date comparison'], ['Planning budget', rm(first(budget.total, budget.totalRM, g.budgetRM)), 'Allocations, not vendor quotations'], ['Expected guests', first(g.attendance, 'Unconfirmed'), 'Planning assumption'], ['Venue', first(p.venues?.selected?.name, p.venues?.recommended?.name, 'To be confirmed'), 'No booking has been made']];
    return `${intro}<div class="kpi-grid">${kpis.map(([title, value, note]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value"${String(value).length > 23 ? ' style="font-size:17px"' : ''}>${esc(value)}</div><div class="kpi-note">${esc(note)}</div></div>`).join('')}</div><div class="content-grid">${card('Your brief, translated', facts([['Event type', g.eventType], ['Cause / purpose', g.cause], ['Campus', g.campus], ['Date window', g.dateStart && g.dateEnd ? `${g.dateStart} to ${g.dateEnd}` : first(g.dateStart, g.dateEnd)], ['Budget cap', rm(g.budgetRM)], ['Attendance', g.attendance]]))}${card('Assumptions to confirm', valueHTML(p.assumptions), false, 'Proposed defaults are editable. No campus calendar clearance, sponsor agreement or vendor price is implied.')}${card('Validation & re-planning', valueHTML(p.validation), false, 'Reported results of actual validation — inspect the execution trace for tools and re-plan steps.')}${card('Next real-world checks', valueHTML(first(p.rechecks, p.pendingChecks)), false, 'Weather, venue, attendance and sponsor confirmations are still your responsibility.')}${p.metrics || state.metrics ? card('Recorded run metrics', valueHTML(p.metrics || state.metrics), true, 'These values are reported by the runtime, not simulated counters.') : ''}</div>`;
  }
  function dateDecision() {
    const d = state.pack.dateDecision || {}, chosen = d.chosen;
    const preferred = typeof chosen === 'object' ? first(chosen?.date, chosen?.label, chosen?.dateISO) : chosen;
    const candidates = array(d.candidates);
    const rows = candidates.map((c) => typeof c !== 'object' ? [esc(c), missing(), missing(), missing()] : [esc(first(c.date, c.label, c.dateISO, 'Unspecified date')), valueHTML(first(c.score, c.totalScore, c.weightedScore)), valueHTML(first(c.reasons, c.reason, c.rationale, c.factors, c.scores, c.breakdown)), `${badge(c.blocked ? 'Excluded: cited clash' : first(c.status, 'Proposed'), c.blocked ? 'error' : 'warning')}<p>${esc(c.examStatus ? `Exam status: ${c.examStatus}` : first(c.availability, c.risk, c.notes, 'Availability unconfirmed'))}</p>`]);
    return `${callout('A proposed date, not a booking', 'Historical weather patterns and supplied availability can support a choice, but do not prove campus clearance or future weather. Confirm the calendar and recheck a short-range forecast before committing.')}<div class="content-grid">${card('Preferred date', `${preferred ? `<div class="weather-number">${esc(preferred)}</div>` : missing('No date selected')}${valueHTML(chosen && typeof chosen === 'object' ? Object.fromEntries(Object.entries(chosen).filter(([k]) => !['date', 'dateISO', 'label'].includes(k))) : first(d.reason, d.rationale))}`)}${card('Backup dates', valueHTML(first(d.backups, d.alternatives)), false, 'Use if availability, weather or operational conditions change.')}${card('Candidate comparison', table(['Candidate date', 'Score', 'Decision factors', 'Status / caveats'], rows), true, 'Scores are relative planning comparisons. They are not forecast probabilities or confirmed free dates.')}${card('Scoring weights & rules', valueHTML(first(d.weights, d.criteria)), true)}${sources(d) ? card('Decision evidence', sources(d), true) : ''}</div>`;
  }
  function timeline() {
    const programme = state.pack.programme || state.pack.program || {};
    const runOfShow = array(first(programme.runOfShow, programme.timeline));
    const countdown = array(first(programme.countdown, programme.preEvent));
    const show = runOfShow.map((item) => typeof item === 'object' ? [esc(first(item.time, item.start, item.startTime, 'TBC')), esc(first(item.activity, item.title, item.task, item.name, 'Activity')), valueHTML(first(item.owner, item.role, item.responsible)), valueHTML(first(item.notes, item.description, item.durationMinutes != null ? `${item.durationMinutes} minutes · ${item.status || 'Proposed'}` : undefined, item.duration, item.end))] : [missing(), esc(item), missing(), missing()]);
    const tasks = countdown.map((item) => typeof item === 'object' ? `<li class="timeline-item"><div class="timeline-time">${esc(first(item.label, item.when, item.daysBefore, item.date, item.time, item.deadline, 'TBC'))}</div><div class="timeline-copy"><strong>${esc(first(item.action, item.task, item.activity, item.title, item.name, 'Planning task'))}</strong><p>${esc([item.owner || item.responsible || 'Owner to confirm', item.date, item.status].filter(Boolean).join(' · '))}</p></div></li>` : `<li class="timeline-item"><div class="timeline-time">Before event</div><div class="timeline-copy">${esc(item)}</div></li>`).join('');
    return `${callout('An editable operational plan', 'Times and owners are proposed until the organisers, venue and participants confirm them.', 'info')}<div class="content-grid">${card('Event-day run of show', table(['Time', 'Activity', 'Owner', 'Notes / duration'], show), true)}${card('Countdown to event day', tasks ? `<ol class="countdown-list">${tasks}</ol>` : missing('No countdown supplied'))}${card('Programme details', valueHTML(Object.fromEntries(Object.entries(programme).filter(([key]) => !['runOfShow', 'timeline', 'countdown', 'preEvent'].includes(key)))))}${state.pack.venues ? card('Venue options & operations', valueHTML(state.pack.venues), true, 'Venue suitability is a proposal; contact the campus team for availability and approval.') : ''}</div>`;
  }
  function budgetTab() {
    const b = state.pack.budget || {}, items = array(first(b.items, b.allocations));
    const amount = (item) => number(first(item.amountRM, item.totalRM, item.amount, item.costRM, item.total, item.cost));
    const total = first(b.total, b.totalRM, items.reduce((sum, item) => sum + (amount(item) || 0), 0));
    const limit = first(b.limit, b.limitRM, b.budgetRM, state.pack.goal?.budgetRM);
    const denominator = Math.max(1, Number(total) || 0, ...items.map((i) => amount(i) || 0));
    const bars = items.map((item) => `<div class="budget-bar"><div class="budget-bar-header"><span>${esc(first(item.category, item.name, item.item, 'Allocation'))}</span><strong>${esc(rm(amount(item)))}</strong></div><div class="budget-track"><div class="budget-fill" style="width:${Math.max(0, Math.min(100, (amount(item) || 0) / denominator * 100))}%"></div></div></div>`).join('');
    const rows = items.map((item) => [esc(first(item.category, item.name, item.item, 'Allocation')), esc(rm(amount(item))), valueHTML(first(item.quantity, item.qty)), valueHTML(first(item.basis, item.notes, item.description, item.rationale, item.assumption, item.status))]);
    return `${callout('Planning allocations — not vendor quotes', 'Every figure is in Malaysian ringgit (RM). Obtain real quotes before spending. Prospective sponsor support is unconfirmed and must not be treated as secured income.')}<div class="kpi-grid">${[['Budget limit', rm(limit)], ['Allocated total', rm(total)], ['Contingency', rm(first(b.contingencyRM, b.contingency?.amountRM, b.contingency?.amount, b.contingency))], ['Funding gap', rm(first(b.gapRM, b.gap?.amountRM, b.gap))]].map(([title, value]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value">${esc(value)}</div></div>`).join('')}</div><div class="content-grid">${card('Where the budget goes', bars ? `<div class="budget-bars">${bars}</div><p class="budget-legend">Bar widths show the share of the recorded allocation total.</p>` : missing('No allocations supplied'))}${card('Funding & guardrails', facts([['Organiser funds', typeof b.organiserFunds === 'object' ? b.organiserFunds : rm(first(b.organiserFundsRM, b.organiserFunds))], ['Sponsor support', first(b.sponsorship, b.sponsorFunds, 'Unconfirmed; no commitment implied')], ['Funding status', b.fundingStatus], ['Gap resolution', first(b.gapResolution, b.fundingPlan, b.notes, 'Verify organiser funds and secure written support; reduce spend if the gap remains.')], ['Contingency policy', first(b.contingencyPolicy, b.contingency?.notes, b.contingencyPercent != null ? `${b.contingencyPercent}% protected planning reserve` : undefined)], ['Scenario', b.scenario], ['Sponsor accounting', b.sponsorAccounting]]))}${card('Allocation breakdown', table(['Item / category', 'Allocation (RM)', 'Quantity', 'Basis / caveats'], rows), true)}</div>`;
  }
  function weatherTab() {
    const w = state.pack.weather || {}, risks = state.pack.risks || {};
    const forecast = w.mode === 'forecast';
    const rain = first(w.rainProbability, number(w.probability) == null ? undefined : `${Math.round(Number(w.probability) * 100)}%`);
    const sampleYears = array(first(w.sampleYears, w.years));
    const validYears = sampleYears.map(Number).filter(Number.isFinite);
    const sampled = validYears.length ? `${Math.min(...validYears)}–${Math.max(...validYears)}` : 'Not available';
    const rows = array(risks.register).map((r) => [esc(first(r.risk, r.name, 'Risk')), esc(first(r.score, '—')), esc(first(r.mitigation, 'Pending')), esc(first(r.trigger, 'Pending')), esc(first(r.contingency, 'Pending')), esc(first(r.owner, 'Unassigned'))]);
    const samples = array(w.samples).map((s) => [esc(first(s.date, 'Unknown date')), esc(first(s.precipitationMm, 'Unavailable')), esc(first(s.tempMaxC, 'Unavailable')), esc(first(s.tempMeanC, 'Unavailable'))]);
    const kpis = [['Rain measure', rain == null ? 'Unavailable' : `${rain}${typeof rain === 'number' ? '%' : ''}`, forecast ? 'Source forecast probability; not a guarantee' : 'Observed historical frequency; not a forecast'], ['Historical samples', first(w.sampleCount, 'Unavailable'), 'Missing observations are not filled'], ['Sample years', sampled, 'Actual reported year coverage'], ['Plan B', w.indoorRequired ? 'Indoor required' : 'Check evidence', 'Venue approval remains unconfirmed']];
    return `${callout(forecast ? 'Actual near-term forecast evidence — not a guarantee.' : 'Historical climatology. Not a forecast.', forecast ? 'The source returned a forecast within its supported horizon. Recheck alerts and the forecast before the event; campus conditions and safety still need local review.' : 'Weather values describe historical patterns, not the weather on your future event date. Review the reported sample size and years. A near-term forecast recheck remains pending.')}<div class="kpi-grid">${kpis.map(([title, value, note]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value">${esc(value)}</div><div class="kpi-note">${esc(note)}</div></div>`).join('')}</div><div class="content-grid">${card('Weather interpretation & uncertainty', facts([['Evidence mode', w.mode], ['Event date', w.date], ['Source location', first(w.locationEvidence, w.location)], ['Average rainfall', w.precipitationMm != null ? `${w.precipitationMm} mm` : null], ['Average maximum temperature', w.avgTempMax != null ? `${w.avgTempMax} °C` : null], ['Decision', w.decision], ['Uncertainty', w.uncertainty], ['Warnings', w.warnings]]))}${card('Weather citations & rechecks', `${sources(w)}${facts([['Proposed thresholds', w.threshold], ['Reasoning', w.rationale], ['Next checks', first(w.recheck, w.recheckStatus, 'T-14 / T-7 / T-1 checks are pending; no automated notification is claimed')]])}`)}${samples.length ? card('Actual observed sample rows', table(['Sample date', 'Rain (mm)', 'Max temp (°C)', 'Mean temp (°C)'], samples), true) : ''}${card('Risk register & mitigations', rows.length ? table(['Risk', 'L × I', 'Mitigation', 'Trigger', 'Contingency', 'Owner'], rows) : valueHTML(risks), true, first(risks.scale, 'Risk scores are planner assessments, not empirical event probabilities.'))}${risks.planB ? card('Plan B playbooks', valueHTML(risks.planB), true) : ''}${card('Pending weather & operational rechecks', valueHTML(state.pack.rechecks), true)}</div>`;
  }
  function peopleTab() {
    const p = state.pack.people || {};
    const rows = array(first(p.roster, p.members)).map((m) => [esc(first(m.name, 'Name not supplied')), esc(first(m.role, 'Unassigned')), valueHTML(m.freeDates), `${badge(m.demo ? 'Demo only' : first(m.availabilityStatus, 'Unconfirmed'), 'warning')}<br>${esc(m.availableOnProposedDate === true ? 'Listed free on proposed date' : m.availableOnProposedDate === false ? 'Not listed free on proposed date' : 'Availability unknown')}`, esc(first(m.experienceScore, 'Not supplied'))]);
    return `${callout('Availability is not assumed', 'Only an authorised supplied roster can establish stated availability. Suggested roles, student MCs and named demo entries are proposals, not confirmed participants. Private roster names and emails are redacted in the public pack; role aliases preserve the availability comparison.')}<div class="content-grid">${card('Preferred MC · not booked', p.topMC ? valueHTML(p.topMC) : missing('Supply an authorised MC roster to shortlist a real host.'))}${card('Backup MC · not booked', p.backupMC ? valueHTML(p.backupMC) : missing('No backup MC supplied or eligible.'))}${card('Organiser-supplied availability', rows.length ? table(['Public role alias', 'Role', 'Listed free dates', 'Availability caveat', 'Experience score'], rows) : missing('No roster supplied. No demo or real person is automatically assumed.'), true)}${card('Selection & confirmation rules', facts([['Availability status', p.availabilityStatus], ['Selection rule', p.selectionRule], ['Booking confirmed', p.bookingConfirmed], ['Demo data present', p.demo], ['Next actions', first(p.rechecks, p.pendingChecks, p.availabilityNotes, 'Ask organisers and MCs to confirm their availability and responsibilities.')]]), true)}</div>`;
  }
  function draftItems() {
    const d = state.pack?.drafts;
    return Array.isArray(d) ? array(d) : array(first(d?.items, d?.emails, d?.sponsorEmails, d?.outreach, d?.drafts));
  }
  function gmailURL(draft) {
    const url = new URL('https://mail.google.com/mail/');
    url.searchParams.set('view', 'cm'); url.searchParams.set('fs', '1');
    const recipient = first(draft.to, draft.recipientEmail);
    if (typeof recipient === 'string' && /^[^\s@,]+@[^\s@,]+\.[^\s@,]+$/.test(recipient)) url.searchParams.set('to', recipient);
    url.searchParams.set('su', first(draft.subject, 'Event partnership enquiry'));
    url.searchParams.set('body', first(draft.body, draft.text, draft.message, ''));
    return url.href;
  }
  function sponsorTab() {
    const sponsorValue = state.pack.sponsors;
    const sponsorsList = Array.isArray(sponsorValue) ? array(sponsorValue) : array(first(sponsorValue?.shortlist, sponsorValue?.items, sponsorValue?.candidates, sponsorValue?.sponsors));
    const sponsorsHTML = sponsorsList.length ? sponsorsList.map((s) => card(first(s.name, s.company, s.brand, 'Potential partner'), `<div class="badge-group">${badge('Potential sponsor · unconfirmed', 'warning')}${s.confidence ? badge(s.confidence, 'info') : ''}</div>${facts([['Fit / rationale', first(s.fit, s.rationale, s.reason, s.why)], ['Proposed ask', first(s.ask, s.proposedAsk, s.askRM != null ? rm(s.askRM) : undefined, s.supportType, s.offer)], ['Alternative tiers', s.tiers], ['Contact status', first(s.contactStatus, s.contact?.status, s.contactVerified ? 'Source-verified contact — review before outreach' : 'Email needed — use the official contact page')], ['Contact route', s.contactType], ['Evidence', first(s.evidence, s.sourceNotes, s.verifiedFacts, s.fitStatus)], ['Accounting', s.accounting]])}${sources(s)}`, false)).join('') : card('Sponsor research', valueHTML(sponsorValue), true);
    const drafts = draftItems();
    const draftsHTML = drafts.map((d, index) => `<article class="draft-card"><h4>${esc(first(d.recipient, d.sponsor, d.company, d.name, d.title, `Outreach draft ${index + 1}`))}</h4><div class="badge-group">${badge('Draft only — never sent', 'info')}${d.type ? badge(label(d.type), 'info') : ''}${d.demo ? badge('Fictional demo recipient', 'warning') : ''}${!first(d.to, d.recipientEmail) ? badge('Recipient email needed', 'warning') : ''}</div>${facts([['Recipient', first(d.to, d.recipientEmail, 'Blank — verify an official email first')], ['Subject', first(d.subject, 'Event partnership enquiry')], ...(d.condition ? [['Use only when', d.condition]] : []), ...(d.sendAfterDays != null ? [['Suggested follow-up', `${d.sendAfterDays} days after a manually reviewed initial message`]] : [])])}${sources(d)}<div class="draft-body">${esc(first(d.body, d.text, d.message, 'No message body supplied.'))}</div><div class="draft-actions"><a class="button secondary" href="${esc(gmailURL(d))}" target="_blank" rel="noopener noreferrer">Open Gmail compose ↗</a><button class="text-button" data-copy-draft="${index}">Copy draft</button><a class="text-button" href="/api/runs/${encodeURIComponent(state.id)}/eml/${index}">Download .eml ↓</a></div></article>`).join('');
    return `${callout('Prospective partnerships, not secured sponsorship', 'Source citations establish public information only. Contact channels need verification; no email address is guessed. Compose links may leave the recipient blank. Nothing is sent automatically.')}<div class="content-grid">${sponsorsHTML}</div><div class="mini-separator"></div>${gmailReceiptHTML()}<div class="gmail-banner"><div><strong>Create Gmail drafts — you keep the final say.</strong><p class="sources-note">Saved run metrics: ${esc(first(state.pack.metrics?.gmailDraftsCreated, state.metrics?.gmailDraftsCreated, 0))} confirmed Gmail drafts · ${esc(first(state.pack.metrics?.emailsSent, state.metrics?.emailsSent, 0))} emails sent. Only eligible non-demo recipients are attempted, at most 24 draft indexes per request.</p><p id="gmail-help">${state.clientId ? 'Connect Google in a popup to authorise gmail.compose only. The app creates drafts, never sends mail.' : 'Google OAuth is not configured. The button explains the fallback: Gmail compose, copy text, or .eml download. No account connection is pretended.'}</p></div><button class="button primary" id="gmail-drafts" ${state.gmailBusy ? 'disabled' : ''}>${state.gmailBusy ? 'Creating drafts…' : 'Create Gmail drafts ↗'}</button></div>${draftsHTML ? `<div class="draft-grid">${draftsHTML}</div>` : empty('No outreach drafts supplied', 'Sponsor facts may be available, but no email text was included in this saved pack.')}`;
  }
  function promoTab() {
    const promo = state.pack.promo;
    const entries = Array.isArray(promo) ? array(promo) : array(first(promo?.posts, promo?.captions, promo?.assets, promo?.items));
    if (!entries.length) return `<div class="content-grid">${card('Promotion plan & ready-to-edit copy', valueHTML(promo), true, 'Verify final venue, date, links and partner permission before posting. Nothing is published automatically.')}</div>`;
    return `${callout('Ready to edit. Not automatically published.', 'Confirm the final date, venue, registration link and any sponsor branding permissions before posting.', 'info')}<div class="content-grid">${promo?.poster ? card('Poster copy & details', valueHTML(promo.poster), true) : ''}${entries.map((entry, index) => card(typeof entry === 'string' ? `Ready-to-edit caption ${index + 1}` : first(entry.channel, entry.platform, entry.title, entry.name, 'Promotion asset'), typeof entry === 'string' ? `<div class="draft-body">${esc(entry)}</div>` : `${facts([['Audience', entry.audience], ['When', first(entry.when, entry.date, entry.timing)], ['Call to action', first(entry.cta, entry.callToAction)]])}<div class="draft-body">${esc(first(entry.copy, entry.text, entry.caption, entry.body, entry.message, 'No copy supplied.'))}</div>${sources(entry)}`)).join('')}${!Array.isArray(promo) ? card('Promotion schedule & guardrails', valueHTML(Object.fromEntries(Object.entries(promo || {}).filter(([key]) => !['posts', 'captions', 'assets', 'items', 'poster'].includes(key)))), true) : ''}</div>`;
  }
  function exportTab() {
    return `${callout('Saved, shareable, and still subject to confirmation', 'The run link shows the Event Pack and actual execution trace without login. Roster email addresses and OAuth tokens must not appear in shared packs. PDF and email drafts are exports, not bookings or sent messages.', 'info')}<div class="export-grid"><section class="export-option"><h3>A readable event pack</h3><p>Download the structured plan as a PDF for organiser handover and review.</p><a class="button primary" href="/api/runs/${encodeURIComponent(state.id)}/pdf">Download Event Pack PDF ↓</a></section><section class="export-option"><h3>Share the saved run</h3><p>Read-only plan, sources and genuine specialist trace. No login required.</p><button class="button secondary" data-copy-link>Copy run link ↗</button></section><section class="export-option"><h3>Outreach drafts, not sent mail</h3><p>Gmail compose, clipboard copy and individual .eml exports are available under Sponsors / Gmail.</p><button class="button secondary" data-open-sponsors>Review draft emails →</button></section><section class="export-option"><h3>Inspect real recorded execution</h3><p>Replay preserves recorded tool results and identifies itself as a replay, not new research.</p><button class="button secondary" data-replay>Replay recorded run →</button></section></div>${card('Validation before handover', valueHTML(state.pack.validation), true)}`;
  }
  function renderContent() {
    if (!state.pack) return;
    const renderers = { Overview: overview, 'Date Decision': dateDecision, Timeline: timeline, Budget: budgetTab, 'Risk / Weather': weatherTab, 'People / MCs': peopleTab, 'Sponsors / Gmail': sponsorTab, Promo: promoTab, Export: exportTab };
    $('tab-content').innerHTML = renderers[state.tab]();
  }
  function selectTab(tab) { if (!tabs.includes(tab)) return; state.tab = tab; renderTabs(); renderContent(); }
  async function copyText(text, success) {
    try { if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text); else { const input = document.createElement('textarea'); input.value = text; input.style.position = 'fixed'; input.style.opacity = '0'; document.body.append(input); input.select(); const copied = document.execCommand('copy'); input.remove(); if (!copied) throw new Error('Copy failed'); } notice(success); } catch { notice('Clipboard access was blocked. Select and copy from the visible draft, or copy the saved run address from the browser.'); }
  }
  function copyRunLink() { if (state.id) copyText(`${location.origin}/run/${encodeURIComponent(state.id)}`, 'Saved run link copied. The public pack excludes private roster email addresses.'); }
  function editRerun() {
    const g = state.pack?.goal || {};
    for (const [id, key] of [['event-type', 'eventType'], ['cause', 'cause'], ['date-start', 'dateStart'], ['date-end', 'dateEnd'], ['budget', 'budgetRM'], ['organiser-funds', 'organiserFundsRM'], ['attendance', 'attendance'], ['campus', 'campus'], ['location', 'location']]) if (g[key] != null) $(id).value = String(g[key]);
    if (!$('prompt').value.trim()) $('prompt').value = `Plan ${first(g.eventType, 'a campus event')} at ${first(g.campus, 'Taylor’s Lakeside Campus')} for ${first(g.attendance, 120)} attendees. Purpose: ${first(g.cause, 'student engagement')}. Use the editable planning assumptions below; all commitments require confirmation.`;
    document.querySelector('.brief-details').open = true; $('planner').scrollIntoView({ behavior: 'smooth', block: 'start' }); $('prompt').focus(); notice('Your recorded planning assumptions are loaded below. Edit any field, then build a new run. Private roster data is not recovered from the public pack.');
  }
  async function loadGoogleLibrary() {
    if (window.google?.accounts?.oauth2) return;
    await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client'; script.async = true; script.onload = resolve; script.onerror = () => reject(new Error('Google authorisation could not load. Use the compose/copy/.eml fallback instead.')); document.head.append(script); });
    if (!window.google?.accounts?.oauth2) throw new Error('Google authorisation is unavailable. Use the compose/copy/.eml fallback instead.');
  }
  function gmailReceiptHTML() {
    const result = state.gmailResult;
    if (!result) return '';
    const receipts = array(first(result.created, result.drafts, result.items));
    const errors = array(result.errors);
    const rows = [...receipts.map((receipt) => [esc(receipt.index), esc(receipt.alreadyCreated ? receipt.contentChanged ? 'Existing draft — content changed; review manually' : 'Existing draft — no duplicate created' : 'New draft receipt confirmed'), esc(first(receipt.subject, 'Review in Gmail'))]), ...errors.map((error) => [esc(first(error.index, 'Request')), badge('Failed / review required', 'error'), esc(first(error.error, error.message, 'Use compose, copy or .eml fallback.'))])];
    return `${card('Gmail draft results', `${callout('No email was sent', 'Indexes below match the saved draft array. Failed or uncertain items need manual review; do not assume a draft exists without a receipt.', 'info')}${table(['Draft index (zero-based)', 'Receipt / outcome', 'Details'], rows)}${result.unattempted?.length ? `<p class="sources-note">Not attempted after the server stopped processing: ${esc(result.unattempted.join(', '))}. Review the reported failure before retrying.</p>` : ''}`, true)}<div class="mini-separator"></div>`;
  }
  async function createGmailDrafts() {
    if (!state.clientId) { notice('Google OAuth is not configured. No Gmail drafts were created. Use the Open Gmail compose, Copy draft, or Download .eml actions below; verify recipient addresses and save drafts yourself.'); $('gmail-help')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
    if (state.gmailBusy) return;
    const runId = state.id;
    const drafts = draftItems();
    const eligible = drafts.map((draft, index) => ({ draft, index })).filter(({ draft }) => !draft.demo && typeof draft.to === 'string' && /^[^\s@,]+@[^\s@,]+\.[^\s@,]+$/.test(draft.to) && draft.sourceVerified !== false);
    const indices = eligible.slice(0, 24).map(({ index }) => index);
    if (!indices.length) { notice('No eligible verified recipient drafts are available. No Google authorisation or draft creation was attempted. Use blank-recipient Gmail compose, copy or .eml after verifying an appropriate contact.'); return; }
    let attempted = false;
    try {
      if (!window.google?.accounts?.oauth2) { await loadGoogleLibrary(); notice('Google authorisation is ready. Click Create Gmail drafts again to open the consent popup. No drafts have been created yet.'); return; }
      state.gmailBusy = true;
      const accessToken = await new Promise((resolve, reject) => {
        const client = window.google.accounts.oauth2.initTokenClient({ client_id: state.clientId, scope: 'https://www.googleapis.com/auth/gmail.compose', include_granted_scopes: false, callback: (response) => response.error ? reject(new Error(response.error_description || response.error)) : response.access_token ? resolve(response.access_token) : reject(new Error('Google did not return an access token.')), error_callback: () => reject(new Error('Google authorisation was cancelled or could not open. No email was sent.')) });
        client.requestAccessToken({ prompt: 'consent' });
      });
      renderContent(); attempted = true;
      let result;
      try { result = await request(`/api/runs/${encodeURIComponent(runId)}/gmail-drafts`, { method: 'POST', body: JSON.stringify({ accessToken, indices }) }); }
      catch (error) { if (Array.isArray(error.data?.errors)) result = error.data; else throw error; }
      const receipts = array(first(result.created, result.drafts, result.items));
      const failures = array(result.errors);
      const existing = receipts.filter((receipt) => receipt.alreadyCreated).length;
      const newlyCreated = receipts.length - existing;
      const outcomes = new Set([...receipts, ...failures].map((item) => item.index));
      const unattempted = indices.filter((index) => !outcomes.has(index));
      state.gmailResult = { ...result, unattempted };
      notice(`${newlyCreated} new Gmail draft(s) created; ${existing} existing draft receipt(s) confirmed without duplicates. ${failures.length ? `Failed/review-needed indexes: ${failures.map((failure) => first(failure.index, 'request')).join(', ')}. ` : ''}${unattempted.length ? `Not attempted: ${unattempted.join(', ')}. ` : ''}${eligible.length > 24 ? `${eligible.length - 24} eligible draft(s) omitted by the 24-item limit. ` : ''}No email was sent. See per-index results below and review Gmail before acting.`, failures.length > 0 || unattempted.length > 0);
    } catch (error) { notice(`${error.message} Compose, copy and .eml fallback actions remain available.`, true); }
    finally {
      if (attempted) {
        try { const saved = await request(`/api/runs/${encodeURIComponent(runId)}`); if (state.id === runId) { state.pack = saved.pack || state.pack; state.metrics = saved.metrics || saved.pack?.metrics || state.metrics; if (state.pack && state.metrics) state.pack.metrics = { ...state.pack.metrics, ...state.metrics }; state.trace = array(saved.trace); renderTrace(); } }
        catch { notice('The Gmail attempt completed, but saved metrics could not be refreshed. Reload this run before relying on counters. Review the per-index receipts below; no email was sent.', true); }
      }
      state.gmailBusy = false; if (state.pack) renderContent();
    }
  }
  $('run-form').addEventListener('submit', (event) => { event.preventDefault(); startRun(); });
  document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => { $('prompt').value = examples[button.dataset.example]; $('prompt').focus(); }));
  $('run-example').addEventListener('click', () => { $('prompt').value = examples.canonical; document.querySelectorAll('.field-grid input').forEach((input) => { input.value = ''; }); $('roster').value = ''; state.demo = false; updateRosterStatus(); startRun(); });
  $('replay-button').addEventListener('click', () => startRun('replay'));
  $('sample-roster').addEventListener('click', () => { state.demo = true; $('roster').value = 'name,role,freeDates,email\nDemo organiser,Organiser,2026-11-07;2026-11-14;2026-11-21,\nDemo MC,MC,2026-11-14;2026-11-21,\nDemo volunteer,Volunteer,2026-11-07;2026-11-21,'; updateRosterStatus(); });
  $('roster').addEventListener('input', () => { state.demo = $('roster').value.includes('Demo organiser'); updateRosterStatus(); });
  $('copy-link').addEventListener('click', copyRunLink); $('edit-rerun').addEventListener('click', editRerun);
  $('tabs').addEventListener('click', (event) => { const button = event.target.closest('[data-tab]'); if (button) selectTab(button.dataset.tab); });
  $('tabs').addEventListener('keydown', (event) => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const current = tabs.indexOf(state.tab); const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; selectTab(tabs[index]); $(`tab-${index}`).focus(); });
  $('tab-content').addEventListener('click', (event) => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.id === 'gmail-drafts') createGmailDrafts();
    else if (button.hasAttribute('data-copy-link')) copyRunLink();
    else if (button.hasAttribute('data-open-sponsors')) selectTab('Sponsors / Gmail');
    else if (button.hasAttribute('data-replay')) startRun('replay');
    else if (button.hasAttribute('data-copy-draft')) { const d = draftItems()[Number(button.dataset.copyDraft)]; if (d) copyText(`To: ${first(d.to, d.recipientEmail, '[verify recipient email]')}\nSubject: ${first(d.subject, 'Event partnership enquiry')}\n\n${first(d.body, d.text, d.message, '')}`, 'Draft copied. No message was sent. Verify the recipient before using it.'); }
  });
  window.addEventListener('popstate', () => { const match = location.pathname.match(/^\/run\/([^/]+)\/?$/); closeStream(); if (match) loadRun(decodeURIComponent(match[1])).catch((error) => notice(error.message, true)); else { state.id = null; state.pack = null; state.trace = []; state.replay = false; $('results').hidden = true; $('empty-results').hidden = false; setBusy(false); runStatus('idle'); renderTrace(); } });
  renderDAG();
  request('/api/config').then((config) => { state.clientId = config.googleClientId || ''; state.configLoaded = true; if (state.clientId) loadGoogleLibrary().catch(() => {}); if (state.pack && state.tab === 'Sponsors / Gmail') renderContent(); }).catch(() => { state.configLoaded = true; });
  const saved = location.pathname.match(/^\/run\/([^/]+)\/?$/);
  if (saved) loadRun(decodeURIComponent(saved[1])).catch((error) => { setBusy(false); runStatus('failed'); notice(`Could not load the saved run. ${error.message}`, true); });
})();
