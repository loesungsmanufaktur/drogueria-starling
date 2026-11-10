import { createI18n } from 'vue-i18n'

import en from './en'
import es from './es'

export type MessageSchema = typeof es

function initialLocale(): 'es' | 'en' {
  try {
    const saved = localStorage.getItem('ds.locale')
    if (saved === 'es' || saved === 'en') return saved
  } catch {
    // storage unavailable
  }
  return 'es'
}

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'es',
  messages: { es, en },
})

export function setLocale(locale: 'es' | 'en'): void {
  i18n.global.locale.value = locale
  try {
    localStorage.setItem('ds.locale', locale)
  } catch {
    // storage unavailable
  }
}
