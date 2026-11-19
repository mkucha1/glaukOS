import fs from 'node:fs';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

// HTTPS for phones on the ship LAN: put mkcert output in certs/ (see README).
function https() {
  const cert = 'certs/cert.pem';
  const key = 'certs/key.pem';
  return fs.existsSync(cert) && fs.existsSync(key)
    ? { cert: fs.readFileSync(cert), key: fs.readFileSync(key) }
    : undefined;
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
      manifest: {
        name: 'Mózg statku',
        short_name: 'Ship Brain',
        description: 'Voice reports to approved log entries, on board and offline.',
        display: 'standalone',
        orientation: 'any',
        start_url: '/',
        scope: '/',
        theme_color: '#122C4F',
        background_color: '#122C4F',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // App shell only. API responses are never cached: state lives in IndexedDB + MQTT.
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
      },
    }),
  ],
  server: { host: true, https: https() },
  preview: { host: true, https: https() },
});
