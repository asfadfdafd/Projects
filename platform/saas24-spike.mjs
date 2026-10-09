#!/usr/bin/env node
// End-to-end spike: order ONE machine, wait for it, try SSH, delete it.
//
// THIS SPENDS MONEY. The minimum order period is one month and there is no
// hourly billing, so the machine costs a month even though it lives for
// minutes. It refuses to run without --i-accept-the-charge for that reason.
//
//   SAAS24_BILLMGR_USER=... SAAS24_BILLMGR_PASSWORD=... \
//   SAAS24_PRICELIST=123 SAAS24_DATACENTER=1 SAAS24_OSTEMPL='...' \
//   SAAS24_DOMAIN_SUFFIX=vm.example.kz \
//   SAAS24_SSH_KEY=~/.ssh/jistudio_platform \
//   node scripts/saas24-spike.mjs --i-accept-the-charge
//
// What a green run proves, in order: the account may order via API; our
// correlation domain survives the round trip; how long activation really
// takes; whether the VMmanager SSH key landed on the machine; and that delete
// actually deletes.

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

if (!process.argv.includes('--i-accept-the-charge')) {
  console.error('Refusing to run: this orders a billable machine (one month minimum).');
  console.error('Re-run with --i-accept-the-charge once that is acceptable.');
  process.exit(2);
}

const cfg = {
  url: process.env.SAAS24_BILLMGR_URL ?? 'https://cabinet.24saas.kz/billmgr',
  user: process.env.SAAS24_BILLMGR_USER,
  password: process.env.SAAS24_BILLMGR_PASSWORD,
  pricelist: process.env.SAAS24_PRICELIST,
  datacenter: process.env.SAAS24_DATACENTER,
  ostempl: process.env.SAAS24_OSTEMPL,
  suffix: process.env.SAAS24_DOMAIN_SUFFIX ?? 'vm.example.kz',
  sshKey: process.env.SAAS24_SSH_KEY,
  waitMinutes: Number(process.env.SAAS24_WAIT_MINUTES ?? 45),
};

for (const key of ['user', 'password', 'pricelist', 'datacenter', 'ostempl']) {
  if (!cfg[key]) {
    console.error(`Missing SAAS24_${key.toUpperCase()} — take the ids from saas24-discover output.`);
    process.exit(2);
  }
}

let session = null;

async function call(func, params = {}) {
  if (!session && func !== 'auth') await auth();
  const body = new URLSearchParams({ ...params, func, out: 'json', ...(session ? { auth: session } : {}) });
  const res = await fetch(cfg.url, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  const text = await res.text();
  let doc;
  try {
    doc = JSON.parse(text);
  } catch {
    throw new Error(`non-JSON from ${func}: ${text.slice(0, 200)}`);
  }
  const err = doc?.doc?.error ?? doc?.error;
  if (err) throw new Error(`${func} rejected: ${JSON.stringify(err).slice(0, 300)}`);
  return doc.doc ?? doc;
}

async function auth() {
  const body = new URLSearchParams({ func: 'auth', username: cfg.user, password: cfg.password, out: 'json' });
  const res = await fetch(cfg.url, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  const doc = JSON.parse(await res.text());
  session = doc?.doc?.auth?.$ ?? doc?.doc?.auth?.$id ?? doc?.auth?.$;
  if (!session) throw new Error(`no session id: ${JSON.stringify(doc).slice(0, 300)}`);
}

const val = (n) => (n && typeof n === 'object' && '$' in n ? String(n.$) : n == null ? undefined : String(n));

async function listServices() {
  const doc = await call('vds');
  const elem = doc.elem ?? [];
  return (Array.isArray(elem) ? elem : [elem]).map((row) =>
    Object.fromEntries(Object.entries(row).map(([k, v]) => [k, val(v)])),
  );
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const domain = `spike-${Date.now().toString(36)}.${cfg.suffix}`;
  console.log(`correlation domain: ${domain}\n`);

  console.log('1/5 ordering …');
  const t0 = Date.now();
  const cart = await call('v2.vds.order.param', {
    pricelist: cfg.pricelist,
    datacenter: cfg.datacenter,
    ostempl: cfg.ostempl,
    order_period: '1',
    autoprolong: 'on',
    force_use_new_cart: 'on',
    clicked_button: 'order',
    domain,
    sok: 'ok',
  });
  const lineItem = val(cart['lineitem.id']);
  console.log(`    lineitem.id=${lineItem}`);

  const order = await call('cartorder.create.confirm', { elid: lineItem, paymethod_id: '0', sok: 'ok' });
  console.log(`    billorder=${val(order.billorder)}\n`);

  console.log('2/5 waiting for activation (this is the number we need) …');
  let service = null;
  const deadline = Date.now() + cfg.waitMinutes * 60_000;
  while (Date.now() < deadline) {
    const found = (await listServices()).find((s) => s.domain === domain);
    if (found) {
      if (found !== service) {
        console.log(`    t+${Math.round((Date.now() - t0) / 1000)}s item_status=${found.item_status} ip=${found.ip ?? '-'} ${found.status_msg ?? ''}`);
      }
      service = found;
      if (found.item_status === '2' && found.ip) break;
    }
    await sleep(30_000);
  }
  if (!service?.ip || service.item_status !== '2') {
    console.log('\n    not active within the window. Leaving it in place so it can be');
    console.log(`    inspected in the cabinet. Domain: ${domain}`);
    process.exit(1);
  }
  const elapsed = Math.round((Date.now() - t0) / 1000);
  console.log(`    active after ${elapsed}s, ip=${service.ip}, id=${service.id}\n`);

  console.log('3/5 SSH with the platform key …');
  if (!cfg.sshKey) {
    console.log('    skipped (SAAS24_SSH_KEY not set)');
  } else {
    try {
      const { stdout } = await run('ssh', [
        '-i', cfg.sshKey,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ConnectTimeout=15',
        '-o', 'BatchMode=yes',
        `root@${service.ip}`,
        'cat /etc/os-release | head -2; id',
      ]);
      console.log(`    key works:\n${stdout.trim().split('\n').map((l) => `      ${l}`).join('\n')}`);
      console.log('\n    >>> This is the answer that removes the recipe from the plan.');
    } catch (e) {
      console.log(`    key did NOT work: ${String(e.message).split('\n')[0]}`);
      console.log('    Register the platform public key in the VMmanager cabinet, or');
      console.log('    fall back to asking 24saas for a bootstrap recipe.');
    }
  }

  console.log('\n4/5 deleting …');
  await call('vds.delete', { elid: service.id, sok: 'ok' });

  console.log('5/5 verifying deletion (delete answers ok even for unknown ids) …');
  await sleep(10_000);
  const after = (await listServices()).find((s) => s.domain === domain);
  console.log(after ? `    still listed, item_status=${after.item_status}` : '    gone from the list');

  console.log('\nRecord in docs/24saas-integration.md: activation time, whether SSH');
  console.log('worked, and what deletion left behind.');
}

main().catch((e) => {
  console.error(`\nfailed: ${e.message}`);
  console.error('If an order was placed, check the cabinet — a cart line or a machine may exist.');
  process.exit(1);
});
