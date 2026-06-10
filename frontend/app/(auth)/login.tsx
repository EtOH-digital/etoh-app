import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
  Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";

export default function Login() {
  const { login, signup, googleLogin } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null);
    if (!email || !password) {
      setErr("Email et mot de passe requis");
      return;
    }
    setLoading(true);
    try {
      if (mode === "signup") {
        await signup(email.trim().toLowerCase(), password, name.trim() || undefined);
      } else {
        await login(email.trim().toLowerCase(), password);
      }
    } catch (e: any) {
      setErr(e.message || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  const onGoogle = async () => {
    setErr(null);
    setLoading(true);
    try {
      await googleLogin();
    } catch (e: any) {
      setErr(e.message || "Erreur Google");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={s.brand}>
            <Image
              source={require("../../assets/brand/studio.png")}
              style={s.logoImg}
              resizeMode="contain"
            />
            <Text style={s.tagline}>Votre Directeur Commercial IA{"\n"}vins & spiritueux</Text>
          </View>

          <View style={s.card}>
            <View style={s.tabs}>
              <TouchableOpacity
                testID="auth-tab-login"
                style={[s.tab, mode === "login" && s.tabActive]}
                onPress={() => setMode("login")}
              >
                <Text style={[s.tabText, mode === "login" && s.tabTextActive]}>Connexion</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="auth-tab-signup"
                style={[s.tab, mode === "signup" && s.tabActive]}
                onPress={() => setMode("signup")}
              >
                <Text style={[s.tabText, mode === "signup" && s.tabTextActive]}>
                  Créer un compte
                </Text>
              </TouchableOpacity>
            </View>

            {mode === "signup" && (
              <TextInput
                testID="auth-name-input"
                placeholder="Nom (optionnel)"
                placeholderTextColor={Colors.textMuted}
                style={s.input}
                value={name}
                onChangeText={setName}
                autoCapitalize="words"
              />
            )}
            <TextInput
              testID="auth-email-input"
              placeholder="Email"
              placeholderTextColor={Colors.textMuted}
              style={s.input}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              autoCorrect={false}
            />
            <TextInput
              testID="auth-password-input"
              placeholder="Mot de passe (min. 6)"
              placeholderTextColor={Colors.textMuted}
              style={s.input}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoCapitalize="none"
            />

            {err && (
              <Text testID="auth-error" style={s.err}>
                {err}
              </Text>
            )}

            <TouchableOpacity
              testID="auth-submit-button"
              style={[s.primaryBtn, loading && { opacity: 0.6 }]}
              onPress={submit}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={s.primaryBtnText}>
                  {mode === "login" ? "Se connecter" : "Créer mon compte"}
                </Text>
              )}
            </TouchableOpacity>

            <View style={s.divider}>
              <View style={s.dividerLine} />
              <Text style={s.dividerText}>ou</Text>
              <View style={s.dividerLine} />
            </View>

            <TouchableOpacity
              testID="auth-google-button"
              style={s.googleBtn}
              onPress={onGoogle}
              disabled={loading}
              activeOpacity={0.85}
            >
              <Ionicons name="logo-google" size={18} color={Colors.text} />
              <Text style={s.googleBtnText}>Continuer avec Google</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.footer}>
            En continuant, vous acceptez les conditions d'utilisation.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  scroll: { flexGrow: 1, justifyContent: "center", padding: Spacing.lg, maxWidth: 480, width: "100%", alignSelf: "center" },
  brand: { alignItems: "center", marginBottom: Spacing.xl },
  logoImg: { width: 200, height: 110, marginBottom: Spacing.sm },
  tagline: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, textAlign: "center", marginTop: Spacing.sm, lineHeight: 20 },
  card: {
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.xl,
    padding: Spacing.lg,
    borderWidth: 1, borderColor: Colors.border,
  },
  tabs: { flexDirection: "row", backgroundColor: Colors.bgTertiary, borderRadius: Radii.md, padding: 4, marginBottom: Spacing.lg },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: Radii.sm },
  tabActive: { backgroundColor: Colors.bgSecondary },
  tabText: { fontSize: 14, color: Colors.textSecondary, fontWeight: "500", fontFamily: Fonts.body },
  tabTextActive: { color: Colors.text, fontWeight: "700", fontFamily: Fonts.bodyMedium },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingHorizontal: Spacing.md, paddingVertical: 14, marginBottom: Spacing.sm,
    fontSize: 15, color: Colors.text, backgroundColor: Colors.bgSecondary,
    fontFamily: Fonts.body,
  },
  err: { color: Colors.error, fontSize: 13, marginTop: Spacing.xs, marginBottom: Spacing.xs, fontFamily: Fonts.body },
  primaryBtn: {
    backgroundColor: Colors.brandPrimary, borderRadius: Radii.md,
    paddingVertical: 14, alignItems: "center", marginTop: Spacing.sm,
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15, fontFamily: Fonts.bodyMedium },
  divider: { flexDirection: "row", alignItems: "center", marginVertical: Spacing.md },
  dividerLine: { flex: 1, height: 1, backgroundColor: Colors.border },
  dividerText: { marginHorizontal: Spacing.md, color: Colors.textMuted, fontSize: 12 },
  googleBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10,
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingVertical: 14, backgroundColor: Colors.bgSecondary,
  },
  googleBtnText: { fontWeight: "500", fontSize: 14, color: Colors.text },
  footer: { textAlign: "center", color: Colors.textMuted, fontSize: 12, marginTop: Spacing.lg },
});
