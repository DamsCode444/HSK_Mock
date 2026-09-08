<script setup>
import { ref } from 'vue'
import { UserButton } from '@clerk/vue'
import { ArrowRight, Close, Menu } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const mobileOpen = ref(false)

const userButtonAppearance = {
  variables: { colorPrimary: '#a8362a' },
  elements: {
    avatarBox: 'h-9 w-9',
    userButtonPopoverCard: 'border border-black/10 shadow-soft',
  },
}

function closeMobile() {
  mobileOpen.value = false
}

async function logout() {
  await auth.logout()
  closeMobile()
  await router.push('/')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-black/5 bg-paper/90 backdrop-blur-xl">
    <div class="page-shell flex h-[72px] items-center justify-between">
      <RouterLink to="/" class="group flex items-center gap-3" aria-label="Mòkǎo home">
        <span
          class="grid h-10 w-10 place-items-center rounded-xl bg-cinnabar font-serif text-xl font-bold text-white shadow-lg shadow-red-900/15 transition-transform group-hover:-rotate-3"
        >墨</span>
        <span>
          <span class="block font-serif text-lg font-bold leading-none tracking-tight">Mòkǎo</span>
          <span class="mt-1 block text-[10px] font-bold uppercase tracking-[0.19em] text-black/45">HSK mock tests</span>
        </span>
      </RouterLink>

      <nav class="hidden items-center gap-8 text-sm font-semibold md:flex" aria-label="Main navigation">
        <RouterLink to="/#levels" class="transition hover:text-cinnabar">Mock tests</RouterLink>
        <RouterLink to="/materials" class="transition hover:text-cinnabar">Study library</RouterLink>
        <RouterLink v-if="auth.isAuthenticated && !auth.isAdmin" to="/dashboard" class="transition hover:text-cinnabar">
          My progress
        </RouterLink>
        <RouterLink v-if="auth.isAdmin" to="/admin" class="transition hover:text-cinnabar">Admin</RouterLink>
      </nav>

      <div class="hidden items-center gap-3 md:flex">
        <template v-if="auth.isAuthenticated">
          <span class="max-w-40 truncate text-sm font-semibold text-black/60">{{ auth.displayName }}</span>
          <UserButton after-sign-out-url="/" :appearance="userButtonAppearance" />
        </template>
        <template v-else>
          <RouterLink to="/login" class="px-3 py-2 text-sm font-bold hover:text-cinnabar">Sign in</RouterLink>
          <RouterLink
            to="/register"
            class="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-bold text-white transition hover:bg-cinnabar"
          >
            Start practising <el-icon><ArrowRight /></el-icon>
          </RouterLink>
        </template>
      </div>

      <button
        type="button"
        class="grid h-10 w-10 place-items-center rounded-xl border border-black/10 md:hidden"
        :aria-expanded="mobileOpen"
        aria-label="Toggle menu"
        @click="mobileOpen = !mobileOpen"
      >
        <el-icon :size="20"><Close v-if="mobileOpen" /><Menu v-else /></el-icon>
      </button>
    </div>

    <Transition name="mobile-menu">
      <div v-if="mobileOpen" class="border-t border-black/5 bg-paper px-4 pb-5 pt-3 md:hidden">
        <nav class="flex flex-col gap-1 text-sm font-bold">
          <div v-if="auth.isAuthenticated" class="mb-2 flex items-center gap-3 rounded-xl bg-white/70 px-3 py-3">
            <UserButton after-sign-out-url="/" :appearance="userButtonAppearance" />
            <span class="min-w-0 truncate">{{ auth.displayName }}</span>
          </div>
          <RouterLink to="/#levels" class="rounded-xl px-3 py-3 hover:bg-black/5" @click="closeMobile">Mock tests</RouterLink>
          <RouterLink to="/materials" class="rounded-xl px-3 py-3 hover:bg-black/5" @click="closeMobile">Study library</RouterLink>
          <RouterLink v-if="auth.isAuthenticated && !auth.isAdmin" to="/dashboard" class="rounded-xl px-3 py-3 hover:bg-black/5" @click="closeMobile">My progress</RouterLink>
          <RouterLink v-if="auth.isAdmin" to="/admin" class="rounded-xl px-3 py-3 hover:bg-black/5" @click="closeMobile">Admin</RouterLink>
          <template v-if="auth.isAuthenticated">
            <button class="mt-2 rounded-xl border border-black/10 px-3 py-3 text-left" @click="logout">Sign out</button>
          </template>
          <template v-else>
            <RouterLink to="/login" class="rounded-xl px-3 py-3 hover:bg-black/5" @click="closeMobile">Sign in</RouterLink>
            <RouterLink to="/register" class="mt-1 rounded-xl bg-ink px-3 py-3 text-center text-white" @click="closeMobile">Create free account</RouterLink>
          </template>
        </nav>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.mobile-menu-enter-active,
.mobile-menu-leave-active { transition: all 180ms ease; }
.mobile-menu-enter-from,
.mobile-menu-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
