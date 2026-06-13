import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Modal,
  Linking,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import ChatScreen, { SendHelpers } from "@/src/components/ChatScreen";

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
  "Trouve-moi des cavistes à Paris orientés vins nature",
  "Importateurs de vin bio en Belgique",
  "Restaurants étoilés à Lyon ouverts aux nouveaux fournisseurs",
  "Distributeurs de spiritueux à New York",
];

export default function PilotScreen() {
  const { user, refresh } = useAuth();
  const credits = user?.credits ?? 0;

  // Track the latest search so the modal can post to /pilot/draft etc.
  const [latestSearch, setLatestSearch] = useState<SearchResult | null>(null);

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

  const handleSend = async (text: string, helpers: SendHelpers) => {
    const lang = user?.business_profile?.language || "fr";
    const data = await apiFetch<SearchResult>("/pilot/search", {
      method: "POST",
      body: JSON.stringify({ query: text, language: lang }),
    });
    setLatestSearch(data);
    const intro =
      `🎯 ${data.targets.length} cibles trouvées pour « ${data.query} »` +
      (data.interpretation ? `\n\n${data.interpretation}` : "");
    helpers.appendAssistant({
      role: "assistant",
      content: intro,
      extras: (
        <TargetsList
          targets={data.targets}
          onOpenAction={(t, c) => openAction(data, t, c)}
        />
      ),
    });
  };

  const openAction = async (search: SearchResult, target: Target, channel: Channel) => {
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
          search_id: search.search_id,
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
    if (!activeTarget || !latestSearch) return;
    if (credits < 1) {
      setActionStatus("⚠️ Crédits insuffisants. Profil → ajoutez des crédits.");
      return;
    }
    const to = (editedTo || "").trim();
    if (!to || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      setActionStatus("⚠️ Adresse email invalide. Corrigez le champ « À » et réessayez.");
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
            search_id: latestSearch.search_id,
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
          ? `✓ Email simulé. Crédits restants : ${r.credits_remaining}`
          : `✓ Email envoyé à ${to}. Crédits restants : ${r.credits_remaining}`
      );
    } catch (e: any) {
      let msg = e?.message || "Erreur";
      if (/email/i.test(msg)) msg = "Adresse email invalide. Corrigez « À » et réessayez.";
      setActionStatus(`⚠️ ${msg}`);
    } finally {
      setSending(false);
    }
  };

  const openWhatsApp = async () => {
    if (!activeTarget || !latestSearch) return;
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
          search_id: latestSearch.search_id,
          target_id: activeTarget.id,
          channel: "whatsapp",
        }),
      });
      await refresh();
      const phone = (activeTarget.phone || "").replace(/[^0-9+]/g, "");
      const url = `https://wa.me/${phone.replace(/^\+/, "")}?text=${encodeURIComponent(editedBody)}`;
      Linking.openURL(url);
      setActionStatus("✓ WhatsApp ouvert. Crédit décompté.");
    } catch (e: any) {
      setActionStatus(`Erreur : ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  const openLinkedIn = async () => {
    if (!activeTarget || !latestSearch) return;
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
          search_id: latestSearch.search_id,
          target_id: activeTarget.id,
          channel: "linkedin",
        }),
      });
      await Clipboard.setStringAsync(editedBody);
      await refresh();
      const url = activeTarget.linkedin_url || "https://www.linkedin.com/messaging/";
      Linking.openURL(url);
      setActionStatus("✓ Message copié + LinkedIn ouvert. Collez le message dans la conversation.");
    } catch (e: any) {
      setActionStatus(`Erreur : ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <ChatScreen
        testID="pilot"
        color={Colors.pilot}
        logo={require("../../assets/brand/pilot.png")}
        emptyTitle="Qui voulez-vous prospecter ?"
        emptySub="Décrivez vos cibles en langage naturel (type, zone, profil). Le Pilot identifie les contacts et écrit pour vous."
        suggestions={SUGGESTIONS}
        placeholder="Décrivez votre cible…"
        headerRight={
          <View style={mod.creditBadge}>
            <Ionicons name="flash" size={12} color={Colors.pilot} />
            <Text style={mod.creditText}>{credits}</Text>
          </View>
        }
        onSend={handleSend}
      />

      {/* Action Modal (reused from previous Pilot version) */}
      <Modal
        visible={!!activeTarget}
        animationType="slide"
        transparent
        onRequestClose={closeModal}
      >
        <View style={mod.backdrop}>
          <View style={mod.card}>
            <View style={mod.head}>
              <View style={{ flex: 1 }}>
                <Text style={mod.title}>
                  {activeChannel === "email"
                    ? "Email à"
                    : activeChannel === "whatsapp"
                    ? "WhatsApp à"
                    : "LinkedIn à"}{" "}
                  {activeTarget?.name}
                </Text>
                <Text style={mod.sub}>
                  {activeChannel === "email" && activeTarget?.email}
                  {activeChannel === "whatsapp" && activeTarget?.phone}
                  {activeChannel === "linkedin" && (activeTarget?.contact_name || "—")}
                </Text>
              </View>
              <TouchableOpacity onPress={closeModal} style={mod.closeBtn} testID="pilot-close-modal">
                <Ionicons name="close" size={20} color={Colors.text} />
              </TouchableOpacity>
            </View>

            {draftLoading && (
              <View style={{ alignItems: "center", paddingVertical: Spacing.xl }}>
                <ActivityIndicator color={Colors.pilot} />
                <Text style={{ color: Colors.textMuted, marginTop: 8, fontFamily: Fonts.body }}>
                  Rédaction par l&apos;IA…
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
                    <Text style={mod.fieldLabel}>À</Text>
                    <TextInput
                      testID="pilot-email-to"
                      style={mod.input}
                      value={editedTo}
                      onChangeText={setEditedTo}
                      placeholder="contact@exemple.com"
                      placeholderTextColor={Colors.textMuted}
                      autoCapitalize="none"
                      keyboardType="email-address"
                    />
                    <Text style={mod.fieldLabel}>Objet</Text>
                    <TextInput
                      testID="pilot-email-subject"
                      style={mod.input}
                      value={editedSubject}
                      onChangeText={setEditedSubject}
                    />
                  </>
                )}
                <Text style={mod.fieldLabel}>Message</Text>
                <TextInput
                  testID="pilot-msg-body"
                  style={[mod.input, { minHeight: 200, textAlignVertical: "top" }]}
                  value={editedBody}
                  onChangeText={setEditedBody}
                  multiline
                />

                {actionStatus && (
                  <Text testID="pilot-action-status" style={mod.statusText}>
                    {actionStatus}
                  </Text>
                )}

                <View style={mod.actions}>
                  <Text style={mod.creditCost}>Coût : 1 crédit (0,099 €)</Text>
                  {activeChannel === "email" && (
                    <TouchableOpacity
                      testID="pilot-send-email"
                      style={[mod.sendBtn, { backgroundColor: Colors.pilot }, sending && { opacity: 0.6 }]}
                      onPress={sendEmail}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="send" size={14} color="#fff" />
                          <Text style={mod.sendBtnText}>Envoyer l&apos;email</Text>
                        </>
                      )}
                    </TouchableOpacity>
                  )}
                  {activeChannel === "whatsapp" && (
                    <TouchableOpacity
                      testID="pilot-open-whatsapp"
                      style={[mod.sendBtn, { backgroundColor: "#25D366" }, sending && { opacity: 0.6 }]}
                      onPress={openWhatsApp}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="logo-whatsapp" size={14} color="#fff" />
                          <Text style={mod.sendBtnText}>Ouvrir WhatsApp</Text>
                        </>
                      )}
                    </TouchableOpacity>
                  )}
                  {activeChannel === "linkedin" && (
                    <TouchableOpacity
                      testID="pilot-open-linkedin"
                      style={[mod.sendBtn, { backgroundColor: "#0A66C2" }, sending && { opacity: 0.6 }]}
                      onPress={openLinkedIn}
                      disabled={sending}
                    >
                      {sending ? (
                        <ActivityIndicator color="#fff" />
                      ) : (
                        <>
                          <Ionicons name="logo-linkedin" size={14} color="#fff" />
                          <Text style={mod.sendBtnText}>Copier + ouvrir LinkedIn</Text>
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
    </>
  );
}

function TargetsList({
  targets,
  onOpenAction,
}: {
  targets: Target[];
  onOpenAction: (t: Target, c: Channel) => void;
}) {
  return (
    <View style={list.wrap}>
      {targets.map((t) => (
        <View key={t.id} style={list.card} testID={`pilot-target-${t.id}`}>
          <View style={{ flex: 1 }}>
            <Text style={list.name}>{t.name}</Text>
            <Text style={list.meta}>
              {t.type} · {t.city}
              {t.country ? `, ${t.country}` : ""}
            </Text>
          </View>
          {!!t.snippet && <Text style={list.snippet}>{t.snippet}</Text>}
          {!!t.contact_name && (
            <View style={list.row}>
              <Ionicons name="person-outline" size={12} color={Colors.textMuted} />
              <Text style={list.rowText}>
                {t.contact_name}
                {t.contact_role ? ` · ${t.contact_role}` : ""}
              </Text>
            </View>
          )}
          {(t.tags || []).length > 0 && (
            <View style={list.tags}>
              {t.tags.slice(0, 4).map((tag, i) => (
                <View key={i} style={list.tag}>
                  <Text style={list.tagText}>{tag}</Text>
                </View>
              ))}
            </View>
          )}
          <View style={list.actions}>
            <TouchableOpacity
              testID={`pilot-act-email-${t.id}`}
              style={[list.actBtn, { backgroundColor: Colors.pilot }]}
              onPress={() => onOpenAction(t, "email")}
              activeOpacity={0.85}
            >
              <Ionicons name="mail-outline" size={14} color="#fff" />
              <Text style={list.actText}>Email</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID={`pilot-act-whatsapp-${t.id}`}
              style={[list.actBtn, { backgroundColor: "#25D366" }]}
              onPress={() => onOpenAction(t, "whatsapp")}
              activeOpacity={0.85}
            >
              <Ionicons name="logo-whatsapp" size={14} color="#fff" />
              <Text style={list.actText}>WhatsApp</Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID={`pilot-act-linkedin-${t.id}`}
              style={[list.actBtn, { backgroundColor: "#0A66C2" }]}
              onPress={() => onOpenAction(t, "linkedin")}
              activeOpacity={0.85}
            >
              <Ionicons name="logo-linkedin" size={14} color="#fff" />
              <Text style={list.actText}>LinkedIn</Text>
            </TouchableOpacity>
          </View>
        </View>
      ))}
    </View>
  );
}

const list = StyleSheet.create({
  wrap: { gap: Spacing.sm, marginTop: 4 },
  card: {
    backgroundColor: Colors.bgSecondary,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radii.lg,
    padding: Spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: Colors.pilot,
  },
  name: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text },
  meta: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  snippet: {
    fontFamily: Fonts.body,
    fontSize: 13,
    color: Colors.textSecondary,
    marginTop: 6,
    lineHeight: 18,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: Spacing.xs },
  rowText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: Spacing.sm },
  tag: {
    backgroundColor: Colors.bgTertiary,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: Radii.pill,
  },
  tagText: { fontSize: 10, color: Colors.textSecondary, fontFamily: Fonts.body },
  actions: { flexDirection: "row", gap: 6, marginTop: Spacing.md },
  actBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    paddingVertical: 9,
    borderRadius: Radii.md,
  },
  actText: { color: "#fff", fontSize: 12, fontFamily: Fonts.bodyMedium, fontWeight: "700" },
});

