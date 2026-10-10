'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const examples = {
    canonical: 'I want to organize a charity event at my university in March with a budget of RM2k.',
    bazaar: 'Plan a charity bazaar at Taylor\u2019s Lakeside Campus for 120 attendees between 1 and 30 November 2026 with a RM 5,000 budget. Support student wellbeing, compare dates using local weather climatology, propose a covered venue, student MCs, suitable Malaysian sponsors, outreach drafts and a promotion plan. Treat all bookings and sponsor commitments as unconfirmed.',
    workshop: 'Plan a career skills workshop at Taylor\u2019s Lakeside Campus for 80 students between 1 and 30 November 2026 with a RM 3,000 budget. Compare dates, propose an indoor venue, organisers and MC roles, a practical programme, potential Malaysian sponsors, outreach drafts and a promotion plan.',
    dormathon: 'Plan a Dormathon Track 2 student project showcase at Taylor\u2019s Lakeside Campus for 120 attendees between 1 and 30 November 2026 with a RM 5,000 budget. Compare dates using local weather climatology, propose a covered venue, student MCs, suitable Malaysian sponsors, outreach drafts and a promotion plan. Treat all bookings and sponsor commitments as unconfirmed.',
    esports: 'Plan an e-sports tournament at Taylor\u2019s Lakeside Campus on 15 March 2027 with a RM 2,000 budget for 50 participants. Compare dates, propose an indoor venue with gaming setups, suitable Malaysian sponsors, outreach drafts and a promotion plan.'
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
  const state = { id: null, status: 'idle', pack: null, trace: [], metrics: null, tab: 'Overview', source: null, demo: false, replay: false, clientId: '', configLoaded: false, gmailBusy: false, gmailResult: null, startedAt: null, llmEnabled: false, llmModel: null, llmBusy: false };
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
    return links.length ? `<div class="source-list">${links.map((item) => `<a class="source-link" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(item.title)} \u2197</a>`).join('')}</div>` : '';
  }
  function valueHTML(value, depth = 0) {
    if (value == null || value === '') return missing();
    if (typeof value === 'boolean') return esc(value ? 'Yes' : 'No');
    if (typeof value !== 'object') { const url = safeURL(String(value)); return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(new URL(url).hostname)} \u2197</a>` : esc(value); }
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

  // === LLM-POWERED PROMPT INTERPRETER ===
  // Calls the server-side /api/llm-interpret proxy which uses the AI/ML API.
  // The API key stays server-side and is never exposed to the browser.
  // Falls back to deterministic keyword extraction when LLM is unavailable.
  async function interpretPromptWithLLM(text) {
    if (!state.llmEnabled || !text || text.length < 5) return null;
    try {
      const result = await request('/api/llm-interpret', {
        method: 'POST',
        body: JSON.stringify({ prompt: text }),
      });
      if (result.fallback || !result.interpretation) return null;
      return result.interpretation;
    } catch (error) {
      console.warn('LLM interpretation failed, will use deterministic fallback:', error.message || error);
      return null;
    }
  }

  // === PROMPT INTERPRETER (deterministic keyword extraction, fallback when LLM unavailable, max ~300 tokens) ===
  function interpretPrompt(text) {
    if (!text || typeof text !== 'string') return null;
    const t = text.toLowerCase();
    const now = new Date();
    const currentMonth = now.getMonth();
    const currentYear = now.getFullYear();
    const result = { eventType: '', cause: '', budgetRM: null, attendance: null, dateStart: '', dateEnd: '', month: null, year: null, campus: '', location: '', eventName: '' };
    const monthMap = { january: 0, jan: 0, february: 1, feb: 1, march: 2, mar: 2, april: 3, apr: 3, may: 4, june: 5, jun: 5, july: 6, jul: 6, august: 7, aug: 7, september: 8, sep: 8, sept: 8, october: 9, oct: 9, november: 10, nov: 10, december: 11, dec: 11 };

    // ── Event type detection (expanded) ──────────────────────────
    const typeMap = [
      ['e-sport', 'e-sports tournament'], ['esport', 'e-sports tournament'], ['e sport', 'e-sports tournament'], ['gaming', 'e-sports tournament'],
      ['hackathon', 'hackathon'], ['code jam', 'hackathon'],
      ['bazaar', 'bazaar'], ['market', 'bazaar'], ['sale', 'bazaar'], ['jumble', 'bazaar'],
      ['workshop', 'workshop'], ['seminar', 'seminar'], ['talk', 'talk'], ['forum', 'forum'],
      ['charity concert', 'charity concert'], ['charity gala', 'charity gala'],
      ['charity', 'charity event'], ['fundrais', 'charity event'], ['donat', 'charity event'],
      ['showcase', 'showcase'], ['exhibition', 'exhibition'], ['expo', 'exhibition'],
      ['concert', 'concert'], ['performance', 'performance'], ['gig', 'performance'],
      ['festival', 'festival'], ['jamboree', 'festival'],
      ['competition', 'competition'], ['contest', 'competition'], ['tournament', 'tournament'],
      ['debate', 'debate competition'], ['public speaking', 'public speaking competition'],
      ['career', 'career workshop'], ['networking', 'networking session'],
      ['dormathon', 'Dormathon showcase'],
      ['sports day', 'sports day'], ['sports', 'sports event'], ['athletic', 'sports event'],
      ['cultural night', 'cultural night'], ['cultural', 'cultural event'],
      ['food', 'food fair'], ['food fair', 'food fair'], ['food fest', 'food fair'],
      ['game', 'game event'],
    ];
    for (const [kw, type] of typeMap) { if (t.includes(kw)) { result.eventType = type; break; } }
    if (!result.eventType) result.eventType = 'campus event';

    // ── Cause / purpose detection ────────────────────────────────
    const causeMap = [
      ['student wellbeing', 'student wellbeing'], ['wellbeing', 'student wellbeing'],
      ['mental health', 'mental health awareness'], ['charity', 'charity / fundraising'],
      ['fundrais', 'charity / fundraising'], ['donat', 'charity / fundraising'],
      ['community', 'community engagement'], ['sustainability', 'sustainability'],
      ['environment', 'environmental awareness'], ['social impact', 'social impact'],
      ['education', 'educational outreach'], ['refugee', 'refugee support'],
    ];
    for (const [kw, cause] of causeMap) { if (t.includes(kw)) { result.cause = cause; break; } }

    // ── Budget detection ────────────────────────────────────────
    const budgetMatch = t.match(/rm\s*([0-9]+(?:[,.][0-9]{3})*(?:\.[0-9]+)?)/) || t.match(/budget[^0-9]*([0-9]+(?:[,.][0-9]{3})*(?:\.[0-9]+)?)/);
    if (budgetMatch) result.budgetRM = Number(budgetMatch[1].replace(/[,]/g, ''));
    const kMatch = t.match(/rm\s*([0-9]+)\s*k/) || t.match(/([0-9]+)\s*k\s*budget/);
    if (kMatch) result.budgetRM = Number(kMatch[1]) * 1000;

    // ── Attendance detection ─────────────────────────────────────
    const attMatch = t.match(/(\d+)\s*(?:students?|attendees?|guests?|participants?|people|visitors?|pax)/) || t.match(/(?:for|around|about|~)\s*(\d+)\s*(?:students?|attendees?|guests?|participants?|people|visitors?|pax)/);
    if (attMatch) result.attendance = Number(attMatch[1]);

    // ── Date detection (only use dates the user explicitly stated) ──
    let foundMonth = null, foundYear = null;
    for (const [monthName, monthNum] of Object.entries(monthMap)) {
      if (t.includes(monthName)) { foundMonth = monthNum; break; }
    }
    const yearMatch = t.match(/\b(20[2-9][0-9])\b/);
    if (yearMatch) foundYear = Number(yearMatch[1]);

    // Specific date: "15 March 2027", "March 15 2027", "15 Mar 2027"
    const specificDate1 = t.match(/\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s*(20\d{2})?/i);
    const specificDate2 = t.match(/\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})?/i);
    // Date range: "between 1 and 30 November 2026"
    const rangeMatch = t.match(/between\s+(\d{1,2})\s+and\s+(\d{1,2})\s+(\w+)\s*(\d{4})?/i);
    // Slash dates: "15/3/2027" or "15/03/2027"
    const slashDate = t.match(/\b(\d{1,2})\/(\d{1,2})\/(20\d{2})\b/);

    function makeDate(y, m, d) { return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`; }

    // Only set dates that the user explicitly wrote — no proposed defaults
    if (rangeMatch) {
      const day1 = Number(rangeMatch[1]), day2 = Number(rangeMatch[2]);
      const mn = monthMap[rangeMatch[3].toLowerCase()];
      if (mn !== undefined) {
        // Use the year the user wrote, or leave empty if not specified
        if (rangeMatch[4]) {
          const y = Number(rangeMatch[4]);
          result.dateStart = makeDate(y, mn, day1);
          result.dateEnd = makeDate(y, mn, day2);
          result.month = mn + 1;
          result.year = y;
        } else {
          // Year not given — only set month, let server pick the year
          result.month = mn + 1;
        }
      }
    } else if (slashDate) {
      const d = Number(slashDate[1]), mn = Number(slashDate[2]) - 1, y = Number(slashDate[3]);
      result.dateStart = makeDate(y, mn, d);
      result.dateEnd = makeDate(y, mn, d);
      result.month = mn + 1;
      result.year = y;
    } else if (specificDate1) {
      const d = Number(specificDate1[1]), mn = monthMap[specificDate1[2].toLowerCase()];
      if (specificDate1[3]) {
        // User gave a full date with year — use it exactly
        const y = Number(specificDate1[3]);
        result.dateStart = makeDate(y, mn, d);
        result.dateEnd = makeDate(y, mn, d);
        result.month = mn + 1;
        result.year = y;
      } else {
        // User gave a date without year — only set month, let server pick the year
        result.month = mn + 1;
      }
    } else if (specificDate2) {
      const mn = monthMap[specificDate2[1].toLowerCase()], d = Number(specificDate2[2]);
      if (specificDate2[3]) {
        const y = Number(specificDate2[3]);
        result.dateStart = makeDate(y, mn, d);
        result.dateEnd = makeDate(y, mn, d);
        result.month = mn + 1;
        result.year = y;
      } else {
        result.month = mn + 1;
      }
    } else if (foundMonth !== null) {
      // User mentioned a month but no specific day — just pass the month, let server handle the rest
      result.month = foundMonth + 1;
      if (foundYear) result.year = foundYear;
    }
    // If no date info at all, leave everything empty — no proposed defaults

    // ── Campus detection ────────────────────────────────────────
    if (t.includes('taylor') || t.includes('lakeside')) result.campus = "Taylor's Lakeside Campus";
    else if (t.includes('campus')) result.campus = 'Campus (specify)';

    // ── Location / venue preference ─────────────────────────────
    if (t.includes('indoor')) result.location = 'Indoor venue preferred';
    else if (t.includes('covered')) result.location = 'Covered venue preferred';
    else if (t.includes('outdoor')) result.location = 'Outdoor venue considered';

    // ── Event name generation from user's words ─────────────────
    // Try to extract a descriptive phrase from the prompt
    let nameParts = [];
    // Check for compound phrases the user actually typed
    const phrasePatterns = [
      /\b(e-?sports?\s+tournament)\b/i,
      /\b(e-?sports?\s+competition)\b/i,
      /\b(charity\s+concert)\b/i,
      /\b(charity\s+bazaar)\b/i,
      /\b(charity\s+gala)\b/i,
      /\b(charity\s+event)\b/i,
      /\b(career\s+workshop)\b/i,
      /\b(cultural\s+night)\b/i,
      /\b(sports\s+day)\b/i,
      /\b(food\s+fair)\b/i,
      /\b(networking\s+session)\b/i,
    ];
    let phrase = null;
    for (const p of phrasePatterns) { const m = text.match(p); if (m) { phrase = m[1]; break; } }
    if (phrase) {
      nameParts.push(phrase);
    } else if (result.cause) {
      // "E-Sports Tournament for Student Wellbeing"
      nameParts.push(result.eventType);
    } else {
      nameParts.push(result.eventType);
    }
    // Add cause if present and not already in the phrase
    if (result.cause && phrase && !phrase.toLowerCase().includes(result.cause.toLowerCase().split(' ')[0])) {
      nameParts.push('for', result.cause);
    } else if (result.cause && !phrase) {
      nameParts.push('for', result.cause);
    }
    // Capitalize each part
    const eventName = nameParts.join(' ').replace(/\b\w/g, (c) => c.toUpperCase());
    result.eventName = eventName + (result.campus ? ' at ' + result.campus.replace(/'s Lakeside Campus/i, "'s University") : '');

    return result;
  }

  function applyInterpretation(interp) {
    if (!interp) return;
    // Clear previously auto-filled fields (preserve manually edited ones)
    document.querySelectorAll('.field-grid input[data-autofilled="true"]').forEach((el) => { el.value = ''; el.removeAttribute('data-autofilled'); });

    // Auto-fill form fields (only if currently empty — don't override manual edits)
    const fieldMap = {
      'event-type': interp.eventType,
      'cause': interp.cause,
      'date-start': interp.dateStart,
      'date-end': interp.dateEnd,
      'budget': interp.budgetRM,
      'attendance': interp.attendance,
      'campus': interp.campus,
      'location': interp.location,
    };
    for (const [id, val] of Object.entries(fieldMap)) {
      const el = $(id);
      if (el && !el.value && val) { el.value = val; el.setAttribute('data-autofilled', 'true'); }
    }

    const rows = [
      ['Event name', interp.eventName || 'From your brief'],
      ['Event type', interp.eventType || 'From your brief'],
      ['Budget', interp.budgetRM ? `RM ${interp.budgetRM.toLocaleString('en-MY')}` : 'From your brief'],
      ['Attendance', interp.attendance ? `${interp.attendance}` : 'From your brief'],
      ['Date window', interp.dateStart && interp.dateEnd ? `${interp.dateStart} to ${interp.dateEnd}` : (interp.month ? `Month ${interp.month}${interp.year ? ' ' + interp.year : ''} (server picks dates)` : 'Not specified — server will propose')],
      ['Campus', interp.campus || 'From your brief']
    ];
    const sourceLabel = interp._source === 'llm' ? ' (AI-interpreted)' : interp._source === 'llm-fallback' ? ' (AI failed, using rules)' : '';
    preview.innerHTML = `<strong>Interpreted from your brief${sourceLabel} (editable below):</strong>${rows.map(([k, v]) => `<div class="preview-row"><span class="preview-label">${esc(k)}:</span><span class="preview-value">${esc(v)}</span></div>`).join('')}`;
    preview.classList.add('visible');
  }

  let llmPreviewToken = 0;
  function showPromptPreview() {
    const text = $('prompt').value.trim();
    const preview = $('prompt-preview');
    if (!preview || text.length < 10) { if (preview) preview.classList.remove('visible'); return; }

    // Always show deterministic result immediately
    const detInterp = interpretPrompt(text);
    if (detInterp) { detInterp._source = state.llmEnabled ? 'llm-pending' : 'rules'; applyInterpretation(detInterp); }

    // If LLM is available, try to enhance asynchronously
    if (state.llmEnabled && !state.llmBusy) {
      const myToken = ++llmPreviewToken;
      state.llmBusy = true;
      interpretPromptWithLLM(text).then((llmInterp) => {
        state.llmBusy = false;
        if (myToken !== llmPreviewToken) return; // a newer prompt superseded this one
        if (llmInterp) {
          llmInterp._source = 'llm';
          applyInterpretation(llmInterp);
        } else if (detInterp) {
          detInterp._source = 'llm-fallback';
          applyInterpretation(detInterp);
        }
      }).catch(() => { state.llmBusy = false; });
    }
  }

  // === EXCEL EXPORT ===
  function exportBudgetExcel() {
    if (!state.pack) { notice('Run a plan first to export the budget.'); return; }
    if (typeof XLSX === 'undefined') { notice('Spreadsheet library is still loading. Please try again in a moment.'); return; }
    const b = state.pack.budget || {}, items = array(first(b.items, b.allocations));
    const g = state.pack.goal || {};
    const amount = (item) => number(first(item.amountRM, item.totalRM, item.amount, item.costRM, item.total, item.cost));
    const total = first(b.total, b.totalRM, items.reduce((sum, item) => sum + (amount(item) || 0), 0));
    const limit = first(b.limit, b.limitRM, b.budgetRM, g.budgetRM);
    const contingency = first(b.contingencyRM, b.contingency?.amountRM, b.contingency?.amount, b.contingency);
    const gap = first(b.gapRM, b.gap?.amountRM, b.gap);
    const organiserFunds = first(b.organiserFundsRM, b.organiserFunds);
    const chosen = state.pack.dateDecision?.chosen;
    const eventDate = typeof chosen === 'string' ? chosen : first(chosen?.date, chosen?.label, chosen?.dateISO, state.pack.dateDecision?.chosenDate);
    const venue = state.pack.venues || {};
    const venueName = venue.selected?.name || venue.recommended?.name || 'To be confirmed';

    // ── Sheet 1: Event Summary ──────────────────────────────────
    const summaryData = [
      ['EventPilot — Budget Export', ''],
      ['', ''],
      ['Event Type', g.eventType || 'Not specified'],
      ['Event Name', (g.eventType || 'Campus Event') + ' at ' + (g.campus || 'Campus')],
      ['Cause / Purpose', g.cause || 'Not specified'],
      ['Campus', g.campus || 'Not specified'],
      ['Preferred Date', eventDate || 'Pending'],
      ['Venue', venueName],
      ['Expected Attendance', g.attendance || 'Not specified'],
      ['Budget Ceiling (RM)', limit || 0],
      ['Total Allocated (RM)', total || 0],
      ['Contingency (RM)', contingency || 240],
      ['Funding Gap (RM)', gap || 0],
      ['Organiser Funds (RM)', organiserFunds || 0],
      ['Generated', new Date().toLocaleString('en-MY')],
      ['Run ID', state.pack.runId || state.id || 'N/A'],
      ['', ''],
      ['NOTE', 'All figures are planning estimates, not vendor quotes.'],
      ['', ''],
      ['Sponsor Support', first(b.sponsorship, b.sponsorFunds, 'Unconfirmed; no commitment implied')],
      ['Funding Status', b.fundingStatus || 'To be confirmed'],
      ['Gap Resolution', first(b.gapResolution, b.fundingPlan, b.notes, 'Verify organiser funds; reduce spend if gap remains.')],
    ];
    const ws0 = XLSX.utils.aoa_to_sheet(summaryData);
    ws0['!cols'] = [{ wch: 22 }, { wch: 50 }];

    // ── Sheet 2: Budget Breakdown (with % of total) ─────────────
    const breakdownData = [
      ['Category', 'Amount (RM)', '% of Total', 'Quantity', 'Basis / Notes', 'Running Total (RM)'],
    ];
    let runningTotal = 0;
    for (const item of items) {
      const amt = amount(item) || 0;
      runningTotal += amt;
      const pct = total > 0 ? Math.round((amt / total) * 100 * 100) / 100 : 0;
      breakdownData.push([
        first(item.category, item.name, item.item, 'Allocation'),
        amt,
        pct,
        first(item.quantity, item.qty, '') || '',
        first(item.basis, item.notes, item.description, item.rationale, item.assumption, item.status, '') || '',
        Math.round(runningTotal * 100) / 100,
      ]);
    }
    breakdownData.push([]);
    breakdownData.push(['SUMMARY', '', '', '', '', '']);
    breakdownData.push(['Budget ceiling (limit)', limit || 0, '', '', 'RM planning ceiling', '']);
    breakdownData.push(['Allocated total', total || 0, '100%', '', 'Sum of all allocations', '']);
    breakdownData.push(['Contingency reserve', contingency || 240, '', '', 'Protected planning reserve', '']);
    breakdownData.push(['Funding gap', gap || 0, '', '', 'Amount to resolve', '']);
    breakdownData.push(['Organiser funds', organiserFunds || 0, '', '', 'Available from organiser', '']);
    breakdownData.push(['Net position', ((organiserFunds || 0) - (total || 0)), '', '', 'Organiser funds minus allocated total', '']);
    const ws1 = XLSX.utils.aoa_to_sheet(breakdownData);
    ws1['!cols'] = [{ wch: 28 }, { wch: 15 }, { wch: 12 }, { wch: 10 }, { wch: 40 }, { wch: 18 }];

    // ── Sheet 3: Funding & Guardrails ────────────────────────────
    const fundingData = [
      ['Funding Source', 'Amount (RM)', 'Status', 'Notes'],
      ['Organiser funds', organiserFunds || 0, first(b.fundingStatus, 'To confirm'), 'Proposed default: 70% of budget'],
      ['Sponsor support (in-kind)', '', 'Unconfirmed', first(b.sponsorship, b.sponsorFunds, 'No commitment implied')],
      ['Contingency reserve', contingency || 240, 'Protected', 'Do not spend without approval'],
      ['Funding gap', gap || 0, 'To resolve', first(b.gapResolution, b.fundingPlan, 'Reduce spend or secure sponsor support')],
      [],
      ['Guardrails', '', '', ''],
      ['Budget ceiling', limit || 0, 'Hard limit', 'Exceeding requires approval'],
      ['Total allocated', total || 0, 'Committed', 'Sum of all category allocations'],
      ['Remaining (ceiling - allocated)', ((limit || 0) - (total || 0)), 'Available', 'Unallocated headroom'],
      ['Contingency policy', '', '', first(b.contingencyPolicy, b.contingency?.notes, b.contingencyPercent != null ? `${b.contingencyPercent}% reserve` : 'Standard 12% reserve')],
      ['Sponsor accounting', '', '', first(b.sponsorAccounting, 'In-kind support recorded at fair value; no cash assumed without written confirmation')],
    ];
    const ws2 = XLSX.utils.aoa_to_sheet(fundingData);
    ws2['!cols'] = [{ wch: 28 }, { wch: 15 }, { wch: 15 }, { wch: 50 }];

    // ── Sheet 4: Chart Data ─────────────────────────────────────
    const chartData = [
      ['Category', 'Spend (RM)', 'Ceiling (RM)', '% Used'],
      ...items.map((item) => {
        const amt = amount(item) || 0;
        const ceil = Number(limit) || 2000;
        return [first(item.category, item.name, item.item, 'Allocation'), amt, ceil, ceil > 0 ? Math.round((amt / ceil) * 100 * 100) / 100 : 0];
      }),
    ];
    const ws3 = XLSX.utils.aoa_to_sheet(chartData);
    ws3['!cols'] = [{ wch: 28 }, { wch: 15 }, { wch: 15 }, { wch: 10 }];
    if (items.length > 0) ws3['!autofilter'] = { ref: `A1:D${chartData.length}` };

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws0, 'Event Summary');
    XLSX.utils.book_append_sheet(wb, ws1, 'Budget Breakdown');
    XLSX.utils.book_append_sheet(wb, ws2, 'Funding & Guardrails');
    XLSX.utils.book_append_sheet(wb, ws3, 'Chart Data');

    const fileName = `EventPilot-Budget-${(g.eventType || 'event').replace(/\s+/g, '-')}.xlsx`;
    XLSX.writeFile(wb, fileName);
    notice('Budget spreadsheet downloaded with 4 sheets: Summary, Breakdown, Funding, and Chart Data.');
  }

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
  function setBusy(busy) { $('run-button').disabled = busy; $('run-example').disabled = busy; $('replay-button').disabled = busy; $('run-button').textContent = busy ? 'Specialists are working\u2026' : 'Build my event pack \u2191'; }
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
    const laneNames = ['01 \u00b7 FRAME & SOURCE', '02 \u00b7 PARALLEL DATE / COST / VENUE', '03 \u00b7 PARALLEL SPECIALIST OUTPUTS', '04 \u00b7 DRAFT / PROMO \u2192 VALIDATE'];
    $('agent-dag').innerHTML = laneNames.map((name, lane) => `<div class="dag-lane"><div class="lane-title">${esc(name)}</div>${agents.filter((a) => a.lane === lane).map((a) => {
      const events = state.trace.filter((e) => resolveAgent(e) === a.id);
      const event = events.slice().reverse().find((e) => normalizedStatus(e.status) !== 'waiting') || events[events.length - 1]; const status = event ? normalizedStatus(event.status) : 'waiting';
      const statusText = event ? String(event.status || 'event received') : 'Not started';
      return `<div class="agent-card ${esc(status)}"><div class="agent-top"><span class="agent-icon">${esc(a.icon)}</span><div><div class="agent-name">${esc(a.label)}</div><div class="agent-number">${esc(a.id)}</div></div></div><div class="agent-state"><span>${esc(statusText)}</span><span>${event ? status === 'completed' ? '\u2713' : status === 'failed' ? '!' : '\u2191' : '\u2014'}</span></div><div class="agent-deps">${a.deps.length ? `\u2190 ${esc(a.deps.join(' + '))}` : '\u2190 event brief'}</div></div>`;
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
    $('workflow-checks').innerHTML = checkpoints.slice(-8).map((event) => `<div class="workflow-check"><span>${badge(/re.?plan|repair/.test(`${event.status} ${event.tool}`) ? 'Real re-plan / repair' : 'Real validation', /re.?plan|repair/.test(`${event.status} ${event.tool}`) ? 'warning' : 'info')}</span><div><strong>${esc(event.tool || 'Runtime check')} \u00b7 ${esc(event.status || 'event')}</strong><p>${esc(event.message || 'Actual runtime event')}</p></div></div>`).join('');
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
    $('run-status').textContent = state.replay ? `Recorded replay \u00b7 ${status}` : label(status);
    $('run-meta').hidden = !state.id;
    $('run-meta').innerHTML = state.id ? `<span>Run <code>${esc(state.id)}</code> \u00b7 ${state.replay ? '<strong>Replay of a real recorded run</strong>' : 'Actual tool-driven execution'}</span><span>Read-only sharing \u00b7 no roster emails in pack</span>` : '';
  }
  function closeStream() { if (state.source) { state.source.close(); state.source = null; } }
  function complete(pack) {
    closeStream(); state.pack = pack || state.pack; runStatus('completed'); setBusy(false);
    if (!state.pack) { notice('The run completed but no Event Pack was returned. Reload the saved run to retry.', true); return; }
    $('results').hidden = false; $('empty-results').hidden = true;
    const goal = state.pack.goal || {};
    $('results-title').textContent = first(state.pack.title, goal.eventType ? `${goal.eventType} \u00b7 Event Pack` : null, 'The Event Pack');
    $('results-subtitle').textContent = `Proposed plan \u00b7 ${first(goal.campus, 'Taylor\u2019s University')} \u00b7 commitments and availability require confirmation.`;
    $('pdf-link').href = `/api/runs/${encodeURIComponent(state.id)}/pdf`;
    renderTabs(); renderContent();
    if (state.pack.engine) $('engine-description').textContent = typeof state.pack.engine === 'string' ? state.pack.engine : first(state.pack.engine.description, state.pack.engine.disclosure, state.pack.engine.note, 'Tool-driven specialist runtime.');
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
      // Merge: LLM-interpreted values (or deterministic fallback) as defaults, then form overrides take precedence
      let overrides = {};
      if (mode !== 'replay') {
        // Try LLM interpretation first, fall back to deterministic
        let interp = null;
        if (state.llmEnabled) {
          interp = await interpretPromptWithLLM(prompt);
        }
        if (!interp) interp = interpretPrompt(prompt) || {};
        const formOv = formOverrides();
        // Start with interpreted values (clean out nulls/empties)
        for (const [k, v] of Object.entries(interp)) {
          if (v !== null && v !== '' && v !== undefined && k !== 'eventName' && k !== '_source') {
            overrides[k] = v;
          }
        }
        // Form overrides take precedence over interpreted values
        overrides = { ...overrides, ...formOv };
      }
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
    const kpis = [["Preferred date", date || 'Pending', 'Proposed \u00b7 see date comparison'], ['Planning budget', rm(first(budget.total, budget.totalRM, g.budgetRM)), 'Allocations, not vendor quotations'], ['Expected guests', first(g.attendance, 'Unconfirmed'), 'Planning assumption'], ['Venue', first(p.venues?.selected?.name, p.venues?.recommended?.name, 'To be confirmed'), 'No booking has been made']];
    return `${intro}<div class="kpi-grid">${kpis.map(([title, value, note]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value"${String(value).length > 23 ? ' style="font-size:17px"' : ''}>${esc(value)}</div><div class="kpi-note">${esc(note)}</div></div>`).join('')}</div><div class="content-grid">${card('Your brief, translated', facts([['Event type', g.eventType], ['Cause / purpose', g.cause], ['Campus', g.campus], ['Date window', g.dateStart && g.dateEnd ? `${g.dateStart} to ${g.dateEnd}` : first(g.dateStart, g.dateEnd)], ['Budget cap', rm(g.budgetRM)], ['Attendance', g.attendance]]))}${card('Assumptions to confirm', valueHTML(p.assumptions), false, 'Proposed defaults are editable. No campus calendar clearance, sponsor agreement or vendor price is implied.')}${card('Validation & re-planning', valueHTML(p.validation), false, 'Reported results of actual validation \u2014 inspect the execution trace for tools and re-plan steps.')}${card('Next real-world checks', valueHTML(first(p.rechecks, p.pendingChecks)), false, 'Weather, venue, attendance and sponsor confirmations are still your responsibility.')}${p.metrics || state.metrics ? card('Recorded run metrics', valueHTML(p.metrics || state.metrics), true, 'These values are reported by the runtime, not simulated counters.') : ''}</div>`;
  }
  function dateDecision() {
    const d = state.pack.dateDecision || {}, chosen = d.chosen;
    const preferred = typeof chosen === 'object' ? first(chosen?.date, chosen?.label, chosen?.dateISO) : chosen;
    const candidates = array(d.candidates);
    const rows = candidates.map((c) => typeof c !== 'object' ? [esc(c), missing(), missing(), missing()] : [esc(first(c.date, c.label, c.dateISO, 'Unspecified date')), valueHTML(first(c.score, c.totalScore, c.weightedScore)), valueHTML(first(c.reasons, c.reason, c.rationale, c.factors, c.scores, c.breakdown)), `${badge(c.blocked ? 'Excluded: cited clash' : first(c.status, 'Proposed'), c.blocked ? 'error' : 'warning')}<p>${esc(c.examStatus ? `Exam status: ${c.examStatus}` : first(c.availability, c.risk, c.notes, 'Availability unconfirmed'))}</p>`]);
    return `${callout('A proposed date, not a booking', 'Historical weather patterns and supplied availability can support a choice, but do not prove campus clearance or future weather. Confirm the calendar and recheck a short-range forecast before committing.')}<div class="content-grid">${card('Preferred date', `${preferred ? `<div class="weather-number">${esc(preferred)}</div>` : missing('No date selected')}${valueHTML(chosen && typeof chosen === 'object' ? Object.fromEntries(Object.entries(chosen).filter(([k]) => !['date', 'dateISO', 'label'].includes(k))) : first(d.reason, d.rationale))}`)}${card('Backup dates', valueHTML(first(d.backups, d.alternatives)), false, 'Use if availability, weather or operational conditions change.')}${card('Candidate comparison', table(['Candidate date', 'Score', 'Decision factors', 'Status / caveats'], rows), true, 'Scores are relative planning comparisons. They are not forecast probabilities or confirmed free dates.')}${card('Scoring weights & rules', valueHTML(first(d.weights, d.criteria)), true)}${sources(d) ? card('Decision evidence', sources(d), true) : ''}</div>`;
  }
  // === EVENT-TYPE-SPECIFIC TIMELINE TEMPLATES ===
  function suggestedRunOfShow(eventType) {
    const t = (eventType || '').toLowerCase();
    const templates = {
      'e-sports tournament': [
        { time: '08:00', activity: 'Venue setup & equipment check', owner: 'Technical team', notes: 'Gaming rigs, monitors, network, streaming setup' },
        { time: '09:00', activity: 'Player registration & check-in', owner: 'Registration desk', notes: 'Verify IDs, assign player tags, distribute wristbands' },
        { time: '09:30', activity: 'Briefing & rules explanation', owner: 'Tournament admin', notes: 'Format, map pools, rules, disqualification criteria' },
        { time: '10:00', activity: 'Group stage — Round 1', owner: 'Tournament admin', notes: 'Round-robin or Swiss format; 2-3 hours' },
        { time: '13:00', activity: 'Lunch break', owner: 'F&B coordinator', notes: '30-45 minutes' },
        { time: '13:45', activity: 'Group stage — Round 2', owner: 'Tournament admin', notes: 'Complete group standings' },
        { time: '15:30', activity: 'Quarterfinals', owner: 'Tournament admin', notes: 'Best-of-3 single elimination' },
        { time: '16:30', activity: 'Semifinals', owner: 'Tournament admin', notes: 'Best-of-3' },
        { time: '17:30', activity: 'Grand Finals', owner: 'Tournament admin', notes: 'Best-of-5; livestream if available' },
        { time: '18:30', activity: 'Awards ceremony & closing', owner: 'MC / Host', notes: 'Trophy/prize presentation, thank sponsors, photo session' },
        { time: '19:00', activity: 'Teardown', owner: 'Technical team', notes: 'Pack equipment, clean venue' },
      ],
      'tournament': [
        { time: '07:30', activity: 'Venue setup & registration opens', owner: 'Organising team', notes: 'Check equipment, signage, refreshments' },
        { time: '08:30', activity: 'Participant briefing', owner: 'Tournament director', notes: 'Rules, safety, schedule' },
        { time: '09:00', activity: 'Preliminary rounds', owner: 'Officials/Judges', notes: 'Groups or heats' },
        { time: '12:00', activity: 'Lunch break', owner: 'F&B coordinator', notes: '45 minutes' },
        { time: '13:00', activity: 'Knockout rounds', owner: 'Officials/Judges', notes: 'Quarterfinals and semifinals' },
        { time: '15:30', activity: 'Final', owner: 'Officials/Judges', notes: 'Main event' },
        { time: '16:30', activity: 'Awards & closing', owner: 'MC', notes: 'Prize presentation, photos' },
        { time: '17:00', activity: 'Teardown', owner: 'Organising team', notes: 'Clean and pack' },
      ],
      'bazaar': [
        { time: '07:00', activity: 'Booth setup', owner: 'Stall holders', notes: 'Tables, displays, pricing' },
        { time: '08:30', activity: 'Final inspection & briefing', owner: 'Organising team', notes: 'Safety, layout, emergency exits' },
        { time: '09:00', activity: 'Doors open — official welcome', owner: 'MC / Host', notes: 'Opening announcement' },
        { time: '09:15', activity: 'Bazaar trading begins', owner: 'Stall holders', notes: 'Sales, promotions, activities' },
        { time: '11:00', activity: 'Interactive session / games', owner: 'Activities team', notes: 'Audience engagement' },
        { time: '13:00', activity: 'Lunch & entertainment', owner: 'MC / F&B', notes: 'Performance or activity during lunch' },
        { time: '14:00', activity: 'Afternoon trading & activities', owner: 'Stall holders', notes: 'Final push for sales' },
        { time: '15:30', activity: 'Auction / lucky draw', owner: 'MC', notes: 'Fundraising highlight' },
        { time: '16:00', activity: 'Closing & thank-you', owner: 'MC / Host', notes: 'Announce totals, thank sponsors' },
        { time: '16:30', activity: 'Booth teardown', owner: 'Stall holders', notes: 'Clean and vacate' },
      ],
      'workshop': [
        { time: '08:30', activity: 'Registration & coffee', owner: 'Registration desk', notes: 'Name tags, materials' },
        { time: '09:00', activity: 'Opening & introduction', owner: 'Facilitator', notes: 'Welcome, objectives, agenda' },
        { time: '09:15', activity: 'Speaker session 1', owner: 'Speaker', notes: '45 min presentation' },
        { time: '10:15', activity: 'Interactive exercise', owner: 'Facilitator', notes: 'Group activity or hands-on' },
        { time: '11:00', activity: 'Tea break', owner: 'F&B coordinator', notes: '15 min' },
        { time: '11:15', activity: 'Speaker session 2', owner: 'Speaker', notes: '45 min presentation' },
        { time: '12:15', activity: 'Panel discussion / Q&A', owner: 'Facilitator', notes: 'Open floor' },
        { time: '13:00', activity: 'Networking lunch', owner: 'F&B coordinator', notes: '45-60 min' },
        { time: '14:00', activity: 'Practical workshop activity', owner: 'Facilitator', notes: 'Hands-on group work' },
        { time: '15:30', activity: 'Group presentations & feedback', owner: 'Participants', notes: 'Share outputs' },
        { time: '16:00', activity: 'Closing & certificates', owner: 'Facilitator', notes: 'Summary, next steps, certificates' },
      ],
      'concert': [
        { time: '14:00', activity: 'Sound check & technical rehearsal', owner: 'Technical team', notes: 'Audio, lighting, stage' },
        { time: '16:00', activity: 'Doors open', owner: 'Front of house', notes: 'Ticket check, ushering' },
        { time: '16:30', activity: 'Opening act', owner: 'MC / Opening performer', notes: '15-20 min warmup' },
        { time: '17:00', activity: 'Main performance — Set 1', owner: 'Main performer(s)', notes: '45-60 min' },
        { time: '18:00', activity: 'Intermission', owner: 'F&B / MC', notes: '15 min break, refreshments' },
        { time: '18:15', activity: 'Main performance — Set 2', owner: 'Main performer(s)', notes: '45-60 min' },
        { time: '19:15', activity: 'Encore', owner: 'Main performer(s)', notes: '1-2 songs' },
        { time: '19:30', activity: 'Closing & thank-you', owner: 'MC', notes: 'Thank sponsors, announce totals' },
        { time: '20:00', activity: 'Teardown', owner: 'Technical team', notes: 'Pack equipment, clean' },
      ],
      'showcase': [
        { time: '09:00', activity: 'Setup & exhibit assembly', owner: 'Participants', notes: 'Booths, posters, demos' },
        { time: '10:00', activity: 'Doors open & welcome', owner: 'MC / Host', notes: 'Opening remarks' },
        { time: '10:15', activity: 'Showcase session 1', owner: 'Participants', notes: 'Rotating viewing of exhibits' },
        { time: '11:30', activity: 'Lightning talks', owner: 'Selected presenters', notes: '5-min presentations' },
        { time: '12:15', activity: 'Networking lunch', owner: 'F&B coordinator', notes: '45 min' },
        { time: '13:00', activity: 'Showcase session 2', owner: 'Participants', notes: 'Continue exhibit viewing' },
        { time: '14:30', activity: 'Judging / peer review', owner: 'Judges / Facilitator', notes: 'Evaluate exhibits' },
        { time: '15:30', activity: 'Awards & closing', owner: 'MC', notes: 'Present awards, thank participants' },
        { time: '16:00', activity: 'Teardown', owner: 'Participants', notes: 'Clean and pack' },
      ],
      'hackathon': [
        { time: '08:00', activity: 'Check-in & breakfast', owner: 'Registration desk', notes: 'Team confirmation, wristbands' },
        { time: '09:00', activity: 'Opening ceremony', owner: 'MC / Host', notes: 'Rules, theme reveal, API demos' },
        { time: '10:00', activity: 'Hacking begins', owner: 'Teams', notes: 'Build phase starts' },
        { time: '13:00', activity: 'Lunch', owner: 'F&B coordinator', notes: 'Working lunch' },
        { time: '14:00', activity: 'Mentoring round', owner: 'Mentors', notes: 'Office hours for teams' },
        { time: '18:00', activity: 'Dinner & mini-event', owner: 'MC', notes: 'Lightning talks or games' },
        { time: '22:00', activity: 'Late-night coding', owner: 'Teams', notes: 'Optional overnight' },
        { time: '08:00', activity: 'Breakfast (Day 2)', owner: 'F&B coordinator', notes: 'Final sprint' },
        { time: '10:00', activity: 'Hacking ends — submission', owner: 'Teams', notes: 'Code freeze' },
        { time: '10:30', activity: 'Judging round 1', owner: 'Judges', notes: 'Initial screening' },
        { time: '12:00', activity: 'Finalist presentations', owner: 'Finalist teams', notes: '5-min demos to panel' },
        { time: '13:00', activity: 'Awards & closing', owner: 'MC', notes: 'Winners announced, prizes' },
      ],
      'food fair': [
        { time: '07:00', activity: 'Vendor setup & food prep', owner: 'Food vendors', notes: 'Stalls, cooking, hygiene check' },
        { time: '08:30', activity: 'Final inspection', owner: 'Organising team', notes: 'Safety, fire, health compliance' },
        { time: '09:00', activity: 'Doors open & opening ceremony', owner: 'MC', notes: 'Welcome, food safety briefing' },
        { time: '09:15', activity: 'Food trading begins', owner: 'Food vendors', notes: 'Sales open to public' },
        { time: '11:00', activity: 'Cooking demonstration', owner: 'Guest chef', notes: '30-min demo' },
        { time: '12:00', activity: 'Peak lunch service', owner: 'Food vendors', notes: 'Busiest period' },
        { time: '14:00', activity: 'Eating contest / food game', owner: 'MC', notes: 'Audience activity' },
        { time: '15:00', activity: 'Final sales & cleanup prep', owner: 'Food vendors', notes: 'Last orders' },
        { time: '15:30', activity: 'Closing & thank-you', owner: 'MC', notes: 'Announce totals, thank vendors' },
        { time: '16:00', activity: 'Teardown', owner: 'Food vendors', notes: 'Clean, dispose waste properly' },
      ],
      'cultural night': [
        { time: '17:00', activity: 'Backstage prep & sound check', owner: 'Technical team', notes: 'Audio, costumes, props' },
        { time: '18:30', activity: 'Doors open', owner: 'Front of house', notes: 'Ticket check, ushering' },
        { time: '19:00', activity: 'Opening performance', owner: 'MC / Performers', notes: 'Welcome dance or song' },
        { time: '19:15', activity: 'Cultural performance — Act 1', owner: 'Performers', notes: 'Traditional performances' },
        { time: '20:00', activity: 'Intermission', owner: 'F&B / MC', notes: '15 min, refreshments' },
        { time: '20:15', activity: 'Cultural performance — Act 2', owner: 'Performers', notes: 'Contemporary fusion' },
        { time: '21:00', activity: 'Audience participation segment', owner: 'MC', notes: 'Interactive cultural activity' },
        { time: '21:30', activity: 'Finale & thank-you', owner: 'All performers', notes: 'Group performance, sponsors' },
        { time: '22:00', activity: 'Teardown', owner: 'Technical team', notes: 'Pack equipment, clean' },
      ],
    };
    // Find matching template
    for (const [key, sched] of Object.entries(templates)) {
      if (t.includes(key) || t === key) return { type: key, schedule: sched };
    }
    // Default generic template
    return { type: 'generic', schedule: [
      { time: '08:00', activity: 'Venue setup', owner: 'Organising team', notes: 'Equipment, signage, refreshments' },
      { time: '09:00', activity: 'Registration & welcome', owner: 'MC / Host', notes: 'Check-in, opening remarks' },
      { time: '09:30', activity: 'Main activity — Session 1', owner: 'Facilitator', notes: 'Core programme' },
      { time: '12:00', activity: 'Lunch break', owner: 'F&B coordinator', notes: '45-60 min' },
      { time: '13:00', activity: 'Main activity — Session 2', owner: 'Facilitator', notes: 'Continue programme' },
      { time: '15:00', activity: 'Interactive segment', owner: 'MC', notes: 'Audience engagement' },
      { time: '16:00', activity: 'Closing & awards', owner: 'MC', notes: 'Thank sponsors, wrap-up' },
      { time: '16:30', activity: 'Teardown', owner: 'Organising team', notes: 'Clean and pack' },
    ]};
  }

  function timeline() {
    const programme = state.pack.programme || state.pack.program || {};
    const runOfShow = array(first(programme.runOfShow, programme.timeline));
    const countdown = array(first(programme.countdown, programme.preEvent));
    const eventType = state.pack.goal?.eventType || '';
    const show = runOfShow.map((item) => typeof item === 'object' ? [esc(first(item.time, item.start, item.startTime, 'TBC')), esc(first(item.activity, item.title, item.task, item.name, 'Activity')), valueHTML(first(item.owner, item.role, item.responsible)), valueHTML(first(item.notes, item.description, item.durationMinutes != null ? `${item.durationMinutes} minutes \u00b7 ${item.status || 'Proposed'}` : undefined, item.duration, item.end))] : [missing(), esc(item), missing(), missing()]);
    const tasks = countdown.map((item) => typeof item === 'object' ? `<li class="timeline-item"><div class="timeline-time">${esc(first(item.label, item.when, item.daysBefore, item.date, item.time, item.deadline, 'TBC'))}</div><div class="timeline-copy"><strong>${esc(first(item.action, item.task, item.activity, item.title, item.name, 'Planning task'))}</strong><p>${esc([item.owner || item.responsible || 'Owner to confirm', item.date, item.status].filter(Boolean).join(' \u00b7 '))}</p></div></li>` : `<li class="timeline-item"><div class="timeline-time">Before event</div><div class="timeline-copy">${esc(item)}</div></li>`).join('');

    // Generate event-type-specific suggested run of show
    const suggested = suggestedRunOfShow(eventType);
    const suggestedRows = suggested.schedule.map((s) => [esc(s.time), esc(s.activity), esc(s.owner), esc(s.notes)]);
    const suggestedCard = card(`Suggested run of show for ${suggested.type === 'generic' ? 'this event' : suggested.type}`, table(['Time', 'Activity', 'Owner', 'Notes'], suggestedRows), true, 'This is a suggested timeline based on the event type. Edit it to fit your specific needs — times and owners are proposed until confirmed.');

    return `${callout('An editable operational plan', 'Times and owners are proposed until the organisers, venue and participants confirm them.', 'info')}<div class="content-grid">${card('Event-day run of show', table(['Time', 'Activity', 'Owner', 'Notes / duration'], show), true)}${suggestedCard}${card('Countdown to event day', tasks ? `<ol class="countdown-list">${tasks}</ol>` : missing('No countdown supplied'))}${card('Programme details', valueHTML(Object.fromEntries(Object.entries(programme).filter(([key]) => !['runOfShow', 'timeline', 'countdown', 'preEvent'].includes(key)))))}${state.pack.venues ? card('Venue options & operations', valueHTML(state.pack.venues), true, 'Venue suitability is a proposal; contact the campus team for availability and approval.') : ''}</div>`;
  }
  function budgetTab() {
    const b = state.pack.budget || {}, items = array(first(b.items, b.allocations));
    const amount = (item) => number(first(item.amountRM, item.totalRM, item.amount, item.costRM, item.total, item.cost));
    const total = first(b.total, b.totalRM, items.reduce((sum, item) => sum + (amount(item) || 0), 0));
    const limit = first(b.limit, b.limitRM, b.budgetRM, state.pack.goal?.budgetRM);
    const denominator = Math.max(1, Number(total) || 0, ...items.map((i) => amount(i) || 0));
    const bars = items.map((item) => `<div class="budget-bar"><div class="budget-bar-header"><span>${esc(first(item.category, item.name, item.item, 'Allocation'))}</span><strong>${esc(rm(amount(item)))}</strong></div><div class="budget-track"><div class="budget-fill" style="width:${Math.max(0, Math.min(100, (amount(item) || 0) / denominator * 100))}%"></div></div></div>`).join('');
    const rows = items.map((item) => [esc(first(item.category, item.name, item.item, 'Allocation')), esc(rm(amount(item))), valueHTML(first(item.quantity, item.qty)), valueHTML(first(item.basis, item.notes, item.description, item.rationale, item.assumption, item.status))]);
    return `${callout('Planning allocations \u2014 not vendor quotes', 'Every figure is in Malaysian ringgit (RM). Obtain real quotes before spending. Prospective sponsor support is unconfirmed and must not be treated as secured income.')}<div class="kpi-grid">${[['Budget limit', rm(limit)], ['Allocated total', rm(total)], ['Contingency', rm(first(b.contingencyRM, b.contingency?.amountRM, b.contingency?.amount, b.contingency))], ['Funding gap', rm(first(b.gapRM, b.gap?.amountRM, b.gap))]].map(([title, value]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value">${esc(value)}</div></div>`).join('')}</div><div class="content-grid">${card('Where the budget goes', bars ? `<div class="budget-bars">${bars}</div><p class="budget-legend">Bar widths show the share of the recorded allocation total.</p>` : missing('No allocations supplied'))}${card('Funding & guardrails', facts([['Organiser funds', typeof b.organiserFunds === 'object' ? b.organiserFunds : rm(first(b.organiserFundsRM, b.organiserFunds))], ['Sponsor support', first(b.sponsorship, b.sponsorFunds, 'Unconfirmed; no commitment implied')], ['Funding status', b.fundingStatus], ['Gap resolution', first(b.gapResolution, b.fundingPlan, b.notes, 'Verify organiser funds and secure written support; reduce spend if the gap remains.')], ['Contingency policy', first(b.contingencyPolicy, b.contingency?.notes, b.contingencyPercent != null ? `${b.contingencyPercent}% protected planning reserve` : undefined)], ['Scenario', b.scenario], ['Sponsor accounting', b.sponsorAccounting]]))}${card('Allocation breakdown', table(['Item / category', 'Allocation (RM)', 'Quantity', 'Basis / caveats'], rows), true)}</div><div class="excel-export"><h4>Export budget to Excel</h4><button class="button secondary" id="excel-export-btn" type="button">Download .xlsx \u2193</button><p class="excel-note">Downloads a spreadsheet you can open in Excel or Google Sheets.</p></div>`;
  }

  // === SIMPLIFIED WEATHER TAB ===
  function weatherTab() {
    const w = state.pack.weather || {}, risks = state.pack.risks || {};
    const forecast = w.mode === 'forecast';
    const rain = first(w.rainProbability, number(w.probability) == null ? undefined : `${Math.round(Number(w.probability) * 100)}%`);
    const sampleYears = array(first(w.sampleYears, w.years));
    const validYears = sampleYears.map(Number).filter(Number.isFinite);
    const sampled = validYears.length ? `${Math.min(...validYears)}\u2013${Math.max(...validYears)}` : 'Not available';

    // Calculate rain-risk level
    let rainPct = 0;
    if (typeof rain === 'number') rainPct = rain;
    else if (typeof rain === 'string' && rain.endsWith('%')) rainPct = Number(rain.slice(0, -1));
    else if (number(w.probability) != null) rainPct = Math.round(number(w.probability) * 100);

    let riskLevel = 'Low', riskClass = 'low', riskRec = 'Outdoor plan is reasonable; monitor forecast closer to the date.';
    if (rainPct >= 40) { riskLevel = 'High'; riskClass = 'high'; riskRec = 'Plan an indoor backup venue.'; }
    else if (rainPct >= 20) { riskLevel = 'Medium'; riskClass = 'medium'; riskRec = 'Consider a covered venue or have an indoor backup.'; }
    if (w.indoorRequired) { riskLevel = 'High'; riskClass = 'high'; riskRec = 'Plan an indoor backup venue.'; }

    // Date for weather
    const chosen = state.pack.dateDecision?.chosen;
    const eventDate = typeof chosen === 'string' ? chosen : first(chosen?.date, chosen?.label, chosen?.dateISO, w.date);

    // Simplified key info
    const summaryHTML = `
      <div class="content-grid">
        ${card('Rain risk for proposed date', `
          <div class="weather-summary">
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
              ${eventDate ? `<div class="weather-number">${esc(eventDate)}</div>` : missing('No date selected')}
              <span class="rain-risk ${riskClass}"><span class="dot"></span>${riskLevel}</span>
            </div>
            <p class="weather-rec">${esc(riskRec)}</p>
            <p class="weather-disclaimer-short">${esc(forecast ? 'Near-term forecast evidence \u2014 not a guarantee; recheck before the event.' : 'Historical climatology, not a forecast \u2014 review sample size and years.')}</p>
          </div>
        `)}
      </div>`;

    // Full evidence behind toggle (all existing content preserved)
    const fullEvidence = `
      <div class="kpi-grid">${[['Rain measure', rain == null ? 'Unavailable' : `${rain}${typeof rain === 'number' ? '%' : ''}`, forecast ? 'Source forecast probability; not a guarantee' : 'Observed historical frequency; not a forecast'], ['Historical samples', first(w.sampleCount, 'Unavailable'), 'Missing observations are not filled'], ['Sample years', sampled, 'Actual reported year coverage'], ['Plan B', w.indoorRequired ? 'Indoor required' : 'Check evidence', 'Venue approval remains unconfirmed']].map(([title, value, note]) => `<div class="kpi"><div class="kpi-label">${esc(title)}</div><div class="kpi-value">${esc(value)}</div><div class="kpi-note">${esc(note)}</div></div>`).join('')}</div>
      <div class="content-grid">
        ${card('Weather interpretation & uncertainty', facts([['Evidence mode', w.mode], ['Event date', w.date], ['Source location', first(w.locationEvidence, w.location)], ['Average rainfall', w.precipitationMm != null ? `${w.precipitationMm} mm` : null], ['Average maximum temperature', w.avgTempMax != null ? `${w.avgTempMax} \u00b0C` : null], ['Decision', w.decision], ['Uncertainty', w.uncertainty], ['Warnings', w.warnings]]))}
        ${card('Weather citations & rechecks', `${sources(w)}${facts([['Proposed thresholds', w.threshold], ['Reasoning', w.rationale], ['Next checks', first(w.recheck, w.recheckStatus, 'T-14 / T-7 / T-1 checks are pending; no automated notification is claimed')]])}`)}
        ${(array(w.samples)).length ? card('Actual observed sample rows', table(['Sample date', 'Rain (mm)', 'Max temp (\u00b0C)', 'Mean temp (\u00b0C)'], (array(w.samples)).map((s) => [esc(first(s.date, 'Unknown date')), esc(first(s.precipitationMm, 'Unavailable')), esc(first(s.tempMaxC, 'Unavailable')), esc(first(s.tempMeanC, 'Unavailable'))])), true) : ''}
        ${card('Risk register & mitigations', (() => { const rows = array(risks.register).map((r) => [esc(first(r.risk, r.name, 'Risk')), esc(first(r.score, '\u2014')), esc(first(r.mitigation, 'Pending')), esc(first(r.trigger, 'Pending')), esc(first(r.contingency, 'Pending')), esc(first(r.owner, 'Unassigned'))]); return rows.length ? table(['Risk', 'L \u00d7 I', 'Mitigation', 'Trigger', 'Contingency', 'Owner'], rows) : valueHTML(risks); })(), true, first(risks.scale, 'Risk scores are planner assessments, not empirical event probabilities.'))}
        ${risks.planB ? card('Plan B playbooks', valueHTML(risks.planB), true) : ''}
        ${card('Pending weather & operational rechecks', valueHTML(state.pack.rechecks), true)}
      </div>`;

    return `${summaryHTML}<details class="weather-toggle"><summary>See full weather evidence</summary><div style="padding:8px 14px 14px">${fullEvidence}</div></details>`;
  }

  function peopleTab() {
    const p = state.pack.people || {};
    const rows = array(first(p.roster, p.members)).map((m) => [esc(first(m.name, 'Name not supplied')), esc(first(m.role, 'Unassigned')), valueHTML(m.freeDates), `${badge(m.demo ? 'Demo only' : first(m.availabilityStatus, 'Unconfirmed'), 'warning')}<br>${esc(m.availableOnProposedDate === true ? 'Listed free on proposed date' : m.availableOnProposedDate === false ? 'Not listed free on proposed date' : 'Availability unknown')}`, esc(first(m.experienceScore, 'Not supplied'))]);
    return `${callout('Availability is not assumed', 'Only an authorised supplied roster can establish stated availability. Suggested roles, student MCs and named demo entries are proposals, not confirmed participants. Private roster names and emails are redacted in the public pack; role aliases preserve the availability comparison.')}<div class="content-grid">${card('Preferred MC \u00b7 not booked', p.topMC ? valueHTML(p.topMC) : missing('Supply an authorised MC roster to shortlist a real host.'))}${card('Backup MC \u00b7 not booked', p.backupMC ? valueHTML(p.backupMC) : missing('No backup MC supplied or eligible.'))}${card('Organiser-supplied availability', rows.length ? table(['Public role alias', 'Role', 'Listed free dates', 'Availability caveat', 'Experience score'], rows) : missing('No roster supplied. No demo or real person is automatically assumed.'), true)}${card('Selection & confirmation rules', facts([['Availability status', p.availabilityStatus], ['Selection rule', p.selectionRule], ['Booking confirmed', p.bookingConfirmed], ['Demo data present', p.demo], ['Next actions', first(p.rechecks, p.pendingChecks, p.availabilityNotes, 'Ask organisers and MCs to confirm their availability and responsibilities.')]]), true)}</div>`;
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
    const sponsorsHTML = sponsorsList.length ? sponsorsList.map((s) => card(first(s.name, s.company, s.brand, 'Potential partner'), `<div class="badge-group">${badge('Potential sponsor \u00b7 unconfirmed', 'warning')}${s.confidence ? badge(s.confidence, 'info') : ''}</div>${facts([['Fit / rationale', first(s.fit, s.rationale, s.reason, s.why)], ['Proposed ask', first(s.ask, s.proposedAsk, s.askRM != null ? rm(s.askRM) : undefined, s.supportType, s.offer)], ['Alternative tiers', s.tiers], ['Contact status', first(s.contactStatus, s.contact?.status, s.contactVerified ? 'Source-verified contact \u2014 review before outreach' : 'Email needed \u2014 use the official contact page')], ['Contact route', s.contactType], ['Evidence', first(s.evidence, s.sourceNotes, s.verifiedFacts, s.fitStatus)], ['Accounting', s.accounting]])}${sources(s)}`, false)).join('') : card('Sponsor research', valueHTML(sponsorValue), true);
    const drafts = draftItems();
    const draftsHTML = drafts.map((d, index) => `<article class="draft-card"><h4>${esc(first(d.recipient, d.sponsor, d.company, d.name, d.title, `Outreach draft ${index + 1}`))}</h4><div class="badge-group">${badge('Draft only \u2014 never sent', 'info')}${d.type ? badge(label(d.type), 'info') : ''}${d.demo ? badge('Fictional demo recipient', 'warning') : ''}${!first(d.to, d.recipientEmail) ? badge('Recipient email needed', 'warning') : ''}</div>${facts([['Recipient', first(d.to, d.recipientEmail, 'Blank \u2014 verify an official email first')], ['Subject', first(d.subject, 'Event partnership enquiry')], ...(d.condition ? [['Use only when', d.condition]] : []), ...(d.sendAfterDays != null ? [['Suggested follow-up', `${d.sendAfterDays} days after a manually reviewed initial message`]] : [])])}${sources(d)}<div class="draft-body">${esc(first(d.body, d.text, d.message, 'No message body supplied.'))}</div><div class="draft-actions"><a class="button secondary" href="${esc(gmailURL(d))}" target="_blank" rel="noopener noreferrer">Open Gmail compose \u2197</a><button class="text-button" data-copy-draft="${index}">Copy draft</button><a class="text-button" href="/api/runs/${encodeURIComponent(state.id)}/eml/${index}">Download .eml \u2193</a></div></article>`).join('');
    return `${callout('Prospective partnerships, not secured sponsorship', 'Source citations establish public information only. Contact channels need verification; no email address is guessed. Compose links may leave the recipient blank. Nothing is sent automatically.')}<div class="content-grid">${sponsorsHTML}</div><div class="mini-separator"></div>${gmailReceiptHTML()}<div class="gmail-banner"><div><strong>Create Gmail drafts \u2014 you keep the final say.</strong><p class="sources-note">Saved run metrics: ${esc(first(state.pack.metrics?.gmailDraftsCreated, state.metrics?.gmailDraftsCreated, 0))} confirmed Gmail drafts \u00b7 ${esc(first(state.pack.metrics?.emailsSent, state.metrics?.emailsSent, 0))} emails sent. Only eligible non-demo recipients are attempted, at most 24 draft indexes per request.</p><p id="gmail-help">${state.clientId ? 'Connect Google in a popup to authorise gmail.compose only. The app creates drafts, never sends mail.' : 'Google OAuth is not configured. The button explains the fallback: Gmail compose, copy text, or .eml download. No account connection is pretended.'}</p></div><button class="button primary" id="gmail-drafts" ${state.gmailBusy ? 'disabled' : ''}>${state.gmailBusy ? 'Creating drafts\u2026' : 'Create Gmail drafts \u2197'}</button></div>${draftsHTML ? `<div class="draft-grid">${draftsHTML}</div>` : empty('No outreach drafts supplied', 'Sponsor facts may be available, but no email text was included in this saved pack.')}`;
  }
  function promoTab() {
    const promo = state.pack.promo;
    const entries = Array.isArray(promo) ? array(promo) : array(first(promo?.posts, promo?.captions, promo?.assets, promo?.items));
    if (!entries.length) return `<div class="content-grid">${card('Promotion plan & ready-to-edit copy', valueHTML(promo), true, 'Verify final venue, date, links and partner permission before posting. Nothing is published automatically.')}</div>`;
    return `${callout('Ready to edit. Not automatically published.', 'Confirm the final date, venue, registration link and any sponsor branding permissions before posting.', 'info')}<div class="content-grid">${promo?.poster ? card('Poster copy & details', valueHTML(promo.poster), true) : ''}${entries.map((entry, index) => card(typeof entry === 'string' ? `Ready-to-edit caption ${index + 1}` : first(entry.channel, entry.platform, entry.title, entry.name, 'Promotion asset'), typeof entry === 'string' ? `<div class="draft-body">${esc(entry)}</div>` : `${facts([['Audience', entry.audience], ['When', first(entry.when, entry.date, entry.timing)], ['Call to action', first(entry.cta, entry.callToAction)]])}<div class="draft-body">${esc(first(entry.copy, entry.text, entry.caption, entry.body, entry.message, 'No copy supplied.'))}</div>${sources(entry)}`)).join('')}${!Array.isArray(promo) ? card('Promotion schedule & guardrails', valueHTML(Object.fromEntries(Object.entries(promo || {}).filter(([key]) => !['posts', 'captions', 'assets', 'items', 'poster'].includes(key)))), true) : ''}</div>`;
  }
  function exportTab() {
    return `${callout('Saved, shareable, and still subject to confirmation', 'The run link shows the Event Pack and actual execution trace without login. Roster email addresses and OAuth tokens must not appear in shared packs. PDF and email drafts are exports, not bookings or sent messages.', 'info')}<div class="export-grid"><section class="export-option"><h3>A readable event pack</h3><p>Download the structured plan as a PDF for organiser handover and review.</p><a class="button primary" href="/api/runs/${encodeURIComponent(state.id)}/pdf">Download Event Pack PDF \u2193</a></section><section class="export-option proposal-export"><h3>Generate proposal (PDF)</h3><p>Produces a formatted proposal document with event summary, date, venue, budget, risk plan, and next actions.</p><a class="button primary" href="/api/runs/${encodeURIComponent(state.id)}/proposal">Generate proposal PDF \u2193</a><p class="proposal-note">This is a draft for your review. EventPilot never sends anything automatically \u2014 review and send it yourself.</p></section><section class="export-option"><h3>Export budget to Excel</h3><p>Download the full budget breakdown with category totals, ceiling, contingency, and funding gap as a spreadsheet.</p><button class="button primary" id="export-excel-btn">Download .xlsx \u2193</button><p class="proposal-note">Downloads a spreadsheet you can open in Excel or Google Sheets.</p></section><section class="export-option"><h3>Share the saved run</h3><p>Read-only plan, sources and genuine specialist trace. No login required.</p><button class="button secondary" data-copy-link>Copy run link \u2197</button></section><section class="export-option"><h3>Outreach drafts, not sent mail</h3><p>Gmail compose, clipboard copy and individual .eml exports are available under Sponsors / Gmail.</p><button class="button secondary" data-open-sponsors>Review draft emails \u2192</button></section><section class="export-option"><h3>Inspect real recorded execution</h3><p>Replay preserves recorded tool results and identifies itself as a replay, not new research.</p><button class="button secondary" data-replay>Replay recorded run \u2192</button></section></div>${card('Validation before handover', valueHTML(state.pack.validation), true)}`;
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
    if (!$('prompt').value.trim()) $('prompt').value = `Plan ${first(g.eventType, 'a campus event')} at ${first(g.campus, 'Taylor\u2019s Lakeside Campus')} for ${first(g.attendance, 120)} attendees. Purpose: ${first(g.cause, 'student engagement')}. Use the editable planning assumptions below; all commitments require confirmation.`;
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
    const rows = [...receipts.map((receipt) => [esc(receipt.index), esc(receipt.alreadyCreated ? receipt.contentChanged ? 'Existing draft \u2014 content changed; review manually' : 'Existing draft \u2014 no duplicate created' : 'New draft receipt confirmed'), esc(first(receipt.subject, 'Review in Gmail'))]), ...errors.map((error) => [esc(first(error.index, 'Request')), badge('Failed / review required', 'error'), esc(first(error.error, error.message, 'Use compose, copy or .eml fallback.'))])];
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

  // === EVENT LISTENERS ===
  $('workflow-toggle').addEventListener('click', () => {
    const expanded = $('workflow-toggle').getAttribute('aria-expanded') !== 'true';
    $('workflow-toggle').setAttribute('aria-expanded', String(expanded));
    $('workflow-toggle').setAttribute('aria-label', `${expanded ? 'Collapse' : 'Expand'} specialist workflow`);
    $('workflow-content').hidden = !expanded;
  });
  $('run-form').addEventListener('submit', (event) => { event.preventDefault(); startRun(); });
  document.querySelectorAll('[data-example]').forEach((button) => button.addEventListener('click', () => { $('prompt').value = examples[button.dataset.example]; showPromptPreview(); $('prompt').focus(); }));
  $('prompt').addEventListener('input', () => { clearTimeout(window._promptTimer); window._promptTimer = setTimeout(showPromptPreview, 400); });
  // Remove auto-fill marker when user manually edits a form field
  document.querySelectorAll('.field-grid input').forEach((input) => { input.addEventListener('input', () => { input.removeAttribute('data-autofilled'); }); });
  $('run-example').addEventListener('click', () => { $('prompt').value = examples.canonical; showPromptPreview(); document.querySelectorAll('.field-grid input').forEach((input) => { input.value = ''; }); $('roster').value = ''; state.demo = false; updateRosterStatus(); startRun(); });
  $('replay-button').addEventListener('click', () => startRun('replay'));
  $('sample-roster').addEventListener('click', () => { state.demo = true; $('roster').value = 'name,role,freeDates,email\nDemo organiser,Organiser,2026-11-07;2026-11-14;2026-11-21,\nDemo MC,MC,2026-11-14;2026-11-21,\nDemo volunteer,Volunteer,2026-11-07;2026-11-21,'; updateRosterStatus(); });
  $('roster').addEventListener('input', () => { state.demo = $('roster').value.includes('Demo organiser'); updateRosterStatus(); });

  // === TOOLS DROPDOWN ===
  const toolsBtn = $('tools-toggle');
  const toolsMenu = $('tools-menu');
  if (toolsBtn && toolsMenu) {
    toolsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = toolsMenu.classList.toggle('open');
      toolsBtn.setAttribute('aria-expanded', String(isOpen));
    });
    toolsMenu.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-tool]');
      if (!btn) return;
      toolsMenu.classList.remove('open');
      toolsBtn.setAttribute('aria-expanded', 'false');
      const tool = btn.dataset.tool;
      if (tool === 'canonical') { $('prompt').value = examples.canonical; showPromptPreview(); document.querySelectorAll('.field-grid input').forEach((input) => { input.value = ''; }); $('roster').value = ''; state.demo = false; updateRosterStatus(); startRun(); }
      else if (tool === 'replay') startRun('replay');
      else if (tool === 'roster') { state.demo = true; $('roster').value = 'name,role,freeDates,email\nDemo organiser,Organiser,2026-11-07;2026-11-14;2026-11-21,\nDemo MC,MC,2026-11-14;2026-11-21,\nDemo volunteer,Volunteer,2026-11-07;2026-11-21,'; updateRosterStatus(); notice('Demo roster loaded. Names and emails are redacted in the public pack.'); }
      else if (tool === 'excel') { if (state.pack) { selectTab('Budget'); setTimeout(exportBudgetExcel, 100); } else notice('Run a plan first to export the budget.'); }
      else if (tool === 'proposal') { if (state.pack && state.id) { window.open(`/api/runs/${encodeURIComponent(state.id)}/proposal`, '_blank'); } else notice('Run a plan first to generate a proposal.'); }
    });
    document.addEventListener('click', (e) => {
      if (!toolsMenu.contains(e.target) && e.target !== toolsBtn) {
        toolsMenu.classList.remove('open');
        toolsBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }
  $('copy-link').addEventListener('click', copyRunLink); $('edit-rerun').addEventListener('click', editRerun);
  $('tabs').addEventListener('click', (event) => { const button = event.target.closest('[data-tab]'); if (button) selectTab(button.dataset.tab); });
  $('tabs').addEventListener('keydown', (event) => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const current = tabs.indexOf(state.tab); const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; selectTab(tabs[index]); $(`tab-${index}`).focus(); });
  $('tab-content').addEventListener('click', (event) => {
    const button = event.target.closest('button'); if (!button) {
      const link = event.target.closest('a'); if (!link) return;
      // Let proposal/excel links work natively
      return;
    }
    if (button.id === 'gmail-drafts') createGmailDrafts();
    else if (button.id === 'excel-export-btn') exportBudgetExcel();
    else if (button.id === 'export-excel-btn') exportBudgetExcel();
    else if (button.hasAttribute('data-copy-link')) copyRunLink();
    else if (button.hasAttribute('data-open-sponsors')) selectTab('Sponsors / Gmail');
    else if (button.hasAttribute('data-replay')) startRun('replay');
    else if (button.hasAttribute('data-copy-draft')) { const d = draftItems()[Number(button.dataset.copyDraft)]; if (d) copyText(`To: ${first(d.to, d.recipientEmail, '[verify recipient email]')}\nSubject: ${first(d.subject, 'Event partnership enquiry')}\n\n${first(d.body, d.text, d.message, '')}`, 'Draft copied. No message was sent. Verify the recipient before using it.'); }
  });
  window.addEventListener('popstate', () => { const match = location.pathname.match(/^\/run\/([^/]+)\/?$/); closeStream(); if (match) loadRun(decodeURIComponent(match[1])).catch((error) => notice(error.message, true)); else { state.id = null; state.pack = null; state.trace = []; state.replay = false; $('results').hidden = true; $('empty-results').hidden = false; setBusy(false); runStatus('idle'); renderTrace(); } });
  renderDAG();
  request('/api/config').then((config) => {
    state.clientId = config.googleClientId || '';
    state.configLoaded = true;
    state.llmEnabled = !!config.llmEnabled;
    if (state.clientId) loadGoogleLibrary().catch(() => {});
    // Update engine banner based on LLM availability
    if (state.llmEnabled) {
      $('engine-description').textContent = 'AI-powered prompt interpretation is active. The LLM interprets your brief; deterministic specialist tools execute the plan.';
    } else {
      $('engine-description').textContent = 'LLM is not configured. This build uses a deterministic specialist runtime with real tool results.';
    }
    if (state.pack && state.tab === 'Sponsors / Gmail') renderContent();
  }).catch(() => { state.configLoaded = true; $('engine-description').textContent = 'LLM is not configured. This build uses a deterministic specialist runtime with real tool results.'; });
  const saved = location.pathname.match(/^\/run\/([^/]+)\/?$/);
  if (saved) loadRun(decodeURIComponent(saved[1])).catch((error) => { setBusy(false); runStatus('failed'); notice(`Could not load the saved run. ${error.message}`, true); });
})();
