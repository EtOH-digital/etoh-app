import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";
import { apiFetch } from "@/src/api/client";

type Rec = {
  title: string;
  description: string;
  module: "coach" | "studio" | "pilot";
  icon: string;
};

const MODULE_META: Record<Rec["module"], { color: string; label: string; route: string }> = {
  coach: { color: Colors.coach, label: "Coach", route: "/(tabs)/coach" },
  studio: { color: Colors.studio, label: "Studio", route: "/(tabs)/studio" },
  pilot: { color: Colors.pilot, label: "Pilot", route: "/(tabs)/pilot" },
};

export default function Home() {
  const { user } = useAuth();
  const router = useRouter();
  const [recs, setRecs] = useState<Rec[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<{ recommendations: Rec[] }>("/home/recommendations", {
        method: "POST",
        body: JSON.stringify({ language: lang }),
      });
      setRecs(data.recommendations);
    } catch (e) {
      console.warn("recs", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.business_profile?.language]);

  useEffect(() => {
    load();
  }, [load]);

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return "Bonjour";
    if (h < 18) return "Bon après-midi";
    return "Bonsoir";
  })();

  const firstName = user?.name?.split(" ")[0] || user?.email?.split("@")[0] || "";

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />
        }
        showsVerticalScrollIndicator={false}
      >
        <View style={s.header}>
          <Text style={s.greeting}>
            {greeting}
            {firstName ? `, ${firstName}` : ""}
          </Text>
          <Text style={s.headline}>Votre Directeur Commercial IA</Text>
          <Text style={s.sub}>Vins & Spiritueux</Text>
        </View>

        <View style={s.modulesRow}>
          <ModuleTile
            testID="home-tile-coach"
            label="Coach"
            sub="Que faire ?"
            color={Colors.coach}
            soft={Colors.coachSoft}
            letter="C"
            onPress={() => router.push("/(tabs)/coach")}
          />
          <ModuleTile
            testID="home-tile-studio"
            label="Studio"
            sub="Comment ?"
            color={Colors.studio}
            soft={Colors.studioSoft}
            letter="S"
            onPress={() => router.push("/(tabs)/studio")}
          />
          <ModuleTile
            testID="home-tile-pilot"
            label="Pilot"
            sub="Avec qui ?"
            color={Colors.pilot}
            soft={Colors.pilotSoft}
            letter="P"
            onPress={() => router.push("/(tabs)/pilot")}
          />
        </View>

        <View style={s.sectionHead}>
          <Text style={s.sectionTitle}>3 actions prioritaires cette semaine</Text>
          <Text style={s.sectionSub}>Recommandées par l'IA pour vous</Text>
        </View>

        {loading ? (
          <View style={s.loadingBox}>
            <ActivityIndicator color={Colors.coach} />
            <Text style={s.loadingText}>Analyse de votre activité…</Text>
          </View>
        ) : (
          <View testID="home-recommendations" style={{ gap: Spacing.md }}>
            {recs?.map((r, i) => (
              <TouchableOpacity
                key={i}
                testID={`home-rec-${i}`}
                style={[s.recCard, { borderLeftColor: MODULE_META[r.module].color }]}
                activeOpacity={0.85}
                onPress={() => router.push(MODULE_META[r.module].route as any)}
              >
                <View style={s.recHeader}>
                  <Text style={s.recIcon}>{r.icon}</Text>
                  <View style={[s.recBadge, { backgroundColor: MODULE_META[r.module].color }]}>
                    <Text style={s.recBadgeText}>{MODULE_META[r.module].label}</Text>
                  </View>
                </View>
                <Text style={s.recTitle}>{r.title}</Text>
                <Text style={s.recDesc}>{r.description}</Text>
                <View style={s.recCta}>
                  <Text style={[s.recCtaText, { color: MODULE_META[r.module].color }]}>
                    Lancer →
                  </Text>
                </View>
              </TouchableOpacity>
            ))}
          </View>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function ModuleTile({
  testID, label, sub, color, soft, letter, onPress,
}: {
  testID: string; label: string; sub: string; color: string; soft: string; letter: string; onPress: () => void;
}) {
  return (
    <TouchableOpacity
      testID={testID}
      style={[s.tile, { backgroundColor: soft }]}
      onPress={onPress}
      activeOpacity={0.85}
    >
      <View style={[s.tileMark, { backgroundColor: color }]}>
        <Text style={s.tileLetter}>{letter}</Text>
      </View>
      <Text style={[s.tileLabel, { color }]}>{label}</Text>
      <Text style={s.tileSub}>{sub}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  scroll: { padding: Spacing.lg, paddingBottom: 60 },
  header: { marginBottom: Spacing.lg },
  greeting: { fontSize: 14, color: Colors.textSecondary, marginBottom: Spacing.xs },
  headline: { fontSize: 28, fontWeight: "700", color: Colors.text, fontFamily: "serif", letterSpacing: -0.5, lineHeight: 32 },
  sub: { fontSize: 14, color: Colors.textSecondary, marginTop: 4 },
  modulesRow: { flexDirection: "row", gap: Spacing.sm, marginBottom: Spacing.xl },
  tile: { flex: 1, borderRadius: Radii.lg, padding: Spacing.md, alignItems: "flex-start" },
  tileMark: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center", marginBottom: Spacing.sm },
  tileLetter: { color: "#fff", fontWeight: "700", fontSize: 16, fontFamily: "serif" },
  tileLabel: { fontSize: 15, fontWeight: "700" },
  tileSub: { fontSize: 11, color: Colors.textSecondary, marginTop: 2 },
  sectionHead: { marginBottom: Spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: "600", color: Colors.text, fontFamily: "serif" },
  sectionSub: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },
  loadingBox: { paddingVertical: Spacing.xl, alignItems: "center", gap: Spacing.sm },
  loadingText: { color: Colors.textMuted, fontSize: 13 },
  recCard: {
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1, borderColor: Colors.border,
    borderLeftWidth: 4,
    borderRadius: Radii.lg, padding: Spacing.md,
  },
  recHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: Spacing.sm },
  recIcon: { fontSize: 24 },
  recBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: Radii.pill },
  recBadgeText: { color: "#fff", fontSize: 11, fontWeight: "700", letterSpacing: 0.5 },
  recTitle: { fontSize: 16, fontWeight: "600", color: Colors.text, marginBottom: Spacing.xs },
  recDesc: { fontSize: 13, color: Colors.textSecondary, lineHeight: 18 },
  recCta: { marginTop: Spacing.sm },
  recCtaText: { fontSize: 13, fontWeight: "600" },
});
