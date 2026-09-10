<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { UserButton } from '@clerk/vue'
import { ArrowRight, Close, Menu } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)

const userButtonAppearance = {
  variables: { colorPrimary: '#b73b2e', borderRadius: '0.8rem' },
  elements: {
    avatarBox: 'h-10 w-10 ring-2 ring-white shadow-sm',
    userButtonPopoverCard: 'border border-black/10 shadow-soft',
  },
}

const navigation = computed(() => {
  const items = [
    { label: 'Mock tests', to: { path: '/', hash: '#levels' }, section: 'tests' },
    { label: 'Study library', to: '/materials', section: 'materials' },
  ]
  if (auth.isAuthenticated && !auth.isAdmin) {
    items.push({ label: 'My progress', to: '/dashboard', section: 'dashboard' })
  }
  if (auth.isAdmin) {
    items.push({ label: 'Administration', to: '/admin', section: 'admin' })
  }
  return items
})

function isActive(item) {
  if (item.section === 'tests') return route.path === '/'
  if (item.section === 'materials') return route.path.startsWith('/materials')
  return route.path.startsWith(`/${item.section}`)
}

function closeMobile() {
  mobileOpen.value = false
}

async function logout() {
  await auth.logout()
  closeMobile()
  await router.push('/')
}

let previousOverflow = ''
watch(mobileOpen, (open) => {
  if (open) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = previousOverflow
  }
})

watch(() => route.fullPath, closeMobile)

onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
})
</script>

<template>
  <header class="app-header" @keydown.esc="closeMobile">
    <div class="page-shell flex h-[68px] items-center justify-between gap-5 md:h-[76px]">
      <RouterLink to="/" class="brand group" aria-label="Mòkǎo home">
        <span class="brand-mark" aria-hidden="true">
          <span>墨</span>
          <i />
        </span>
        <span class="min-w-0">
          <span class="block font-serif text-lg font-bold leading-none tracking-[-0.025em]">Mòkǎo</span>
          <span class="mt-1.5 block text-[9px] font-extrabold uppercase tracking-[0.2em] text-black/45">
            HSK preparation
          </span>
        </span>
      </RouterLink>

      <nav class="hidden items-center gap-1 rounded-2xl border border-black/[0.06] bg-white/55 p-1.5 lg:flex" aria-label="Main navigation">
        <RouterLink
          v-for="item in navigation"
          :key="item.label"
          :to="item.to"
          class="nav-link"
          :class="{ 'nav-link--active': isActive(item) }"
          :aria-current="isActive(item) ? 'page' : undefined"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="hidden min-w-[220px] items-center justify-end gap-3 lg:flex">
        <template v-if="auth.isAuthenticated">
          <div class="min-w-0 text-right">
            <span class="block max-w-36 truncate text-sm font-extrabold">{{ auth.displayName }}</span>
            <span class="block text-[10px] font-bold uppercase tracking-wider text-black/40">
              {{ auth.isAdmin ? 'Administrator' : 'Student account' }}
            </span>
          </div>
          <UserButton after-sign-out-url="/" :appearance="userButtonAppearance" />
        </template>
        <template v-else>
          <RouterLink to="/login" class="btn-quiet !min-h-10 !border-transparent !bg-transparent !px-3">
            Sign in
          </RouterLink>
          <RouterLink to="/register" class="btn-primary !min-h-10 !px-4">
            Start free <el-icon><ArrowRight /></el-icon>
          </RouterLink>
        </template>
      </div>

      <button
        type="button"
        class="menu-trigger lg:hidden"
        :aria-expanded="mobileOpen"
        aria-controls="mobile-navigation"
        :aria-label="mobileOpen ? 'Close navigation' : 'Open navigation'"
        @click="mobileOpen = !mobileOpen"
      >
        <el-icon :size="21"><Close v-if="mobileOpen" /><Menu v-else /></el-icon>
      </button>
    </div>

    <Transition name="menu-fade">
      <button
        v-if="mobileOpen"
        type="button"
        class="menu-backdrop lg:hidden"
        tabindex="-1"
        aria-label="Close navigation"
        @click="closeMobile"
      />
    </Transition>

    <Transition name="mobile-menu">
      <div v-if="mobileOpen" id="mobile-navigation" class="mobile-panel lg:hidden">
        <div v-if="auth.isAuthenticated" class="mb-3 flex items-center gap-3 rounded-2xl border border-black/[0.07] bg-white p-3.5">
          <UserButton after-sign-out-url="/" :appearance="userButtonAppearance" />
          <span class="min-w-0">
            <strong class="block truncate text-sm">{{ auth.displayName }}</strong>
            <small class="mt-0.5 block text-[10px] font-bold uppercase tracking-wider text-black/40">
              {{ auth.isAdmin ? 'Administrator' : 'Student account' }}
            </small>
          </span>
        </div>

        <nav class="grid gap-1.5" aria-label="Mobile navigation">
          <RouterLink
            v-for="item in navigation"
            :key="item.label"
            :to="item.to"
            class="mobile-nav-link"
            :class="{ 'mobile-nav-link--active': isActive(item) }"
            :aria-current="isActive(item) ? 'page' : undefined"
            @click="closeMobile"
          >
            {{ item.label }}
            <span aria-hidden="true">→</span>
          </RouterLink>
        </nav>

        <div class="mt-4 border-t border-black/[0.07] pt-4">
          <button v-if="auth.isAuthenticated" type="button" class="btn-quiet w-full" @click="logout">
            Sign out securely
          </button>
          <div v-else class="grid grid-cols-2 gap-2.5">
            <RouterLink to="/login" class="btn-quiet" @click="closeMobile">Sign in</RouterLink>
            <RouterLink to="/register" class="btn-primary" @click="closeMobile">Start free</RouterLink>
          </div>
        </div>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  z-index: 40;
  top: 0;
  border-bottom: 1px solid rgba(23, 33, 30, 0.07);
  background: rgba(247, 244, 237, 0.9);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.6) inset;
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
}

