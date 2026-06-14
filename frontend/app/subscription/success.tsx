import React, { useEffect } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Fonts, Radii, Spacing } from "@/src/theme";

/**
 * Success landing page hit by Stripe after a successful subscription Checkout.
 * Webhooks do the heavy lifting (creating the subscription in Mongo + crediting
 * the user). We just display a confirmation and route back to /home.
 */
export default function SubscriptionSuccess() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ session_id?: string }>();

  useEffect(() => {
    // Auto-redirect to home after 6s — webhook will have processed by then.
    const t = setTimeout(() => router.replace("/(tabs)"), 6000);
    return () => clearTimeout(t);
  }, [router]);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 80 }]}>
      <View style={styles.iconCircle}>
        <Ionicons name="checkmark" size={48} color="#fff" />
      </View>
      <Text style={styles.title}>Abonnement confirmé !</Text>
      <Text style={styles.body}>
        Merci. Vos crédits seront crédités d'ici quelques secondes.
        Vous pouvez maintenant utiliser toutes les fonctionnalités incluses dans votre plan.
      </Text>
      <ActivityIndicator color={Colors.text} style={{ marginTop: 24 }} />
      <Pressable onPress={() => router.replace("/(tabs)")} style={styles.cta}>
        <Text style={styles.ctaText}>Accéder à l'application</Text>
      </Pressable>
      {params.session_id ? (
        <Text style={styles.session}>Session : {String(params.session_id).slice(0, 24)}…</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg, alignItems: "center", paddingHorizontal: Spacing.lg },
  iconCircle: {
    width: 84, height: 84, borderRadius: 42,
    backgroundColor: Colors.success,
    alignItems: "center", justifyContent: "center",
    marginBottom: Spacing.lg,
  },
  title: { fontFamily: Fonts.headingBold, fontSize: 26, color: Colors.text, marginBottom: Spacing.sm, textAlign: "center" },
  body: { fontFamily: Fonts.body, fontSize: 15, color: Colors.textSecondary, textAlign: "center", lineHeight: 22, maxWidth: 420 },
  cta: { marginTop: Spacing.xl, backgroundColor: Colors.brandPrimary, paddingHorizontal: Spacing.xl, paddingVertical: 14, borderRadius: Radii.md },
  ctaText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 15 },
  session: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: Spacing.lg },
});
