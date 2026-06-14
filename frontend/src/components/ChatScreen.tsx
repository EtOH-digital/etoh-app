import { ReactNode, useEffect, useRef, useState } from "react";
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
  Share,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Clipboard from "expo-clipboard";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import { useT } from "@/src/i18n/I18nContext";
import MarkdownText from "@/src/components/MarkdownText";

export type ChatMsg = {
  role: "user" | "assistant";
  content: string;
  /** Optional custom JSX rendered under the assistant bubble (e.g. cards, buttons) */
  extras?: ReactNode;
  /** When true, show copy / share actions on the assistant bubble */
  copyable?: boolean;
};

export type SendHelpers = {
  appendAssistant: (msg: ChatMsg) => void;
  appendUser: (text: string) => void;
};

type Props = {
  testID: string;
  /** Brand color for accents (send button, suggestion border, spinner) */
  color: string;
  /** Header logo (require(...)) */
  logo: any;
  /** Empty-state title shown when no messages */
  emptyTitle: string;
  /** Empty-state subtitle */
  emptySub: string;
  /** Quick suggestion chips */
  suggestions: string[];
  /** Input placeholder */
  placeholder: string;
  /** Optional right header content (e.g. credit chip) */
  headerRight?: ReactNode;
  /** Called when user submits a message. Append assistant replies via helpers. */
  onSend: (text: string, helpers: SendHelpers) => Promise<void>;
};

