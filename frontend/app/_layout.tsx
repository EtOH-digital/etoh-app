import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFonts as useExpletus, ExpletusSans_400Regular, ExpletusSans_700Bold } from "@expo-google-fonts/expletus-sans";
import { Lato_400Regular, Lato_700Bold, Lato_900Black } from "@expo-google-fonts/lato";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/auth/AuthContext";

SplashScreen.preventAutoHideAsync();

function RootNav() {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuthGroup = (segments[0] as string) === "(auth)";
    if (!user && !inAuthGroup) {
      router.replace("/(auth)/login");
    } else if (user && inAuthGroup) {
      router.replace("/(tabs)");
    }
  }, [user, loading, segments, router]);

  return (
    <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(tabs)" />
    </Stack>
  );
}

export default function RootLayout() {
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
      <AuthProvider>
        <RootNav />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
