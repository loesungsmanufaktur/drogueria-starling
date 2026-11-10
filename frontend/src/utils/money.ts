// Integer-cent arithmetic that mirrors the backend rules (SAL-1): no floats,
// half-up rounding per line. The server stays authoritative; this preview lets
// the cashier see the same total the API will charge.

/** "12.30" → 1230. Accepts up to 2 decimals. */
export function toCents(value: string | number): number {
  const text = typeof value === 'number' ? value.toFixed(2) : value.trim()
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(text)
  if (!match) throw new Error(`Invalid money value: ${value}`)
  const [, sign, whole, frac = ''] = match
  const cents = Number(whole) * 100 + Number(frac.padEnd(2, '0'))
  return sign === '-' ? -cents : cents
}

/** 1230 → "12.30" */
export function fromCents(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}

/** Percentage string ("12.5") → basis points (1250). */
export function toBasisPoints(percent: string | number): number {
  return toCents(percent)
}

/** round_half_up(numerator / denominator) for non-negative integers. */
function divHalfUp(numerator: number, denominator: number): number {
  return Math.floor((2 * numerator + denominator) / (2 * denominator))
}

export interface LinePrice {
  gross: number
  discount: number
  total: number
  tax: number
}

/** Same formula as app.services.sales.price_line (tax-included prices). */
export function priceLine(
  unitPrice: string,
  quantity: number,
  discountPercent: string,
  taxRate: string,
): LinePrice {
  const gross = toCents(unitPrice) * quantity
  const discount = divHalfUp(gross * toBasisPoints(discountPercent), 10000)
  const total = gross - discount
  const rate = toBasisPoints(taxRate)
  const tax = divHalfUp(total * rate, 10000 + rate)
  return { gross, discount, total, tax }
}

const formatter = new Intl.NumberFormat('es-GT', {
  style: 'currency',
  currency: 'GTQ',
  minimumFractionDigits: 2,
})

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const cents = typeof value === 'number' ? value : toCents(value)
  return formatter.format(cents / 100)
}
