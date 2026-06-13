import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

// ---------------------------------------------------------------------------
// Aligned with onboarding wizard (/app/(onboarding)/index.tsx)
// ---------------------------------------------------------------------------
const BUSINESS_TYPES = [
  { id: "winery", label: "Domaine viticole", icon: "🍷" },
  { id: "cooperative", label: "Cave / Coopérative", icon: "🏚️" },
  { id: "merchant", label: "Négoce", icon: "📦" },
  { id: "importer", label: "Importateur", icon: "🌎" },
  { id: "distributor", label: "Distributeur", icon: "🚚" },
  { id: "restaurant", label: "Restaurant", icon: "🍽️" },
  { id: "brewery", label: "Brasserie", icon: "🍺" },
  { id: "distillery", label: "Distillerie", icon: "🥃" },
  { id: "wine_shop", label: "Caviste", icon: "🏪" },
  { id: "other", label: "Autre", icon: "✨" },
];

const REVENUES = [
  { id: "<100k", label: "< 100 k€" },
  { id: "100k-500k", label: "100 k - 500 k€" },
  { id: "500k-2M", label: "500 k - 2 M€" },
  { id: "2M-10M", label: "2 M - 10 M€" },
  { id: "10M+", label: "+ 10 M€" },
];

const OBJECTIVES = [
  { id: "distributors", label: "Trouver des distributeurs" },
  { id: "export", label: "Développer l'export" },
  { id: "clients", label: "Trouver des clients" },
  { id: "visibility", label: "Augmenter la visibilité" },
  { id: "content", label: "Produire plus de contenu" },
  { id: "time", label: "Gagner du temps" },
];

const PRODUCTS = [
  { id: "red_wine", label: "Vins rouges" },
  { id: "white_wine", label: "Vins blancs" },
  { id: "rose", label: "Rosés" },
  { id: "sparkling", label: "Effervescents" },
  { id: "spirits", label: "Spiritueux" },
  { id: "beer", label: "Bière" },
  { id: "alcohol_free", label: "Sans alcool" },
  { id: "other", label: "Autres" },
];

const COUNTRIES = [
  "France", "Belgique", "Allemagne", "Royaume-Uni", "USA",
  "Canada", "Suisse", "Japon", "Chine", "Autre",
];
const CHANNELS = ["CHR", "Cavistes", "GMS", "E-commerce", "Export", "Vente directe", "Marketplaces"];

const STATUS_OPTS = [
  { id: "new", label: "Nouveau", color: Colors.textMuted },
  { id: "contacted", label: "Contacté", color: Colors.hex2 },
  { id: "replied", label: "Répondu", color: Colors.hex3 },
  { id: "in_discussion", label: "En discussion", color: Colors.studio },
  { id: "won", label: "Gagné", color: Colors.success },
  { id: "lost", label: "Perdu", color: Colors.error },
];

