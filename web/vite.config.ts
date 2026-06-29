import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // PWA — installable on iOS/Android home screen.
    // autoUpdate (was 'prompt'): every Railway deploy auto-applies on next launch.
    // 'prompt' left the Capacitor/Electron WebViews (which only background, never truly
    // reload) stuck on the cached old app shell until the user caught the reload prompt —
    // so new UI silently never appeared. With skipWaiting+clientsClaim below, the new SW
    // takes over and the page refreshes itself on relaunch.
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['logo-profile.svg'],
      manifest: {
        name: 'BusyTradersDesk',
        short_name: 'BTDesk',
        description: 'The trading desk for busy professionals — scans, alerts, and a pattern library',
        theme_color: '#0d1117',
        background_color: '#0d1117',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          { src: '/logo-profile.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Take over immediately on update so Capacitor WebView (which doesn't
        // truly close tabs between app kills) picks up new assets on next
        // launch instead of staying on the old waiting SW indefinitely.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 5 },
              networkTimeoutSeconds: 5,
            },
          },
        ],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        cookieDomainRewrite: 'localhost',
      },
    },
  },
})
