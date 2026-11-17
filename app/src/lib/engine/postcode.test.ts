import { describe, expect, it } from 'vitest'
import { isNorthernIreland, normalisePostcode } from './postcode'

describe('normalisePostcode', () => {
  it.each([
    ['CH1 1AA', 'CH1 1AA'],
    ['ch11aa', 'CH1 1AA'],
    ['  ll11   1aa ', 'LL11 1AA'],
    ['EH1 1YZ', 'EH1 1YZ'],
    ['W1A 0AX', 'W1A 0AX'],
    ['M11AE', 'M1 1AE'],
    ['GIR0AA', 'GIR 0AA'],
  ])('normalises %j to %j', (raw, expected) => {
    expect(normalisePostcode(raw)).toBe(expected)
  })

  it.each(['', '   ', 'CH1', '12345', 'CH1 1A', 'CHH1 1AA', 'CH1 1AAA', 'C'])(
    'returns null for %j',
    (raw) => {
      expect(normalisePostcode(raw)).toBeNull()
    },
  )
})

describe('isNorthernIreland', () => {
  it.each([
    ['BT1 1AA', true],
    ['bt481aa', true],
    ['B1 1AA', false],
    ['CH1 1AA', false],
  ])('%j -> %s', (postcode, expected) => {
    expect(isNorthernIreland(postcode)).toBe(expected)
  })
})
