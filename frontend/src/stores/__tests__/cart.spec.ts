import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { Prescription, Product } from '@/types/api'

import { missingPaymentDetails, newPayment, useCartStore } from '../cart'

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
      {
        ...newPayment('card', '5.00'),
        reference: ' AUTH-1 ',
        cardType: 'visa',
        cardLast4: '4242',
      },
      newPayment('cash', '20.00'),
    ]
    cart.cashTendered = '50'
    expect(cart.balance).toBe(0)
    expect(cart.change).toBe(3000)
    expect(cart.paymentsComplete).toBe(true)

    const input = cart.toSaleInput(7)
    expect(input.register_id).toBe(7)
    expect(input.cash_tendered).toBe('50.00')
    expect(input.payments).toEqual([
      {
        method: 'card',
        amount: '5.00',
        reference: 'AUTH-1',
        card_type: 'visa',
        card_last4: '4242',
        bank_name: null,
      },
      {
        method: 'cash',
        amount: '20.00',
        reference: null,
        card_type: null,
        card_last4: null,
        bank_name: null,
      },
    ])
  })

  it('SAL-11/SAL-12: card and transfer payments need their details', () => {
    const card = newPayment('card', '10.00')
    expect(missingPaymentDetails(card)).toEqual(['reference', 'cardType', 'cardLast4'])
    card.reference = 'A1'
    card.cardType = 'amex'
    card.cardLast4 = '12345'
    expect(missingPaymentDetails(card)).toEqual(['cardLast4'])
    card.cardLast4 = '0005'
    expect(missingPaymentDetails(card)).toEqual([])

    const transfer = { ...newPayment('transfer', '10.00'), reference: 'T-9' }
    expect(missingPaymentDetails(transfer)).toEqual(['bankName'])
    expect(missingPaymentDetails(newPayment('cash', '1.00'))).toEqual([])

    const cart = useCartStore()
    cart.payments = [transfer]
    expect(cart.paymentsComplete).toBe(false)
  })

  it('asks for the customer once per sale', () => {
    const cart = useCartStore()
    cart.customerAsked = true
    cart.clear()
    expect(cart.customerAsked).toBe(false)
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
