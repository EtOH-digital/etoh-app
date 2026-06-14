/**
 * Public conversational AI chat for a Hub `/hub/[slug]`.
 *
 * - Anonymous (no auth header) — backend rate-limits 10/min per IP
 * - Calls POST /api/public/hub/:slug/chat with {session_id, message}
 * - After 2 user messages the AI naturally suggests leaving an email;
 *   we then render a lightweight lead-capture inline form which POSTs
 *   to /api/public/hub/:slug/lead.
 *
 * Renders only when the Hub's `chat_enabled` flag is true (Pro+ owner plan).
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Fonts, Radii, Spacing } from "@/src/theme";

type Msg = { role: "user" | "assistant"; content: string };

const API_BASE =
  process.env.EXPO_PUBLIC_BACKEND_URL ||
  (typeof window !== "undefined" ? window.location.origin : "");

export default function HubPublicChat({
  slug,
  hubName,
  language = "fr",
}: {
  slug: string;
  hubName: string;
  language?: string;
}) {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "assistant",
      content: `Bonjour 👋 Je suis l'assistant IA de ${hubName}. Posez-moi vos questions sur nos produits, nos marchés, nos services — je suis là pour vous aider.`,
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [showLead, setShowLead] = useState(false);
  const [leadDone, setLeadDone] = useState(false);
  const [leadName, setLeadName] = useState("");
  const [leadEmail, setLeadEmail] = useState("");
  const [leadPhone, setLeadPhone] = useState("");
  const [leadCompany, setLeadCompany] = useState("");
  const [leadConsent, setLeadConsent] = useState(true);
  const [leadSending, setLeadSending] = useState(false);
  const userMsgCountRef = useRef(0);

  const send = useCallback(async () => {
    const msg = input.trim();
    if (!msg || sending) return;
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setInput("");
    try {
      const r = await fetch(`${API_BASE}/api/public/hub/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: msg, visitor_lang: language }),
      });
      if (r.status === 429) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Vous m'avez parlé trop vite 😅. Réessayez dans une minute." },
        ]);
        return;
      }
      if (r.status === 402) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              "Le chat IA n'est pas activé pour ce Hub. Contactez l'équipe directement par email.",
          },
        ]);
        return;
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (data.session_id && !sessionId) setSessionId(data.session_id);
      userMsgCountRef.current = data.user_message_count || userMsgCountRef.current + 1;
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      // After 2 substantive exchanges, surface the lead capture form.
      if (userMsgCountRef.current >= 2 && !leadDone) {
        setShowLead(true);
      }
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Désolé, je suis momentanément indisponible. Vous pouvez nous contacter directement par email.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }, [input, sending, sessionId, slug, language, leadDone]);

  const submitLead = useCallback(async () => {
    if (!leadEmail || !leadConsent) return;
    setLeadSending(true);
    try {
      const r = await fetch(`${API_BASE}/api/public/hub/${slug}/lead`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          name: leadName || null,
          email: leadEmail,
          phone: leadPhone || null,
          company: leadCompany || null,
          consent: leadConsent,
        }),
      });
      if (!r.ok) throw new Error("lead failed");
      setLeadDone(true);
      setShowLead(false);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Merci ${leadName || ""} ! L'équipe ${hubName} vous recontactera très bientôt. 🍷`,
        },
      ]);
    } catch (e) {
      // soft fail
    } finally {
      setLeadSending(false);
    }
  }, [leadEmail, leadConsent, slug, sessionId, leadName, leadPhone, leadCompany, hubName]);

  return (
    <View style={st.root}>
      <View style={st.header}>
        <View style={st.aiDot} />
        <Text style={st.title}>Posez vos questions</Text>
      </View>
      <View style={st.chatBox}>
        {messages.map((m, i) => (
          <View
            key={i}
            style={[
              st.bubble,
              m.role === "user" ? st.bubbleUser : st.bubbleAssistant,
            ]}
          >
            <Text
              style={[
                st.bubbleText,
                m.role === "user" ? st.bubbleTextUser : st.bubbleTextAssistant,
              ]}
            >
              {m.content}
            </Text>
          </View>
        ))}
        {sending ? (
          <View style={[st.bubble, st.bubbleAssistant]}>
            <ActivityIndicator color={Colors.textMuted} size="small" />
          </View>
        ) : null}
      </View>

      {/* Lead capture form, inline */}
      {showLead && !leadDone ? (
        <View style={st.lead}>
          <Text style={st.leadTitle}>📩 Souhaitez-vous être recontacté ?</Text>
          <Text style={st.leadSubtitle}>
            Laissez vos coordonnées et notre équipe vous enverra une réponse personnalisée.
          </Text>
          <View style={st.leadRow}>
            <TextInput
              placeholder="Prénom Nom"
              placeholderTextColor={Colors.textMuted}
              value={leadName}
              onChangeText={setLeadName}
              style={st.leadInput}
            />
          </View>
          <View style={st.leadRow}>
            <TextInput
              placeholder="Email *"
              placeholderTextColor={Colors.textMuted}
              value={leadEmail}
              onChangeText={setLeadEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              style={st.leadInput}
            />
          </View>
          <View style={st.leadRow}>
            <TextInput
              placeholder="Téléphone (optionnel)"
              placeholderTextColor={Colors.textMuted}
              value={leadPhone}
              onChangeText={setLeadPhone}
              keyboardType="phone-pad"
              style={st.leadInput}
            />
          </View>
          <View style={st.leadRow}>
            <TextInput
              placeholder="Entreprise (optionnel)"
              placeholderTextColor={Colors.textMuted}
              value={leadCompany}
              onChangeText={setLeadCompany}
              style={st.leadInput}
            />
          </View>
          <Pressable onPress={() => setLeadConsent((v) => !v)} style={st.consentRow}>
            <View style={[st.checkbox, leadConsent ? st.checkboxOn : null]}>
              {leadConsent ? <Ionicons name="checkmark" size={14} color="#fff" /> : null}
            </View>
            <Text style={st.consentText}>
              J'accepte d'être recontacté par {hubName} (RGPD).
            </Text>
          </Pressable>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
            <Pressable
              onPress={submitLead}
              disabled={!leadEmail || !leadConsent || leadSending}
              style={({ pressed }) => [
                st.leadBtn,
                (!leadEmail || !leadConsent) ? { opacity: 0.4 } : null,
                pressed ? { opacity: 0.8 } : null,
              ]}
            >
              {leadSending ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={st.leadBtnText}>Envoyer</Text>
              )}
            </Pressable>
            <Pressable onPress={() => setShowLead(false)} style={st.leadCancel}>
              <Text style={st.leadCancelText}>Plus tard</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* Composer */}
      <View style={st.composer}>
        <TextInput
          value={input}
          onChangeText={setInput}
          onSubmitEditing={send}
          placeholder="Tapez votre message…"
          placeholderTextColor={Colors.textMuted}
          style={st.input}
          multiline={false}
          editable={!sending}
          returnKeyType="send"
        />
        <Pressable
          onPress={send}
          disabled={!input.trim() || sending}
          style={({ pressed }) => [
            st.sendBtn,
            (!input.trim() || sending) ? { opacity: 0.4 } : null,
            pressed ? { opacity: 0.8 } : null,
          ]}
        >
          <Ionicons name="send" size={18} color="#fff" />
        </Pressable>
      </View>
      <Text style={st.disclaimer}>
        Propulsé par l'IA d'EtOH. Les réponses peuvent être imparfaites.
      </Text>
    </View>
  );
}

