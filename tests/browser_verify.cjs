'use strict';
let playwright;
try { playwright = require('playwright-core'); }
catch { playwright = require(process.env.EVENTPILOT_PLAYWRIGHT_PATH || 'C:/Users/HP Victus/.workbuddy-ai/binaries/node/workspace/node_modules/playwright-core'); }
const { chromium } = playwright;
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'outputs');
const base = process.env.EVENTPILOT_TEST_URL || 'http://127.0.0.1:3000';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.EVENTPILOT_CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  const errors = [];
  const evidence = { base, checkedAt: new Date().toISOString(), checks: [], screenshots: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.locator('#run-example').waitFor();
    await page.screenshot({ path: path.join(out, 'eventpilot-home-desktop.png') });
    evidence.screenshots.push('eventpilot-home-desktop.png');
    const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/runs') && r.request().method() === 'POST');
    await page.locator('#run-example').click();
    const response = await responsePromise;
    assert.strictEqual(response.status(), 202);
    const created = await response.json();
    evidence.runId = created.id;
    await page.waitForFunction(() => !document.getElementById('results').hidden || document.getElementById('run-status').classList.contains('failed'), null, { timeout: 120000 });
    if (await page.locator('#results').evaluate(el => el.hidden)) {
      const failedRun = await (await page.request.get(`${base}/api/runs/${created.id}`)).json();
      fs.writeFileSync(path.join(out, 'browser-failure-evidence.json'), JSON.stringify({ ...failedRun, browserNotice: await page.locator('#notice').innerText() }, null, 2));
      throw new Error('Actual run failed: ' + (failedRun.error || 'see saved failure evidence'));
    }
    const run = await (await page.request.get(`${base}/api/runs/${created.id}`)).json();
    assert.strictEqual(run.status, 'complete');
    assert.strictEqual(run.pack.goal.prompt, 'I want to organize a charity event at my university in March with a budget of RM2k.');
    assert.strictEqual(run.pack.budget.totalCents, 200000);
    assert.strictEqual(run.pack.people.roster.length, 0);
    assert.strictEqual(run.pack.validation.passed, true);
    assert.strictEqual(run.pack.validation.ready, false);
    assert.strictEqual(run.pack.metrics.llmCalls, 0);
    assert.strictEqual(run.pack.metrics.emailsSent, 0);
    assert(run.trace.some(e => /replan|re-plan/.test(e.status + ' ' + e.tool)));
    evidence.checks.push('Actual canonical click, POST, SSE completion and saved-pack assertions passed');
    evidence.metrics = run.pack.metrics;
    evidence.chosenDate = run.pack.dateDecision.chosen.date;
    await page.evaluate(() => window.scrollTo(0, document.getElementById('results').getBoundingClientRect().top + scrollY - 12));
    await page.screenshot({ path: path.join(out, 'eventpilot-pack-desktop.png') });
    evidence.screenshots.push('eventpilot-pack-desktop.png');
    for (const name of ['Overview', 'Date Decision', 'Timeline', 'Budget', 'Risk / Weather', 'People / MCs', 'Sponsors / Gmail', 'Promo', 'Export']) {
      await page.getByRole('tab', { name, exact: true }).click();
      const text = await page.locator('#tab-content').innerText();
      assert(text.length > 80, name + ' has no substantive content');
      assert(!/NaN|\[object Object\]/.test(text), name + ' has invalid rendered values');
      if (name === 'Sponsors / Gmail') {
        await page.locator('#gmail-drafts').click();
        await page.locator('#notice').waitFor({ state: 'visible' });
        assert((await page.locator('#notice').innerText()).includes('not configured'));
        evidence.checks.push('Unconfigured Google OAuth visibly falls back without claiming draft creation');
      }
      if (['Budget', 'Risk / Weather', 'Sponsors / Gmail'].includes(name)) {
        await page.evaluate(() => window.scrollTo(0, document.getElementById('results').getBoundingClientRect().top + scrollY - 12));
        const filename = 'eventpilot-' + name.toLowerCase().replace(/[^a-z]+/g, '-') + '-desktop.png';
        await page.screenshot({ path: path.join(out, filename) });
        evidence.screenshots.push(filename);
      }
      evidence.checks.push(name + ' rendered successfully');
    }
    const pdf = await page.request.get(`${base}/api/runs/${created.id}/pdf`);
    assert.strictEqual(pdf.status(), 200);
    const bytes = await pdf.body();
    assert(bytes.subarray(0, 5).toString() === '%PDF-');
    fs.writeFileSync(path.join(out, 'EventPilot-Canonical-Event-Pack.pdf'), bytes);
    const eml = await page.request.get(`${base}/api/runs/${created.id}/eml/0`);
    assert.strictEqual(eml.status(), 200);
    assert((await eml.text()).includes('sponsorship@printcious.com'));
    fs.writeFileSync(path.join(out, 'EventPilot-Printcious-Draft.eml'), await eml.body());
    evidence.checks.push('PDF and sourced .eml exported successfully');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#results').waitFor({ state: 'visible' });
    evidence.checks.push('Saved run reloaded from SQLite');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    const width = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, viewport: innerWidth }));
    assert(width.content <= width.viewport + 1, 'Mobile home has horizontal overflow');
    await page.screenshot({ path: path.join(out, 'eventpilot-home-mobile.png'), fullPage: true });
    evidence.screenshots.push('eventpilot-home-mobile.png');
    await page.goto(`${base}/run/${created.id}`, { waitUntil: 'domcontentloaded' });
    await page.locator('#results').waitFor({ state: 'visible' });
    await page.evaluate(() => window.scrollTo(0, document.getElementById('results').getBoundingClientRect().top + scrollY - 12));
    await page.screenshot({ path: path.join(out, 'eventpilot-pack-mobile.png') });
    evidence.screenshots.push('eventpilot-pack-mobile.png');
    evidence.checks.push('390px mobile home has no horizontal overflow and saved pack renders');
    assert.deepStrictEqual(errors, [], 'Browser JavaScript errors occurred');
    evidence.checks.push('No browser JavaScript errors');
    fs.writeFileSync(path.join(out, 'canonical-run-evidence.json'), JSON.stringify({ ...run, browser: evidence }, null, 2));
    console.log(JSON.stringify(evidence, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
