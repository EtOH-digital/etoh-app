import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";

type Plan = {
  summary: string;
  targets: { name: string; city: string; type: string; approach: string }[];
  tasks: { title: string; deadline: string }[];
};

const TARGET_TYPES = [
  { id: "restaurants", label: "Restaurants", icon: "restaurant-outline" as const },
  { id: "importers", label: "Importateurs", icon: "globe-outline" as const },
  { id: "distributors", label: "Distributeurs", icon: "cube-outline" as const },
  { id: "wine_shops", label: "Cavistes", icon: "wine-outline" as const },
  { id: "other", label: "Autre", icon: "ellipsis-horizontal-outline" as const },
];

export default function Pilot() {
  const { user } = useAuth();
  const [targetType, setTargetType] = useState("restaurants");
  const [region, setRegion] = useState("");
  const [productFocus, setProductFocus] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [completed, setCompleted] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const launch = async () => {
    if (!region.trim()) {
      setErr("Indiquez une région cible");
      return;
    }
    setErr(null);
    setLoading(true);
    setPlan(null);
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<{ plan: Plan }>("/pilot/plan", {
        method: "POST",
        body: JSON.stringify({
          target_type: targetType,
          region: region.trim(),
          product_focus: productFocus.trim() || undefined,
          language: lang,
        }),
      });
      setPlan(data.plan);
      setCompleted({});
    } catch (e: any) {
      setErr(e.message || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <View style={s.header}>
        <View style={[s.brandDot, { backgroundColor: Colors.pilot }]}>
          <Text style={s.brandLetter}>P</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Pilot</Text>
          <Text style={s.headerSub}>Avec qui agir ?</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: Spacing.lg, paddingBottom: 60 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Text style={s.label}>Type de cible</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: Spacing.sm, paddingVertical: Spacing.xs }}
          >
            {TARGET_TYPES.map((t) => {
              const active = targetType === t.id;
              return (
                <TouchableOpacity
                  key={t.id}
                  testID={`pilot-target-${t.id}`}
                  style={[s.chip, active && { backgroundColor: Colors.pilot, borderColor: Colors.pilot }]}
                  onPress={() => setTargetType(t.id)}
                >
                  <Ionicons name={t.icon} size={14} color={active ? "#fff" : Colors.text} />
                  <Text style={[s.chipText, active && { color: "#fff" }]}>{t.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <Text style={[s.label, { marginTop: Spacing.lg }]}>Région / Pays cible</Text>
          <TextInput
            testID="pilot-region-input"
            style={s.input}
            placeholder="Ex. Paris, Belgique, USA…"
            placeholderTextColor={Colors.textMuted}
            value={region}
            onChangeText={setRegion}
          />

          <Text style={[s.label, { marginTop: Spacing.md }]}>Produit ciblé (optionnel)</Text>
          <TextInput
            testID="pilot-product-input"
            style={s.input}
            placeholder="Ex. Bordeaux rouge, Cognac VS…"
            placeholderTextColor={Colors.textMuted}
            value={productFocus}
            onChangeText={setProductFocus}
          />

          {err && <Text style={s.err}>{err}</Text>}

          <TouchableOpacity
            testID="pilot-launch"
            style={[s.primaryBtn, { backgroundColor: Colors.pilot, opacity: loading ? 0.6 : 1 }]}
            onPress={launch}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnText}>Lancer le plan</Text>}
          </TouchableOpacity>

          {plan && (
            <View testID="pilot-plan" style={{ marginTop: Spacing.lg }}>
              <View style={s.planCard}>
                <Text style={s.planLabel}>Approche</Text>
                <Text style={s.planSummary}>{plan.summary}</Text>
              </View>

              {plan.targets?.length > 0 && (
                <>
                  <Text style={s.sectionTitle}>Cibles suggérées</Text>
                  {plan.targets.map((t, i) => (
                    <View key={i} style={s.targetCard} testID={`pilot-target-card-${i}`}>
                      <View style={s.targetHead}>
                        <Text style={s.targetName}>{t.name}</Text>
                        <Text style={s.targetCity}>{t.city}</Text>
                      </View>
                      <Text style={s.targetApproach}>{t.approach}</Text>
                    </View>
                  ))}
                </>
              )}

              {plan.tasks?.length > 0 && (
                <>
                  <Text style={s.sectionTitle}>Tâches à exécuter</Text>
                  {plan.tasks.map((task, i) => {
                    const key = `t${i}`;
                    const done = completed[key];
                    return (
                      <TouchableOpacity
                        key={i}
                        testID={`pilot-task-${i}`}
                        style={s.taskRow}
                        onPress={() => setCompleted({ ...completed, [key]: !done })}
                        activeOpacity={0.7}
                      >
                        <View style={[s.checkbox, done && { backgroundColor: Colors.pilot, borderColor: Colors.pilot }]}>
                          {done && <Ionicons name="checkmark" size={14} color="#fff" />}
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={[s.taskTitle, done && { textDecorationLine: "line-through", color: Colors.textMuted }]}>
                            {task.title}
                          </Text>
                          <Text style={s.taskDeadline}>{task.deadline}</Text>
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </>
              )}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: "row", alignItems: "center", gap: Spacing.sm,
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  brandDot: { width: 36, height: 36, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  brandLetter: { color: "#fff", fontWeight: "700", fontSize: 18, fontFamily: "serif" },
  headerTitle: { fontSize: 18, fontWeight: "700", color: Colors.text, fontFamily: "serif" },
  headerSub: { fontSize: 12, color: Colors.textMuted },
  label: { fontSize: 12, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginBottom: Spacing.sm, fontWeight: "600" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: Spacing.md, paddingVertical: 10,
    borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.bgSecondary, flexShrink: 0,
  },
  chipText: { fontSize: 13, color: Colors.text, fontWeight: "500" },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: 14,
    color: Colors.text, backgroundColor: Colors.bgSecondary,
  },
  err: { color: Colors.error, marginTop: Spacing.sm, fontSize: 13 },
  primaryBtn: { borderRadius: Radii.md, paddingVertical: 14, alignItems: "center", marginTop: Spacing.lg },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  planCard: {
    backgroundColor: Colors.pilotSoft, borderRadius: Radii.lg, padding: Spacing.md,
    borderLeftWidth: 4, borderLeftColor: Colors.pilot,
  },
  planLabel: { fontSize: 11, fontWeight: "700", color: Colors.pilot, textTransform: "uppercase", letterSpacing: 1, marginBottom: Spacing.xs },
  planSummary: { fontSize: 14, color: Colors.text, lineHeight: 20 },
  sectionTitle: { fontSize: 16, fontWeight: "600", color: Colors.text, fontFamily: "serif", marginTop: Spacing.lg, marginBottom: Spacing.sm },
  targetCard: {
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.md, padding: Spacing.md, marginBottom: Spacing.sm,
  },
  targetHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  targetName: { fontSize: 15, fontWeight: "600", color: Colors.text, flex: 1 },
  targetCity: { fontSize: 12, color: Colors.pilot, fontWeight: "500" },
  targetApproach: { fontSize: 13, color: Colors.textSecondary, lineHeight: 18 },
  taskRow: {
    flexDirection: "row", alignItems: "center", gap: Spacing.sm,
    padding: Spacing.md, backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.md, borderWidth: 1, borderColor: Colors.border,
    marginBottom: Spacing.sm,
  },
  checkbox: {
    width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: Colors.border,
    alignItems: "center", justifyContent: "center",
  },
  taskTitle: { fontSize: 14, color: Colors.text, fontWeight: "500" },
  taskDeadline: { fontSize: 11, color: Colors.textMuted, marginTop: 2 },
});
