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
import { useAuth } from "@/src/auth/AuthContext";

const BUSINESS_TYPES = [
  { id: "winery", label: "Domaine" },
  { id: "cooperative", label: "Coopérative" },
  { id: "merchant", label: "Négociant" },
  { id: "spirits", label: "Spiritueux" },
  { id: "other", label: "Autre" },
];

export default function Profile() {
  const { user, logout, updateProfile } = useAuth();
  const bp = user?.business_profile || {};

  const [businessName, setBusinessName] = useState(bp.business_name || "");
  const [businessType, setBusinessType] = useState(bp.business_type || "winery");
  const [region, setRegion] = useState(bp.region || "");
  const [mainProducts, setMainProducts] = useState(bp.main_products || "");
  const [role, setRole] = useState(bp.role || "");
  const [language, setLanguage] = useState<"fr" | "en">(bp.language || "fr");
  const [goalProspects, setGoalProspects] = useState(String((bp as any).goal_prospects ?? 50));
  const [goalCampaigns, setGoalCampaigns] = useState(String((bp as any).goal_campaigns ?? 5));
  const [goalDistributors, setGoalDistributors] = useState(String((bp as any).goal_distributors ?? 20));
  const [goalMarkets, setGoalMarkets] = useState(String((bp as any).goal_markets ?? 4));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await updateProfile({
        business_name: businessName.trim() || undefined,
        business_type: businessType as any,
        region: region.trim() || undefined,
        main_products: mainProducts.trim() || undefined,
        role: role.trim() || undefined,
        language,
        goal_prospects: Math.max(1, parseInt(goalProspects, 10) || 50),
        goal_campaigns: Math.max(1, parseInt(goalCampaigns, 10) || 5),
        goal_distributors: Math.max(1, parseInt(goalDistributors, 10) || 20),
        goal_markets: Math.max(1, parseInt(goalMarkets, 10) || 4),
      } as any);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: Spacing.lg, paddingBottom: 60 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={s.header}>
            <View style={s.avatar}>
              <Text style={s.avatarText}>
                {(user?.name || user?.email || "?").charAt(0).toUpperCase()}
              </Text>
            </View>
            <Text style={s.name}>{user?.name || user?.email}</Text>
            <Text style={s.email}>{user?.email}</Text>
          </View>

          <Text style={s.sectionTitle}>Mon entreprise</Text>

          <Text style={s.label}>Nom de l'entreprise</Text>
          <TextInput
            testID="profile-business-name"
            style={s.input}
            value={businessName}
            onChangeText={setBusinessName}
            placeholder="Ex. Domaine de la Roche"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Type</Text>
          <View style={s.chipsRow}>
            {BUSINESS_TYPES.map((b) => {
              const active = businessType === b.id;
              return (
                <TouchableOpacity
                  key={b.id}
                  testID={`profile-type-${b.id}`}
                  style={[s.chip, active && { backgroundColor: Colors.text, borderColor: Colors.text }]}
                  onPress={() => setBusinessType(b.id)}
                >
                  <Text style={[s.chipText, active && { color: "#fff" }]}>{b.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={s.label}>Région</Text>
          <TextInput
            testID="profile-region"
            style={s.input}
            value={region}
            onChangeText={setRegion}
            placeholder="Ex. Bordeaux, Cognac, Champagne…"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Produits principaux</Text>
          <TextInput
            testID="profile-products"
            style={s.input}
            value={mainProducts}
            onChangeText={setMainProducts}
            placeholder="Ex. Vins rouges AOC, Cognac VSOP"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Votre rôle</Text>
          <TextInput
            testID="profile-role"
            style={s.input}
            value={role}
            onChangeText={setRole}
            placeholder="Ex. Directeur commercial, Vigneron…"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Langue</Text>
          <View style={s.chipsRow}>
            <TouchableOpacity
              testID="profile-lang-fr"
              style={[s.chip, language === "fr" && { backgroundColor: Colors.text, borderColor: Colors.text }]}
              onPress={() => setLanguage("fr")}
            >
              <Text style={[s.chipText, language === "fr" && { color: "#fff" }]}>Français</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="profile-lang-en"
              style={[s.chip, language === "en" && { backgroundColor: Colors.text, borderColor: Colors.text }]}
              onPress={() => setLanguage("en")}
            >
              <Text style={[s.chipText, language === "en" && { color: "#fff" }]}>English</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.label}>Langue</Text>
          <View style={s.chipsRow}>
            <TouchableOpacity
              testID="profile-lang-fr"
              style={[s.chip, language === "fr" && { backgroundColor: Colors.text, borderColor: Colors.text }]}
              onPress={() => setLanguage("fr")}
            >
              <Text style={[s.chipText, language === "fr" && { color: "#fff" }]}>Français</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="profile-lang-en"
              style={[s.chip, language === "en" && { backgroundColor: Colors.text, borderColor: Colors.text }]}
              onPress={() => setLanguage("en")}
            >
              <Text style={[s.chipText, language === "en" && { color: "#fff" }]}>English</Text>
            </TouchableOpacity>
          </View>

          <Text style={[s.sectionTitle, { marginTop: 32 }]}>Mes objectifs hebdomadaires</Text>
          <Text style={[s.label, { marginTop: 8 }]}>Prospects identifiés / semaine</Text>
          <TextInput testID="profile-goal-prospects" style={s.input} value={goalProspects} onChangeText={setGoalProspects} keyboardType="number-pad" />
          <Text style={s.label}>Campagnes envoyées / semaine</Text>
          <TextInput testID="profile-goal-campaigns" style={s.input} value={goalCampaigns} onChangeText={setGoalCampaigns} keyboardType="number-pad" />
          <Text style={s.label}>Distributeurs contactés / semaine</Text>
          <TextInput testID="profile-goal-distributors" style={s.input} value={goalDistributors} onChangeText={setGoalDistributors} keyboardType="number-pad" />
          <Text style={s.label}>Marchés analysés / semaine</Text>
          <TextInput testID="profile-goal-markets" style={s.input} value={goalMarkets} onChangeText={setGoalMarkets} keyboardType="number-pad" />

          <TouchableOpacity
            testID="profile-save"
            style={[s.saveBtn, saving && { opacity: 0.6 }]}
            onPress={save}
            disabled={saving}
            activeOpacity={0.85}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={s.saveBtnText}>{saved ? "✓ Enregistré" : "Enregistrer"}</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity testID="profile-logout" style={s.logoutBtn} onPress={logout}>
            <Ionicons name="log-out-outline" size={18} color={Colors.error} />
            <Text style={s.logoutText}>Se déconnecter</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: { alignItems: "center", marginBottom: Spacing.xl, paddingTop: Spacing.md },
  avatar: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: Colors.coach,
    alignItems: "center", justifyContent: "center", marginBottom: Spacing.md,
  },
  avatarText: { color: "#fff", fontSize: 28, fontWeight: "700", fontFamily: "serif" },
  name: { fontSize: 18, fontWeight: "600", color: Colors.text, fontFamily: "serif" },
  email: { fontSize: 13, color: Colors.textMuted, marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: "600", color: Colors.text, fontFamily: "serif", marginBottom: Spacing.md },
  label: { fontSize: 12, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginBottom: Spacing.xs, marginTop: Spacing.md, fontWeight: "600" },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: 14,
    color: Colors.text, backgroundColor: Colors.bgSecondary,
  },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: Spacing.sm },
  chip: {
    paddingHorizontal: Spacing.md, paddingVertical: 8,
    borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  chipText: { fontSize: 13, color: Colors.text },
  saveBtn: {
    backgroundColor: Colors.text, borderRadius: Radii.md,
    paddingVertical: 14, alignItems: "center", marginTop: Spacing.xl,
  },
  saveBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  logoutBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 14, marginTop: Spacing.md,
  },
  logoutText: { color: Colors.error, fontWeight: "500", fontSize: 14 },
});
