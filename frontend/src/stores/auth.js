import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useAuth as useClerkAuth, useClerk, useUser as useClerkUser } from '@clerk/vue'
import { http, unwrap } from '../services/http'

export const useAuthStore = defineStore('auth', () => {
  const clerk = useClerk()
  const {
    isLoaded: isClerkLoaded,
    isSignedIn,
    sessionId,
    signOut,
  } = useClerkAuth()
  const { user: clerkUser } = useClerkUser()
  const user = ref(null)
  const bootstrapped = ref(false)
  const profileSessionId = ref(null)
  let bootstrapPromise = null

  const isAuthenticated = computed(() => Boolean(isClerkLoaded.value && isSignedIn.value))
  const isAdmin = computed(() => String(user.value?.role || '').toLowerCase() === 'admin')
  const displayName = computed(() => (
    user.value?.username
    || user.value?.name
    || clerkUser.value?.fullName
    || clerkUser.value?.firstName
    || clerkUser.value?.primaryEmailAddress?.emailAddress?.split('@')[0]
    || 'Student'
  ))

  async function fetchMe() {
    const { data } = await http.get('/auth/me')
    user.value = unwrap(data, ['user'])
    profileSessionId.value = sessionId.value
    return user.value
  }

  async function waitForClerk() {
    if (isClerkLoaded.value) return true
    return new Promise((resolve) => {
      let stop = () => {}
      const timeout = window.setTimeout(() => {
        stop()
        resolve(false)
      }, 15000)
      stop = watch(isClerkLoaded, (loaded) => {
        if (!loaded) return
        window.clearTimeout(timeout)
        stop()
        resolve(true)
      }, { immediate: true })
    })
  }

  async function bootstrap(force = false) {
    if (bootstrapPromise) return bootstrapPromise
    bootstrapPromise = (async () => {
      const loaded = await waitForClerk()
      if (!loaded || !isSignedIn.value) {
        clearSession()
        bootstrapped.value = true
        return null
      }

      if (!force && user.value && profileSessionId.value === sessionId.value) {
        bootstrapped.value = true
        return user.value
      }

      await fetchMe()
      bootstrapped.value = true
      return user.value
    })()
    try {
      return await bootstrapPromise
    } finally {
      bootstrapPromise = null
    }
  }

  function clearSession() {
    user.value = null
    profileSessionId.value = null
    bootstrapped.value = false
  }

  async function logout() {
    try {
      if (typeof signOut.value === 'function') await signOut.value()
      else if (clerk.value) await clerk.value.signOut()
    } finally {
      clearSession()
    }
  }

  watch(sessionId, (nextSessionId, previousSessionId) => {
    if (nextSessionId === previousSessionId) return
    clearSession()
  })

  return {
    user,
    bootstrapped,
    isClerkLoaded,
    isAuthenticated,
    isAdmin,
    displayName,
    fetchMe,
    bootstrap,
    logout,
    clearSession,
  }
})
