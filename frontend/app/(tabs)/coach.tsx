import { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "Comment vendre plus en restaurants ?",
  "Comment trouver des importateurs en Belgique ?",
  "Comment préparer mon prochain salon ?",
  "Comment lancer un nouveau millésime ?",
];

export default function Coach() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<ScrollView | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [messages, loading]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || loading) return;
    setInput("");
    const next = [...messages, { role: "user" as const, content }];
    setMessages(next);
    setLoading(true);
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<{ session_id: string; reply: string }>("/coach/message", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, message: content, language: lang }),
      });
      setSessionId(data.session_id);
      setMessages([...next, { role: "assistant", content: data.reply }]);
    } catch (e: any) {
      setMessages([...next, { role: "assistant", content: `⚠️ ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setMessages([]);
    setSessionId(undefined);
  };

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <View style={s.header}>
        <View style={[s.brandDot, { backgroundColor: Colors.coach }]}>
          <Text style={s.brandLetter}>C</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Coach</Text>
          <Text style={s.headerSub}>Que devez-vous faire ?</Text>
        </View>
        {messages.length > 0 && (
          <TouchableOpacity testID="coach-reset" onPress={reset} style={s.iconBtn}>
            <Ionicons name="add" size={22} color={Colors.text} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {messages.length === 0 && (
            <View style={s.empty}>
              <Text style={s.emptyTitle}>Posez votre question business</Text>
              <Text style={s.emptySub}>
                Diagnostic, recommandations et plan d'action en quelques secondes.
              </Text>
              <View style={s.suggestions}>
                {SUGGESTIONS.map((q, i) => (
                  <TouchableOpacity
                    key={i}
                    testID={`coach-suggestion-${i}`}
                    style={s.suggestion}
                    onPress={() => send(q)}
                  >
                    <Text style={s.suggestionText}>{q}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {messages.map((m, i) => (
            <View
              key={i}
              testID={`coach-msg-${i}`}
              style={[
                s.bubble,
                m.role === "user" ? s.userBubble : s.aiBubble,
              ]}
            >
              <Text style={m.role === "user" ? s.userText : s.aiText}>{m.content}</Text>
            </View>
          ))}

          {loading && (
            <View style={[s.bubble, s.aiBubble]}>
              <ActivityIndicator color={Colors.coach} />
            </View>
          )}
        </ScrollView>

        <View style={s.inputBar}>
          <TextInput
            testID="coach-input"
            style={s.input}
            placeholder="Posez votre question…"
            placeholderTextColor={Colors.textMuted}
            value={input}
            onChangeText={setInput}
            multiline
            editable={!loading}
          />
          <TouchableOpacity
            testID="coach-send"
            style={[s.sendBtn, { backgroundColor: Colors.coach, opacity: !input.trim() || loading ? 0.4 : 1 }]}
            onPress={() => send(input)}
            disabled={!input.trim() || loading}
          >
            <Ionicons name="arrow-up" size={20} color="#fff" />
          </TouchableOpacity>
        </View>
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
  iconBtn: { padding: 8, borderRadius: 8, backgroundColor: Colors.bgTertiary },
  scroll: { padding: Spacing.md, gap: Spacing.sm, paddingBottom: Spacing.lg },
  empty: { paddingVertical: Spacing.xl, alignItems: "center" },
  emptyTitle: { fontSize: 18, fontWeight: "600", color: Colors.text, fontFamily: "serif", marginBottom: Spacing.xs },
  emptySub: { fontSize: 13, color: Colors.textSecondary, textAlign: "center", marginBottom: Spacing.lg, paddingHorizontal: Spacing.lg },
  suggestions: { width: "100%", gap: Spacing.sm },
  suggestion: {
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.md, padding: Spacing.md,
    borderWidth: 1, borderColor: Colors.border,
  },
  suggestionText: { fontSize: 14, color: Colors.text },
  bubble: { padding: Spacing.md, borderRadius: 18, maxWidth: "88%" },
  userBubble: { alignSelf: "flex-end", backgroundColor: Colors.bgTertiary, borderBottomRightRadius: 4 },
  aiBubble: { alignSelf: "flex-start", backgroundColor: Colors.bgSecondary, borderWidth: 1, borderColor: Colors.border, borderBottomLeftRadius: 4 },
  userText: { color: Colors.text, fontSize: 15, lineHeight: 21 },
  aiText: { color: Colors.text, fontSize: 15, lineHeight: 22 },
  inputBar: {
    flexDirection: "row", alignItems: "flex-end", gap: Spacing.sm,
    padding: Spacing.md, paddingBottom: Spacing.md,
    borderTopWidth: 1, borderTopColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  input: {
    flex: 1, backgroundColor: Colors.bgTertiary,
    borderRadius: Radii.lg, paddingHorizontal: Spacing.md, paddingVertical: 12,
    fontSize: 15, color: Colors.text, maxHeight: 120,
  },
  sendBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
});
