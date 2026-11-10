import { http } from '@/services/http'
import type {
  Alert,
  ApprovalToken,
  AuditEntry,
  Customer,
  DailySales,
  ExpiringLot,
  Lot,
  LowStockRow,
  Movement,
  Named,
  PaymentMethod,
  Prescription,
  Product,
  ProductInput,
  PurchaseOrder,
  Register,
  Role,
  Sale,
  SaleInput,
  SaleReturn,
  Shift,
  StockValuation,
  Supplier,
  TokenPair,
  User,
} from '@/types/api'

const approvalHeader = (token?: string | null) =>
  token ? { headers: { 'X-Approval-Token': token } } : {}

async function get<T>(url: string, params?: object): Promise<T> {
  return (await http.get<T>(url, { params })).data
}

export const authApi = {
  async login(username: string, password: string): Promise<TokenPair> {
    const form = new URLSearchParams({ username, password })
    return (await http.post<TokenPair>('/auth/token', form)).data
  },
  me: () => get<User>('/auth/me'),
  async approve(username: string, password: string): Promise<ApprovalToken> {
    return (await http.post<ApprovalToken>('/auth/approvals', { username, password })).data
  },
}

export const usersApi = {
  list: () => get<User[]>('/users'),
  create: async (body: { username: string; full_name: string; role: Role; password: string }) =>
    (await http.post<User>('/users', body)).data,
  update: async (
    id: number,
    body: Partial<{ full_name: string; role: Role; is_active: boolean; password: string }>,
  ) => (await http.patch<User>(`/users/${id}`, body)).data,
  audit: (params: { entity?: string; limit?: number }) => get<AuditEntry[]>('/audit', params),
}

export const catalogApi = {
  categories: () => get<Named[]>('/categories'),
  createCategory: async (name: string) => (await http.post<Named>('/categories', { name })).data,
  ingredients: () => get<Named[]>('/ingredients'),
  createIngredient: async (name: string) => (await http.post<Named>('/ingredients', { name })).data,
  search: (params: { q?: string; category_id?: number; active?: boolean | null; limit?: number }) =>
    get<Product[]>('/products', params),
  byBarcode: (code: string) => get<Product>(`/products/barcode/${encodeURIComponent(code)}`),
  product: (id: number) => get<Product>(`/products/${id}`),
  create: async (body: ProductInput) => (await http.post<Product>('/products', body)).data,
  update: async (id: number, body: Partial<ProductInput>) =>
    (await http.patch<Product>(`/products/${id}`, body)).data,
  remove: async (id: number) => {
    await http.delete(`/products/${id}`)
  },
}

export const inventoryApi = {
  lots: (params: { product_id?: number; include_empty?: boolean }) =>
    get<Lot[]>('/inventory/lots', params),
  openingLot: async (body: {
    product_id: number
    lot_number: string
    expiry_date: string
    quantity: number
    unit_cost: string
    reason: string
  }) => (await http.post<Lot>('/inventory/lots', body)).data,
  adjust: async (body: { lot_id: number; quantity: number; reason: string }) =>
    (await http.post<Movement>('/inventory/adjustments', body)).data,
  writeOff: async (lotId: number, reason: string) =>
    (await http.post<Movement>(`/inventory/lots/${lotId}/write-off`, { reason })).data,
  movements: (params: { product_id?: number; limit?: number }) =>
    get<Movement[]>('/inventory/movements', params),
}

export const purchasingApi = {
  suppliers: () => get<Supplier[]>('/suppliers'),
  saveSupplier: async (body: Omit<Supplier, 'id'>, id?: number) =>
    id
      ? (await http.put<Supplier>(`/suppliers/${id}`, body)).data
      : (await http.post<Supplier>('/suppliers', body)).data,
  orders: (params: { status?: string }) => get<PurchaseOrder[]>('/purchase-orders', params),
  createOrder: async (body: {
    supplier_id: number
    notes: string | null
    lines: { product_id: number; quantity: number; unit_cost: string }[]
  }) => (await http.post<PurchaseOrder>('/purchase-orders', body)).data,
  cancel: async (id: number) =>
    (await http.post<PurchaseOrder>(`/purchase-orders/${id}/cancel`)).data,
  receive: async (
    id: number,
    lines: {
      line_id: number
      lot_number: string
      expiry_date: string
      quantity: number
      unit_cost: string | null
    }[],
  ) => (await http.post<PurchaseOrder>(`/purchase-orders/${id}/receive`, { lines })).data,
}

