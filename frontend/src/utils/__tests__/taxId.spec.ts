import { describe, expect, it } from 'vitest'

import { isValidTaxId, normalizeTaxId } from '../taxId'

// Same cases as backend/tests/test_customers_payments.py (SAL-13).
describe('NIT/CUI', () => {
  it('treats a missing or blank number as CF', () => {
    expect(normalizeTaxId(null)).toBe('CF')
    expect(normalizeTaxId('   ')).toBe('CF')
    expect(normalizeTaxId('cf')).toBe('CF')
  })

  it('strips spaces and hyphens and upper-cases the K check digit', () => {
    expect(normalizeTaxId('123456-k')).toBe('123456K')
    expect(normalizeTaxId('1234 56789 0101')).toBe('1234567890101')
  })

  it('accepts digits with an optional K check digit, or CF', () => {
    expect(isValidTaxId('1234567890101')).toBe(true)
    expect(isValidTaxId('123456-K')).toBe(true)
    expect(isValidTaxId('CF')).toBe(true)
    expect(isValidTaxId('ABC-1')).toBe(false)
    expect(isValidTaxId('K')).toBe(false)
  })
})
