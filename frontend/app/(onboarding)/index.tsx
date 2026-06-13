import { useMemo, useRef, useState } from "react";
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, ActivityIndicator, Image, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";
import { HexDots } from "@/src/components/HexDots";
import { apiFetch } from "@/src/api/client";

type Answers = {
  business_type?: string;
  revenue?: string;
  objectives: string[];
  products: string[];
  avg_bottle_price?: string;
  avg_case_price?: string;
  target_countries: string[];
  target_channels: string[];
};

const BUSINESS_TYPES = [
  { id: "winery", label: "Domaine viticole", icon: "🍷" },
  { id: "cooperative", label: "Cave / Coopérative", icon: "🏚️" },
  { id: "merchant", label: "Négoce", icon: "📦" },
  { id: "importer", label: "Importateur", icon: "🌎" },
  { id: "distributor", label: "Distributeur", icon: "🚚" },
  { id: "restaurant", label: "Restaurant", icon: "🍽️" },
  { id: "brewery", label: "Brasserie", icon: "🍺" },
  { id: "distillery", label: "Distillerie", icon: "🥃" },
  { id: "wine_shop", label: "Caviste", icon: "🏪" },
  { id: "other", label: "Autre", icon: "✨" },
];

const REVENUES = [
  { id: "<100k", label: "< 100 k€" },
  { id: "100k-500k", label: "100 k - 500 k€" },
  { id: "500k-2M", label: "500 k - 2 M€" },
  { id: "2M-10M", label: "2 M - 10 M€" },
  { id: "10M+", label: "+ 10 M€" },
];

const OBJECTIVES = [
  { id: "distributors", label: "Trouver des distributeurs" },
  { id: "export", label: "Développer l'export" },
  { id: "clients", label: "Trouver des clients" },
  { id: "visibility", label: "Augmenter la visibilité" },
  { id: "content", label: "Produire plus de contenu" },
  { id: "time", label: "Gagner du temps" },
];

const PRODUCTS = [
  { id: "red_wine", label: "Vins rouges" },
  { id: "white_wine", label: "Vins blancs" },
  { id: "rose", label: "Rosés" },
  { id: "sparkling", label: "Effervescents" },
  { id: "spirits", label: "Spiritueux" },
  { id: "beer", label: "Bière" },
  { id: "alcohol_free", label: "Sans alcool" },
  { id: "other", label: "Autres" },
];

const COUNTRIES = ["France", "Belgique", "Allemagne", "Royaume-Uni", "USA", "Canada", "Suisse", "Japon", "Chine", "Autre"];
const CHANNELS = ["CHR", "Cavistes", "GMS", "E-commerce", "Export", "Vente directe", "Marketplaces"];

const STEPS = ["Métier", "CA", "Objectifs", "Produits", "Prix & Marchés"];

