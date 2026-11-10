// SAL-13: every customer has a NIT/CUI; "CF" (consumidor final) when they have none.
// Mirrors app.schemas.customers.normalize_tax_id so the UI and API agree.

export const CF = 'CF'

/** Strip spaces and hyphens, upper-case; empty means CF. */
export function normalizeTaxId(value: string | null | undefined): string {
  const normalized = (value ?? '').replace(/[\s-]/g, '').toUpperCase()
  return normalized || CF
}

/** CUI is 13 digits; NIT is digits with a check digit that may be K. */
export function isValidTaxId(value: string): boolean {
  return /^(CF|\d{1,29}[\dK])$/.test(normalizeTaxId(value))
}