const mod = StyleSheet.create({
  creditBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: Colors.pilotSoft,
    borderRadius: Radii.pill,
    borderWidth: 1,
    borderColor: Colors.pilot,
  },
  creditText: {
    fontSize: 12,
    color: Colors.pilotDark,
    fontFamily: Fonts.bodyMedium,
    fontWeight: "700",
  },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  card: {
    backgroundColor: Colors.bgSecondary,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: Spacing.lg,
    paddingBottom: Spacing.xl,
    maxHeight: "92%",
  },
  head: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  title: { fontFamily: Fonts.headingBold, fontSize: 17, color: Colors.text },
  sub: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: Colors.bgTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  fieldLabel: {
    fontFamily: Fonts.bodyMedium,
    fontSize: 11,
    color: Colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginTop: Spacing.sm,
    marginBottom: 6,
    fontWeight: "700",
  },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radii.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: 12,
    fontSize: 14,
    color: Colors.text,
    backgroundColor: Colors.bg,
    fontFamily: Fonts.body,
  },
  statusText: {
    fontFamily: Fonts.body,
    fontSize: 13,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
    lineHeight: 18,
  },
  actions: { marginTop: Spacing.md, gap: Spacing.sm, alignItems: "stretch" },
  creditCost: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, textAlign: "right" },
  sendBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 13,
    borderRadius: Radii.md,
  },
  sendBtnText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 14 },
});
