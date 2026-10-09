/**
 * Saas24ApiAdapter — Phase 2.
 *
 * The one file besides saas24-manual.ts that knows 24saas exists. It orders a
 * VPS in their BILLmanager, reports its status, and deletes it. Installing the
 * service onto the machine is NOT done here: the orchestrator does that over
 * SSH once status() reports an address (see docs/24saas-integration.md §2),
 * because the provider contract ends at "a machine exists and is reachable".
 *
 * Three decisions worth not re-litigating:
 *
 * 1. Ordering goes through the cart (order.param -> cartorder.create.confirm)
 *    rather than skipbasket=on. Each step returns an id we can persist before
 *    taking the next one, which is what makes a crashed order recoverable.
 *
 * 2. Correlation is by `domain`, chosen by us and written to our database
 *    BEFORE the order call. BILLmanager offers no idempotency key, and `domain`
 *    is the one field we control that comes back in the service list. A retry
 *    therefore starts with a lookup, never with an order.
 *
 * 3. A service that cannot be found is reported as such, never as "failed".
 *    Their side retries a failed creation for up to half an hour and then
 *    hands it to their own operator, so an early FAILED here would have us
 *    order a second machine on top of one that is still being built.
 */

import { BillmgrClient, BillmgrError, rowsOf, type BillmgrDoc } from './billmgr-client.js';

export type DeploymentStatus = 'pending' | 'provisioning' | 'active' | 'failed' | 'stopped';

export interface TierSpec {
  vcpu: number;
  ramGb: number;
  diskGb: number;
}

/**
 * Ids from the provider's catalogue. Discovered once with
 * `npm run saas24:discover` and kept in configuration, never guessed:
 * a wrong pricelist id orders the wrong machine and bills for it.
 */
export interface Saas24Catalogue {
  datacenter: string;
  ostempl: string;
  /** Our tier name -> their pricelist id. */
  pricelistByTier: Record<string, string>;
  /**
   * Addon ids for configurable tariffs. Omit entirely when the provider only
   * sells fixed configurations — then the pricelist alone carries the size.
   */
  addons?: { vcpu?: string; ramGb?: string; diskGb?: string };
  /** Suffix for the correlation hostname, e.g. "vm.jistudio.kz". */
  domainSuffix: string;
  orderPeriodMonths?: number;
}

export interface Saas24Service {
  externalRef: string;
  domain?: string;
  ip?: string;
  itemStatus: number;
  statusMessage?: string;
}

/** 1 ordered, 2 active, 3 suspended, 4 deleted, 5 processing. */
export function mapItemStatus(itemStatus: number, ip: string | undefined): DeploymentStatus {
  switch (itemStatus) {
    case 1:
    case 5:
      return 'provisioning';
    case 2:
      return ip ? 'active' : 'provisioning';
    case 3:
    case 4:
      return 'stopped';
    default:
      return 'provisioning';
  }
}

/**
 * Deterministic, DNS-safe, stable for the life of the deployment. Short
 * because BILLmanager and the OS both care about hostname length.
 */
export function correlationDomain(deploymentId: string, suffix: string): string {
  const slug = deploymentId.replace(/[^a-zA-Z0-9]/g, '').toLowerCase().slice(0, 12);
  return `d-${slug}.${suffix}`;
}

export function orderParams(
  tierName: string,
  tier: TierSpec,
  domain: string,
  catalogue: Saas24Catalogue,
): Record<string, string> {
  const pricelist = catalogue.pricelistByTier[tierName];
  if (!pricelist) {
    throw new Error(
      `no 24saas pricelist configured for tier "${tierName}" — run saas24:discover and fill SAAS24_PRICELIST_*`,
    );
  }
  const params: Record<string, string> = {
    func: 'v2.vds.order.param',
    pricelist,
    datacenter: catalogue.datacenter,
    ostempl: catalogue.ostempl,
    order_period: String(catalogue.orderPeriodMonths ?? 1),
    autoprolong: 'on',
    force_use_new_cart: 'on',
    clicked_button: 'order',
    domain,
  };
  const { addons } = catalogue;
  if (addons?.vcpu) params[`addon_${addons.vcpu}`] = String(tier.vcpu);
  if (addons?.ramGb) params[`addon_${addons.ramGb}`] = String(tier.ramGb);
  if (addons?.diskGb) params[`addon_${addons.diskGb}`] = String(tier.diskGb);
  return params;
}

