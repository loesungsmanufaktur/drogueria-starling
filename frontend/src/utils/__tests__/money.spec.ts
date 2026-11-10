import { describe, expect, it } from 'vitest'

import { fromCents, priceLine, toCents } from '../money'

describe('money', () => {
  it('parses and formats cents without floats', () => {
    expect(toCents('12.3')).toBe(1230)
    expect(toCents('0.05')).toBe(5)
    expect(toCents('100')).toBe(10000)
    expect(fromCents(1230)).toBe('12.30')
    expect(fromCents(-450)).toBe('-4.50')
    expect(() => toCents('1.005')).toThrow()
  })

  // Same cases as backend/tests/test_sales.py, so preview and server agree.
  it('prices a line like the backend: 3 x 11.20, 5% off, 12% VAT included', () => {
    expect(priceLine('11.20', 3, '5', '12.00')).toEqual({
      gross: 3360,
      discount: 168,
      total: 3192,
      tax: 342,
    })
  })

  it('rounds discounts half-up per line', () => {
    // 0.25 x 10% = 0.025 → 0.03
    expect(priceLine('0.25', 1, '10', '12.00').discount).toBe(3)
  })

  it('handles zero tax and zero discount', () => {
    expect(priceLine('9.99', 2, '0', '0')).toEqual({
      gross: 1998,
      discount: 0,
      total: 1998,
      tax: 0,
    })
  })
})
