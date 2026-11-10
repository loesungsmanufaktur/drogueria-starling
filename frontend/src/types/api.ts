// Shapes returned by the FastAPI backend. Money and rates arrive as strings
// (Decimal) and are never converted to floats for arithmetic.

export type Role = 'admin' | 'pharmacist' | 'cashier'
export type Money = string

export interface ApiError {
  detail: unknown
  code: string
}

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
}

export interface ApprovalToken {
  approval_token: string
  approver_id: number
  approver_name: string
  expires_in_seconds: number
}

export interface Named {
  id: number
  name: string
}

export interface ProductIngredient {
  ingredient_id: number
  name: string
  strength: string | null
}

export interface Product {
  id: number
  name: string
  description: string | null
  presentation: string | null
  category_id: number | null
  category_name: string | null
  barcode: string | null
  sanitary_registration: string | null
  requires_prescription: boolean
  controlled: boolean
  tax_rate: Money
  price: Money
  cost: Money
  min_stock: number
  is_active: boolean
  ingredients: ProductIngredient[]
  stock: number
}

export interface ProductInput {
  name: string
  description: string | null
  presentation: string | null
  category_id: number | null
  barcode: string | null
  sanitary_registration: string | null
  requires_prescription: boolean
  controlled: boolean
  tax_rate: Money
  price: Money
  cost: Money
  min_stock: number
  is_active?: boolean
  ingredients: { ingredient_id: number; strength: string | null }[]
}

export interface Lot {
  id: number
  product_id: number
  lot_number: string
  expiry_date: string
  quantity: number
  unit_cost: Money
  created_at: string
}

export interface Movement {
  id: number
  product_id: number
  lot_id: number
  type: string
  quantity: number
  reason: string | null
  reference_type: string | null
  reference_id: number | null
  user_id: number | null
  created_at: string
}

export interface Supplier {
  id: number
  name: string
  tax_id: string | null
  phone: string | null
  email: string | null
  is_active: boolean
}

export interface PurchaseLine {
  id: number
  product_id: number
  product_name: string
  quantity: number
  unit_cost: Money
  received_quantity: number
}

export interface PurchaseOrder {
  id: number
  supplier: Supplier
  status: 'draft' | 'received' | 'cancelled'
  notes: string | null
  created_at: string
  received_at: string | null
  lines: PurchaseLine[]
}

export interface Customer {
  id: number
  full_name: string
  document_id: string | null
  phone: string | null
  email: string | null
}

export interface PrescriptionItem {
  id: number
  product_id: number
  product_name: string
  max_quantity: number
  dispensed_quantity: number
  remaining: number
}

export interface Prescription {
  id: number
  customer_id: number
  prescriber_name: string
  prescriber_license: string | null
  issued_on: string
  notes: string | null
  file_name: string
  items: PrescriptionItem[]
}

export interface Register {
  id: number
  code: string
  name: string
  is_active: boolean
}

export interface ShiftSummary {
  sales_count: number
  sales_total: Money
  cash_sales: Money
  voided_cash: Money
  cash_refunds: Money
  expected_cash: Money
}

export interface Shift {
  id: number
  register_id: number
  register_code: string
  register_name: string
  user_id: number
  status: 'open' | 'closed'
  opened_at: string
  opening_cash: Money
  closed_at: string | null
  expected_cash: Money | null
  counted_cash: Money | null
  difference: Money | null
  summary: ShiftSummary | null
}

export type PaymentMethod = 'cash' | 'card' | 'transfer'

export interface SaleLine {
  id: number
  product_id: number
  product_name: string
  quantity: number
  unit_price: Money
  tax_rate: Money
  discount_percent: Money
  discount_amount: Money
  line_total: Money
  tax_amount: Money
  prescription_id: number | null
}

export interface SaleReturn {
  id: number
  document_number: number
  reason: string
  refund_method: PaymentMethod
  refund_total: Money
  created_at: string
  lines: { sale_line_id: number; quantity: number; amount: Money }[]
}

export interface Sale {
  id: number
  register_id: number
  register_code: string
  register_name: string
  shift_id: number
  receipt_number: number
  user_id: number
  customer_id: number | null
  approved_by: number | null
  subtotal: Money
  tax_total: Money
  discount_total: Money
  total: Money
  cash_tendered: Money | null
  change_given: Money
  created_at: string
  lines: SaleLine[]
  payments: { method: PaymentMethod; amount: Money; reference: string | null }[]
  void: { document_number: number; reason: string; created_at: string } | null
  returns: SaleReturn[]
}

export interface SaleInput {
  register_id: number
  customer_id: number | null
  lines: {
    product_id: number
    quantity: number
    discount_percent: Money
    lot_id: number | null
    prescription_id: number | null
  }[]
  payments: { method: PaymentMethod; amount: Money; reference: string | null }[]
  cash_tendered: Money | null
}

export interface DailySales {
  date: string
  sales_count: number
  gross_total: Money
  discount_total: Money
  tax_total: Money
  voided_count: number
  voided_total: Money
  returns_total: Money
  net_total: Money
  by_payment_method: { method: PaymentMethod; amount: Money }[]
}

export interface ExpiringLot {
  lot_id: number
  product_id: number
  product_name: string
  lot_number: string
  expiry_date: string
  quantity: number
  days_left: number
  expired: boolean
}

export interface LowStockRow {
  product_id: number
  product_name: string
  stock: number
  min_stock: number
}

export interface StockValuation {
  total_value: Money
  rows: { product_id: number; product_name: string; quantity: number; value: Money }[]
}

export interface Alert {
  id: number
  type: 'expired' | 'expiring' | 'low_stock'
  message: string
  alert_date: string
  acknowledged_at: string | null
}

export interface AuditEntry {
  id: number
  user_id: number | null
  action: string
  entity: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  created_at: string
}
