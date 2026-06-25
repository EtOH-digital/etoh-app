/**
 * PWAInstallPrompt — Bannière discrète d'installation PWA (web only)
 *
 * - Android / Chrome / Edge : capture beforeinstallprompt + bouton "Installer"
 * - iOS Safari : pas d'API native -> affiche un mini-tooltip "Ajouter à l'écran d'accueil"
 * - Dismissable : stocke le choix dans localStorage pour ne pas réapparaître
 * - Auto-hide si l'app est déjà installée (display-mode: standalone)
 */
import React, { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

const DISMISS_KEY = 'etoh.pwa.installPromptDismissedAt';
const DISMISS_TTL_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

export default function PWAInstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosHint, setIosHint] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    // ── Inject PWA <head> tags once (manifest, theme color, apple meta…) ──
    // We do this here (rather than in app/+html.tsx) because Expo Router's
    // `output: "single"` mode ignores +html.tsx at export time.
    const head = document.head;
    const ensureTag = (selector: string, create: () => HTMLElement) => {
      if (!head.querySelector(selector)) head.appendChild(create());
    };
    const meta = (name: string, content: string, attr: 'name' | 'property' = 'name') => {
      const sel = `meta[${attr}="${name}"]`;
      ensureTag(sel, () => {
        const m = document.createElement('meta');
        m.setAttribute(attr, name);
        m.setAttribute('content', content);
        return m;
      });
    };
    const link = (rel: string, href: string, extra?: Record<string, string>) => {
      const sel = `link[rel="${rel}"][href="${href}"]`;
      ensureTag(sel, () => {
        const l = document.createElement('link');
        l.setAttribute('rel', rel);
        l.setAttribute('href', href);
        if (extra) Object.entries(extra).forEach(([k, v]) => l.setAttribute(k, v));
        return l;
      });
    };
    link('manifest', '/manifest.webmanifest');
    link('apple-touch-icon', '/apple-touch-icon.png');
    link('icon', '/icon-192.png', { type: 'image/png', sizes: '192x192' });
    link('icon', '/icon-512.png', { type: 'image/png', sizes: '512x512' });
    meta('theme-color', '#2C2D2C');
    meta('application-name', 'EtOH AI');
    meta('apple-mobile-web-app-capable', 'yes');
    meta('apple-mobile-web-app-title', 'EtOH AI');
    meta('apple-mobile-web-app-status-bar-style', 'black-translucent');
    meta('mobile-web-app-capable', 'yes');
    meta('msapplication-TileColor', '#2C2D2C');

    // Register the service worker (idempotent)
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker
        .register('/sw.js')
        .catch((err) => console.warn('[PWA] SW registration failed:', err));
    }

    // ── Install-prompt UI logic ──

    // Don't show if already installed (standalone display mode)
    const isStandalone =
      window.matchMedia?.('(display-mode: standalone)')?.matches ||
      (window.navigator as any).standalone === true;
    if (isStandalone) return;

    // Honour previous dismissal (14-day cooldown)
    try {
      const raw = window.localStorage?.getItem(DISMISS_KEY);
      if (raw) {
        const ts = parseInt(raw, 10);
        if (!isNaN(ts) && Date.now() - ts < DISMISS_TTL_MS) return;
      }
    } catch {}

    // Android / Chrome path: listen for the install prompt event
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setVisible(true);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);

    // iOS Safari fallback: show a hint after a short delay if BIP never fires
    const ua = window.navigator.userAgent || '';
    const isIOS = /iPhone|iPad|iPod/i.test(ua) && !(window as any).MSStream;
    const isSafari = /^((?!chrome|android|crios|fxios).)*safari/i.test(ua);
    if (isIOS && isSafari) {
      const t = setTimeout(() => {
        setIosHint(true);
        setVisible(true);
      }, 2500);
      return () => {
        window.removeEventListener('beforeinstallprompt', onBeforeInstall);
        clearTimeout(t);
      };
    }

    return () => window.removeEventListener('beforeinstallprompt', onBeforeInstall);
  }, []);

  if (Platform.OS !== 'web' || !visible) return null;

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage?.setItem(DISMISS_KEY, String(Date.now()));
    } catch {}
  };

  const install = async () => {
    if (!deferred) return;
    try {
      await deferred.prompt();
      const { outcome } = await deferred.userChoice;
      if (outcome === 'accepted' || outcome === 'dismissed') {
        setVisible(false);
        setDeferred(null);
        try {
          window.localStorage?.setItem(DISMISS_KEY, String(Date.now()));
        } catch {}
      }
    } catch {
      dismiss();
    }
  };

  return (
    <View style={styles.container} pointerEvents="box-none">
      <View style={styles.card}>
        <View style={styles.textCol}>
          <Text style={styles.title}>Installer EtOH AI</Text>
          <Text style={styles.subtitle} numberOfLines={2}>
            {iosHint
              ? 'Appuyez sur Partager puis "Sur l\'écran d\'accueil" pour installer.'
              : 'Accédez à EtOH AI plus rapidement depuis votre écran d\'accueil.'}
          </Text>
        </View>
        <View style={styles.actionsCol}>
          {!iosHint && deferred ? (
            <TouchableOpacity onPress={install} style={styles.installBtn} activeOpacity={0.85}>
              <Text style={styles.installBtnText}>Installer</Text>
            </TouchableOpacity>
          ) : null}
          <TouchableOpacity onPress={dismiss} style={styles.dismissBtn} activeOpacity={0.6} hitSlop={8}>
            <Text style={styles.dismissBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 16,
    alignItems: 'center',
    zIndex: 9999,
    paddingHorizontal: 12,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2C2D2C',
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 16,
    width: '100%',
    maxWidth: 480,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
  textCol: { flex: 1, paddingRight: 12 },
  title: { color: '#FFFFFF', fontSize: 15, fontWeight: '700', marginBottom: 2 },
  subtitle: { color: 'rgba(255,255,255,0.78)', fontSize: 12, lineHeight: 16 },
  actionsCol: { flexDirection: 'row', alignItems: 'center' },
  installBtn: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 10,
    marginRight: 6,
  },
  installBtnText: { color: '#2C2D2C', fontSize: 13, fontWeight: '700' },
  dismissBtn: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  dismissBtnText: { color: 'rgba(255,255,255,0.65)', fontSize: 16, fontWeight: '600' },
});
