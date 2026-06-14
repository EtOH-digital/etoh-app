import { useRouter } from "expo-router";
import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Image,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { useI18n } from "@/src/i18n/I18nContext";
import { LANGUAGES, Lang } from "@/src/i18n/translations";

export default function LanguagePicker() {
  const { lang, setLang, t } = useI18n();
  const router = useRouter();
  const [picked, setPicked] = useState<Lang>(lang);
  const [busy, setBusy] = useState(false);

  const continueNext = async () => {
    setBusy(true);
    await setLang(picked);
    router.replace("/(auth)/login");
  };

  return (
    <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
      <View style={s.brand}>
        <Image
          source={require("../../assets/brand/etoh.png")}
          style={s.logo}
          resizeMode="contain"
        />
      </View>

      <View style={s.body}>
        <Text style={s.title}>{t("lang.title")}</Text>
        <Text style={s.sub}>{t("lang.subtitle")}</Text>

        <View style={s.grid}>
          {LANGUAGES.map((l) => {
            const active = picked === l.code;
            return (
              <TouchableOpacity
                key={l.code}
                testID={`lang-${l.code}`}
                onPress={() => setPicked(l.code)}
                activeOpacity={0.85}
                style={[s.card, active && s.cardActive]}
              >
                <Text style={s.flag}>{l.flag}</Text>
                <Text style={[s.cardLabel, active && { color: "#fff" }]}>
                  {l.native}
                </Text>
                {active && (
                  <View style={s.check}>
                    <Ionicons name="checkmark" size={16} color="#fff" />
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      <View style={s.footer}>
        <TouchableOpacity
          testID="lang-continue"
          style={[s.continue, busy && { opacity: 0.6 }]}
          onPress={continueNext}
          disabled={busy}
          activeOpacity={0.85}
        >
          {busy ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Text style={s.continueText}>{t("common.continue")}</Text>
              <Ionicons name="arrow-forward" size={16} color="#fff" />
            </>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  brand: { alignItems: "center", paddingTop: Spacing.xl, paddingBottom: Spacing.lg },
  logo: { width: 140, height: 60 },
  body: { flex: 1, paddingHorizontal: Spacing.lg, justifyContent: "center" },
  title: {
    fontFamily: Fonts.headingBold,
    fontSize: 24,
    color: Colors.text,
    textAlign: "center",
    marginBottom: Spacing.sm,
  },
  sub: {
    fontFamily: Fonts.body,
    fontSize: 14,
    color: Colors.textSecondary,
    textAlign: "center",
    marginBottom: Spacing.xl,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, justifyContent: "center" },
  card: {
    width: "47%",
    aspectRatio: 1.4,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.lg,
    alignItems: "center",
    justifyContent: "center",
    padding: Spacing.md,
    position: "relative",
  },
  cardActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  flag: { fontSize: 36, marginBottom: 8 },
  cardLabel: { fontFamily: Fonts.bodyMedium, fontSize: 14, color: Colors.text, fontWeight: "700" },
  check: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "rgba(0,0,0,0.25)",
    alignItems: "center",
    justifyContent: "center",
  },
  footer: { padding: Spacing.lg },
  continue: {
    backgroundColor: Colors.brandPrimary,
    borderRadius: Radii.md,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  continueText: {
    color: "#fff",
    fontFamily: Fonts.bodyMedium,
    fontWeight: "700",
    fontSize: 15,
  },
});
