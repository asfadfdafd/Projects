#!/usr/bin/env node
// Read-only probe of the VMmanager panel behind a 24saas VPS service.
//
// Answers two of the five open questions in docs/24saas-integration.md:
// which VMmanager generation this is, and whether our account can manage SSH
// keys and VM power state itself (which is what makes `resume` ours rather
// than the provider's).
//
//   SAAS24_VM_URL=https://panel.example.kz \
//   SAAS24_VM_USER=you@example.kz \
//   SAAS24_VM_PASSWORD='...' \
//   node scripts/vmmanager-discover.mjs
//
// Every call is a GET or a login. Nothing is created or changed.

const URL_BASE = (process.env.SAAS24_VM_URL ?? '').replace(/\/+$/, '');
const USER = process.env.SAAS24_VM_USER;
const PASSWORD = process.env.SAAS24_VM_PASSWORD;

if (!URL_BASE || !USER || !PASSWORD) {
  console.error('Set SAAS24_VM_URL, SAAS24_VM_USER, SAAS24_VM_PASSWORD.');
  console.error('The URL is the panel the cabinet sends you to from a VPS service.');
  process.exit(2);
}

const short = (v) => JSON.stringify(v).slice(0, 600);

async function tryV6() {
  const res = await fetch(`${URL_BASE}/auth/v4/public/token`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email: USER, password: PASSWORD }),
  });
  const text = await res.text();
  let token = null;
  try {
    token = JSON.parse(text)?.token ?? null;
  } catch {
    /* not v6, or 2FA, or a different error shape */
  }
  return { ok: Boolean(token), token, status: res.status, text };
}

async function v6Get(token, pathname) {
  const res = await fetch(`${URL_BASE}${pathname}`, {
    headers: { 'x-xsrf-token': token },
  });
  const text = await res.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    /* keep raw */
  }
  return { status: res.status, body, text };
}

async function tryV5() {
  // VMmanager 5 speaks the COREmanager API, like BILLmanager does.
  const body = new URLSearchParams({ func: 'auth', username: USER, password: PASSWORD, out: 'xml' });
  for (const entry of ['/vmmgr', '/manager/vmmgr', '/ispmgr']) {
    const res = await fetch(`${URL_BASE}${entry}`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body,
    });
    const text = await res.text();
    const id = (text.match(/<auth[^>]*id="([^"]+)"/) ?? [])[1];
    if (id) return { ok: true, entry, session: id };
  }
  return { ok: false };
}

async function main() {
  console.log(`panel: ${URL_BASE}\n`);

  const v6 = await tryV6();
  if (v6.ok) {
    console.log('VMmanager 6 — token auth works (/auth/v4/public/token).\n');

    const hosts = await v6Get(v6.token, '/vm/v3/host');
    const list = hosts.body?.list ?? [];
    console.log(`GET /vm/v3/host -> ${hosts.status}, ${Array.isArray(list) ? list.length : '?'} VMs`);
    for (const h of (Array.isArray(list) ? list : []).slice(0, 5)) {
      const ip = h.ip_addr?.[0]?.ip ?? h.ip?.[0]?.ip ?? '?';
      console.log(`  vm ${h.id} name=${h.name} state=${h.state} ip=${ip}`);
    }

    const keys = await v6Get(v6.token, '/auth/v4/ssh_key');
    console.log(`\nGET /auth/v4/ssh_key -> ${keys.status} ${keys.body ? short(keys.body) : keys.text.slice(0, 200)}`);
    console.log(
      keys.status === 200
        ? '\nSSH keys are ours to manage: register the platform key here and every\n' +
            'new VM gets it in /root/.ssh/authorized_keys at creation.'
        : '\nSSH key endpoint not reachable with this account — check the panel UI\n' +
            'for an SSH keys section before falling back to a recipe.',
    );

    console.log('\nPower actions to verify in the UI (they decide whether `resume`');
    console.log('is ours): start / stop / restart on a VM you own.');
    return;
  }

  console.log(`not VMmanager 6 (token endpoint: HTTP ${v6.status}) ${v6.text.slice(0, 200)}\n`);

  const v5 = await tryV5();
  if (v5.ok) {
    console.log(`VMmanager 5 — COREmanager API at ${v5.entry}, session acquired.`);
    console.log('Relevant functions: `vm` (list/status), `vm.edit` (sshpubkey),');
    console.log('`vm.start`, `vm.stop`, `vm.reboot`, `sshkey`.');
    return;
  }

  console.log('Neither generation answered. Likely causes: wrong panel URL, the');
  console.log('panel only accepts the pass-through login from the cabinet, or the');
  console.log('account has no direct panel credentials. Check in a browser first.');
}

main().catch((e) => {
  console.error(`failed: ${e.message}`);
  process.exit(1);
});