export class Saas24ApiAdapter {
  constructor(
    private readonly client: BillmgrClient,
    private readonly catalogue: Saas24Catalogue,
    private readonly log: { info: (m: string, c?: unknown) => void; warn: (m: string, c?: unknown) => void },
  ) {}

  /** The lookup every retry starts with. */
  async findByDomain(domain: string): Promise<Saas24Service | null> {
    const doc = await this.client.read<BillmgrDoc>('vds');
    const row = rowsOf(doc).find((r) => r.domain === domain);
    if (!row) return null;
    return {
      externalRef: String(row.id),
      domain: row.domain,
      ip: row.ip || undefined,
      itemStatus: Number(row.item_status ?? 0),
      statusMessage: row.status_msg,
    };
  }

  /**
   * Orders one machine. Safe to call again after a timeout: an existing
   * service with the same domain is returned instead of a second order.
   */
  async provision(input: {
    deploymentId: string;
    tierName: string;
    tier: TierSpec;
  }): Promise<{ externalRef: string; domain: string; reused: boolean }> {
    const domain = correlationDomain(input.deploymentId, this.catalogue.domainSuffix);

    const existing = await this.findByDomain(domain);
    if (existing) {
      this.log.info('saas24: service already exists for this deployment', { domain, externalRef: existing.externalRef });
      return { externalRef: existing.externalRef, domain, reused: true };
    }

    const params = orderParams(input.tierName, input.tier, domain, this.catalogue);
    const cartDoc = await this.client.write<BillmgrDoc>(params.func, params);
    const lineItem = scalar(cartDoc, 'lineitem.id');
    if (!lineItem) {
      throw new Error('24saas: order accepted but no lineitem.id returned; check the raw response');
    }

    // paymethod_id=0 pays from the account balance. A failure here leaves a
    // cart line, not a machine — recoverable, and visible in the cabinet.
    await this.client.write<BillmgrDoc>('cartorder.create.confirm', {
      elid: lineItem,
      paymethod_id: '0',
    });

    // The service id appears once their side picks the order up; the caller
    // resolves it through findByDomain on the next status poll.
    const service = await this.findByDomain(domain);
    return { externalRef: service?.externalRef ?? '', domain, reused: false };
  }

  async status(ref: { externalRef?: string; domain: string }): Promise<{
    status: DeploymentStatus;
    ip?: string;
    externalRef?: string;
    message?: string;
  }> {
    const service = await this.findByDomain(ref.domain);
    if (!service) {
      // Not an error: their side may still be processing the order, or the
      // service was deleted. The caller decides based on how long it has been.
      return { status: 'provisioning', message: 'service not listed yet' };
    }
    return {
      status: mapItemStatus(service.itemStatus, service.ip),
      ip: service.ip,
      externalRef: service.externalRef,
      message: service.statusMessage,
    };
  }

  /** Deletion returns ok even for an unknown id, so the result is verified. */
  async deprovision(ref: { externalRef: string; domain: string }): Promise<void> {
    try {
      await this.client.write('vds.delete', { elid: ref.externalRef });
    } catch (e) {
      if (!(e instanceof BillmgrError)) throw e;
      this.log.warn('saas24: delete rejected', { externalRef: ref.externalRef, type: e.type });
    }
    const after = await this.findByDomain(ref.domain);
    if (after && after.itemStatus !== 4) {
      throw new Error(
        `24saas: service ${ref.externalRef} still present after delete (item_status=${after.itemStatus})`,
      );
    }
  }

  /** Stop is available to a client account; start may not be — see the doc. */
  async stop(externalRef: string): Promise<void> {
    await this.client.write('vds.suspend.confirm', { elid: externalRef, force: 'off' });
  }

  async reboot(externalRef: string): Promise<void> {
    await this.client.write('vds.reboot.confirm', { elid: externalRef, force: 'off' });
  }
}

function scalar(doc: BillmgrDoc, key: string): string | undefined {
  const node = (doc.doc?.[key] ?? doc[key]) as unknown;
  if (node == null) return undefined;
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (typeof node === 'object' && '$' in (node as Record<string, unknown>)) {
    return String((node as { $: unknown }).$);
  }
  return undefined;
}