.brand {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.7rem;
}

.brand-mark {
  position: relative;
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  place-items: center;
  overflow: hidden;
  border-radius: 0.85rem;
  color: white;
  background: linear-gradient(145deg, #cb4b39, #9d3026);
  box-shadow: 0 9px 22px rgba(157, 48, 38, 0.22);
  font-family: Georgia, "Noto Serif SC", serif;
  font-size: 1.15rem;
  font-weight: 800;
  transition: transform 180ms ease, box-shadow 180ms ease;
}

.brand-mark i {
  position: absolute;
  top: 0.35rem;
  right: 0.35rem;
  width: 0.25rem;
  height: 0.25rem;
  border-radius: 999px;
  background: #f2c878;
}

.brand:hover .brand-mark {
  transform: translateY(-1px) rotate(-2deg);
  box-shadow: 0 12px 27px rgba(157, 48, 38, 0.27);
}

.nav-link {
  position: relative;
  border-radius: 0.8rem;
  padding: 0.65rem 0.9rem;
  color: rgba(23, 33, 30, 0.62);
  font-size: 0.82rem;
  font-weight: 750;
  transition: color 160ms ease, background-color 160ms ease;
}

.nav-link:hover {
  color: var(--ink);
  background: rgba(255, 255, 255, 0.7);
}

.nav-link--active {
  color: var(--ink);
  background: white;
  box-shadow: 0 3px 12px rgba(23, 33, 30, 0.07);
}

.nav-link--active::after {
  position: absolute;
  right: 0.8rem;
  bottom: 0.3rem;
  left: 0.8rem;
  height: 2px;
  border-radius: 999px;
  content: '';
  background: var(--cinnabar);
}

.menu-trigger {
  display: grid;
  width: 2.65rem;
  height: 2.65rem;
  flex: none;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 0.85rem;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.7);
  transition: border-color 160ms ease, background-color 160ms ease;
}

.menu-trigger:hover {
  border-color: rgba(183, 59, 46, 0.25);
  background: #fff;
}

.menu-backdrop {
  position: fixed;
  z-index: 0;
  inset: var(--header-height) 0 0;
  width: 100%;
  border: 0;
  background: rgba(12, 20, 17, 0.35);
  backdrop-filter: blur(3px);
}

.mobile-panel {
  position: absolute;
  z-index: 1;
  top: calc(100% + 0.65rem);
  right: 0.65rem;
  left: 0.65rem;
  border: 1px solid var(--line);
  border-radius: 1.25rem;
  background: rgba(250, 248, 243, 0.98);
  padding: 0.8rem;
  box-shadow: var(--shadow-md);
}

.mobile-nav-link {
  display: flex;
  min-height: 3rem;
  align-items: center;
  justify-content: space-between;
  border-radius: 0.85rem;
  padding: 0.7rem 0.9rem;
  color: rgba(23, 33, 30, 0.68);
  font-size: 0.9rem;
  font-weight: 750;
}

.mobile-nav-link:hover,
.mobile-nav-link--active {
  color: var(--ink);
  background: white;
}

.mobile-nav-link--active span {
  color: var(--cinnabar);
}

.mobile-menu-enter-active,
.mobile-menu-leave-active,
.menu-fade-enter-active,
.menu-fade-leave-active {
  transition: opacity 180ms ease, transform 180ms ease;
}

.mobile-menu-enter-from,
.mobile-menu-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.985);
}

.menu-fade-enter-from,
.menu-fade-leave-to {
  opacity: 0;
}

@media (min-width: 1024px) {
  .menu-trigger,
  .menu-backdrop,
  .mobile-panel {
    display: none;
  }
}

@media (max-width: 420px) {
  .brand-mark {
    width: 2.45rem;
    height: 2.45rem;
  }
}
</style>
