import { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";
import { apiFetch } from "@/src/api/client";

type Rec = { title: string; description: string; module: "coach" | "studio" | "pilot"; icon: string };

type Metrics = {
  etoh_score: number;
  score_components: Record<string, number>;
  kpis: {
    prospects_identified: { current: number; target: number };
    campaigns_sent: { current: number; target: number };
    distributors_contacted: { current: number; target: number };
    markets_analyzed: { current: number; target: number };
    opportunities_detected: { current: number; target: number | null };
  };
  level: { name: string; icon: string; min: number; next: number | null; progress_pct: number; lifetime_points: number };
  sprint: { items: { id: string; title: string; current: number; target: number; done: boolean }[]; progress_pct: number };
};

const MODULE_META: Record<Rec["module"], { color: string; label: string; route: string; medal: string }> = {
  coach: { color: Colors.coach, label: "Coach", route: "/(tabs)/coach", medal: "🥇" },
  studio: { color: Colors.studio, label: "Studio", route: "/(tabs)/studio", medal: "🥈" },
  pilot: { color: Colors.pilot, label: "Pilot", route: "/(tabs)/pilot", medal: "🥉" },
};

export default function Home() {
  const { user } = useAuth();
  const router = useRouter();
  const [recs, setRecs] = useState<Rec[] | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const lang = user?.business_profile?.language || "fr";
      const [m, r] = await Promise.all([
        apiFetch<Metrics>("/dashboard/metrics"),
        apiFetch<{ recommendations: Rec[] }>("/home/recommendations", {
          method: "POST",
          body: JSON.stringify({ language: lang }),
        }),
      ]);
      setMetrics(m);
      setRecs(r.recommendations);
    } catch (e) {
      console.warn("dashboard", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const firstName = user?.name?.split(" ")[0] || user?.email?.split("@")[0] || "";

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={s.header}>
          <View style={s.headerRow}>
            <Image source={require("../../assets/brand/etoh.png")} style={{ width: 70, height: 50 }} resizeMode="contain" />
            <View style={s.creditChip} testID="home-credits">
              <Ionicons name="flash" size={11} color={Colors.brandPrimary} />
              <Text style={s.creditChipText}>{user?.credits ?? 0} crédits</Text>
            </View>
          </View>
          <Text style={s.greeting}>Bonjour{firstName ? `, ${firstName}` : ""}</Text>
          <Text style={s.tagline}>Vendez plus, vendez mieux.</Text>
        </View>

        {loading || !metrics ? (
          <View style={{ alignItems: "center", paddingVertical: Spacing.xxl }}>
            <ActivityIndicator color={Colors.brandPrimary} />
          </View>
        ) : (
          <>
            {/* EtOH Score */}
            <View style={s.scoreCard} testID="dashboard-score">
              <View style={{ flex: 1 }}>
                <Text style={s.scoreLabel}>EtOH Score™</Text>
                <Text style={s.scoreValue}>
                  {metrics.etoh_score}
                  <Text style={s.scoreMax}> / 100</Text>
                </Text>
                <Text style={s.scoreHint}>Votre activité commerciale cette semaine</Text>
              </View>
              <View style={s.scoreRing}>
                <Text style={s.scoreRingText}>{metrics.etoh_score}</Text>
              </View>
            </View>

            {/* Level */}
            <View style={s.levelCard} testID="dashboard-level">
              <Text style={s.levelIcon}>{metrics.level.icon}</Text>
              <View style={{ flex: 1 }}>
                <Text style={s.levelName}>{metrics.level.name}</Text>
                <Text style={s.levelHint}>
                  {metrics.level.lifetime_points} points
                  {metrics.level.next ? ` · ${metrics.level.next - metrics.level.lifetime_points} pour le niveau suivant` : " · niveau max"}
                </Text>
                <View style={s.progressTrack}>
                  <View style={[s.progressFill, { width: `${Math.max(4, metrics.level.progress_pct)}%`, backgroundColor: Colors.hex2 }]} />
                </View>
              </View>
            </View>

            {/* KPIs grid */}
            <Text style={s.sectionTitle}>KPIs de la semaine</Text>
            <View style={s.kpiGrid}>
              <Kpi icon="people-outline" color={Colors.hex1} label="Prospects identifiés" value={metrics.kpis.prospects_identified.current} target={metrics.kpis.prospects_identified.target} />
              <Kpi icon="mail-outline" color={Colors.hex2} label="Campagnes envoyées" value={metrics.kpis.campaigns_sent.current} target={metrics.kpis.campaigns_sent.target} />
              <Kpi icon="briefcase-outline" color={Colors.hex3} label="Distributeurs contactés" value={metrics.kpis.distributors_contacted.current} target={metrics.kpis.distributors_contacted.target} />
              <Kpi icon="globe-outline" color={Colors.hex4} label="Marchés analysés" value={metrics.kpis.markets_analyzed.current} target={metrics.kpis.markets_analyzed.target} />
            </View>

            {/* Weekly Sprint */}
            <Text style={s.sectionTitle}>Mission de la semaine</Text>
            <View style={s.sprintCard} testID="dashboard-sprint">
              <View style={s.sprintHead}>
                <Text style={s.sprintLabel}>Weekly Sprint</Text>
                <Text style={s.sprintPct}>{metrics.sprint.progress_pct}% complété</Text>
              </View>
              <View style={s.progressTrack}>
                <View style={[s.progressFill, { width: `${Math.max(4, metrics.sprint.progress_pct)}%`, backgroundColor: Colors.success }]} />
              </View>
              {metrics.sprint.items.map((it) => (
                <View key={it.id} style={s.sprintRow} testID={`sprint-${it.id}`}>
                  <View style={[s.sprintCheck, it.done && { backgroundColor: Colors.success, borderColor: Colors.success }]}>
                    {it.done && <Ionicons name="checkmark" size={12} color="#fff" />}
                  </View>
                  <Text style={[s.sprintItemText, it.done && { color: Colors.textMuted, textDecorationLine: "line-through" }]}>
                    {it.title}
                  </Text>
                  <Text style={s.sprintCount}>{it.current}/{it.target}</Text>
                </View>
              ))}
            </View>

            {/* AI Recommendations */}
            <Text style={s.sectionTitle}>Actions prioritaires</Text>
            <View testID="home-recommendations" style={{ gap: Spacing.sm }}>
              {recs?.slice(0, 3).map((r, i) => {
                const meta = MODULE_META[r.module];
                return (
                  <TouchableOpacity
                    key={i}
                    testID={`home-rec-${i}`}
                    style={[s.recCard, { borderLeftColor: meta.color }]}
                    activeOpacity={0.85}
                    onPress={() => router.push(meta.route as any)}
                  >
                    <View style={s.recHead}>
                      <Text style={s.recMedal}>{meta.medal}</Text>
                      <View style={[s.recBadge, { backgroundColor: meta.color }]}>
                        <Text style={s.recBadgeText}>{meta.label}</Text>
                      </View>
                    </View>
                    <Text style={s.recTitle}>{r.title}</Text>
                    <Text style={s.recDesc}>{r.description}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Module tiles */}
            <Text style={s.sectionTitle}>Vos 3 modules</Text>
            <View style={s.modulesRow}>
              <ModuleTile testID="home-tile-coach" label="Coach" sub="Learn" color={Colors.coach} soft={Colors.coachSoft} onPress={() => router.push("/(tabs)/coach")} />
              <ModuleTile testID="home-tile-studio" label="Studio" sub="Create" color={Colors.studio} soft={Colors.studioSoft} onPress={() => router.push("/(tabs)/studio")} />
              <ModuleTile testID="home-tile-pilot" label="Pilot" sub="Sell" color={Colors.pilot} soft={Colors.pilotSoft} onPress={() => router.push("/(tabs)/pilot")} />
            </View>
          </>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Kpi({ icon, color, label, value, target }: { icon: any; color: string; label: string; value: number; target: number | null }) {
  const pct = target ? Math.min(100, Math.round((value / target) * 100)) : 0;
  return (
    <View style={s.kpiCard}>
      <View style={[s.kpiIcon, { backgroundColor: color + "22" }]}>
        <Ionicons name={icon} size={16} color={color} />
      </View>
      <Text style={s.kpiValue}>
        {value}
        {target != null && <Text style={s.kpiTarget}> / {target}</Text>}
      </Text>
      <Text style={s.kpiLabel} numberOfLines={2}>{label}</Text>
      {target != null && (
        <View style={s.kpiTrack}>
          <View style={[s.kpiFill, { width: `${Math.max(4, pct)}%`, backgroundColor: color }]} />
        </View>
      )}
    </View>
  );
}

function ModuleTile({ testID, label, sub, color, soft, onPress }: { testID: string; label: string; sub: string; color: string; soft: string; onPress: () => void }) {
  return (
    <TouchableOpacity testID={testID} style={[s.tile, { backgroundColor: soft }]} onPress={onPress} activeOpacity={0.85}>
      <View style={[s.tileMark, { backgroundColor: color }]}>
        <Text style={s.tileLetter}>{label.charAt(0)}</Text>
      </View>
      <Text style={[s.tileLabel, { color }]}>{label}</Text>
      <Text style={s.tileSub}>{sub}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  scroll: { padding: Spacing.lg, paddingBottom: 60 },
  header: { marginBottom: Spacing.lg, paddingTop: Spacing.sm },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  creditChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: Colors.brandPrimary, backgroundColor: Colors.bgSecondary, borderRadius: Radii.pill },
  creditChipText: { color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 12 },
  greeting: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, marginTop: Spacing.md, marginBottom: 2 },
  tagline: { fontFamily: Fonts.headingBold, fontSize: 24, color: Colors.text, letterSpacing: -0.5, lineHeight: 30 },

  scoreCard: { flexDirection: "row", alignItems: "center", backgroundColor: Colors.brandPrimary, borderRadius: Radii.lg, padding: Spacing.md, gap: Spacing.md },
  scoreLabel: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: "rgba(255,255,255,0.7)", textTransform: "uppercase", letterSpacing: 1.5, fontWeight: "700" },
  scoreValue: { fontFamily: Fonts.headingBold, fontSize: 36, color: "#fff", lineHeight: 42, marginTop: 4 },
  scoreMax: { fontFamily: Fonts.body, fontSize: 16, color: "rgba(255,255,255,0.5)" },
  scoreHint: { fontFamily: Fonts.body, fontSize: 12, color: "rgba(255,255,255,0.65)", marginTop: 2 },
  scoreRing: { width: 70, height: 70, borderRadius: 35, borderWidth: 4, borderColor: Colors.hex4, alignItems: "center", justifyContent: "center" },
  scoreRingText: { fontFamily: Fonts.headingBold, fontSize: 22, color: "#fff" },

  levelCard: { flexDirection: "row", alignItems: "center", gap: Spacing.md, backgroundColor: Colors.bgSecondary, borderRadius: Radii.lg, padding: Spacing.md, borderWidth: 1, borderColor: Colors.border, marginTop: Spacing.sm },
  levelIcon: { fontSize: 28 },
  levelName: { fontFamily: Fonts.headingBold, fontSize: 16, color: Colors.text },
  levelHint: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 2 },

  sectionTitle: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text, textTransform: "uppercase", letterSpacing: 1, marginTop: Spacing.xl, marginBottom: Spacing.sm },

  kpiGrid: { flexDirection: "row", flexWrap: "wrap", gap: Spacing.sm },
  kpiCard: { width: "48%", backgroundColor: Colors.bgSecondary, borderRadius: Radii.md, padding: Spacing.md, borderWidth: 1, borderColor: Colors.border },
  kpiIcon: { width: 28, height: 28, borderRadius: 8, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  kpiValue: { fontFamily: Fonts.headingBold, fontSize: 22, color: Colors.text },
  kpiTarget: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textMuted },
  kpiLabel: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textSecondary, marginTop: 2 },
  kpiTrack: { height: 4, backgroundColor: Colors.bgTertiary, borderRadius: 2, marginTop: 6, overflow: "hidden" },
  kpiFill: { height: 4, borderRadius: 2 },

  sprintCard: { backgroundColor: Colors.bgSecondary, borderRadius: Radii.lg, padding: Spacing.md, borderWidth: 1, borderColor: Colors.border },
  sprintHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  sprintLabel: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700" },
  sprintPct: { fontFamily: Fonts.headingBold, fontSize: 13, color: Colors.success },
  progressTrack: { height: 6, backgroundColor: Colors.bgTertiary, borderRadius: 3, overflow: "hidden", marginTop: 8 },
  progressFill: { height: 6, borderRadius: 3 },
  sprintRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: Spacing.sm },
  sprintCheck: { width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: Colors.border, alignItems: "center", justifyContent: "center" },
  sprintItemText: { flex: 1, fontFamily: Fonts.body, fontSize: 13, color: Colors.text },
  sprintCount: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textMuted, fontWeight: "700" },

  recCard: { backgroundColor: Colors.bgSecondary, borderWidth: 1, borderColor: Colors.border, borderLeftWidth: 4, borderRadius: Radii.lg, padding: Spacing.md },
  recHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  recMedal: { fontSize: 20 },
  recBadge: { paddingHorizontal: 9, paddingVertical: 3, borderRadius: Radii.pill },
  recBadgeText: { color: "#fff", fontSize: 10, fontFamily: Fonts.bodyMedium, fontWeight: "700", letterSpacing: 0.5 },
  recTitle: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text },
  recDesc: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, marginTop: 2, lineHeight: 17 },

  modulesRow: { flexDirection: "row", gap: Spacing.sm },
  tile: { flex: 1, borderRadius: Radii.lg, padding: Spacing.md, alignItems: "flex-start" },
  tileMark: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center", marginBottom: Spacing.sm },
  tileLetter: { color: "#fff", fontFamily: Fonts.headingBold, fontSize: 16 },
  tileLabel: { fontFamily: Fonts.headingBold, fontSize: 15 },
  tileSub: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textSecondary, marginTop: 2 },
});
