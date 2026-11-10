import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { Prescription, Product } from '@/types/api'

import { useCartStore } from '../cart'

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: 'Acetaminofén',
    description: null,
    presentation: null,
    category_id: null,
    category_name: null,
    barcode: '111',
    sanitary_registration: null,
    requires_prescription: false,
    controlled: false,
    tax_rate: '12.00',
    price: '10.00',
    cost: '5.00',
    min_stock: 0,
    is_active: true,
    ingredients: [],
    stock: 10,
    ...overrides,
  }
}

describe('cart store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('merges repeated scans and totals with tax included', () => {
    const cart = useCartStore()
    cart.add(product())
    cart.add(product())
    expect(cart.lines).toHaveLength(1)
    expect(cart.lines[0]!.quantity).toBe(2)
    expect(cart.totals.total).toBe(2000)
    expect(cart.totals.tax).toBe(214) // 20.00 * 12/112
  })

  it('computes change only from the cash part', () => {
    const cart = useCartStore()
    cart.add(product({ price: '25.00' }))
    cart.payments = [
      { method: 'card', amount: '5.00', reference: '' },
      { method: 'cash', amount: '20.00', reference: '' },
    ]
    cart.cashTendered = '50'
    expect(cart.balance).toBe(0)
    expect(cart.change).toBe(3000)

    const input = cart.toSaleInput(7)
    expect(input.register_id).toBe(7)
    expect(input.cash_tendered).toBe('50.00')
    expect(input.payments).toEqual([
      { method: 'card', amount: '5.00', reference: null },
      { method: 'cash', amount: '20.00', reference: null },
    ])
  })

  it('assigns a covering prescription to Rx lines and blocks charging without one', () => {
    const cart = useCartStore()
    const rx = product({ id: 2, requires_prescription: true })
    cart.add(rx)
    expect(cart.needsPrescription).toBe(true)

    const prescription: Prescription = {
      id: 9,
      customer_id: 3,
      prescriber_name: 'Dra. López',
      prescriber_license: 'COL-1',
      issued_on: '2026-11-01',
      notes: null,
      file_name: 'receta.png',
      items: [
        {
          id: 1,
          product_id: 2,
          product_name: 'x',
          max_quantity: 2,
          dispensed_quantity: 0,
          remaining: 2,
        },
      ],
    }
    cart.setCustomer({ id: 3, full_name: 'Juan', document_id: '1', phone: null, email: null }, [
      prescription,
    ])
    expect(cart.lines[0]!.prescriptionId).toBe(9)
    expect(cart.needsPrescription).toBe(false)
    expect(cart.toSaleInput(1).lines[0]!.prescription_id).toBe(9)
  })
})
