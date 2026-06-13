import { useEffect, useState } from "react";
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
  Share,
  Image,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Clipboard from "expo-clipboard";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";

type Template = {
  id: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  placeholder: string;
};

const TEMPLATES: Template[] = [
  { id: "linkedin_post", label: "Post LinkedIn", icon: "logo-linkedin", placeholder: "Sujet du post : nouveau millésime, médaille, salon…" },
  { id: "email_campaign", label: "Email campagne", icon: "mail-outline", placeholder: "Objet de la campagne et cible visée…" },
  { id: "sales_message", label: "Message commercial", icon: "send-outline", placeholder: "À qui écrivez-vous et pour quelle offre ?" },
  { id: "product_description", label: "Description produit", icon: "wine-outline", placeholder: "Nom du vin/spiritueux, cépages, appellation…" },
  { id: "trade_show_followup", label: "Relance post-salon", icon: "people-outline", placeholder: "Nom du salon et type de contact rencontré…" },
  { id: "commercial_presentation", label: "Présentation commerciale", icon: "easel-outline", placeholder: "Public cible et message clé…" },
];

const TONES = [
  { id: "professional", label: "Pro" },
  { id: "warm", label: "Chaleureux" },
  { id: "premium", label: "Premium" },
  { id: "casual", label: "Direct" },
];

export default function Studio() {
  const { user } = useAuth();
  const params = useLocalSearchParams<{ prompt?: string }>();
  const [selected, setSelected] = useState<Template>(TEMPLATES[0]);
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState("professional");
  const [output, setOutput] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (params.prompt && !brief) setBrief(params.prompt as string);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.prompt]);

  const generate = async () => {
    if (!brief.trim()) {
      setErr("Décrivez votre besoin");
      return;
    }
    setErr(null);
    setLoading(true);
    setOutput(null);
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<{ content: string }>("/studio/generate", {
        method: "POST",
        body: JSON.stringify({
          template: selected.id,
          brief: brief.trim(),
          tone,
          language: lang,
        }),
      });
      setOutput(data.content);
    } catch (e: any) {
      setErr(e.message || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (output) await Clipboard.setStringAsync(output);
  };

  const share = async () => {
    if (output) {
      try {
        await Share.share({ message: output });
      } catch {}
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <View style={s.header}>
        <Image source={require("../../assets/brand/studio.png")} style={s.headerLogo} resizeMode="contain" />
        <View style={{ flex: 1 }} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: Spacing.lg, paddingBottom: 40 }}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={{ fontFamily: Fonts.headingBold, fontSize: 22, color: Colors.text, marginBottom: 6 }}>
            Quel contenu voulez-vous générer&nbsp;?
          </Text>
          <Text style={{ fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginBottom: Spacing.lg }}>
            Choisissez un format, décrivez votre besoin, Studio s'occupe du reste.
          </Text>
          <Text style={s.label}>Quel type de contenu ?</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: Spacing.sm, paddingVertical: Spacing.xs }}
          >
            {TEMPLATES.map((t) => {
              const active = selected.id === t.id;
              return (
                <TouchableOpacity
                  key={t.id}
                  testID={`studio-template-${t.id}`}
                  style={[s.chip, active && { backgroundColor: Colors.studio, borderColor: Colors.studio }]}
                  onPress={() => setSelected(t)}
                >
                  <Ionicons name={t.icon} size={14} color={active ? "#fff" : Colors.text} />
                  <Text style={[s.chipText, active && { color: "#fff" }]}>{t.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <Text style={[s.label, { marginTop: Spacing.lg }]}>Brief</Text>
          <TextInput
            testID="studio-brief-input"
            style={s.textarea}
            value={brief}
            onChangeText={setBrief}
            placeholder={selected.placeholder}
            placeholderTextColor={Colors.textMuted}
            multiline
            numberOfLines={4}
          />

          <Text style={[s.label, { marginTop: Spacing.lg }]}>Ton</Text>
          <View style={{ flexDirection: "row", gap: Spacing.sm, flexWrap: "wrap" }}>
            {TONES.map((tn) => {
              const active = tone === tn.id;
              return (
                <TouchableOpacity
                  key={tn.id}
                  testID={`studio-tone-${tn.id}`}
                  style={[s.toneChip, active && { backgroundColor: Colors.text, borderColor: Colors.text }]}
                  onPress={() => setTone(tn.id)}
                >
                  <Text style={[s.toneText, active && { color: "#fff" }]}>{tn.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {err && <Text style={s.err}>{err}</Text>}

          <TouchableOpacity
            testID="studio-generate"
            style={[s.primaryBtn, { backgroundColor: Colors.studio, opacity: loading ? 0.6 : 1 }]}
            onPress={generate}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={s.primaryBtnText}>Générer</Text>
            )}
          </TouchableOpacity>

          {output && (
            <View style={s.outputCard} testID="studio-output">
              <View style={s.outputHeader}>
                <Text style={s.outputLabel}>Résultat</Text>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <TouchableOpacity testID="studio-copy" onPress={copy} style={s.outputBtn}>
                    <Ionicons name="copy-outline" size={16} color={Colors.text} />
                    <Text style={s.outputBtnText}>Copier</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="studio-share" onPress={share} style={s.outputBtn}>
                    <Ionicons name="share-outline" size={16} color={Colors.text} />
                    <Text style={s.outputBtnText}>Partager</Text>
                  </TouchableOpacity>
                </View>
              </View>
              <Text style={s.outputText} selectable>{output}</Text>
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
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  headerLogo: { width: 110, height: 50 },
  label: { fontSize: 12, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginBottom: Spacing.sm, fontWeight: "600" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: Spacing.md, paddingVertical: 10,
    borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border,
    backgroundColor: Colors.bgSecondary, flexShrink: 0,
  },
  chipText: { fontSize: 13, color: Colors.text, fontWeight: "500" },
  textarea: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    padding: Spacing.md, fontSize: 14, color: Colors.text, minHeight: 110,
    textAlignVertical: "top", backgroundColor: Colors.bgSecondary,
  },
  toneChip: {
    paddingHorizontal: Spacing.md, paddingVertical: 8,
    borderRadius: Radii.pill, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  toneText: { fontSize: 13, color: Colors.text },
  err: { color: Colors.error, marginTop: Spacing.sm, fontSize: 13 },
  primaryBtn: {
    borderRadius: Radii.md, paddingVertical: 14, alignItems: "center", marginTop: Spacing.lg,
  },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  outputCard: {
    marginTop: Spacing.lg, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.lg, padding: Spacing.md, backgroundColor: Colors.bgSecondary,
    borderLeftWidth: 4, borderLeftColor: Colors.studio,
  },
  outputHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: Spacing.sm },
  outputLabel: { fontSize: 12, fontWeight: "600", color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1 },
  outputBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: Radii.sm,
    backgroundColor: Colors.bgTertiary,
  },
  outputBtnText: { fontSize: 12, color: Colors.text, fontWeight: "500" },
  outputText: { fontSize: 14, color: Colors.text, lineHeight: 22, fontFamily: Platform.select({ ios: "Georgia", default: "serif" }) },
});
