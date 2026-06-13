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
  Image,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "Comment vendre plus en restaurants ?",
  "Veille : tendances vin bio en Allemagne 2026",
  "Comment trouver des importateurs en Belgique ?",
  "Veille : concurrents en Champagne premium",
];

export default function Coach() {
  const { user } = useAuth();
  const params = useLocalSearchParams<{ prompt?: string }>();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<ScrollView | null>(null);
  const handledPromptRef = useRef<string | null>(null);

  useEffect(() => {
    const p = (params.prompt as string) || "";
    if (p && p !== handledPromptRef.current) {
      handledPromptRef.current = p;
      setInput(p);
    }
  }, [params.prompt]);

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
      // Auto-trigger Tavily web research for keywords that need fresh market data
      const needsResearch = /\b(tendance|tendances|march[ée]|concurrent|concurrence|veille|nouveau|2024|2025|2026|importateur|distributeur|trend|market|competitor)\b/i.test(content);
      const endpoint = needsResearch ? "/coach/research" : "/coach/message";
      const body = needsResearch
        ? { query: content, language: lang }
        : { session_id: sessionId, message: content, language: lang };
      const data = await apiFetch<any>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (needsResearch) {
        const sourcesBlock = (data.sources || [])
          .map((s: any) => `- [${s.title}](${s.url})`).join("\n");
        const reply = `🔎 **Veille web (Tavily)**\n\n${data.synthesis}\n\n${sourcesBlock ? "**Sources :**\n" + sourcesBlock : ""}`;
        setMessages([...next, { role: "assistant", content: reply }]);
      } else {
        setSessionId(data.session_id);
        setMessages([...next, { role: "assistant", content: data.reply }]);
      }
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
        <Image source={require("../../assets/brand/coach.png")} style={s.headerLogo} resizeMode="contain" />
        <View style={{ flex: 1 }} />
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
              <Text style={s.emptyTitle}>Que voulez-vous savoir&nbsp;?</Text>
              <Text style={s.emptySub}>
                Demandez à votre Coach IA n'importe quelle question commerciale.
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
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  headerLogo: { width: 110, height: 50 },
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