export const customersApi = {
  // Personal data goes in the request body, never in the URL (SEC-3).
  search: async (q: string) => (await http.post<Customer[]>('/customers/search', { q })).data,
  /** Exact NIT/CUI match; rejects with CUSTOMER_NOT_FOUND when there is none. */
  lookup: async (document_id: string) =>
    (await http.post<Customer>('/customers/lookup', { document_id })).data,
  get: (id: number) => get<Customer>(`/customers/${id}`),
  create: async (body: Omit<Customer, 'id'>) =>
    (await http.post<Customer>('/customers', body)).data,
  update: async (id: number, body: Partial<Omit<Customer, 'id'>>) =>
    (await http.patch<Customer>(`/customers/${id}`, body)).data,
  prescriptions: (customerId: number) =>
    get<Prescription[]>(`/customers/${customerId}/prescriptions`),
  async createPrescription(
    meta: {
      customer_id: number
      prescriber_name: string
      prescriber_license: string | null
      issued_on: string
      notes: string | null
      items: { product_id: number; max_quantity: number }[]
    },
    file: File,
  ): Promise<Prescription> {
    const form = new FormData()
    form.append('meta', JSON.stringify(meta))
    form.append('file', file)
    return (await http.post<Prescription>('/prescriptions', form)).data
  },
  async prescriptionFile(id: number): Promise<Blob> {
    return (await http.get<Blob>(`/prescriptions/${id}/file`, { responseType: 'blob' })).data
  },
}

export const posApi = {
  registers: () => get<Register[]>('/registers'),
  createRegister: async (body: { code: string; name: string; is_active: boolean }) =>
    (await http.post<Register>('/registers', body)).data,
  currentShift: () => get<Shift | null>('/shifts/current'),
  openShift: async (register_id: number, opening_cash: string) =>
    (await http.post<Shift>('/shifts/open', { register_id, opening_cash })).data,
  closeShift: async (id: number, counted_cash: string, notes: string | null) =>
    (await http.post<Shift>(`/shifts/${id}/close`, { counted_cash, notes })).data,
  shifts: (params: { status?: string; limit?: number }) => get<Shift[]>('/shifts', params),
  checkout: async (body: SaleInput, approvalToken?: string | null) =>
    (await http.post<Sale>('/sales', body, approvalHeader(approvalToken))).data,
  sales: (params: {
    shift_id?: number
    receipt_number?: number
    register_id?: number
    limit?: number
  }) => get<Sale[]>('/sales', params),
  sale: (id: number) => get<Sale>(`/sales/${id}`),
  void: async (id: number, reason: string, approvalToken?: string | null) =>
    (await http.post<Sale>(`/sales/${id}/void`, { reason }, approvalHeader(approvalToken))).data,
  returnSale: async (
    id: number,
    body: {
      reason: string
      refund_method: PaymentMethod
      lines: { sale_line_id: number; quantity: number }[]
    },
    approvalToken?: string | null,
  ) =>
    (await http.post<SaleReturn>(`/sales/${id}/returns`, body, approvalHeader(approvalToken))).data,
}

export const reportsApi = {
  daily: (day?: string) => get<DailySales>('/reports/daily-sales', day ? { day } : undefined),
  valuation: () => get<StockValuation>('/reports/stock-valuation'),
  expiring: (days?: number) => get<ExpiringLot[]>('/reports/expiring', days ? { days } : undefined),
  lowStock: () => get<LowStockRow[]>('/reports/low-stock'),
  alerts: () => get<Alert[]>('/alerts'),
  acknowledge: async (id: number) => (await http.post<Alert>(`/alerts/${id}/acknowledge`)).data,
  runAlerts: async () => (await http.post<{ created: number }>('/alerts/run')).data,
}