const st = StyleSheet.create({
  root: {
    backgroundColor: Colors.bgSecondary,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    padding: Spacing.lg,
  },
  header: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: Spacing.md },
  aiDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.success },
  title: { fontFamily: Fonts.headingBold, fontSize: 20, color: Colors.text },
  chatBox: { gap: 8, marginBottom: Spacing.md },
  bubble: {
    maxWidth: "85%",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
  },
  bubbleAssistant: {
    backgroundColor: Colors.bgTertiary,
    alignSelf: "flex-start",
    borderTopLeftRadius: 4,
  },
  bubbleUser: {
    backgroundColor: Colors.brandPrimary,
    alignSelf: "flex-end",
    borderTopRightRadius: 4,
  },
  bubbleText: { fontFamily: Fonts.body, fontSize: 14, lineHeight: 20 },
  bubbleTextAssistant: { color: Colors.text },
  bubbleTextUser: { color: "#fff" },
  composer: { flexDirection: "row", alignItems: "center", gap: 8 },
  input: {
    flex: 1,
    backgroundColor: Colors.bg,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radii.pill,
    paddingHorizontal: 16,
    paddingVertical: Platform.OS === "ios" ? 12 : 9,
    fontFamily: Fonts.body,
    color: Colors.text,
    fontSize: 14,
  },
  sendBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: Colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  disclaimer: {
    fontFamily: Fonts.body, fontSize: 10, color: Colors.textMuted, textAlign: "center", marginTop: 8,
  },
  lead: {
    marginVertical: Spacing.md,
    padding: Spacing.md,
    borderRadius: Radii.lg,
    backgroundColor: Colors.studioSoft,
    borderWidth: 1,
    borderColor: Colors.border,
    gap: 8,
  },
  leadTitle: { fontFamily: Fonts.headingBold, fontSize: 16, color: Colors.text },
  leadSubtitle: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginBottom: 6 },
  leadRow: {},
  leadInput: {
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: Fonts.body,
    color: Colors.text,
    fontSize: 14,
  },
  consentRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  checkbox: {
    width: 20, height: 20, borderRadius: 4,
    borderWidth: 1.5, borderColor: Colors.border,
    backgroundColor: "#fff",
    alignItems: "center", justifyContent: "center",
  },
  checkboxOn: { backgroundColor: Colors.success, borderColor: Colors.success },
  consentText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, flex: 1 },
  leadBtn: {
    backgroundColor: Colors.brandPrimary, borderRadius: Radii.md,
    paddingVertical: 12, paddingHorizontal: 24, flex: 1, alignItems: "center",
  },
  leadBtnText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 14 },
  leadCancel: {
    paddingVertical: 12, paddingHorizontal: 16, justifyContent: "center",
  },
  leadCancelText: { color: Colors.textMuted, fontFamily: Fonts.body, fontSize: 13 },
});
