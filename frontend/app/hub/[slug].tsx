import { useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Linking,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Colors, Spacing, Radii, Fonts } from "@/src/theme";
import HubPublicChat from "@/src/components/HubPublicChat";

type Item = {
  id: string;
  type: "product" | "service" | "document";
  name: string;
  category?: string | null;
  price?: number | null;
  currency?: string | null;
  description?: string | null;
  available_markets?: string[];
  tags?: string[];
};
type HubData = {
  slug: string;
  company: {
    name: string;
    business_type?: string | null;
    region?: string | null;
    main_products?: string | null;
    language?: string | null;
    target_countries?: string[];
    synthesis_tagline?: string | null;
    synthesis_positioning?: string | null;
  };
  items: Item[];
  chat_enabled?: boolean;
};

const API_BASE =
  process.env.EXPO_PUBLIC_BACKEND_URL ||
  (typeof window !== "undefined" ? window.location.origin : "");

export default function PublicHubPage() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const [data, setData] = useState<HubData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/public/hub/${slug}`);
        if (!r.ok) {
          setErr("not_found");
          return;
        }
        setData(await r.json());
      } catch {
        setErr("network");
      }
    })();
  }, [slug]);

  if (err === "not_found") {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}>
          <Ionicons name="alert-circle-outline" size={48} color={Colors.error} />
          <Text style={s.errTitle}>Hub introuvable</Text>
          <Text style={s.errSub}>Aucune entreprise ne correspond à « {slug} ».</Text>
        </View>
      </SafeAreaView>
    );
  }
  if (!data) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}>
          <ActivityIndicator color={Colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  const products = data.items.filter((i) => i.type === "product");
  const services = data.items.filter((i) => i.type === "service");
  const c = data.company;

  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={{ paddingBottom: 60 }}>
        {/* Hero */}
        <View style={s.hero}>
          <View style={s.heroBadge}>
            <Text style={s.heroBadgeText}>HUB · BUSINESS</Text>
          </View>
          <Text style={s.heroTitle}>{c.name}</Text>
          {!!c.synthesis_tagline && (
            <Text style={s.heroTagline}>&quot;{c.synthesis_tagline}&quot;</Text>
          )}
          {!!c.region && (
            <View style={s.heroMetaRow}>
              <Ionicons name="location-outline" size={14} color={Colors.textSecondary} />
              <Text style={s.heroMeta}>{c.region}</Text>
            </View>
          )}
          {!!c.target_countries?.length && (
            <View style={s.heroMetaRow}>
              <Ionicons name="globe-outline" size={14} color={Colors.textSecondary} />
              <Text style={s.heroMeta}>{c.target_countries.join(", ")}</Text>
            </View>
          )}
        </View>

        {!!c.synthesis_positioning && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Positionnement</Text>
            <Text style={s.posText}>{c.synthesis_positioning}</Text>
          </View>
        )}

        {products.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Produits ({products.length})</Text>
            {products.map((p) => (
              <View key={p.id} style={s.card}>
                <View style={s.cardHead}>
                  <Text style={s.cardName}>{p.name}</Text>
                  {p.price != null && (
                    <Text style={s.cardPrice}>
                      {p.price.toFixed(2)} {p.currency || "€"}
                    </Text>
                  )}
                </View>
                {!!p.category && <Text style={s.cardMeta}>{p.category}</Text>}
                {!!p.description && <Text style={s.cardDesc}>{p.description}</Text>}
              </View>
            ))}
          </View>
        )}

        {services.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Services ({services.length})</Text>
            {services.map((sv) => (
              <View key={sv.id} style={s.card}>
                <Text style={s.cardName}>{sv.name}</Text>
                {!!sv.category && <Text style={s.cardMeta}>{sv.category}</Text>}
                {!!sv.description && <Text style={s.cardDesc}>{sv.description}</Text>}
              </View>
            ))}
          </View>
        )}

        <View style={s.section}>
          <TouchableOpacity
            style={s.ctaBtn}
            onPress={() => Linking.openURL("mailto:contact@example.com")}
          >
            <Ionicons name="mail-outline" size={16} color="#fff" />
            <Text style={s.ctaText}>Nous contacter</Text>
          </TouchableOpacity>
        </View>

        {/* Public AI Chat — only when the Hub owner is on a paid plan */}
        {data.chat_enabled ? (
          <HubPublicChat
            slug={data.slug}
            hubName={c.name}
            language={c.language || "fr"}
          />
        ) : null}

        <View style={s.footer}>
          <Text style={s.footerText}>Propulsé par EtOH</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: Spacing.xl, gap: 12 },
  errTitle: { fontFamily: Fonts.headingBold, fontSize: 20, color: Colors.text },
  errSub: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, textAlign: "center" },

  hero: {
    padding: Spacing.xl, paddingTop: Spacing.lg,
    backgroundColor: Colors.bgSecondary,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  heroBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 8, paddingVertical: 3,
    backgroundColor: Colors.brandPrimarySoft,
    borderRadius: Radii.pill, marginBottom: Spacing.sm,
  },
  heroBadgeText: { fontSize: 9, color: Colors.brandPrimary, fontFamily: Fonts.bodyMedium, fontWeight: "700", letterSpacing: 1 },
  heroTitle: { fontFamily: Fonts.headingBold, fontSize: 28, color: Colors.text, marginBottom: 6 },
  heroTagline: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, fontStyle: "italic", marginBottom: Spacing.md, lineHeight: 20 },
  heroMetaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 },
  heroMeta: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary },

  section: { padding: Spacing.lg, gap: Spacing.sm },
  sectionTitle: { fontFamily: Fonts.headingBold, fontSize: 18, color: Colors.text, marginBottom: 6 },
  posText: { fontFamily: Fonts.body, fontSize: 14, color: Colors.text, lineHeight: 20 },

  card: {
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radii.md, padding: Spacing.md, backgroundColor: Colors.bgSecondary,
  },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  cardName: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text, flex: 1 },
  cardPrice: { fontFamily: Fonts.bodyMedium, fontSize: 14, color: Colors.brandPrimary, fontWeight: "700" },
  cardMeta: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted, marginTop: 2 },
  cardDesc: { fontFamily: Fonts.body, fontSize: 13, color: Colors.textSecondary, marginTop: 6, lineHeight: 18 },

  ctaBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: Colors.brandPrimary, borderRadius: Radii.md, paddingVertical: 14,
  },
  ctaText: { color: "#fff", fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 14 },

  footer: { alignItems: "center", padding: Spacing.lg, marginTop: Spacing.lg },
  footerText: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted },
});
