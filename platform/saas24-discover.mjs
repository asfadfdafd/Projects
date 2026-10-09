#!/usr/bin/env node
// Read-only discovery of a BILLmanager account (24saas.kz cabinet).
//
// It answers the questions the docs cannot: which API functions this account
// may call, which tariff/datacenter/OS/addon ids exist, and what the service
// list actually looks like.
//
// SAFETY: every request here is a read. No request carries `sok=ok`, which is
// what BILLmanager requires to apply a change, so nothing can be ordered,
// edited or deleted by running this.
//
//   SAAS24_BILLMGR_USER=you@example.kz \
//   SAAS24_BILLMGR_PASSWORD='...' \
//   node scripts/saas24-discover.mjs
//
// Writes raw responses to ./saas24-report/<timestamp>/ and prints a summary.
// The raw dumps contain account data — do not commit them.

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.SAAS24_BILLMGR_URL ?? 'https://cabinet.24saas.kz/billmgr';
const USER = process.env.SAAS24_BILLMGR_USER;
const PASSWORD = process.env.SAAS24_BILLMGR_PASSWORD;

if (!USER || !PASSWORD) {
  console.error('Set SAAS24_BILLMGR_USER and SAAS24_BILLMGR_PASSWORD.');
  process.exit(2);
}

const outDir = path.join(
  process.cwd(),
  'saas24-report',
  new Date().toISOString().replace(/[:.]/g, '-'),
);

/** POST a BILLmanager call. Never pass sok here — this tool is read-only. */
async function call(params, { format = 'json' } = {}) {
  const body = new URLSearchParams({ ...params, out: format });
  if (params.sok) throw new Error('refusing to send sok=ok from the read-only tool');
  const res = await fetch(BASE, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
    redirect: 'follow',
  });
  const text = await res.text();
  return { httpStatus: res.status, text };
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** BILLmanager reports errors inside the body, often with HTTP 200. */
function errorOf(doc, text) {
  const err = doc?.doc?.error ?? doc?.error;
  if (err) return err.$type ?? err.type ?? err.msg?.$ ?? JSON.stringify(err).slice(0, 200);
  if (!doc && /<error/i.test(text)) return (text.match(/type="([^"]+)"/) ?? [, 'unknown'])[1];
  return null;
}

async function save(name, text) {
  await writeFile(path.join(outDir, `${name}.txt`), text, 'utf8');
}

async function authenticate() {
  const { text } = await call({ func: 'auth', username: USER, password: PASSWORD }, { format: 'xml' });
  await save('00-auth', text);
  const id = (text.match(/<auth[^>]*id="([^"]+)"/) ?? text.match(/<auth[^>]*>([^<]+)</) ?? [])[1];
  if (!id) throw new Error(`no session id in auth response; see ${outDir}/00-auth.txt`);
  return id;
}

/** Functions worth probing. Each is a plain read. */
const PROBES = [
  ['vds', { func: 'vds' }, 'virtual servers owned by this account'],
  ['vds-active', { func: 'vds', filter: 'on', status: '2' }, 'active services only'],
  ['dedic', { func: 'dedic' }, 'dedicated servers'],
  ['vhost', { func: 'vhost' }, 'shared hosting'],
  ['order-form-vds', { func: 'v2.vds.order.param' }, 'ORDER FORM: pricelist / datacenter / ostempl / recipe / addons'],
  ['pricelist', { func: 'pricelist' }, 'tariff plans (may be admin-only)'],
  ['datacenter', { func: 'datacenter' }, 'data centers (may be admin-only)'],
  ['payment', { func: 'payment' }, 'payments — tells us how balance is reported'],
  ['account', { func: 'account' }, 'account info (may be admin-only)'],
  ['profile', { func: 'profile' }, 'payer profiles'],
  ['paymethod', { func: 'paymethod' }, 'payment methods, for paymethod_id'],
  ['service', { func: 'service' }, 'all services, any product type'],
];

/** Pull every option list out of a form response, whatever the shape. */
function collectOptions(doc) {
  const found = {};
  const walk = (node, keyHint) => {
    if (node == null || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item, keyHint);
      return;
    }
    const name = node.$name ?? node.name;
    const values = node.val ?? node.value ?? node.elem;
    if (name && values) {
      const list = (Array.isArray(values) ? values : [values])
        .map((v) => ({
          key: v?.$key ?? v?.key ?? v?.$value ?? v?.value,
          label: typeof v?.$ === 'string' ? v.$ : (v?.msg?.$ ?? v?.name ?? undefined),
        }))
        .filter((v) => v.key !== undefined);
      if (list.length) found[name] = list;
    }
    for (const [k, v] of Object.entries(node)) walk(v, k);
  };
  walk(doc, '');
  return found;
}

const summary = [];

async function main() {
  await mkdir(outDir, { recursive: true });
  console.log(`BILLmanager: ${BASE}`);

  const auth = await authenticate();
  console.log('auth: ok, session acquired\n');

  for (const [name, params, note] of PROBES) {
    const { httpStatus, text } = await call({ ...params, auth });
    await save(name, text);
    const doc = parseJson(text);
    const err = errorOf(doc, text);
    const elems = doc?.doc?.elem ?? doc?.elem;
    const count = Array.isArray(elems) ? elems.length : elems ? 1 : null;
    const verdict = err ? `ERROR (${err})` : count !== null ? `ok, ${count} rows` : 'ok';
    summary.push({ name, func: params.func, httpStatus, verdict, note });
    console.log(`${name.padEnd(16)} ${verdict.padEnd(24)} ${note}`);

    if (name === 'order-form-vds' && !err && doc) {
      const options = collectOptions(doc);
      await writeFile(
        path.join(outDir, 'order-form-options.json'),
        JSON.stringify(options, null, 2),
        'utf8',
      );
      const interesting = ['pricelist', 'datacenter', 'ostempl', 'recipe', 'order_period'];
      console.log('\n  --- order form options ---');
      for (const key of Object.keys(options)) {
        const isAddon = key.startsWith('addon_');
        if (!interesting.includes(key) && !isAddon) continue;
        const vals = options[key].slice(0, 12)
          .map((v) => `${v.key}${v.label ? `=${v.label}` : ''}`)
          .join(', ');
        console.log(`  ${key}: ${vals}${options[key].length > 12 ? ' …' : ''}`);
      }
      console.log('  (full list in order-form-options.json)\n');
    }

    if (name === 'vds' && !err && Array.isArray(elems)) {
      for (const row of elems.slice(0, 5)) {
        const id = row.id?.$ ?? row.id;
        const flat = Object.fromEntries(
          Object.entries(row).map(([k, v]) => [k, typeof v === 'object' ? (v?.$ ?? '') : v]),
        );
        console.log(`  service ${id}: status=${flat.item_status} ip=${flat.ip} domain=${flat.domain}`);
        const detail = await call({ func: 'vds.edit', elid: String(id), auth });
        await save(`vds-edit-${id}`, detail.text);
      }
      console.log('');
    }
  }

  await writeFile(path.join(outDir, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8');

  console.log(`\nRaw responses: ${outDir}`);
  console.log('Next: fill SAAS24_* ids in .env from order-form-options.json, then');
  console.log('open a service in the cabinet, follow the "go to panel" button and');
  console.log('run scripts/vmmanager-discover.mjs against that URL.');
}

main().catch((e) => {
  console.error(`\nfailed: ${e.message}`);
  process.exit(1);
});
