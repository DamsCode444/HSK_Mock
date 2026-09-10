import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const backendEnv = loadEnv(
    mode,
    fileURLToPath(new URL('../backend', import.meta.url)),
    'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY',
  )
  const backendTarget = env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000'
  const clerkPublishableKey = env.VITE_CLERK_PUBLISHABLE_KEY || backendEnv.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || ''

  return {
    plugins: [
      vue(),
      Components({
        dts: false,
        dirs: [],
        resolvers: [ElementPlusResolver({ importStyle: 'css' })],
      }),
    ],
    define: {
      'import.meta.env.VITE_CLERK_PUBLISHABLE_KEY': JSON.stringify(clerkPublishableKey),
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/media': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
