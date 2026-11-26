#!/usr/bin/env python3
"""Headless UI smoke test of the NEXORA founder console (jsdom via Node)."""
import json, subprocess, sys

SCRIPT = r'''
import { JSDOM, VirtualConsole } from 'jsdom';
const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const results = [];
const check = (name, ok, detail='') => { results.push(ok); console.log(`${ok?'PASS':'FAIL'}  ${name}${detail?' — '+detail:''}`); };

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if (!/scrollTo|Could not load/.test(e.message)) errors.push(e.message); });
vc.on('error', (...a) => errors.push(a.join(' ')));

const html = await (await fetch(BASE + '/')).text();
const dom = new JSDOM(html, {
  url: BASE + '/', runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, virtualConsole: vc,
  beforeParse(window) {
    window.fetch = (input, init) => fetch(new URL(String(input), BASE), init);
    window.scrollTo = () => {};
    window.confirm = () => true;
  },
});
const { window } = dom;
await new Promise(r => window.addEventListener('load', r));
await new Promise(r => setTimeout(r, 2500));
const doc = window.document;

check('console shell renders', Boolean(doc.querySelector('.sidebar')));
check('model status resolved', !doc.getElementById('modelState').textContent.includes('…'), doc.getElementById('modelState').textContent);
check('project list populated', doc.querySelectorAll('#projectList [data-project]').length >= 1,
  `${doc.querySelectorAll('#projectList [data-project]').length} projects`);
check('AI employee directory populated', doc.querySelectorAll('#agentGrid .agent-card').length >= 10,
  `${doc.querySelectorAll('#agentGrid .agent-card').length} agents`);

// open the workspace view for the first project
doc.querySelector('#projectList [data-project]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await new Promise(r => setTimeout(r, 2500));
const wsRoot = doc.getElementById('workspaceRoot');
check('workspace view renders dashboard', Boolean(wsRoot.querySelector('.progress-fill')), '');
check('pipeline strip present', wsRoot.querySelectorAll('.pipeline-step').length >= 10,
  `${wsRoot.querySelectorAll('.pipeline-step').length} steps`);
check('file explorer lists files', wsRoot.querySelectorAll('#fileTree [data-path]').length >= 20,
  `${wsRoot.querySelectorAll('#fileTree [data-path]').length} files`);
check('development log shows agent events', wsRoot.querySelectorAll('#devLog .entry').length >= 3,
  `${wsRoot.querySelectorAll('#devLog .entry').length} events`);
check('build output panel shows real command output', (wsRoot.querySelector('.code-block')?.textContent || '').includes('npm'),
  '');

// open a real source file
const fileBtn = [...wsRoot.querySelectorAll('#fileTree [data-path]')].find(b => b.dataset.path.endsWith('schema.sql'));
check('found schema.sql in the tree', Boolean(fileBtn));
if (fileBtn) {
  fileBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 1200));
  const viewer = doc.getElementById('sourceBody');
  check('source viewer shows real SQL', (viewer.textContent || '').includes('CREATE TABLE'), '');
  check('source viewer marks line metadata', (doc.getElementById('sourceMeta').textContent || '').toLowerCase().includes('lines'), '');
}

// approvals view
doc.querySelector('[data-nav="approvals"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
await new Promise(r => setTimeout(r, 1800));
check('approvals view lists checkpoints', doc.querySelectorAll('#approvalRoot .approval-card').length >= 5,
  `${doc.querySelectorAll('#approvalRoot .approval-card').length} checkpoints`);
check('approval actions available for pending gate', doc.querySelectorAll('#approvalRoot [data-approve]').length >= 1, '');

check('no fatal script errors', errors.length === 0, errors.slice(0,2).join(' | '));
const failed = results.filter(r => !r).length;
console.log(`\n${results.length - failed}/${results.length} UI checks passed`);
dom.window.close();
process.exit(failed ? 1 : 0);
'''

open('/tmp/uismoke/nexora_ui_smoke.mjs', 'w').write(SCRIPT)
result = subprocess.run(['node', '/tmp/uismoke/nexora_ui_smoke.mjs'], cwd='/tmp/uismoke',
                        capture_output=True, text=True, timeout=180)
print(result.stdout)
print(result.stderr[-2000:] if result.returncode else '')
sys.exit(result.returncode)
