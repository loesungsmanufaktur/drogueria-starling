import './assets/main.css'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import { onSessionExpired } from './services/http'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)

onSessionExpired(() => {
  useAuthStore().logout()
  router.push({ name: 'login' })
})

app.mount('#app')
