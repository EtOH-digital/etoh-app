/**
 * Subscription / pricing page (`/subscription`).
 *
 * - Public web URL: `app.etoh.io/subscription` (subscribe before app use).
 * - Lists all plans returned by GET /api/subscription/plans
 * - Highlights the user's current plan from /api/subscription/me
 * - "Subscribe" → POST /api/subscription/checkout → window.location.href (web) or WebBrowser (native)
 * - "Manage" → POST /api/subscription/portal → idem
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import { Colors, Fonts, Radii, Shadow, Spacing } from "@/src/theme";
import { captureException } from "@/src/lib/sentry";

type Plan = {
  id: string;
  name: string;
  tagline: string;
  price_eur: number;
  credits_monthly: number;
  feature_lines: string[];
  features: Record<string, any>;
  stripe_configured: boolean;
};

type MySub = {
  plan_id: string;
  plan_name: string;
  status: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  credits_monthly: number;
};

const FRONTEND_BASE =
  process.env.EXPO_PUBLIC_BACKEND_URL || "https://app.etoh.io";

export default function SubscriptionScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [mySub, setMySub] = useState<MySub | null>(null);
  const [loading, setLoading] = useState(true);
  const [actioning, setActioning] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [p, m] = await Promise.all([
        apiFetch<{ plans: Plan[] }>("/subscription/plans"),
        user ? apiFetch<MySub>("/subscription/me").catch(() => null) : Promise.resolve(null),
      ]);
      setPlans(p.plans);
      setMySub(m as MySub | null);
    } catch (e: any) {
      captureException(e, { context: "subscription.load" });
      Alert.alert("Erreur", e?.message || "Impossible de charger les abonnements");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  const openUrl = useCallback(async (url: string) => {
    if (Platform.OS === "web") {
      // Same-tab redirect = standard SaaS subscription UX
      // @ts-ignore
      window.location.href = url;
      return;
    }
    await WebBrowser.openBrowserAsync(url);
  }, []);

  const handleSubscribe = useCallback(
    async (plan: Plan) => {
      if (!user) {
        router.replace("/(auth)/login");
        return;
      }
      if (plan.price_eur === 0) {
        Alert.alert("Plan Free", "Vous utilisez déjà le plan Free par défaut.");
        return;
      }
      if (!plan.stripe_configured) {
        Alert.alert(
          "Indisponible",
          "Ce plan n'est pas encore disponible. Réessayez plus tard.",
        );
        return;
      }
      try {
        setActioning(plan.id);
        const success = `${FRONTEND_BASE}/subscription/success?session_id={CHECKOUT_SESSION_ID}`;
        const cancel = `${FRONTEND_BASE}/subscription?canceled=1`;
        const res = await apiFetch<{ checkout_url: string }>(
          "/subscription/checkout",
          {
            method: "POST",
            body: { plan_id: plan.id, success_url: success, cancel_url: cancel },
          },
        );
        await openUrl(res.checkout_url);
      } catch (e: any) {
        captureException(e, { context: "subscription.checkout", plan: plan.id });
        Alert.alert("Erreur Stripe", e?.message || "Impossible de démarrer le paiement");
      } finally {
        setActioning(null);
      }
    },
    [user, router, openUrl],
  );

  const handleManage = useCallback(async () => {
    try {
      setActioning("portal");
      const res = await apiFetch<{ portal_url: string }>("/subscription/portal", {
        method: "POST",
      });
      await openUrl(res.portal_url);
    } catch (e: any) {
      captureException(e, { context: "subscription.portal" });
      Alert.alert("Erreur", e?.message || "Impossible d'ouvrir le portail Stripe");
    } finally {
      setActioning(null);
    }
  }, [openUrl]);

  const renderPlanCard = (plan: Plan) => {
    const isCurrent = mySub?.plan_id === plan.id && (mySub.status === "active" || mySub.status === "trialing");
    const isFeatured = plan.id === "pro";
    const cardBorder = isFeatured ? Colors.hex5 : Colors.border;
    const showSubBtn = !isCurrent && plan.price_eur > 0;
    return (
      <View
        key={plan.id}
        style={[
          styles.card,
          { borderColor: cardBorder, borderWidth: isFeatured ? 2 : 1 },
          Shadow.card,
        ]}
      >
        {isFeatured ? (
          <View style={styles.featuredBadge}>
            <Text style={styles.featuredBadgeText}>POPULAIRE</Text>
          </View>
        ) : null}
        {isCurrent ? (
          <View style={styles.currentBadge}>
            <Text style={styles.currentBadgeText}>VOTRE PLAN</Text>
          </View>
        ) : null}
        <Text style={styles.planName}>{plan.name}</Text>
        <Text style={styles.tagline}>{plan.tagline}</Text>

        <View style={styles.priceRow}>
          <Text style={styles.price}>{plan.price_eur === 0 ? "Gratuit" : `${plan.price_eur}€`}</Text>
          {plan.price_eur > 0 ? <Text style={styles.priceSuffix}> / mois HT</Text> : null}
        </View>
        <Text style={styles.creditsLine}>
          <Text style={styles.creditsLineBold}>{plan.credits_monthly}</Text> crédits inclus / mois
        </Text>

        <View style={styles.divider} />

        {plan.feature_lines.map((line) => (
          <View key={line} style={styles.featureRow}>
            <Ionicons name="checkmark" size={18} color={Colors.success} />
            <Text style={styles.featureText}>{line}</Text>
          </View>
        ))}

        <View style={{ height: Spacing.md }} />

        {showSubBtn ? (
          <Pressable
            onPress={() => handleSubscribe(plan)}
            disabled={actioning === plan.id}
            style={({ pressed }) => [
              styles.cta,
              isFeatured ? styles.ctaFeatured : null,
              pressed ? { opacity: 0.8 } : null,
            ]}
            testID={`subscribe-${plan.id}`}
          >
            {actioning === plan.id ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={[styles.ctaText, isFeatured ? styles.ctaTextFeatured : null]}>
                {mySub?.plan_id && mySub.plan_id !== "free" && mySub.status === "active"
                  ? "Changer pour ce plan"
                  : "S'abonner"}
              </Text>
            )}
          </Pressable>
        ) : isCurrent ? (
          <Pressable
            onPress={handleManage}
            disabled={actioning === "portal"}
            style={({ pressed }) => [styles.ctaSecondary, pressed ? { opacity: 0.8 } : null]}
            testID="manage-subscription"
          >
            {actioning === "portal" ? (
              <ActivityIndicator color={Colors.text} />
            ) : (
              <Text style={styles.ctaSecondaryText}>Gérer mon abonnement</Text>
            )}
          </Pressable>
        ) : (
          <View style={styles.ctaSecondary}>
            <Text style={styles.ctaSecondaryText}>Plan par défaut</Text>
          </View>
        )}
      </View>
    );
  };

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={[
        styles.container,
        { paddingTop: insets.top + Spacing.lg, paddingBottom: insets.bottom + Spacing.xl },
      ]}
    >
      <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
        <Ionicons name="chevron-back" size={22} color={Colors.text} />
        <Text style={styles.backText}>Retour</Text>
      </Pressable>

      <Text style={styles.h1}>Choisissez votre plan</Text>
      <Text style={styles.subtitle}>
        Un abonnement de base + des crédits inclus chaque mois. Achetez des crédits supplémentaires à la demande.
      </Text>

      {mySub && mySub.plan_id !== "free" ? (
        <View style={styles.statusCard}>
          <Text style={styles.statusTitle}>Abonnement en cours</Text>
          <Text style={styles.statusBody}>
            <Text style={styles.statusBold}>{mySub.plan_name}</Text> — {mySub.status === "active" ? "Actif" : mySub.status}
            {mySub.current_period_end ? ` · prochaine échéance ${new Date(mySub.current_period_end).toLocaleDateString("fr-FR")}` : ""}
          </Text>
          {mySub.cancel_at_period_end ? (
            <Text style={styles.statusWarn}>Annulation prévue à la fin de la période en cours.</Text>
          ) : null}
        </View>
      ) : null}

      {loading ? (
        <View style={{ paddingVertical: 60, alignItems: "center" }}>
          <ActivityIndicator size="large" color={Colors.text} />
        </View>
      ) : (
        <View style={styles.grid}>{plans?.map(renderPlanCard)}</View>
      )}

      <View style={styles.legal}>
        <Text style={styles.legalText}>
          Paiements sécurisés par Stripe. Vous pouvez annuler à tout moment depuis le portail client.
        </Text>
        <Pressable onPress={() => Linking.openURL("https://etoh.io/cgv")}>
          <Text style={styles.legalLink}>Conditions générales de vente</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.bg },
  container: {
    paddingHorizontal: Spacing.lg,
    maxWidth: 1180,
    width: "100%",
    alignSelf: "center",
  },
  back: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: Spacing.md,
  },
  backText: { fontFamily: Fonts.body, color: Colors.text, fontSize: 15, marginLeft: 4 },
  h1: {
    fontFamily: Fonts.headingBold,
    fontSize: 30,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  subtitle: {
    fontFamily: Fonts.body,
    fontSize: 15,
    color: Colors.textSecondary,
    marginBottom: Spacing.lg,
    lineHeight: 22,
  },
  statusCard: {
    backgroundColor: Colors.studioSoft,
    borderRadius: Radii.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  statusTitle: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.studio, marginBottom: 4 },
  statusBody: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },
  statusBold: { fontFamily: Fonts.bodyMedium },
  statusWarn: { fontFamily: Fonts.body, fontSize: 13, color: Colors.warning, marginTop: 6 },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginHorizontal: -Spacing.sm,
  },
  card: {
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.xl,
    padding: Spacing.lg,
    margin: Spacing.sm,
    flexGrow: 1,
    flexBasis: 260,
    maxWidth: 320,
    minWidth: 240,
    position: "relative",
  },
  featuredBadge: {
    position: "absolute",
    top: -12,
    right: 16,
    backgroundColor: Colors.hex5,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  featuredBadgeText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 10, letterSpacing: 1 },
  currentBadge: {
    position: "absolute",
    top: -12,
    left: 16,
    backgroundColor: Colors.success,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  currentBadgeText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 10, letterSpacing: 1 },
  planName: { fontFamily: Fonts.headingBold, fontSize: 22, color: Colors.text, marginBottom: 2 },
  tagline: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginBottom: Spacing.md },
  priceRow: { flexDirection: "row", alignItems: "baseline" },
  price: { fontFamily: Fonts.headingBold, fontSize: 34, color: Colors.text },
  priceSuffix: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textMuted, marginLeft: 4 },
  creditsLine: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginTop: 4 },
  creditsLineBold: { fontFamily: Fonts.bodyMedium, color: Colors.text },
  divider: { height: 1, backgroundColor: Colors.border, marginVertical: Spacing.md },
  featureRow: { flexDirection: "row", alignItems: "flex-start", marginBottom: 8 },
  featureText: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text, marginLeft: 8, flex: 1, lineHeight: 20 },
  cta: {
    backgroundColor: Colors.brandPrimary,
    borderRadius: Radii.md,
    paddingVertical: 14,
    alignItems: "center",
  },
  ctaFeatured: { backgroundColor: Colors.hex5 },
  ctaText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 15 },
  ctaTextFeatured: { color: "#fff" },
  ctaSecondary: {
    backgroundColor: Colors.bgTertiary,
    borderRadius: Radii.md,
    paddingVertical: 14,
    alignItems: "center",
  },
  ctaSecondaryText: { color: Colors.text, fontFamily: Fonts.bodyMedium, fontSize: 15 },
  legal: {
    marginTop: Spacing.xl,
    alignItems: "center",
  },
  legalText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, textAlign: "center" },
  legalLink: { fontFamily: Fonts.body, fontSize: 12, color: Colors.studio, marginTop: 4, textDecorationLine: "underline" },
});
