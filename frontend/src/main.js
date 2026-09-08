import { clerkPlugin } from '@clerk/vue'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/main.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
if (!PUBLISHABLE_KEY) {
  throw new Error('Missing Clerk publishable key. Configure VITE_CLERK_PUBLISHABLE_KEY or the backend publishable-key fallback.')
}

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(ElementPlus)
app.use(clerkPlugin, {
  publishableKey: PUBLISHABLE_KEY,
  signInUrl: '/login',
  signUpUrl: '/register',
  signInFallbackRedirectUrl: '/dashboard',
  signUpFallbackRedirectUrl: '/dashboard',
})

window.addEventListener('hsk:unauthorized', () => {
  const auth = useAuthStore(pinia)
  const currentRoute = router.currentRoute.value
  auth.clearSession()
  ElMessage.error('The API could not verify your Clerk session. Please try again or sign out and back in.')
  if (currentRoute.meta.requiresAuth) {
    router.replace({ name: 'home', query: { auth_error: 'session' } })
  }
})

app.use(router)
app.mount('#app')
