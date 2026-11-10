import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { Customer, PaymentMethod, Prescription, Product, SaleInput } from '@/types/api'
import { fromCents, priceLine, toCents } from '@/utils/money'

export interface CartLine {
  key: number
  product: Product
  quantity: number
  discountPercent: string
  lotId: number | null
  prescriptionId: number | null
}

export interface CartPayment {
  method: PaymentMethod
  amount: string
  reference: string
}

let nextKey = 1

export const useCartStore = defineStore('cart', () => {
  const lines = ref<CartLine[]>([])
  const customer = ref<Customer | null>(null)
  const prescriptions = ref<Prescription[]>([])
  const payments = ref<CartPayment[]>([])
  const cashTendered = ref('')

  const priced = computed(() =>
    lines.value.map((line) => ({
      line,
      ...priceLine(
        line.product.price,
        line.quantity,
        line.discountPercent || '0',
        line.product.tax_rate,
      ),
    })),
  )
  const totals = computed(() => {
    let gross = 0
    let discount = 0
    let total = 0
    let tax = 0
    for (const p of priced.value) {
      gross += p.gross
      discount += p.discount
      total += p.total
      tax += p.tax
    }
    return { gross, discount, total, tax, subtotal: total - tax }
  })
  const paid = computed(() =>
    payments.value.reduce((sum, p) => sum + (p.amount ? toCents(p.amount) : 0), 0),
  )
  const cashDue = computed(() =>
    payments.value
      .filter((p) => p.method === 'cash')
      .reduce((sum, p) => sum + (p.amount ? toCents(p.amount) : 0), 0),
  )
  const change = computed(() => {
    if (!cashTendered.value || cashDue.value === 0) return 0
    return Math.max(0, toCents(cashTendered.value) - cashDue.value)
  })
  const balance = computed(() => totals.value.total - paid.value)
  const needsPrescription = computed(() =>
    lines.value.some((l) => l.product.requires_prescription && l.prescriptionId === null),
  )

  function add(product: Product, quantity = 1): void {
    const existing = lines.value.find((l) => l.product.id === product.id && l.lotId === null)
    if (existing) existing.quantity += quantity
    else
      lines.value.push({
        key: nextKey++,
        product,
        quantity,
        discountPercent: '0',
        lotId: null,
        prescriptionId: null,
      })
    autoAssignPrescriptions()
  }

  function remove(key: number): void {
    lines.value = lines.value.filter((l) => l.key !== key)
  }

  function setCustomer(value: Customer | null, rx: Prescription[] = []): void {
    customer.value = value
    prescriptions.value = rx
    for (const line of lines.value) line.prescriptionId = null
    autoAssignPrescriptions()
  }

  /** Attach the first prescription that still covers each Rx product. */
  function autoAssignPrescriptions(): void {
    for (const line of lines.value) {
      if (!line.product.requires_prescription || line.prescriptionId !== null) continue
      const match = prescriptions.value.find((rx) =>
        rx.items.some((i) => i.product_id === line.product.id && i.remaining >= line.quantity),
      )
      if (match) line.prescriptionId = match.id
    }
  }

  /** Default to a single cash payment for the full total. */
  function payAllCash(): void {
    payments.value = [{ method: 'cash', amount: fromCents(totals.value.total), reference: '' }]
  }

  function toSaleInput(registerId: number): SaleInput {
    return {
      register_id: registerId,
      customer_id: customer.value?.id ?? null,
      lines: lines.value.map((l) => ({
        product_id: l.product.id,
        quantity: l.quantity,
        discount_percent: l.discountPercent || '0',
        lot_id: l.lotId,
        prescription_id: l.product.requires_prescription ? l.prescriptionId : null,
      })),
      payments: payments.value
        .filter((p) => p.amount && toCents(p.amount) > 0)
        .map((p) => ({
          method: p.method,
          amount: fromCents(toCents(p.amount)),
          reference: p.reference || null,
        })),
      cash_tendered:
        cashTendered.value && cashDue.value > 0 ? fromCents(toCents(cashTendered.value)) : null,
    }
  }

  function clear(): void {
    lines.value = []
    customer.value = null
    prescriptions.value = []
    payments.value = []
    cashTendered.value = ''
  }

  return {
    lines,
    customer,
    prescriptions,
    payments,
    cashTendered,
    priced,
    totals,
    paid,
    cashDue,
    change,
    balance,
    needsPrescription,
    add,
    remove,
    setCustomer,
    autoAssignPrescriptions,
    payAllCash,
    toSaleInput,
    clear,
  }
})
