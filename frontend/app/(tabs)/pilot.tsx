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
  Modal,
  Linking,
  Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";

type Target = {
  id: string;
  name: string;
  type: string;
  city: string;
  country: string;
  snippet: string;
  contact_name: string;
  contact_role: string;
  email: string;
  phone: string;
  linkedin_url: string;
  tags: string[];
};

type SearchResult = {
  search_id: string;
  query: string;
  interpretation: string;
  targets: Target[];
};

type Channel = "email" | "whatsapp" | "linkedin";

type Draft = { subject?: string | null; body: string; channel: Channel };

const SUGGESTIONS = [
  "cavistes paris vins nature",
  "importateurs vin belgique bio",
  "restaurants étoilés lyon",
  "distributeurs spiritueux new york",
];

export default function PilotScreen() {
  const { user, refresh } = useAuth();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Action modal state
  const [activeTarget, setActiveTarget] = useState<Target | null>(null);
  const [activeChannel, setActiveChannel] = useState<Channel | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editedTo, setEditedTo] = useState("");
  const [editedSubject, setEditedSubject] = useState("");
  const [editedBody, setEditedBody] = useState("");
  const [sending, setSending] = useState(false);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const credits = user?.credits ?? 0;

  const runSearch = async (text?: string) => {
    const q = (text ?? query).trim();
    if (!q) return;
    setQuery(q);
    setErr(null);
    setLoading(true);
    setResult(null);
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<SearchResult>("/pilot/search", {
        method: "POST",
        body: JSON.stringify({ query: q, language: lang }),
      });
      setResult(data);
    } catch (e: any) {
      setErr(e.message || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  const openAction = async (target: Target, channel: Channel) => {
    setActiveTarget(target);
    setActiveChannel(channel);
    setDraft(null);
    setActionStatus(null);
    setDraftLoading(true);
    setEditedTo(target.email || "");
    try {
      const lang = user?.business_profile?.language || "fr";
      const data = await apiFetch<{ subject?: string | null; body: string }>("/pilot/draft", {
        method: "POST",
        body: JSON.stringify({
          search_id: result!.search_id,
          target_id: target.id,
          channel,
          language: lang,
        }),
      });
      setDraft({ subject: data.subject, body: data.body, channel });
      setEditedSubject(data.subject || `Proposition pour ${target.name}`);
      setEditedBody(data.body);
    } catch (e: any) {
      setActionStatus(`Erreur : ${e.message}`);
    } finally {
      setDraftLoading(false);
    }
  };

  const closeModal = () => {
    setActiveTarget(null);
    setActiveChannel(null);
    setDraft(null);
    setActionStatus(null);
  };

  const sendEmail = async () => {
    if (!activeTarget || !result) return;
    if (credits < 1) {
      setActionStatus("⚠️ Crédits insuffisants. Profil → ajoutez des crédits.");
      return;
    }
    const to = (editedTo || "").trim();
    if (!to || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      setActionStatus("⚠️ Adresse email du destinataire invalide. Corrigez le champ « À » et réessayez.");
      return;
    }
    setSending(true);
    setActionStatus(null);
    try {
      const r = await apiFetch<{ ok: boolean; mocked: boolean; credits_remaining: number }>(
        "/pilot/send-email",
        {
          method: "POST",
          body: JSON.stringify({
            search_id: result.search_id,
            target_id: activeTarget.id,
            to_email: to,
            to_name: activeTarget.name,
            subject: editedSubject,
            body: editedBody,
          }),
        }
      );
      await refresh();
      setActionStatus(
        r.mocked
          ? `✓ Email simulé (Resend non encore activé). Crédits restants : ${r.credits_remaining}`
          : `✓ Email envoyé à ${to}. Crédits restants : ${r.credits_remaining}`
      );
    } catch (e: any) {
      // Pretty-print common errors
      let msg = e?.message || "Erreur";
      if (msg.includes("value is not a valid email") || msg.toLowerCase().includes("email")) {
        msg = "Adresse email invalide. Corrigez le champ « À » et réessayez.";
      }
      setActionStatus(`⚠️ ${msg}`);
    } finally {
      setSending(false);
    }
  };

  const openWhatsApp = async () => {
    if (!activeTarget || !result) return;
    if (credits < 1) {
      setActionStatus("⚠️ Crédits insuffisants.");
      return;
    }
    setSending(true);
    setActionStatus(null);
    try {
      await apiFetch("/pilot/open-channel", {
        method: "POST",
        body: JSON.stringify({
          search_id: result.search_id,
          target_id: activeTarget.id,
          channel: "whatsapp",
        }),
      });
      await refresh();
      const phone = (activeTarget.phone || "").replace(/[^0-9+]/g, "");
      const url = `https://wa.me/${phone.replace(/^\+/, "")}?text=${encodeURIComponent(editedBody)}`;
      Linking.openURL(url);
      setActionStatus("✓ WhatsApp ouvert. Crédits décomptés.");
    } catch (e: any) {
      setActionStatus(`Erreur : ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  const openLinkedIn = async () => {
    if (!activeTarget || !result) return;
    if (credits < 1) {
      setActionStatus("⚠️ Crédits insuffisants.");
      return;
    }
    setSending(true);
    setActionStatus(null);
    try {
      await apiFetch("/pilot/open-channel", {
        method: "POST",
        body: JSON.stringify({
          search_id: result.search_id,
          target_id: activeTarget.id,
          channel: "linkedin",
        }),
      });
      await Clipboard.setStringAsync(editedBody);
      await refresh();
      const url = activeTarget.linkedin_url || "https://www.linkedin.com/messaging/";
      Linking.openURL(url);
      setActionStatus("✓ Message copié + LinkedIn ouvert. Collez (Ctrl/Cmd+V) dans la conversation.");
    } catch (e: any) {
      setActionStatus(`Erreur : ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <View style={s.header}>
        <Image source={require("../../assets/brand/pilot.png")} style={s.headerLogo} resizeMode="contain" />
        <View style={{ flex: 1 }} />
        <View style={s.creditBadge} testID="pilot-credits">
          <Ionicons name="flash" size={12} color={Colors.pilot} />
          <Text style={s.creditText}>{credits} crédits</Text>
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
          <Text style={s.titleBig}>Trouvez vos prochains clients</Text>
          <Text style={s.subtitle}>
            Décrivez votre cible en langage naturel. L'IA propose des contacts à contacter en 1 clic.
          </Text>

          <View style={s.searchRow}>
            <TextInput
              testID="pilot-search-input"
              value={query}
              onChangeText={setQuery}
              placeholder='Ex. "cavistes paris vins nature"'
              placeholderTextColor={Colors.textMuted}
              style={s.searchInput}
              onSubmitEditing={() => runSearch()}
              returnKeyType="search"
            />
            <TouchableOpacity
              testID="pilot-search-btn"
              style={[s.searchBtn, (loading || !query.trim()) && { opacity: 0.5 }]}
              onPress={() => runSearch()}
              disabled={loading || !query.trim()}
              activeOpacity={0.85}
            >
              {loading ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Ionicons name="search" size={18} color="#fff" />
              )}
            </TouchableOpacity>
          </View>

          {!result && !loading && (
            <View style={{ marginTop: Spacing.md }}>
              <Text style={s.label}>Suggestions</Text>
              {SUGGESTIONS.map((q, i) => (
                <TouchableOpacity
                  key={i}
                  testID={`pilot-suggest-${i}`}
                  style={s.suggestion}
                  onPress={() => runSearch(q)}
                >
                  <Ionicons name="sparkles-outline" size={14} color={Colors.pilot} />
                  <Text style={s.suggestionText}>{q}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {err && <Text style={s.err}>{err}</Text>}

          {loading && (
            <View style={{ alignItems: "center", paddingVertical: Spacing.xl, gap: Spacing.sm }}>
              <ActivityIndicator color={Colors.pilot} />
              <Text style={{ color: Colors.textMuted, fontFamily: Fonts.body }}>
                Recherche en cours…
              </Text>
            </View>
          )}

          {result && (
            <View style={{ marginTop: Spacing.lg }} testID="pilot-results">
              {!!result.interpretation && (
                <View style={s.interpretCard}>
                  <Ionicons name="bulb-outline" size={16} color={Colors.pilot} />
                  <Text style={s.interpretText}>{result.interpretation}</Text>
                </View>
              )}
              <Text style={s.sectionTitle}>
                {result.targets.length} contacts suggérés{" "}
                <Text style={s.suggHint}>(à valider)</Text>
              </Text>

              {result.targets.map((t) => (
                <View key={t.id} style={s.targetCard} testID={`pilot-target-${t.id}`}>
                  <View style={s.targetHead}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.targetName}>{t.name}</Text>
                      <Text style={s.targetMeta}>
                        {t.type} · {t.city}
                        {t.country ? `, ${t.country}` : ""}
                      </Text>
                    </View>
                  </View>
                  {!!t.snippet && <Text style={s.targetSnippet}>{t.snippet}</Text>}
                  {!!t.contact_name && (
                    <View style={s.contactRow}>
                      <Ionicons name="person-outline" size={12} color={Colors.textMuted} />
                      <Text style={s.contactText}>
                        {t.contact_name}
                        {t.contact_role ? ` · ${t.contact_role}` : ""}
                      </Text>
                    </View>
                  )}
                  {(t.tags || []).length > 0 && (
                    <View style={s.tagsRow}>
                      {t.tags.slice(0, 4).map((tag, i) => (
                        <View key={i} style={s.tagChip}>
                          <Text style={s.tagText}>{tag}</Text>
                        </View>
                      ))}
                    </View>
                  )}

                  <View style={s.actionRow}>
                    <TouchableOpacity
                      testID={`pilot-act-email-${t.id}`}
                      style={[s.actBtn, { backgroundColor: Colors.pilot }]}
                      onPress={() => openAction(t, "email")}
                      activeOpacity={0.85}
                    >
                      <Ionicons name="mail-outline" size={14} color="#fff" />
                      <Text style={s.actBtnText}>Email</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      testID={`pilot-act-whatsapp-${t.id}`}
                      style={[s.actBtn, { backgroundColor: "#25D366" }]}
                      onPress={() => openAction(t, "whatsapp")}
                      activeOpacity={0.85}
                    >
                      <Ionicons name="logo-whatsapp" size={14} color="#fff" />
                      <Text style={s.actBtnText}>WhatsApp</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      testID={`pilot-act-linkedin-${t.id}`}
                      style={[s.actBtn, { backgroundColor: "#0A66C2" }]}
                      onPress={() => openAction(t, "linkedin")}
                      activeOpacity={0.85}
                    >
                      <Ionicons name="logo-linkedin" size={14} color="#fff" />
                      <Text style={s.actBtnText}>LinkedIn</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Action Modal */}
      <Modal
        visible={!!activeTarget}
        animationType="slide"
        transparent
        onRequestClose={closeModal}
      >
        <View style={s.modalBackdrop}>
          <View style={s.modalCard}>
            <View style={s.modalHead}>
              <View style={{ flex: 1 }}>
                <Text style={s.modalTitle}>
                  {activeChannel === "email"
                    ? "Email à"
                    : activeChannel === "whatsapp"
                    ? "WhatsApp à"
                    : "LinkedIn à"}{" "}
                  {activeTarget?.name}
                </Text>
                <Text style={s.modalSub}>
                  {activeChannel === "email" && activeTarget?.email}
                  {activeChannel === "whatsapp" && activeTarget?.phone}
                  {activeChannel === "linkedin" && (activeTarget?.contact_name || "—")}
                </Text>
              </View>
              <TouchableOpacity onPress={closeModal} style={s.closeBtn} testID="pilot-close-modal">
                <Ionicons name="close" size={20} color={Colors.text} />
              </TouchableOpacity>
            </View>

            {draftLoading && (
              <View style={{ alignItems: "center", paddingVertical: Spacing.xl }}>
                <ActivityIndicator color={Colors.pilot} />
                <Text style={{ color: Colors.textMuted, marginTop: 8, fontFamily: Fonts.body }}>
                  Rédaction par l'IA…
                </Text>
              </View>
            )}

            {!draftLoading && draft && (
              <ScrollView
                style={{ maxHeight: 480 }}
                contentContainerStyle={{ paddingBottom: Spacing.md }}
                keyboardShouldPersistTaps="handled"
              >
                {activeChannel === "email" && (
                  <>
                    <Text style={s.fieldLabel}>À</Text>
                    <TextInput
                      testID="pilot-email-to"
                      style={s.input}
                      value={editedTo}
                      onChangeText={setEditedTo}
                      placeholder="contact@exemple.com"
                      placeholderTextColor={Colors.textMuted}
                      autoCapitalize="none"
                      keyboardType="email-address"
                    />
                    <Text style={s.fieldLabel}>Objet</Text>
                    <TextInput
                      testID="pilot-email-subject"
                      style={s.input}
                      value={editedSubject}
                      onChangeText={setEditedSubject}
                    />
                  </>
                )}
                <Text style={s.fieldLabel}>Message</Text>
                <TextInput
                  testID="pilot-msg-body"
                  style={[s.input, { minHeight: 200, textAlignVertical: "top" }]}
                  value={editedBody}
                  onChangeText={setEditedBody}
                  multiline
                />

                {actionStatus && (
                  <Text testID="pilot-action-status" style={s.statusText}>
                    {actionStatus}
                  </Text>
                )}

                <View style={s.modalActions}>
                  <Text style={s.creditCost}>
                    Coût : 1 crédit ({(0.099).toFixed(3)}€)
                  </Text>
                  {activeChannel === "email" && (
                    <TouchableOpacity
                      testID="pilot-send-email"
                      style={[s.sendBtn, { backgroundColor: Colors.pilot }, sending && { opacity: 0.6 }]}
                      onPress={sendEmail}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="send" size={14} color="#fff" />
                          <Text style={s.sendBtnText}>Envoyer l'email</Text>
                        </>
                      )}
                    </TouchableOpacity>
                  )}
                  {activeChannel === "whatsapp" && (
                    <TouchableOpacity
                      testID="pilot-open-whatsapp"
                      style={[s.sendBtn, { backgroundColor: "#25D366" }, sending && { opacity: 0.6 }]}
                      onPress={openWhatsApp}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="logo-whatsapp" size={14} color="#fff" />
                          <Text style={s.sendBtnText}>Ouvrir WhatsApp</Text>
                        </>
                      )}
                    </TouchableOpacity>
                  )}
                  {activeChannel === "linkedin" && (
                    <TouchableOpacity
                      testID="pilot-open-linkedin"
                      style={[s.sendBtn, { backgroundColor: "#0A66C2" }, sending && { opacity: 0.6 }]}
                      onPress={openLinkedIn}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="logo-linkedin" size={14} color="#fff" />
                          <Text style={s.sendBtnText}>Copier + ouvrir LinkedIn</Text>
                        </>
                      )}
                    </TouchableOpacity>
                  )}
                </View>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  headerLogo: { width: 110, height: 50 },
  creditBadge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: Colors.pilotSoft, borderRadius: Radii.pill,
    borderWidth: 1, borderColor: Colors.pilot,
  },
  creditText: { fontSize: 12, color: Colors.pilotDark, fontFamily: Fonts.bodyMedium, fontWeight: "700" },
  titleBig: {
    fontFamily: Fonts.headingBold,
    fontSize: 26, color: Colors.text, lineHeight: 32, marginBottom: 6,
  },
  subtitle: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, marginBottom: Spacing.md, lineHeight: 20 },
  searchRow: { flexDirection: "row", gap: Spacing.sm, alignItems: "center" },
  searchInput: {
    flex: 1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.md, paddingHorizontal: Spacing.md, paddingVertical: 12,
    fontSize: 14, color: Colors.text, backgroundColor: Colors.bgSecondary,
    fontFamily: Fonts.body,
  },
  searchBtn: {
    width: 48, height: 46, borderRadius: Radii.md,
    backgroundColor: Colors.pilot, alignItems: "center", justifyContent: "center",
  },
  label: { fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginBottom: Spacing.sm, fontFamily: Fonts.bodyMedium, fontWeight: "700" },
  suggestion: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.md, padding: Spacing.md, marginBottom: Spacing.sm,
  },
  suggestionText: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },
  err: { color: Colors.error, marginTop: Spacing.sm, fontFamily: Fonts.body },
  interpretCard: {
    flexDirection: "row", gap: 8, alignItems: "flex-start",
    backgroundColor: Colors.pilotSoft, padding: Spacing.md,
    borderRadius: Radii.md, borderLeftWidth: 3, borderLeftColor: Colors.pilot,
    marginBottom: Spacing.md,
  },
  interpretText: { flex: 1, fontFamily: Fonts.body, fontSize: 13, color: Colors.text, lineHeight: 18 },
  sectionTitle: {
    fontFamily: Fonts.headingBold, fontSize: 16, color: Colors.text, marginBottom: Spacing.sm,
  },
  suggHint: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, fontWeight: "400" },
  targetCard: {
    backgroundColor: Colors.bgSecondary, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.lg, padding: Spacing.md, marginBottom: Spacing.sm,
  },
  targetHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  targetName: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text },
  targetMeta: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  targetSnippet: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginTop: 6, lineHeight: 18 },
  contactRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: Spacing.xs },
  contactText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary },
  tagsRow: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: Spacing.sm },
  tagChip: { backgroundColor: Colors.bgTertiary, paddingHorizontal: 8, paddingVertical: 2, borderRadius: Radii.pill },
  tagText: { fontSize: 10, color: Colors.textSecondary, fontFamily: Fonts.body },
  actionRow: { flexDirection: "row", gap: 6, marginTop: Spacing.md },
  actBtn: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5,
    paddingVertical: 9, borderRadius: Radii.md,
  },
  actBtnText: { color: "#fff", fontSize: 12, fontFamily: Fonts.bodyMedium, fontWeight: "700" },

  // Modal
  modalBackdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end",
  },
  modalCard: {
    backgroundColor: Colors.bgSecondary,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: Spacing.lg, paddingBottom: Spacing.xl,
    maxHeight: "92%",
  },
  modalHead: { flexDirection: "row", alignItems: "flex-start", marginBottom: Spacing.md, gap: Spacing.sm },
  modalTitle: { fontFamily: Fonts.headingBold, fontSize: 17, color: Colors.text },
  modalSub: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  closeBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: Colors.bgTertiary, alignItems: "center", justifyContent: "center" },
  fieldLabel: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, marginTop: Spacing.sm, marginBottom: 6, fontWeight: "700" },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: 14,
    color: Colors.text, backgroundColor: Colors.bg, fontFamily: Fonts.body,
  },
  statusText: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginTop: Spacing.sm, lineHeight: 18 },
  modalActions: { marginTop: Spacing.md, gap: Spacing.sm, alignItems: "stretch" },
  creditCost: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, textAlign: "right" },
  sendBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    paddingVertical: 13, borderRadius: Radii.md,
  },
  sendBtnText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 14 },
});
