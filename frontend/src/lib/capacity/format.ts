/**
 * Presentation helpers for the cluster-availability readout.
 *
 * Kept out of the page component so the rounding contract is unit-testable:
 * the figures it renders move in quarter-core steps, and an over-eager round
 * makes the readout look wrong (see fmtCapacity).
 */

export type CapacityTone = 'success' | 'warning' | 'destructive' | 'default';

/** Below this fraction of total, capacity reads as critical. */
const DESTRUCTIVE_RATIO = 0.15;
/** Below this fraction of total, capacity reads as tight. */
const WARNING_RATIO = 0.35;

/**
 * Format one side of a "3.25 / 8" capacity fraction.
 *
 * Two decimals with trailing zeros dropped. The precision is deliberate: a VM
 * reserves a quarter of its plan's CPU limit, so free CPU moves in 0.25 steps.
 * Rounding to one decimal turned a 0.25-core release into a "8 -> 8.3" jump,
 * which reads as arithmetic error rather than a quarter core.
 *
 * Rounds halves away from zero in both directions. The API clamps every figure
 * at zero (Capacity.free_* in services/api-gateway/app/services/vm_capacity.py),
 * so negatives should never arrive — but rounding symmetrically costs one call
 * and keeps the contract true of any finite input rather than only the ones we
 * currently happen to send.
 *
 * Returns an em dash for any figure that isn't a finite number: the
 * availability endpoint nulls every capacity field when the orchestrator is
 * unreachable, and a stray NaN must degrade to the same dash rather than
 * printing "NaN" into the card.
 */
export function fmtCapacity(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  return String((Math.sign(n) * Math.round(Math.abs(n) * 100)) / 100);
}

/** Tone a free-capacity card by how much headroom is left. */
export function capacityTone(
  free: number | null | undefined,
  total: number | null | undefined
): CapacityTone {
  if (free === null || free === undefined || !total) return 'default';
  const ratio = free / total;
  if (ratio < DESTRUCTIVE_RATIO) return 'destructive';
  if (ratio < WARNING_RATIO) return 'warning';
  return 'success';
}