export default function OnboardingScreen() {
  const router = useRouter();
  const { user, updateProfile } = useAuth();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [a, setA] = useState<Answers>({ objectives: [], products: [], target_countries: [], target_channels: [] });
  const scrollRef = useRef<ScrollView | null>(null);

  const firstName = user?.name?.split(" ")[0] || user?.email?.split("@")[0] || "";

  const toggle = (arrKey: "objectives" | "products" | "target_countries" | "target_channels", id: string) => {
    setA((prev) => {
      const cur = prev[arrKey];
      const exists = cur.includes(id);
      return { ...prev, [arrKey]: exists ? cur.filter((x) => x !== id) : [...cur, id] };
    });
  };

  const canContinue = useMemo(() => {
    switch (step) {
      case 0: return !!a.business_type;
      case 1: return !!a.revenue;
      case 2: return a.objectives.length > 0;
      case 3: return a.products.length > 0;
      case 4: return true; // optional fields
      default: return false;
    }
  }, [step, a]);

  const next = () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      scrollRef.current?.scrollTo({ y: 0, animated: true });
    } else {
      finish();
    }
  };

  const back = () => {
    if (step > 0) setStep(step - 1);
  };

  const finish = async () => {
    setSaving(true);
    try {
      // Derive a basic Brand Voice from the answers (purely templated for V1)
      const isPremium = (a.avg_bottle_price || "").match(/\d+/) ? parseInt(a.avg_bottle_price || "0", 10) >= 20 : false;
      const tone = isPremium ? ["professionnel", "expert", "premium"] : ["professionnel", "accessible", "chaleureux"];
      const personality = ["passionnée", "authentique", "pédagogique"];
      const style = ["phrases courtes", "pas de jargon", "storytelling"];

      await updateProfile({
        business_type: a.business_type as any,
        revenue: a.revenue,
        objectives: a.objectives,
        products: a.products,
        avg_bottle_price: a.avg_bottle_price,
        avg_case_price: a.avg_case_price,
        target_countries: a.target_countries,
        target_channels: a.target_channels,
        main_products: a.products.join(", "),
        onboarded: true,
        brand_voice_tone: tone,
        brand_voice_personality: personality,
        brand_voice_style: style,
        brand_voice_languages: ["fr", "en"],
      } as any);

      // Generate the AI Commercial Profile synthesis (ICP / positioning / priorities)
      try {
        await apiFetch("/profile/synthesize", { method: "POST" });
      } catch {
        // Best effort — synthesis can be re-triggered later from Profile
      }

      router.replace("/(tabs)");
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    setSaving(true);
    try {
      await updateProfile({ onboarded: true } as any);
      router.replace("/(tabs)");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={s.topBar}>
          <Image source={require("../../assets/brand/etoh.png")} style={{ width: 60, height: 36 }} resizeMode="contain" />
          <View style={{ flex: 1 }} />
          <TouchableOpacity onPress={skip} testID="onboarding-skip">
            <Text style={s.skipText}>Passer</Text>
          </TouchableOpacity>
        </View>

        {/* Progress */}
        <View style={s.progressWrap}>
          {STEPS.map((_, i) => (
            <View key={i} style={[s.progressSegment, { backgroundColor: i <= step ? Colors.brandPrimary : Colors.border }]} />
          ))}
        </View>

        <ScrollView ref={scrollRef} contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          {step === 0 && (
            <>
              <Greeting name={firstName} />
              <Text style={s.questionTitle}>Quel est votre métier ?</Text>
              <Text style={s.questionHint}>Sélectionnez votre activité principale.</Text>
              <View style={s.grid}>
                {BUSINESS_TYPES.map((b) => {
                  const active = a.business_type === b.id;
                  return (
                    <TouchableOpacity
                      key={b.id}
                      testID={`onb-type-${b.id}`}
                      style={[s.optionTile, active && s.optionTileActive]}
                      onPress={() => setA({ ...a, business_type: b.id })}
                      activeOpacity={0.85}
                    >
                      <Text style={s.optionEmoji}>{b.icon}</Text>
                      <Text style={[s.optionLabel, active && { color: "#fff" }]}>{b.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          )}

          {step === 1 && (
            <>
              <Text style={s.questionTitle}>Quel est votre chiffre d'affaires annuel ?</Text>
              <Text style={s.questionHint}>Cette info aide l'IA à calibrer ses recommandations.</Text>
              <View style={{ gap: 8 }}>
                {REVENUES.map((r) => {
                  const active = a.revenue === r.id;
                  return (
                    <TouchableOpacity
                      key={r.id}
                      testID={`onb-rev-${r.id}`}
                      style={[s.radioRow, active && s.radioRowActive]}
                      onPress={() => setA({ ...a, revenue: r.id })}
                      activeOpacity={0.85}
                    >
                      <View style={[s.radio, active && s.radioActive]}>
                        {active && <View style={s.radioDot} />}
                      </View>
                      <Text style={[s.radioLabel, active && { color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium }]}>{r.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          )}

          {step === 2 && (
            <>
              <Text style={s.questionTitle}>Quels sont vos objectifs ?</Text>
              <Text style={s.questionHint}>Sélectionnez tout ce qui s'applique (plusieurs choix).</Text>
              <View style={{ gap: 8 }}>
                {OBJECTIVES.map((o) => {
                  const active = a.objectives.includes(o.id);
                  return (
                    <TouchableOpacity
                      key={o.id}
                      testID={`onb-obj-${o.id}`}
                      style={[s.checkRow, active && s.checkRowActive]}
                      onPress={() => toggle("objectives", o.id)}
                      activeOpacity={0.85}
                    >
                      <View style={[s.check, active && s.checkActive]}>
                        {active && <Ionicons name="checkmark" size={14} color="#fff" />}
                      </View>
                      <Text style={[s.checkLabel, active && { color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium }]}>{o.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          )}

          {step === 3 && (
            <>
              <Text style={s.questionTitle}>Que vendez-vous ?</Text>
              <Text style={s.questionHint}>Cela personnalise les contenus créés par Studio.</Text>
              <View style={s.chipsWrap}>
                {PRODUCTS.map((p) => {
                  const active = a.products.includes(p.id);
                  return (
                    <TouchableOpacity
                      key={p.id}
                      testID={`onb-prod-${p.id}`}
                      style={[s.bigChip, active && s.bigChipActive]}
                      onPress={() => toggle("products", p.id)}
                      activeOpacity={0.85}
                    >
                      <Text style={[s.bigChipText, active && { color: "#fff" }]}>{p.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          )}

          {step === 4 && (
            <>
              <Text style={s.questionTitle}>Prix & marchés cibles</Text>
              <Text style={s.questionHint}>Pour cadrer le positionnement et la prospection.</Text>

              <Text style={s.fieldLabel}>Prix moyen bouteille (€)</Text>
              <TextInput
                testID="onb-bottle-price"
                style={s.input}
                value={a.avg_bottle_price}
                onChangeText={(v) => setA({ ...a, avg_bottle_price: v })}
                placeholder="Ex. 18"
                placeholderTextColor={Colors.textMuted}
                keyboardType="numeric"
              />

              <Text style={s.fieldLabel}>Prix moyen carton (€)</Text>
              <TextInput
                testID="onb-case-price"
                style={s.input}
                value={a.avg_case_price}
                onChangeText={(v) => setA({ ...a, avg_case_price: v })}
                placeholder="Ex. 110"
                placeholderTextColor={Colors.textMuted}
                keyboardType="numeric"
              />

              <Text style={s.fieldLabel}>Pays ciblés</Text>
              <View style={s.chipsWrap}>
                {COUNTRIES.map((c) => {
                  const active = a.target_countries.includes(c);
                  return (
                    <TouchableOpacity
                      key={c}
                      testID={`onb-country-${c}`}
                      style={[s.smallChip, active && s.smallChipActive]}
                      onPress={() => toggle("target_countries", c)}
                    >
                      <Text style={[s.smallChipText, active && { color: "#fff" }]}>{c}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={s.fieldLabel}>Canaux visés</Text>
              <View style={s.chipsWrap}>
                {CHANNELS.map((ch) => {
                  const active = a.target_channels.includes(ch);
                  return (
                    <TouchableOpacity
                      key={ch}
                      testID={`onb-channel-${ch}`}
                      style={[s.smallChip, active && s.smallChipActive]}
                      onPress={() => toggle("target_channels", ch)}
                    >
                      <Text style={[s.smallChipText, active && { color: "#fff" }]}>{ch}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </>
          )}

          <View style={{ height: 32 }} />
        </ScrollView>

        {/* Footer with nav */}
        <View style={s.footer}>
          <View style={s.footerNav}>
            {step > 0 ? (
              <TouchableOpacity testID="onb-back" onPress={back} style={s.backBtn}>
                <Ionicons name="arrow-back" size={18} color={Colors.text} />
              </TouchableOpacity>
            ) : <View style={{ width: 40 }} />}
            <Text style={s.stepCount}>{step + 1}/{STEPS.length} · {STEPS[step]}</Text>
            <TouchableOpacity
              testID="onb-next"
              style={[s.nextBtn, (!canContinue || saving) && { opacity: 0.5 }]}
              onPress={next}
              disabled={!canContinue || saving}
              activeOpacity={0.85}
            >
              {saving ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={s.nextBtnText}>{step === STEPS.length - 1 ? "Lancer EtOH" : "Suivant"}</Text>
              )}
            </TouchableOpacity>
          </View>
          <HexDots size={6} gap={10} />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Greeting({ name }: { name: string }) {
  return (
    <View style={{ marginBottom: Spacing.lg }}>
      <Text style={s.helloEmoji}>👋</Text>
      <Text style={s.helloText}>Bonjour{name ? ` ${name}` : ""}.</Text>
      <Text style={s.helloSub}>Configurons votre Directeur Commercial IA. Moins de 3 minutes.</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  topBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: Spacing.lg, paddingVertical: 10 },
  skipText: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.textMuted },
  progressWrap: { flexDirection: "row", gap: 4, paddingHorizontal: Spacing.lg, marginBottom: Spacing.md },
  progressSegment: { flex: 1, height: 4, borderRadius: 2 },
  scroll: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm, paddingBottom: 100 },

  helloEmoji: { fontSize: 30 },
  helloText: { fontFamily: Fonts.headingBold, fontSize: 24, color: Colors.text, marginTop: 6 },
  helloSub: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, lineHeight: 19, marginTop: 6 },

  questionTitle: { fontFamily: Fonts.headingBold, fontSize: 22, color: Colors.text, lineHeight: 28, marginBottom: 4 },
  questionHint: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textMuted, marginBottom: Spacing.lg },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  optionTile: { width: "48%", padding: Spacing.md, borderRadius: Radii.md, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary, alignItems: "flex-start" },
  optionTileActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  optionEmoji: { fontSize: 22, marginBottom: 6 },
  optionLabel: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.text, fontWeight: "700" },

  radioRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: Spacing.md, borderRadius: Radii.md, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary },
  radioRowActive: { borderColor: Colors.brandPrimary, backgroundColor: Colors.bgSecondary },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: Colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: Colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.brandPrimary },
  radioLabel: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },

  checkRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: Spacing.md, borderRadius: Radii.md, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary },
  checkRowActive: { borderColor: Colors.brandPrimary },
  check: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: Colors.border, alignItems: "center", justifyContent: "center" },
  checkActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  checkLabel: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },

  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  bigChip: { paddingHorizontal: Spacing.md, paddingVertical: 12, borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary },
  bigChipActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  bigChipText: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.text, fontWeight: "700" },

  fieldLabel: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginTop: Spacing.lg, marginBottom: 8, fontWeight: "700" },
  input: { borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: 14, color: Colors.text, backgroundColor: Colors.bgSecondary, fontFamily: Fonts.body },

  smallChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary },
  smallChipActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  smallChipText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.text },

  footer: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.sm, paddingBottom: Spacing.md, borderTopWidth: 1, borderTopColor: Colors.border, backgroundColor: Colors.bgSecondary, gap: 10 },
  footerNav: { flexDirection: "row", alignItems: "center" },
  backBtn: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: Colors.border, alignItems: "center", justifyContent: "center" },
  stepCount: { flex: 1, textAlign: "center", fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted },
  nextBtn: { backgroundColor: Colors.brandPrimary, paddingHorizontal: Spacing.lg, paddingVertical: 12, borderRadius: Radii.md, minWidth: 110, alignItems: "center" },
  nextBtnText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 14 },
});
