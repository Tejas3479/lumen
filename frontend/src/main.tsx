import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';
import { useAppStore } from './store/appStore';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* Session 18: Skip-to-content link for keyboard/screen reader users */}
    <a href="#main-content" className="skip-to-content">
      Skip to main content
    </a>
    <App />
  </React.StrictMode>
);

// ── Session 19: Service Worker Registration ──────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        console.log('Lumen SW registered:', reg.scope);

        // Listen for messages from service worker (offline sync complete)
        navigator.serviceWorker.addEventListener('message', (event) => {
          if (event.data?.type === 'OFFLINE_SYNC_COMPLETE') {
            const { synced, skipped } = event.data;
            // Remove synced drafts from appStore
            const { removePendingDraft } = useAppStore.getState();
            [...(synced || []), ...(skipped || [])].forEach((item: { key: string }) => {
              removePendingDraft(item.key);
            });
          }
        });
      })
      .catch((err) => console.warn('Lumen SW registration failed:', err));
  });
}

