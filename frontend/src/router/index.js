import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
  },
  {
    path: '/login/:pathMatch(.*)*',
    name: 'login',
    component: () => import('../views/AuthView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/register/:pathMatch(.*)*',
    name: 'register',
    component: () => import('../views/AuthView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { requiresAuth: true, requiresStudent: true },
  },
  {
    path: '/materials',
    name: 'materials',
    component: () => import('../views/MaterialsView.vue'),
  },
  {
    path: '/materials/:slug',
    name: 'material-level',
    component: () => import('../views/MaterialLevelView.vue'),
  },
  {
    path: '/materials/:slug/books/:bookId',
    name: 'material-reader',
    component: () => import('../views/MaterialReaderView.vue'),
    meta: { requiresAuth: true, fullScreen: true },
  },
  {
    path: '/exam/:testId',
    name: 'exam',
    component: () => import('../views/ExamView.vue'),
    meta: { requiresAuth: true, fullScreen: true },
  },
  {
    path: '/results/:attemptId',
    name: 'result',
    component: () => import('../views/ResultView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('../views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth', top: 88 }
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  try {
    await auth.bootstrap()
  } catch {
    // The destination still handles its own API error state. The guard remains UX-only.
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) return { name: 'dashboard' }
  if (to.meta.requiresStudent && auth.isAdmin) return { name: 'admin' }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    const requested = typeof to.query.redirect === 'string' && to.query.redirect.startsWith('/')
      ? to.query.redirect
      : null
    if (requested) return requested
    return { name: auth.isAdmin ? 'admin' : 'dashboard' }
  }
  return true
})

export default router
