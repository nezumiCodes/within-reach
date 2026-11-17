/**
 * Postcode normalisation, matching pipeline/src/within_reach_pipeline/postcodes.py.
 * Pure functions: no input or output of their own (spec section 10, engine module).
 */

// Outward code: A9, A99, AA9, AA99, A9A or AA9A. Inward code: 9AA. Plus the special GIR 0AA.
const POSTCODE = /^(?:([A-Z]{1,2}[0-9][A-Z0-9]?)([0-9][A-Z]{2})|(GIR)(0AA))$/

/** Returns the postcode in upper case with a single space, or null if it isn't valid. */
export function normalisePostcode(raw: string): string | null {
  const compact = raw.replace(/\s+/g, '').toUpperCase()
  const match = POSTCODE.exec(compact)
  if (match === null) return null
  const outward = match[1] ?? match[3]
  const inward = match[2] ?? match[4]
  return `${outward} ${inward}`
}

/** True for Northern Ireland (BT) postcodes, which version A doesn't cover. */
export function isNorthernIreland(postcode: string): boolean {
  return postcode.replace(/\s+/g, '').toUpperCase().startsWith('BT')
}
