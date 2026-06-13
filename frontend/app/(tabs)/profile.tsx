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
  Linking,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";
import { apiFetch } from "@/src/api/client";

const BUSINESS_TYPES = [
  { id: "winery", label: "Domaine" },
  { id: "cooperative", label: "Coopérative" },
  { id: "merchant", label: "Négociant" },
  { id: "spirits", label: "Spiritueux" },
  { id: "other", label: "Autre" },
];

export default function Profile() {
  const { user, logout, updateProfile, refresh } = useAuth();
  const bp = (user?.business_profile as any) || {};
  const synthesis = bp.synthesis;
  const [synthesizing, setSynthesizing] = useState(false);
  const [crmItems, setCrmItems] = useState<any[]>([]);
  const [crmLoading, setCrmLoading] = useState(false);

  const loadCrm = async () => {
    setCrmLoading(true);
    try {
      const r = await apiFetch<{ items: any[] }>("/crm/contacts");
      setCrmItems(r.items || []);
    } catch {}
    finally { setCrmLoading(false); }
  };

  useEffect(() => { loadCrm(); }, []);

  const regenSynthesis = async () => {
    setSynthesizing(true);
    try {
      await apiFetch("/profile/synthesize", { method: "POST" });
      await refresh();
    } finally { setSynthesizing(false); }
  };

  const updateStatus = async (id: string, status: string) => {
    await apiFetch(`/crm/contacts/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    loadCrm();
  };

  const buyPack = async (packId: "starter" | "growth" | "pro") => {
    try {
      const successUrl = typeof window !== "undefined"
        ? `${window.location.origin}/`
        : "https://ai-coach-autopilot.preview.emergentagent.com/";
      const cancelUrl = successUrl;
      const r = await apiFetch<{ checkout_url: string; session_id: string }>(
        "/wallet/checkout",
        {
          method: "POST",
          body: JSON.stringify({ pack_id: packId, success_url: successUrl, cancel_url: cancelUrl }),
        }
      );
      if (Platform.OS === "web" && typeof window !== "undefined") {
        // Persist session id so we can confirm payment when user returns
        try { localStorage.setItem("etoh.pending_checkout", r.session_id); } catch {}
        window.location.href = r.checkout_url;
      } else {
        await Linking.openURL(r.checkout_url);
      }
    } catch (e: any) {
      alert?.(`Erreur paiement : ${e?.message || e}`);
    }
  };

  // Confirm payment when user returns from Stripe (web only)
  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    const sid = new URLSearchParams(window.location.search).get("session_id");
    if (!sid) return;
    (async () => {
      try {
        const r = await apiFetch<{ status: string; credits_added?: number }>(
          `/wallet/checkout/${sid}`
        );
        if (r.status === "paid") {
          await refresh();
          try { localStorage.removeItem("etoh.pending_checkout"); } catch {}
          // Strip the query param so refreshes don't retrigger
          window.history.replaceState(null, "", window.location.pathname);
        }
      } catch {}
    })();
  }, []);

  const exportCsv = async () => {
    const r = await apiFetch<{ csv: string }>("/crm/export");
    if (Platform.OS === "web" && typeof window !== "undefined") {
      const blob = new Blob([r.csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `etoh-crm-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

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

          {/* Profil Commercial — synthèse IA (US-003) */}
          <View style={s.synthCard} testID="commercial-profile">
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <Text style={s.synthBadge}>PROFIL COMMERCIAL · IA</Text>
              <TouchableOpacity onPress={regenSynthesis} disabled={synthesizing} testID="commercial-profile-regen">
                {synthesizing ? <ActivityIndicator size="small" color={Colors.brandPrimary} /> : <Ionicons name="refresh" size={16} color={Colors.brandPrimary} />}
              </TouchableOpacity>
            </View>
            {synthesis ? (
              <>
                {!!synthesis.tagline && <Text style={s.synthTagline}>"{synthesis.tagline}"</Text>}
                {!!synthesis.positioning && (
                  <View style={s.synthBlock}>
                    <Text style={s.synthLabel}>Positionnement</Text>
                    <Text style={s.synthValue}>{synthesis.positioning}</Text>
                  </View>
                )}
                {Array.isArray(synthesis.icp) && synthesis.icp.length > 0 && (
                  <View style={s.synthBlock}>
                    <Text style={s.synthLabel}>ICP — Acheteurs cibles</Text>
                    {synthesis.icp.map((it: any, i: number) => (
                      <View key={i} style={s.icpRow}>
                        <Text style={s.icpLabel}>• {it.label}</Text>
                        {!!it.why && <Text style={s.icpWhy}>  {it.why}</Text>}
                      </View>
                    ))}
                  </View>
                )}
                {Array.isArray(synthesis.priorities) && synthesis.priorities.length > 0 && (
                  <View style={s.synthBlock}>
                    <Text style={s.synthLabel}>Priorités commerciales</Text>
                    {synthesis.priorities.map((p: string, i: number) => (
                      <Text key={i} style={s.priorityRow}>{i + 1}. {p}</Text>
                    ))}
                  </View>
                )}
              </>
            ) : (
              <TouchableOpacity onPress={regenSynthesis} style={s.synthGenBtn} testID="commercial-profile-generate">
                <Ionicons name="sparkles" size={14} color="#fff" />
                <Text style={s.synthGenText}>Générer mon profil commercial</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* CRM — Mes prospects (US-034) */}
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 32 }}>
            <Text style={[s.sectionTitle, { marginBottom: 0 }]}>Mes prospects ({crmItems.length})</Text>
            {crmItems.length > 0 && (
              <TouchableOpacity onPress={exportCsv} style={s.csvBtn} testID="crm-export">
                <Ionicons name="download-outline" size={14} color={Colors.brandPrimary} />
                <Text style={s.csvBtnText}>Export CSV</Text>
              </TouchableOpacity>
            )}
          </View>
          {crmLoading && <ActivityIndicator color={Colors.brandPrimary} style={{ marginVertical: 12 }} />}
          {!crmLoading && crmItems.length === 0 && (
            <Text style={s.emptyHint}>
              Vos prospects contactés via Pilot apparaîtront ici automatiquement.
            </Text>
          )}
          {crmItems.map((c) => (
            <View key={c.id} style={s.crmCard} testID={`crm-${c.id}`}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={s.crmName}>{c.name}</Text>
                <StatusPill status={c.status} onChange={(st) => updateStatus(c.id, st)} />
              </View>
              <Text style={s.crmMeta}>{c.type} · {c.city}{c.country ? `, ${c.country}` : ""}</Text>
              {!!c.contact_name && <Text style={s.crmMeta}>{c.contact_name}{c.contact_role ? ` · ${c.contact_role}` : ""}</Text>}
              <View style={s.crmFooter}>
                <Text style={s.crmCount}>{c.contact_count}× contacté · dernier canal {c.last_channel}</Text>
                {!!c.email && (
                  <TouchableOpacity onPress={() => Linking.openURL(`mailto:${c.email}`)}>
                    <Ionicons name="mail-outline" size={14} color={Colors.brandPrimary} />
                  </TouchableOpacity>
                )}
              </View>
            </View>
          ))}

          <Text style={[s.sectionTitle, { marginTop: 32 }]}>Mon entreprise</Text>

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

          {/* Wallet */}
          <Text style={[s.sectionTitle, { marginTop: 36 }]}>Wallet</Text>
          <View style={s.walletCard} testID="wallet-card">
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View>
                <Text style={s.walletLabel}>Solde actuel</Text>
                <Text style={s.walletAmount}>{user?.credits ?? 0} <Text style={s.walletUnit}>crédits</Text></Text>
                <Text style={s.walletHint}>≈ {(((user?.credits ?? 0) * 0.099)).toFixed(2)} €</Text>
              </View>
              <Ionicons name="flash" size={36} color={Colors.brandPrimary} />
            </View>
          </View>

          <Text style={[s.label, { marginTop: Spacing.md }]}>Recharger</Text>
          <View style={{ gap: 8 }}>
            <PackRow testID="wallet-pack-99" credits={100} priceEur={9.9} subtitle="Découverte" />
            <PackRow testID="wallet-pack-495" credits={500} priceEur={49.5} subtitle="Régulier" badge="-0%" />
            <PackRow testID="wallet-pack-198" credits={2000} priceEur={178.2} subtitle="Pro" badge="-10%" />
          </View>
          <Text style={s.smallNote}>Paiement Stripe (CB + SEPA) — disponible prochainement.</Text>

          {/* Action costs */}
          <Text style={[s.sectionTitle, { marginTop: 36 }]}>Coût des actions</Text>
          <View style={s.costsCard}>
            {[
              { label: "Analyse Coach", cost: 1 },
              { label: "Recherche prospects (Pilot)", cost: 3 },
              { label: "Génération email / post", cost: 1 },
              { label: "Campagne complète", cost: 10 },
              { label: "Livre blanc", cost: 25 },
            ].map((it, i) => (
              <View key={i} style={[s.costRow, i > 0 && { borderTopWidth: 1, borderTopColor: Colors.border }]}>
                <Text style={s.costLabel}>{it.label}</Text>
                <View style={s.costChip}>
                  <Ionicons name="flash" size={11} color={Colors.brandPrimary} />
                  <Text style={s.costChipText}>{it.cost}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Brand Voice */}
          <Text style={[s.sectionTitle, { marginTop: 36 }]}>Brand Voice</Text>
          <Text style={s.sectionSub}>L'IA utilise ces traits pour rédiger comme vous.</Text>
          {(() => {
            const bv = (user?.business_profile as any) || {};
            const tone = bv.brand_voice_tone || ["professionnel", "expert", "accessible"];
            const personality = bv.brand_voice_personality || ["passionnée", "authentique", "pédagogique"];
            const style = bv.brand_voice_style || ["phrases courtes", "pas de jargon", "storytelling"];
            const langs = bv.brand_voice_languages || ["fr", "en"];
            return (
              <View style={{ gap: 10 }} testID="brand-voice">
                <BVRow icon="megaphone-outline" color={Colors.coach} title="Ton" items={tone} />
                <BVRow icon="heart-outline" color={Colors.studio} title="Personnalité" items={personality} />
                <BVRow icon="create-outline" color={Colors.pilot} title="Style" items={style} />
                <BVRow icon="globe-outline" color={Colors.hex2} title="Langues" items={langs.map((l: string) => l === "fr" ? "Français" : l === "en" ? "English" : l)} />
              </View>
            );
          })()}
          <TouchableOpacity testID="brand-voice-train" style={s.trainBtn} activeOpacity={0.85}>
            <Ionicons name="sparkles-outline" size={14} color="#fff" />
            <Text style={s.trainBtnText}>Entraîner ma Brand Voice</Text>
          </TouchableOpacity>
          <Text style={s.smallNote}>Bientôt : entraînez sur votre site, plaquette PDF, LinkedIn ou Instagram.</Text>

          <TouchableOpacity testID="profile-logout" style={s.logoutBtn} onPress={logout}>
            <Ionicons name="log-out-outline" size={18} color={Colors.error} />
            <Text style={s.logoutText}>Se déconnecter</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function PackRow({ testID, credits, priceEur, subtitle, badge, onPress }: { testID: string; credits: number; priceEur: number; subtitle: string; badge?: string; onPress?: () => void }) {
  return (
    <TouchableOpacity testID={testID} style={s.packRow} activeOpacity={0.85} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={s.packCredits}>{credits} crédits</Text>
          {badge && <View style={s.packBadge}><Text style={s.packBadgeText}>{badge}</Text></View>}
        </View>
        <Text style={s.packSub}>{subtitle}</Text>
      </View>
      <Text style={s.packPrice}>{priceEur.toFixed(2)} €</Text>
      <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
    </TouchableOpacity>
  );
}

function BVRow({ icon, color, title, items }: { icon: any; color: string; title: string; items: string[] }) {
  return (
    <View style={s.bvRow}>
      <View style={[s.bvIcon, { backgroundColor: color + "22" }]}>
        <Ionicons name={icon} size={16} color={color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.bvTitle}>{title}</Text>
        <View style={s.bvChips}>
          {items.map((t, i) => (
            <View key={i} style={s.bvChip}>
              <Text style={s.bvChipText}>{t}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

function StatusPill({ status, onChange }: { status: string; onChange: (s: string) => void }) {
  const opts = [
    { id: "new", label: "Nouveau", color: Colors.textMuted },
    { id: "contacted", label: "Contacté", color: Colors.hex2 },
    { id: "replied", label: "Répondu", color: Colors.hex3 },
    { id: "in_discussion", label: "En discussion", color: Colors.studio },
    { id: "won", label: "Gagné", color: Colors.success },
    { id: "lost", label: "Perdu", color: Colors.error },
  ];
  const idx = opts.findIndex((o) => o.id === status);
  const cur = opts[idx >= 0 ? idx : 0];
  const next = () => onChange(opts[(idx + 1) % opts.length].id);
  return (
    <TouchableOpacity onPress={next} style={[s.statusPill, { borderColor: cur.color, backgroundColor: cur.color + "22" }]} testID={`crm-status-${status}`}>
      <Text style={[s.statusText, { color: cur.color }]}>{cur.label}</Text>
    </TouchableOpacity>
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
  sectionTitle: { fontSize: 16, fontWeight: "600", color: Colors.text, fontFamily: Fonts.headingBold, marginBottom: Spacing.md },
  sectionSub: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: -8, marginBottom: 12 },
  walletCard: { backgroundColor: Colors.brandPrimarySoft, borderRadius: Radii.lg, padding: Spacing.md, borderWidth: 1, borderColor: Colors.border },
  walletLabel: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700" },
  walletAmount: { fontFamily: Fonts.headingBold, fontSize: 32, color: Colors.text, marginTop: 4 },
  walletUnit: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textMuted },
  walletHint: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, marginTop: 2 },
  packRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 14, borderRadius: Radii.md, borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary },
  packCredits: { fontFamily: Fonts.bodyMedium, fontSize: 14, color: Colors.text, fontWeight: "700" },
  packSub: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  packBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: Colors.success + "22" },
  packBadgeText: { fontFamily: Fonts.bodyMedium, fontSize: 10, color: Colors.success, fontWeight: "700" },
  packPrice: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text },
  smallNote: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 8, fontStyle: "italic" },
  costsCard: { borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md, backgroundColor: Colors.bgSecondary },
  costRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 14, paddingVertical: 12 },
  costLabel: { fontFamily: Fonts.body, fontSize: 13, color: Colors.text },
  costChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: Colors.brandPrimarySoft, borderRadius: Radii.pill },
  costChipText: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.brandPrimary, fontWeight: "700" },
  bvRow: { flexDirection: "row", gap: 10, padding: 12, borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md, backgroundColor: Colors.bgSecondary },
  bvIcon: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  bvTitle: { fontFamily: Fonts.bodyMedium, fontSize: 12, color: Colors.textSecondary, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: "700" },
  bvChips: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 6 },
  bvChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: Radii.pill, backgroundColor: Colors.bgTertiary },
  bvChipText: { fontFamily: Fonts.body, fontSize: 11, color: Colors.text },
  trainBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: Colors.brandPrimary, borderRadius: Radii.md, paddingVertical: 12, marginTop: 12 },
  trainBtnText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 13 },
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