export default function ChatScreen({
  testID,
  color,
  logo,
  emptyTitle,
  emptySub,
  suggestions,
  placeholder,
  headerRight,
  onSend,
}: Props) {
  const params = useLocalSearchParams<{ prompt?: string }>();
  const { refresh } = useAuth();
  const tr = useT();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [learned, setLearned] = useState<string[] | null>(null);
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
    setMessages((m) => [...m, { role: "user", content }]);
    setLoading(true);
    // Fire-and-forget passive memory: extract business info from this message.
    (async () => {
      try {
        const r = await apiFetch<{ learned_fields: string[] }>("/profile/auto-extract", {
          method: "POST",
          body: JSON.stringify({ message: content, source: testID }),
        });
        if (r?.learned_fields?.length) {
          setLearned(r.learned_fields);
          refresh().catch(() => {});
          setTimeout(() => setLearned(null), 6000);
        }
      } catch {
        // silent — passive memory never blocks the user
      }
    })();
    try {
      await onSend(content, {
        appendAssistant: (msg) => setMessages((m) => [...m, msg]),
        appendUser: (t) => setMessages((m) => [...m, { role: "user", content: t }]),
      });
    } catch (e: any) {
      setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${e?.message || "Erreur"}` }]);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => setMessages([]);

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <View style={s.header}>
        <Image source={logo} style={s.headerLogo} resizeMode="contain" />
        <View style={{ flex: 1 }} />
        {headerRight}
        {messages.length > 0 && (
          <TouchableOpacity
            testID={`${testID}-reset`}
            onPress={reset}
            style={s.iconBtn}
            accessibilityLabel="Nouvelle conversation"
          >
            <Ionicons name="add" size={22} color={Colors.text} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
        {learned && learned.length > 0 && (
          <View style={[s.learnedBanner, { borderColor: color }]} testID={`${testID}-learned`}>
            <Ionicons name="bulb-outline" size={14} color={color} />
            <Text style={s.learnedText}>
              {tr("chat.learned")}{" "}
              <Text style={{ fontWeight: "700" }}>{labelLearned(learned, tr)}</Text>. {tr("chat.learned.saved")}
            </Text>
          </View>
        )}
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {messages.length === 0 && (
            <View style={s.empty}>
              <Text style={s.emptyTitle}>{emptyTitle}</Text>
              <Text style={s.emptySub}>{emptySub}</Text>
              <View style={s.suggestions}>
                {suggestions.map((q, i) => (
                  <TouchableOpacity
                    key={i}
                    testID={`${testID}-suggestion-${i}`}
                    style={s.suggestion}
                    onPress={() => send(q)}
                    activeOpacity={0.85}
                  >
                    <Ionicons name="sparkles-outline" size={14} color={color} />
                    <Text style={s.suggestionText}>{q}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {messages.map((m, i) => (
            <View
              key={i}
              style={{
                width: "100%",
                alignItems: m.role === "user" ? "flex-end" : "flex-start",
                marginBottom: 4,
              }}
            >
              <View
                testID={`${testID}-msg-${i}`}
                style={[s.bubble, m.role === "user" ? s.userBubble : s.aiBubble]}
              >
                {m.role === "user" ? (
                  <Text style={s.userText} selectable>
                    {m.content}
                  </Text>
                ) : (
                  <MarkdownText text={m.content} style={s.aiText} linkColor={color} />
                )}
                {m.role === "assistant" && m.copyable && !!m.content && (
                  <View style={s.bubbleActions}>
                    <TouchableOpacity
                      onPress={() => Clipboard.setStringAsync(m.content)}
                      style={s.bubbleActionBtn}
                      hitSlop={8}
                    >
                      <Ionicons name="copy-outline" size={14} color={Colors.textSecondary} />
                      <Text style={s.bubbleActionText}>Copier</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={async () => {
                        try {
                          await Share.share({ message: m.content });
                        } catch {}
                      }}
                      style={s.bubbleActionBtn}
                      hitSlop={8}
                    >
                      <Ionicons name="share-outline" size={14} color={Colors.textSecondary} />
                      <Text style={s.bubbleActionText}>Partager</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
              {m.extras && <View style={{ width: "100%", marginTop: 6 }}>{m.extras}</View>}
            </View>
          ))}

          {loading && (
            <View style={[s.bubble, s.aiBubble, { alignSelf: "flex-start" }]}>
              <ActivityIndicator color={color} />
            </View>
          )}
        </ScrollView>

        <View style={s.inputBar}>
          <TextInput
            testID={`${testID}-input`}
            style={s.input}
            placeholder={placeholder}
            placeholderTextColor={Colors.textMuted}
            value={input}
            onChangeText={setInput}
            multiline
            editable={!loading}
          />
          <TouchableOpacity
            testID={`${testID}-send`}
            style={[
              s.sendBtn,
              { backgroundColor: color, opacity: !input.trim() || loading ? 0.4 : 1 },
            ]}
            onPress={() => send(input)}
            disabled={!input.trim() || loading}
            accessibilityLabel="Envoyer"
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
  learnedBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: Spacing.md,
    paddingVertical: 8,
    backgroundColor: Colors.bgSecondary,
    borderLeftWidth: 3,
    marginHorizontal: Spacing.md,
    marginTop: Spacing.sm,
    borderRadius: Radii.sm,
  },
  learnedText: { flex: 1, fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, lineHeight: 17 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  headerLogo: { width: 110, height: 50 },
  iconBtn: { padding: 8, borderRadius: 8, backgroundColor: Colors.bgTertiary },
  scroll: { padding: Spacing.md, gap: Spacing.sm, paddingBottom: Spacing.lg },
  empty: { paddingVertical: Spacing.xl, alignItems: "center" },
  emptyTitle: {
    fontSize: 22,
    color: Colors.text,
    fontFamily: Fonts.headingBold,
    marginBottom: Spacing.xs,
    textAlign: "center",
    paddingHorizontal: Spacing.lg,
  },
  emptySub: {
    fontFamily: Fonts.body,
    fontSize: 13,
    color: Colors.textSecondary,
    textAlign: "center",
    marginBottom: Spacing.lg,
    paddingHorizontal: Spacing.lg,
    lineHeight: 19,
  },
  suggestions: { width: "100%", gap: Spacing.sm },
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.md,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  suggestionText: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text, flex: 1 },
  bubble: { padding: Spacing.md, borderRadius: 18, maxWidth: "88%" },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: Colors.bgTertiary,
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    alignSelf: "flex-start",
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1,
    borderColor: Colors.border,
    borderBottomLeftRadius: 4,
  },
  userText: { color: Colors.text, fontSize: 15, lineHeight: 21, fontFamily: Fonts.body },
  aiText: { color: Colors.text, fontSize: 15, lineHeight: 22, fontFamily: Fonts.body },
  bubbleActions: {
    flexDirection: "row",
    gap: Spacing.sm,
    marginTop: Spacing.sm,
    paddingTop: Spacing.sm,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  bubbleActionBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: Radii.sm,
    backgroundColor: Colors.bgTertiary,
  },
  bubbleActionText: {
    fontSize: 11,
    color: Colors.textSecondary,
    fontFamily: Fonts.bodyMedium,
    fontWeight: "600",
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: Spacing.sm,
    padding: Spacing.md,
    paddingBottom: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  input: {
    flex: 1,
    backgroundColor: Colors.bgTertiary,
    borderRadius: Radii.lg,
    paddingHorizontal: Spacing.md,
    paddingVertical: 12,
    fontSize: 15,
    color: Colors.text,
    maxHeight: 120,
    fontFamily: Fonts.body,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
});


const FIELD_LABELS_FR: Record<string, string> = {
  business_name: "nom de l'entreprise",
  business_type: "type d'activité",
  region: "région",
  role: "rôle",
  main_products: "produits principaux",
  revenue: "chiffre d'affaires",
  avg_bottle_price: "prix bouteille",
  avg_case_price: "prix carton",
  objectives: "objectifs",
  products: "gamme produits",
  target_countries: "pays cibles",
  target_channels: "canaux cibles",
};

function labelLearned(fields: string[], tr: (k: string) => string): string {
  return fields
    .map((f) => {
      // Map snake_case keys to short i18n labels via translation if available.
      const k = `learn.${f}`;
      const v = tr(k);
      if (v && v !== k) return v;
      return FIELD_LABELS_FR[f] || f;
    })
    .join(", ");
}