// ---------------------------------------------------------------------------
// Profile screen
// ---------------------------------------------------------------------------
export default function Profile() {
  const { user, logout, updateProfile, refresh } = useAuth();
  const bp: any = user?.business_profile || {};

  // --- Form state (mirrors onboarding) ---
  const [businessName, setBusinessName] = useState<string>(bp.business_name || "");
  const [businessType, setBusinessType] = useState<string>(bp.business_type || "");
  const [revenue, setRevenue] = useState<string>(bp.revenue || "");
  const [region, setRegion] = useState<string>(bp.region || "");
  const [role, setRole] = useState<string>(bp.role || "");
  const [mainProducts, setMainProducts] = useState<string>(bp.main_products || "");
  const [language, setLanguage] = useState<"fr" | "en">(bp.language || "fr");
  const [objectives, setObjectives] = useState<string[]>(bp.objectives || []);
  const [products, setProducts] = useState<string[]>(bp.products || []);
  const [avgBottlePrice, setAvgBottlePrice] = useState<string>(bp.avg_bottle_price || "");
  const [avgCasePrice, setAvgCasePrice] = useState<string>(bp.avg_case_price || "");
  const [targetCountries, setTargetCountries] = useState<string[]>(bp.target_countries || []);
  const [targetChannels, setTargetChannels] = useState<string[]>(bp.target_channels || []);
  const [goalProspects, setGoalProspects] = useState<string>(String(bp.goal_prospects ?? 50));
  const [goalCampaigns, setGoalCampaigns] = useState<string>(String(bp.goal_campaigns ?? 5));
  const [goalDistributors, setGoalDistributors] = useState<string>(String(bp.goal_distributors ?? 20));
  const [goalMarkets, setGoalMarkets] = useState<string>(String(bp.goal_markets ?? 4));

  const [autoSaving, setAutoSaving] = useState(false);
  const [autoSavedAt, setAutoSavedAt] = useState<number | null>(null);
  const saveTimerRef = useRef<any>(null);
  const firstRunRef = useRef(true);

  // Resync form when the auth context user changes (auto-extract / refresh)
  const lastLearnAt = bp.last_auto_learn_at;
  useEffect(() => {
    setBusinessName(bp.business_name || "");
    setBusinessType(bp.business_type || "");
    setRevenue(bp.revenue || "");
    setRegion(bp.region || "");
    setRole(bp.role || "");
    setMainProducts(bp.main_products || "");
    setLanguage(bp.language || "fr");
    setObjectives(bp.objectives || []);
    setProducts(bp.products || []);
    setAvgBottlePrice(bp.avg_bottle_price || "");
    setAvgCasePrice(bp.avg_case_price || "");
    setTargetCountries(bp.target_countries || []);
    setTargetChannels(bp.target_channels || []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastLearnAt]);

  // --- Debounced auto-save (Claude-Cowork style) ---
  const formSnapshot = useMemo(
    () => ({
      business_name: businessName.trim() || null,
      business_type: businessType || null,
      revenue: revenue || null,
      region: region.trim() || null,
      role: role.trim() || null,
      main_products: mainProducts.trim() || null,
      language,
      objectives,
      products,
      avg_bottle_price: avgBottlePrice || null,
      avg_case_price: avgCasePrice || null,
      target_countries: targetCountries,
      target_channels: targetChannels,
      goal_prospects: Math.max(1, parseInt(goalProspects, 10) || 50),
      goal_campaigns: Math.max(1, parseInt(goalCampaigns, 10) || 5),
      goal_distributors: Math.max(1, parseInt(goalDistributors, 10) || 20),
      goal_markets: Math.max(1, parseInt(goalMarkets, 10) || 4),
    }),
    [
      businessName, businessType, revenue, region, role, mainProducts, language,
      objectives, products, avgBottlePrice, avgCasePrice, targetCountries, targetChannels,
      goalProspects, goalCampaigns, goalDistributors, goalMarkets,
    ]
  );

  useEffect(() => {
    if (firstRunRef.current) {
      firstRunRef.current = false;
      return;
    }
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      setAutoSaving(true);
      try {
        // Filter undefined / null strings -> send only meaningful values
        const payload: any = {};
        Object.entries(formSnapshot).forEach(([k, v]) => {
          if (v === null || v === undefined) return;
          payload[k] = v;
        });
        await updateProfile(payload);
        setAutoSavedAt(Date.now());
      } catch {
        // silent — best-effort
      } finally {
        setAutoSaving(false);
      }
    }, 800);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [formSnapshot, updateProfile]);

  // --- CRM list ---
  const [crmItems, setCrmItems] = useState<any[]>([]);
  const [crmLoading, setCrmLoading] = useState(false);
  const loadCrm = useCallback(async () => {
    setCrmLoading(true);
    try {
      const r = await apiFetch<{ items: any[] }>("/crm/contacts");
      setCrmItems(r.items || []);
    } catch {
      // ignore
    } finally {
      setCrmLoading(false);
    }
  }, []);
  useEffect(() => {
    loadCrm();
  }, [loadCrm]);
  const updateCrmStatus = async (id: string, status: string) => {
    await apiFetch(`/crm/contacts/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    loadCrm();
  };
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

  // --- AI commercial profile synthesis ---
  const synthesis = bp.synthesis;
  const [synthesizing, setSynthesizing] = useState(false);
  const regenSynthesis = async () => {
    setSynthesizing(true);
    try {
      await apiFetch("/profile/synthesize", { method: "POST" });
      await refresh();
    } finally {
      setSynthesizing(false);
    }
  };

  // --- Wallet checkout ---
  const buyPack = async (packId: "starter" | "growth" | "pro") => {
    try {
      const successUrl =
        typeof window !== "undefined"
          ? `${window.location.origin}/`
          : "https://ai-coach-autopilot.preview.emergentagent.com/";
      const r = await apiFetch<{ checkout_url: string; session_id: string }>(
        "/wallet/checkout",
        {
          method: "POST",
          body: JSON.stringify({
            pack_id: packId,
            success_url: successUrl,
            cancel_url: successUrl,
          }),
        }
      );
      if (Platform.OS === "web" && typeof window !== "undefined") {
        try {
          localStorage.setItem("etoh.pending_checkout", r.session_id);
        } catch {}
        window.location.href = r.checkout_url;
      } else {
        await Linking.openURL(r.checkout_url);
      }
    } catch (e: any) {
      alert?.(`Erreur paiement : ${e?.message || e}`);
    }
  };

  // Confirm payment when coming back from Stripe
  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined") return;
    const sid = new URLSearchParams(window.location.search).get("session_id");
    if (!sid) return;
    (async () => {
      try {
        const r = await apiFetch<{ status: string }>(`/wallet/checkout/${sid}`);
        if (r.status === "paid") {
          await refresh();
          try { localStorage.removeItem("etoh.pending_checkout"); } catch {}
          window.history.replaceState(null, "", window.location.pathname);
        }
      } catch {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Toggles ---
  const toggleInList = (
    list: string[],
    id: string,
    setter: (l: string[]) => void
  ) => {
    setter(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  };

  const completion = useMemo(() => {
    const fields = [
      !!businessName, !!businessType, !!revenue, !!region, !!role,
      !!mainProducts, objectives.length > 0, products.length > 0,
      !!avgBottlePrice, targetCountries.length > 0, targetChannels.length > 0,
    ];
    const filled = fields.filter(Boolean).length;
    return Math.round((filled / fields.length) * 100);
  }, [
    businessName, businessType, revenue, region, role, mainProducts,
    objectives, products, avgBottlePrice, targetCountries, targetChannels,
  ]);

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
          {/* Header */}
          <View style={s.header}>
            <View style={s.avatar}>
              <Text style={s.avatarText}>
                {(user?.name || user?.email || "?").charAt(0).toUpperCase()}
              </Text>
            </View>
            <Text style={s.name}>{user?.name || user?.email}</Text>
            <Text style={s.email}>{user?.email}</Text>
          </View>

          {/* Profile completion + auto-save badge */}
          <View style={s.savingRow} testID="profile-saving-state">
            <View style={s.progressBar}>
              <View style={[s.progressFill, { width: `${completion}%` }]} />
            </View>
            <Text style={s.savingHint}>
              {autoSaving
                ? "Enregistrement…"
                : autoSavedAt
                ? "✓ Enregistré automatiquement"
                : `Profil rempli à ${completion}%`}
            </Text>
          </View>

          {bp.last_auto_learn_fields?.length > 0 && (
            <View style={s.learnBanner} testID="profile-learn-banner">
              <Ionicons name="bulb" size={14} color={Colors.brandPrimary} />
              <Text style={s.learnText}>
                EtOH a appris automatiquement :{" "}
                <Text style={{ fontWeight: "700" }}>
                  {(bp.last_auto_learn_fields || []).join(", ")}
                </Text>{" "}
                via {bp.last_auto_learn_source || "chat"}.
              </Text>
            </View>
          )}

          {/* AI Commercial Profile */}
          <View style={s.synthCard} testID="commercial-profile">
            <View style={s.synthHead}>
              <Text style={s.synthBadge}>PROFIL COMMERCIAL · IA</Text>
              <TouchableOpacity
                onPress={regenSynthesis}
                disabled={synthesizing}
                testID="commercial-profile-regen"
              >
                {synthesizing ? (
                  <ActivityIndicator size="small" color={Colors.brandPrimary} />
                ) : (
                  <Ionicons name="refresh" size={16} color={Colors.brandPrimary} />
                )}
              </TouchableOpacity>
            </View>
            {synthesis ? (
              <>
                {!!synthesis.tagline && (
                  <Text style={s.synthTagline}>&quot;{synthesis.tagline}&quot;</Text>
                )}
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
                      <Text key={i} style={s.priorityRow}>
                        {i + 1}. {p}
                      </Text>
                    ))}
                  </View>
                )}
              </>
            ) : (
              <TouchableOpacity
                onPress={regenSynthesis}
                style={s.synthGenBtn}
                testID="commercial-profile-generate"
              >
                <Ionicons name="sparkles" size={14} color="#fff" />
                <Text style={s.synthGenText}>Générer mon profil commercial</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* ======================================================== */}
          {/* SECTION 1 — Mon entreprise                                */}
          {/* ======================================================== */}
          <SectionHeader title="Mon entreprise" icon="business-outline" />

          <Text style={s.label}>Nom de l&apos;entreprise</Text>
          <TextInput
            testID="profile-business-name"
            style={s.input}
            value={businessName}
            onChangeText={setBusinessName}
            placeholder="Ex. Domaine de la Roche"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Métier</Text>
          <View style={s.grid}>
            {BUSINESS_TYPES.map((b) => {
              const active = businessType === b.id;
              return (
                <TouchableOpacity
                  key={b.id}
                  testID={`profile-type-${b.id}`}
                  style={[s.optionTile, active && s.optionTileActive]}
                  onPress={() => setBusinessType(b.id)}
                  activeOpacity={0.85}
                >
                  <Text style={s.optionEmoji}>{b.icon}</Text>
                  <Text style={[s.optionLabel, active && { color: "#fff" }]}>
                    {b.label}
                  </Text>
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
              style={[s.smallChip, language === "fr" && s.smallChipActive]}
              onPress={() => setLanguage("fr")}
            >
              <Text style={[s.smallChipText, language === "fr" && { color: "#fff" }]}>
                Français
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              testID="profile-lang-en"
              style={[s.smallChip, language === "en" && s.smallChipActive]}
              onPress={() => setLanguage("en")}
            >
              <Text style={[s.smallChipText, language === "en" && { color: "#fff" }]}>
                English
              </Text>
            </TouchableOpacity>
          </View>

          {/* ======================================================== */}
          {/* SECTION 2 — Chiffre d'affaires                            */}
          {/* ======================================================== */}
          <SectionHeader title="Chiffre d'affaires annuel" icon="trending-up-outline" />
          <View style={{ gap: 8 }}>
            {REVENUES.map((r) => {
              const active = revenue === r.id;
              return (
                <TouchableOpacity
                  key={r.id}
                  testID={`profile-rev-${r.id}`}
                  style={[s.radioRow, active && s.radioRowActive]}
                  onPress={() => setRevenue(r.id)}
                  activeOpacity={0.85}
                >
                  <View style={[s.radio, active && s.radioActive]}>
                    {active && <View style={s.radioDot} />}
                  </View>
                  <Text
                    style={[
                      s.radioLabel,
                      active && { color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium },
                    ]}
                  >
                    {r.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ======================================================== */}
          {/* SECTION 3 — Objectifs                                     */}
          {/* ======================================================== */}
          <SectionHeader title="Objectifs commerciaux" icon="flag-outline" />
          <View style={{ gap: 8 }}>
            {OBJECTIVES.map((o) => {
              const active = objectives.includes(o.id);
              return (
                <TouchableOpacity
                  key={o.id}
                  testID={`profile-obj-${o.id}`}
                  style={[s.checkRow, active && s.checkRowActive]}
                  onPress={() => toggleInList(objectives, o.id, setObjectives)}
                  activeOpacity={0.85}
                >
                  <View style={[s.check, active && s.checkActive]}>
                    {active && <Ionicons name="checkmark" size={14} color="#fff" />}
                  </View>
                  <Text
                    style={[
                      s.checkLabel,
                      active && { color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium },
                    ]}
                  >
                    {o.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ======================================================== */}
          {/* SECTION 4 — Produits                                      */}
          {/* ======================================================== */}
          <SectionHeader title="Que vendez-vous ?" icon="cube-outline" />
          <View style={s.chipsWrap}>
            {PRODUCTS.map((p) => {
              const active = products.includes(p.id);
              return (
                <TouchableOpacity
                  key={p.id}
                  testID={`profile-prod-${p.id}`}
                  style={[s.bigChip, active && s.bigChipActive]}
                  onPress={() => toggleInList(products, p.id, setProducts)}
                  activeOpacity={0.85}
                >
                  <Text style={[s.bigChipText, active && { color: "#fff" }]}>{p.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={s.label}>Produits principaux (texte libre)</Text>
          <TextInput
            testID="profile-products"
            style={s.input}
            value={mainProducts}
            onChangeText={setMainProducts}
            placeholder="Ex. Vins rouges AOC, Cognac VSOP"
            placeholderTextColor={Colors.textMuted}
          />

          {/* ======================================================== */}
          {/* SECTION 5 — Prix & marchés                                */}
          {/* ======================================================== */}
          <SectionHeader title="Prix & marchés cibles" icon="cash-outline" />

          <Text style={s.label}>Prix moyen bouteille (€)</Text>
          <TextInput
            testID="profile-bottle-price"
            style={s.input}
            value={avgBottlePrice}
            onChangeText={setAvgBottlePrice}
            placeholder="Ex. 18"
            placeholderTextColor={Colors.textMuted}
            keyboardType="numeric"
          />

          <Text style={s.label}>Prix moyen carton (€)</Text>
          <TextInput
            testID="profile-case-price"
            style={s.input}
            value={avgCasePrice}
            onChangeText={setAvgCasePrice}
            placeholder="Ex. 110"
            placeholderTextColor={Colors.textMuted}
            keyboardType="numeric"
          />

          <Text style={s.label}>Pays ciblés</Text>
          <View style={s.chipsWrap}>
            {COUNTRIES.map((c) => {
              const active = targetCountries.includes(c);
              return (
                <TouchableOpacity
                  key={c}
                  testID={`profile-country-${c}`}
                  style={[s.smallChip, active && s.smallChipActive]}
                  onPress={() => toggleInList(targetCountries, c, setTargetCountries)}
                >
                  <Text style={[s.smallChipText, active && { color: "#fff" }]}>{c}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={s.label}>Canaux visés</Text>
          <View style={s.chipsWrap}>
            {CHANNELS.map((ch) => {
              const active = targetChannels.includes(ch);
              return (
                <TouchableOpacity
                  key={ch}
                  testID={`profile-channel-${ch}`}
                  style={[s.smallChip, active && s.smallChipActive]}
                  onPress={() => toggleInList(targetChannels, ch, setTargetChannels)}
                >
                  <Text style={[s.smallChipText, active && { color: "#fff" }]}>{ch}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* ======================================================== */}
          {/* SECTION 6 — Objectifs hebdomadaires                       */}
          {/* ======================================================== */}
          <SectionHeader title="Objectifs hebdomadaires" icon="speedometer-outline" />
          <Text style={s.label}>Prospects identifiés / semaine</Text>
          <TextInput
            testID="profile-goal-prospects"
            style={s.input}
            value={goalProspects}
            onChangeText={setGoalProspects}
            keyboardType="number-pad"
          />
          <Text style={s.label}>Campagnes envoyées / semaine</Text>
          <TextInput
            testID="profile-goal-campaigns"
            style={s.input}
            value={goalCampaigns}
            onChangeText={setGoalCampaigns}
            keyboardType="number-pad"
          />
          <Text style={s.label}>Distributeurs contactés / semaine</Text>
          <TextInput
            testID="profile-goal-distributors"
            style={s.input}
            value={goalDistributors}
            onChangeText={setGoalDistributors}
            keyboardType="number-pad"
          />
          <Text style={s.label}>Marchés analysés / semaine</Text>
          <TextInput
            testID="profile-goal-markets"
            style={s.input}
            value={goalMarkets}
            onChangeText={setGoalMarkets}
            keyboardType="number-pad"
          />

          {/* ======================================================== */}
          {/* SECTION 7 — CRM                                           */}
          {/* ======================================================== */}
          <SectionHeader title={`Mes prospects (${crmItems.length})`} icon="people-outline">
            {crmItems.length > 0 && (
              <TouchableOpacity onPress={exportCsv} style={s.csvBtn} testID="crm-export">
                <Ionicons name="download-outline" size={14} color={Colors.brandPrimary} />
                <Text style={s.csvBtnText}>Export CSV</Text>
              </TouchableOpacity>
            )}
          </SectionHeader>
          {crmLoading && <ActivityIndicator color={Colors.brandPrimary} style={{ marginVertical: 12 }} />}
          {!crmLoading && crmItems.length === 0 && (
            <Text style={s.emptyHint}>
              Vos prospects contactés via Pilot apparaîtront ici automatiquement.
            </Text>
          )}
          {crmItems.map((c) => (
            <View key={c.id} style={s.crmCard} testID={`crm-${c.id}`}>
              <View style={s.crmHead}>
                <Text style={s.crmName}>{c.name}</Text>
                <StatusPill
                  status={c.status}
                  onChange={(st) => updateCrmStatus(c.id, st)}
                />
              </View>
              <Text style={s.crmMeta}>
                {c.type} · {c.city}
                {c.country ? `, ${c.country}` : ""}
              </Text>
              {!!c.contact_name && (
                <Text style={s.crmMeta}>
                  {c.contact_name}
                  {c.contact_role ? ` · ${c.contact_role}` : ""}
                </Text>
              )}
              <View style={s.crmFooter}>
                <Text style={s.crmCount}>
                  {c.contact_count}× contacté · dernier canal {c.last_channel}
                </Text>
                {!!c.email && (
                  <TouchableOpacity onPress={() => Linking.openURL(`mailto:${c.email}`)}>
                    <Ionicons name="mail-outline" size={14} color={Colors.brandPrimary} />
                  </TouchableOpacity>
                )}
              </View>
            </View>
          ))}

          {/* ======================================================== */}
          {/* SECTION 8 — Wallet                                        */}
          {/* ======================================================== */}
          <SectionHeader title="Wallet" icon="card-outline" />
          <View style={s.walletCard} testID="wallet-card">
            <View style={s.walletRow}>
              <View>
                <Text style={s.walletLabel}>Solde actuel</Text>
                <Text style={s.walletAmount}>
                  {user?.credits ?? 0}{" "}
                  <Text style={s.walletUnit}>crédits</Text>
                </Text>
                <Text style={s.walletHint}>
                  ≈ {(((user?.credits ?? 0) * 0.099)).toFixed(2)} €
                </Text>
              </View>
              <Ionicons name="flash" size={36} color={Colors.brandPrimary} />
            </View>
          </View>

          <Text style={[s.label, { marginTop: Spacing.md }]}>Recharger</Text>
          <View style={{ gap: 8 }}>
            <PackRow
              testID="wallet-pack-99"
              credits={100}
              priceEur={9.9}
              subtitle="Découverte"
              onPress={() => buyPack("starter")}
            />
            <PackRow
              testID="wallet-pack-495"
              credits={500}
              priceEur={49.5}
              subtitle="Régulier"
              badge="-0%"
              onPress={() => buyPack("growth")}
            />
            <PackRow
              testID="wallet-pack-198"
              credits={2000}
              priceEur={178.2}
              subtitle="Pro"
              badge="-10%"
              onPress={() => buyPack("pro")}
            />
          </View>

          {/* Action costs */}
          <SectionHeader title="Coût des actions" icon="pricetag-outline" />
          <View style={s.costsCard}>
            {[
              { label: "Analyse Coach", cost: 1 },
              { label: "Recherche prospects (Pilot)", cost: 3 },
              { label: "Génération email / post", cost: 1 },
              { label: "Campagne complète", cost: 10 },
              { label: "Livre blanc", cost: 25 },
            ].map((it, i) => (
              <View
                key={i}
                style={[s.costRow, i > 0 && { borderTopWidth: 1, borderTopColor: Colors.border }]}
              >
                <Text style={s.costLabel}>{it.label}</Text>
                <View style={s.costChip}>
                  <Ionicons name="flash" size={11} color={Colors.brandPrimary} />
                  <Text style={s.costChipText}>{it.cost}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Brand Voice */}
          <SectionHeader title="Brand Voice" icon="color-palette-outline" />
          <Text style={s.sectionSub}>L&apos;IA utilise ces traits pour rédiger comme vous.</Text>
          {(() => {
            const tone = bp.brand_voice_tone || ["professionnel", "expert", "accessible"];
            const personality = bp.brand_voice_personality || ["passionnée", "authentique", "pédagogique"];
            const style = bp.brand_voice_style || ["phrases courtes", "pas de jargon", "storytelling"];
            const langs = bp.brand_voice_languages || ["fr", "en"];
            return (
              <View style={{ gap: 10 }} testID="brand-voice">
                <BVRow icon="megaphone-outline" color={Colors.coach} title="Ton" items={tone} />
                <BVRow icon="heart-outline" color={Colors.studio} title="Personnalité" items={personality} />
                <BVRow icon="create-outline" color={Colors.pilot} title="Style" items={style} />
                <BVRow
                  icon="globe-outline"
                  color={Colors.hex2}
                  title="Langues"
                  items={langs.map((l: string) => (l === "fr" ? "Français" : l === "en" ? "English" : l))}
                />
              </View>
            );
          })()}
          <TouchableOpacity testID="brand-voice-train" style={s.trainBtn} activeOpacity={0.85}>
            <Ionicons name="sparkles-outline" size={14} color="#fff" />
            <Text style={s.trainBtnText}>Entraîner ma Brand Voice</Text>
          </TouchableOpacity>
          <Text style={s.smallNote}>
            Bientôt : entraînez sur votre site, plaquette PDF, LinkedIn ou Instagram.
          </Text>

          <TouchableOpacity testID="profile-logout" style={s.logoutBtn} onPress={logout}>
            <Ionicons name="log-out-outline" size={18} color={Colors.error} />
            <Text style={s.logoutText}>Se déconnecter</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function SectionHeader({
  title,
  icon,
  children,
}: {
  title: string;
  icon: any;
  children?: React.ReactNode;
}) {
  return (
    <View style={s.sectionHead}>
      <View style={s.sectionTitleRow}>
        <Ionicons name={icon} size={16} color={Colors.text} />
        <Text style={s.sectionTitle}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function PackRow({
  testID,
  credits,
  priceEur,
  subtitle,
  badge,
  onPress,
}: {
  testID: string;
  credits: number;
  priceEur: number;
  subtitle: string;
  badge?: string;
  onPress?: () => void;
}) {
  return (
    <TouchableOpacity testID={testID} style={s.packRow} activeOpacity={0.85} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <View style={s.packTitleRow}>
          <Text style={s.packCredits}>{credits} crédits</Text>
          {badge && (
            <View style={s.packBadge}>
              <Text style={s.packBadgeText}>{badge}</Text>
            </View>
          )}
        </View>
        <Text style={s.packSub}>{subtitle}</Text>
      </View>
      <Text style={s.packPrice}>{priceEur.toFixed(2)} €</Text>
      <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
    </TouchableOpacity>
  );
}

function BVRow({
  icon,
  color,
  title,
  items,
}: {
  icon: any;
  color: string;
  title: string;
  items: string[];
}) {
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

function StatusPill({
  status,
  onChange,
}: {
  status: string;
  onChange: (s: string) => void;
}) {
  const idx = STATUS_OPTS.findIndex((o) => o.id === status);
  const cur = STATUS_OPTS[idx >= 0 ? idx : 0];
  const cycle = () => onChange(STATUS_OPTS[(idx + 1) % STATUS_OPTS.length].id);
  return (
    <TouchableOpacity
      onPress={cycle}
      style={[s.statusPill, { borderColor: cur.color, backgroundColor: cur.color + "22" }]}
      testID={`crm-status-${status}`}
    >
      <Text style={[s.statusText, { color: cur.color }]}>{cur.label}</Text>
    </TouchableOpacity>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  header: { alignItems: "center", marginBottom: Spacing.lg, paddingTop: Spacing.md },
  avatar: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: Colors.coach,
    alignItems: "center", justifyContent: "center", marginBottom: Spacing.md,
  },
  avatarText: { color: "#fff", fontSize: 28, fontFamily: Fonts.headingBold },
  name: { fontSize: 18, color: Colors.text, fontFamily: Fonts.headingBold },
  email: { fontSize: 13, color: Colors.textMuted, marginTop: 2, fontFamily: Fonts.body },

  savingRow: { marginBottom: Spacing.md, gap: 6 },
  progressBar: { height: 4, backgroundColor: Colors.border, borderRadius: 2, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: Colors.brandPrimary },
  savingHint: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, textAlign: "right" },

  learnBanner: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: Colors.brandPrimarySoft,
    borderRadius: Radii.md,
    borderLeftWidth: 3, borderLeftColor: Colors.brandPrimary,
    marginBottom: Spacing.md,
  },
  learnText: { flex: 1, fontFamily: Fonts.body, fontSize: 12, color: Colors.text, lineHeight: 17 },

  sectionHead: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    marginTop: Spacing.xl, marginBottom: Spacing.md,
  },
  sectionTitleRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  sectionTitle: { fontSize: 16, color: Colors.text, fontFamily: Fonts.headingBold },
  sectionSub: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: -8, marginBottom: 12 },

  // Synthesis
  synthCard: {
    borderWidth: 1, borderColor: Colors.brandPrimary,
    backgroundColor: Colors.brandPrimarySoft,
    borderRadius: Radii.lg, padding: Spacing.md, marginBottom: Spacing.md,
  },
  synthHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  synthBadge: {
    fontFamily: Fonts.bodyMedium, fontSize: 10, color: Colors.brandPrimary,
    fontWeight: "700", letterSpacing: 1,
  },
  synthTagline: {
    fontFamily: Fonts.headingBold, fontSize: 16, color: Colors.text,
    fontStyle: "italic", marginBottom: 12, lineHeight: 22,
  },
  synthBlock: { marginTop: 8 },
  synthLabel: {
    fontFamily: Fonts.bodyMedium, fontSize: 10, color: Colors.textSecondary,
    textTransform: "uppercase", letterSpacing: 1, marginBottom: 4, fontWeight: "700",
  },
  synthValue: { fontFamily: Fonts.body, fontSize: 13, color: Colors.text, lineHeight: 18 },
  icpRow: { marginTop: 4 },
  icpLabel: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.text, fontWeight: "600" },
  icpWhy: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, lineHeight: 16 },
  priorityRow: { fontFamily: Fonts.body, fontSize: 13, color: Colors.text, marginTop: 4, lineHeight: 18 },
  synthGenBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: Colors.brandPrimary, borderRadius: Radii.md, paddingVertical: 12,
  },
  synthGenText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 13 },

  // Inputs
  label: {
    fontSize: 11, color: Colors.textSecondary, textTransform: "uppercase",
    letterSpacing: 1, marginBottom: 8, marginTop: Spacing.md, fontWeight: "700",
    fontFamily: Fonts.bodyMedium,
  },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: 14,
    color: Colors.text, backgroundColor: Colors.bgSecondary, fontFamily: Fonts.body,
  },

  // Onboarding-style options
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  optionTile: {
    width: "48%", padding: Spacing.md, borderRadius: Radii.md,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
    alignItems: "flex-start",
  },
  optionTileActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  optionEmoji: { fontSize: 22, marginBottom: 6 },
  optionLabel: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.text, fontWeight: "700" },

  radioRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    padding: Spacing.md, borderRadius: Radii.md,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  radioRowActive: { borderColor: Colors.brandPrimary, backgroundColor: Colors.bgSecondary },
  radio: {
    width: 20, height: 20, borderRadius: 10, borderWidth: 2,
    borderColor: Colors.border, alignItems: "center", justifyContent: "center",
  },
  radioActive: { borderColor: Colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.brandPrimary },
  radioLabel: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },

  checkRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    padding: Spacing.md, borderRadius: Radii.md,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  checkRowActive: { borderColor: Colors.brandPrimary },
  check: {
    width: 22, height: 22, borderRadius: 6, borderWidth: 2,
    borderColor: Colors.border, alignItems: "center", justifyContent: "center",
  },
  checkActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  checkLabel: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text },

  chipsWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: Spacing.sm },
  bigChip: {
    paddingHorizontal: Spacing.md, paddingVertical: 12, borderRadius: Radii.pill,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  bigChipActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  bigChipText: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.text, fontWeight: "700" },
  smallChip: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: Radii.pill,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  smallChipActive: { backgroundColor: Colors.brandPrimary, borderColor: Colors.brandPrimary },
  smallChipText: { fontFamily: Fonts.body, fontSize: 12, color: Colors.text },

  // CRM
  emptyHint: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, fontStyle: "italic" },
  crmCard: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md,
    backgroundColor: Colors.bgSecondary, padding: Spacing.md, marginTop: Spacing.sm,
  },
  crmHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  crmName: { fontFamily: Fonts.headingBold, fontSize: 14, color: Colors.text },
  crmMeta: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  crmFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  crmCount: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted },
  statusPill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: Radii.pill, borderWidth: 1 },
  statusText: { fontFamily: Fonts.bodyMedium, fontSize: 11, fontWeight: "700" },
  csvBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6 },
  csvBtnText: { fontFamily: Fonts.bodyMedium, fontSize: 12, color: Colors.brandPrimary, fontWeight: "700" },

  // Wallet
  walletCard: {
    backgroundColor: Colors.brandPrimarySoft, borderRadius: Radii.lg,
    padding: Spacing.md, borderWidth: 1, borderColor: Colors.border,
  },
  walletRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  walletLabel: {
    fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.textSecondary,
    textTransform: "uppercase", letterSpacing: 1, fontWeight: "700",
  },
  walletAmount: { fontFamily: Fonts.headingBold, fontSize: 32, color: Colors.text, marginTop: 4 },
  walletUnit: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textMuted },
  walletHint: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, marginTop: 2 },

  packRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: 14, paddingVertical: 14, borderRadius: Radii.md,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.bgSecondary,
  },
  packTitleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  packCredits: { fontFamily: Fonts.bodyMedium, fontSize: 14, color: Colors.text, fontWeight: "700" },
  packSub: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  packBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: Colors.success + "22" },
  packBadgeText: { fontFamily: Fonts.bodyMedium, fontSize: 10, color: Colors.success, fontWeight: "700" },
  packPrice: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text },

  costsCard: { borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md, backgroundColor: Colors.bgSecondary },
  costRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 14, paddingVertical: 12 },
  costLabel: { fontFamily: Fonts.body, fontSize: 13, color: Colors.text },
  costChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: Colors.brandPrimarySoft, borderRadius: Radii.pill },
  costChipText: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.brandPrimary, fontWeight: "700" },

  // Brand voice
  bvRow: {
    flexDirection: "row", gap: 10, padding: 12,
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radii.md, backgroundColor: Colors.bgSecondary,
  },
  bvIcon: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  bvTitle: {
    fontFamily: Fonts.bodyMedium, fontSize: 12, color: Colors.textSecondary,
    textTransform: "uppercase", letterSpacing: 0.5, fontWeight: "700",
  },
  bvChips: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 6 },
  bvChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: Radii.pill, backgroundColor: Colors.bgTertiary },
  bvChipText: { fontFamily: Fonts.body, fontSize: 11, color: Colors.text },
  trainBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: Colors.brandPrimary, borderRadius: Radii.md, paddingVertical: 12, marginTop: 12,
  },
  trainBtnText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 13 },
  smallNote: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 8, fontStyle: "italic" },

  logoutBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 14, marginTop: Spacing.lg,
  },
  logoutText: { color: Colors.error, fontFamily: Fonts.bodyMedium, fontWeight: "600", fontSize: 14 },
});
