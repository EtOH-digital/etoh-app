import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFonts as useExpletus, ExpletusSans_400Regular, ExpletusSans_700Bold } from "@expo-google-fonts/expletus-sans";
import { Lato_400Regular, Lato_700Bold, Lato_900Black } from "@expo-google-fonts/lato";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/auth/AuthContext";
import { I18nProvider, useI18n } from "@/src/i18n/I18nContext";
import { initSentry, Sentry } from "@/src/lib/sentry";

// Initialise Sentry as early as possible (before any other side-effect).
initSentry();

SplashScreen.preventAutoHideAsync();

function RootNav() {
  const { user, loading } = useAuth();
  const { ready: i18nReady, hasPickedLang } = useI18n();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading || !i18nReady) return;
    const top = segments[0] as string | undefined;
    const inAuth = top === "(auth)";
    const inOnboarding = top === "(onboarding)";
    const inLang = top === "(lang)";
    const inPublicHub = top === "hub";

    // Public hub pages are always accessible (no auth, no language picker).
    if (inPublicHub) return;

    // Language not picked yet → force language picker first.
    if (!hasPickedLang) {
      if (!inLang) router.replace("/(lang)");
      return;
    }

    if (!user) {
      if (!inAuth && !inLang) router.replace("/(auth)/login");
      return;
    }
    // Logged in
    const onboarded = (user.business_profile as any)?.onboarded === true;
    if (!onboarded && !inOnboarding) {
      router.replace("/(onboarding)");
    } else if (onboarded && (inAuth || inOnboarding || inLang)) {
      router.replace("/(tabs)");
    }
  }, [user, loading, i18nReady, hasPickedLang, segments, router]);

  return (
    <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
      <Stack.Screen name="(lang)" />
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(onboarding)" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

function RootLayoutInner() {
  const [iconsLoaded, iconsError] = useIconFonts();
  const [brandLoaded] = useExpletus({
    ExpletusSans_400Regular,
    ExpletusSans_700Bold,
    Lato_400Regular,
    Lato_700Bold,
    Lato_900Black,
  });

  const ready = iconsLoaded && brandLoaded;

  useEffect(() => {
    if (ready || iconsError) {
      SplashScreen.hideAsync();
    }
  }, [ready, iconsError]);

  if (!ready && !iconsError) return null;

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <I18nProvider>
        <AuthProvider>
          <RootNav />
        </AuthProvider>
      </I18nProvider>
    </SafeAreaProvider>
  );
}

// Wrap the root with Sentry so unhandled JS errors are reported automatically.
// On web (no DSN configured) or when init failed, `wrap` is essentially a passthrough.
export default Sentry.wrap(RootLayoutInner);
