<script setup>
import { computed } from 'vue'
import { ClerkLoaded, ClerkLoading, SignIn, SignUp } from '@clerk/vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const mode = computed(() => route.name === 'register' ? 'register' : 'login')
const redirectUrl = computed(() => {
  const requested = route.query.redirect
  if (
    typeof requested === 'string'
    && requested.startsWith('/')
    && !requested.startsWith('//')
    && !requested.startsWith('/login')
    && !requested.startsWith('/register')
  ) {
    return requested
  }
  return '/dashboard'
})

const clerkAppearance = {
  variables: {
    colorPrimary: '#a8362a',
    colorText: '#17211e',
    colorTextSecondary: '#68706d',
    colorBackground: '#ffffff',
    colorInputBackground: '#ffffff',
    colorInputText: '#17211e',
    borderRadius: '0.8rem',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
  },
  elements: {
    rootBox: 'w-full',
    cardBox: 'w-full shadow-none',
    card: 'w-full border-0 bg-transparent p-0 shadow-none',
    headerTitle: 'font-serif text-3xl font-bold text-ink',
    headerSubtitle: 'text-sm text-black/50',
    formButtonPrimary: 'bg-cinnabar hover:bg-ink normal-case shadow-none',
    footerActionLink: 'font-bold text-cinnabar hover:text-ink',
    socialButtonsBlockButton: 'border-black/10 hover:bg-black/[0.03]',
    formFieldInput: 'border-black/10 focus:border-cinnabar focus:ring-cinnabar',
    dividerLine: 'bg-black/10',
    dividerText: 'text-black/40',
  },
}
</script>

<template>
  <section class="soft-grid min-h-[calc(100vh-72px)] py-8 sm:py-12">
    <div
      class="page-shell grid min-h-[650px] overflow-hidden rounded-[1.6rem] border border-black/10 bg-white/80 shadow-soft lg:grid-cols-[.9fr_1.1fr]"
    >
      <aside class="relative hidden overflow-hidden bg-[#17211e] p-12 text-white lg:block">
        <div class="absolute -right-24 -top-24 h-72 w-72 rounded-full border-[60px] border-white/[0.025]" />
        <RouterLink to="/" class="relative inline-flex items-center gap-3" aria-label="Return to Mòkǎo home">
          <span class="grid h-11 w-11 place-items-center rounded-xl bg-cinnabar font-serif text-xl font-bold">墨</span>
          <span>
            <strong class="block font-serif text-xl leading-none">Mòkǎo</strong>
            <small class="mt-1 block text-[10px] font-bold uppercase tracking-[0.19em] text-white/40">HSK mock tests</small>
          </span>
        </RouterLink>

        <div class="relative mt-20 max-w-md">
          <p class="eyebrow !text-gold">Your preparation space</p>
          <blockquote class="mt-7 font-serif text-4xl font-bold leading-[1.25]">
            “功到自然成”
            <small class="mt-5 block font-sans text-sm font-medium leading-7 text-white/55">
              Success comes naturally when the work is done.
            </small>
          </blockquote>
        </div>

        <div class="absolute bottom-12 left-12 right-12 grid grid-cols-3 gap-3 border-t border-white/10 pt-6 text-center">
          <span><b class="block font-serif text-2xl">6</b><small class="text-[10px] uppercase tracking-wider text-white/35">HSK levels</small></span>
          <span><b class="block font-serif text-2xl">Auto</b><small class="text-[10px] uppercase tracking-wider text-white/35">saving</small></span>
          <span><b class="block font-serif text-2xl">Clear</b><small class="text-[10px] uppercase tracking-wider text-white/35">review</small></span>
        </div>
      </aside>

      <div class="flex items-center justify-center px-5 py-10 sm:px-12">
        <div class="w-full max-w-md">
          <RouterLink to="/" class="mb-8 inline-flex items-center gap-3 lg:hidden" aria-label="Return to Mòkǎo home">
            <span class="grid h-10 w-10 place-items-center rounded-xl bg-cinnabar font-serif text-lg font-bold text-white">墨</span>
            <strong class="font-serif text-xl">Mòkǎo</strong>
          </RouterLink>

          <ClerkLoading>
            <div class="grid min-h-[430px] place-items-center" role="status" aria-live="polite">
              <div class="text-center">
                <span class="mx-auto block h-9 w-9 animate-spin rounded-full border-2 border-black/10 border-t-cinnabar" />
                <p class="mt-4 text-sm font-semibold text-black/50">Loading secure sign-in…</p>
              </div>
            </div>
          </ClerkLoading>

          <ClerkLoaded>
            <SignIn
              v-if="mode === 'login'"
              routing="path"
              path="/login"
              sign-up-url="/register"
              :fallback-redirect-url="redirectUrl"
              :appearance="clerkAppearance"
            />
            <SignUp
              v-else
              routing="path"
              path="/register"
              sign-in-url="/login"
              :fallback-redirect-url="redirectUrl"
              :appearance="clerkAppearance"
            />
          </ClerkLoaded>

          <p class="mt-7 text-center text-xs leading-5 text-black/40">
            Authentication is securely managed by Clerk. Your HSK results and progress remain stored in this platform.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
