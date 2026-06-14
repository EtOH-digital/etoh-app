/**
 * RAG documents management UI for the Hub page.
 *
 * Pro-gated: shows an upgrade card for free users. Otherwise lets the user:
 * - Upload PDF/DOCX files
 * - Ingest a public URL
 * - Paste raw text
 * - List/delete already-indexed documents
 *
 * Backend endpoints:
 *  POST /api/rag/documents (multipart, "file")
 *  POST /api/rag/documents/url   {url, name}
 *  POST /api/rag/documents/text  {text, name}
 *  GET  /api/rag/documents
 *  DELETE /api/rag/documents/{doc_id}
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";

import { apiFetch, API_BASE, getToken } from "@/src/api/client";
import { Colors, Fonts, Radii, Shadow, Spacing } from "@/src/theme";
import { captureException } from "@/src/lib/sentry";

type RagDoc = {
  doc_id: string;
  name: string;
  source_type: "pdf" | "docx" | "url" | "text";
  chunk_count: number;
  char_count: number;
  scope: "user" | "global";
  created_at: string;
};

type Features = {
  plan_id: string;
  plan_name: string;
  features: {
    rag?: boolean;
    rag_max_docs?: number;
    [k: string]: any;
  };
};

const ICON_BY_TYPE: Record<string, string> = {
  pdf: "document-text",
  docx: "document",
  url: "link",
  text: "create-outline",
};

export default function RagDocumentsSection() {
  const router = useRouter();
  const [features, setFeatures] = useState<Features | null>(null);
  const [docs, setDocs] = useState<RagDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [urlName, setUrlName] = useState("");
  const [textInput, setTextInput] = useState("");
  const [textName, setTextName] = useState("");
  const [mode, setMode] = useState<"upload" | "url" | "text">("upload");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [f, d] = await Promise.all([
        apiFetch<Features>("/features/me"),
        apiFetch<{ documents: RagDoc[] }>("/rag/documents").catch(() => ({ documents: [] })),
      ]);
      setFeatures(f);
      setDocs(d.documents || []);
    } catch (e: any) {
      captureException(e, { context: "rag.load" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ragEnabled = features?.features?.rag === true;
  const maxDocs = features?.features?.rag_max_docs ?? 0;
  const userDocs = useMemo(() => docs.filter((d) => d.scope !== "global"), [docs]);
  const globalDocs = useMemo(() => docs.filter((d) => d.scope === "global"), [docs]);
  const quotaFull = maxDocs !== -1 && userDocs.length >= maxDocs;

  // ---------------------------- Upload PDF/DOCX ---------------------------
  const pickAndUploadFile = useCallback(async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: [
          "application/pdf",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        multiple: false,
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.length) return;
      const asset = res.assets[0];
      setUploading(true);
      const form = new FormData();
      // RN/Web FormData expect different shapes
      // @ts-ignore
      const fileBlob: any =
        asset.file ||
        ({ uri: asset.uri, name: asset.name, type: asset.mimeType || "application/octet-stream" } as any);
      form.append("file", fileBlob, asset.name);

      const token = await getToken();
      const r = await fetch(`${API_BASE}/rag/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      Alert.alert("Indexé ✓", `${asset.name} — ${data.chunk_count} morceaux indexés.`);
      await load();
    } catch (e: any) {
      captureException(e, { context: "rag.upload_file" });
      Alert.alert("Échec", e?.message || "Impossible d'indexer ce fichier.");
    } finally {
      setUploading(false);
    }
  }, [load]);

  // ----------------------------- Ingest URL -------------------------------
  const ingestUrl = useCallback(async () => {
    if (!urlInput.trim()) return;
    try {
      setUploading(true);
      const data = await apiFetch<{ doc_id: string; chunk_count: number }>("/rag/documents/url", {
        method: "POST",
        body: { url: urlInput.trim(), name: urlName.trim() || null },
      });
      Alert.alert("Indexé ✓", `URL ingérée — ${data.chunk_count} morceaux.`);
      setUrlInput("");
      setUrlName("");
      await load();
    } catch (e: any) {
      captureException(e, { context: "rag.ingest_url" });
      Alert.alert("Échec", e?.message || "Impossible d'indexer cette URL.");
    } finally {
      setUploading(false);
    }
  }, [urlInput, urlName, load]);

  // ----------------------------- Ingest text ------------------------------
  const ingestText = useCallback(async () => {
    if (textInput.trim().length < 30 || !textName.trim()) {
      Alert.alert("Texte trop court", "30 caractères minimum + un titre.");
      return;
    }
    try {
      setUploading(true);
      const data = await apiFetch<{ doc_id: string; chunk_count: number }>("/rag/documents/text", {
        method: "POST",
        body: { text: textInput, name: textName.trim() },
      });
      Alert.alert("Indexé ✓", `Texte ingéré — ${data.chunk_count} morceaux.`);
      setTextInput("");
      setTextName("");
      await load();
    } catch (e: any) {
      captureException(e, { context: "rag.ingest_text" });
      Alert.alert("Échec", e?.message || "Impossible d'indexer ce texte.");
    } finally {
      setUploading(false);
    }
  }, [textInput, textName, load]);

  // ----------------------------- Delete -----------------------------------
  const removeDoc = useCallback(
    (doc: RagDoc) => {
      Alert.alert(
        "Supprimer ce document ?",
        `${doc.name}\n\nLe document et ses ${doc.chunk_count} morceaux seront supprimés. L'IA ne pourra plus s'en servir.`,
        [
          { text: "Annuler", style: "cancel" },
          {
            text: "Supprimer",
            style: "destructive",
            onPress: async () => {
              try {
                await apiFetch(`/rag/documents/${doc.doc_id}`, { method: "DELETE" });
                await load();
              } catch (e: any) {
                Alert.alert("Erreur", e?.message || "Suppression impossible.");
              }
            },
          },
        ],
      );
    },
    [load],
  );

  // ----------------------------- Render -----------------------------------
  if (loading) {
    return (
      <View style={[st.section, { alignItems: "center", paddingVertical: 40 }]}>
        <ActivityIndicator color={Colors.text} />
      </View>
    );
  }

  if (!ragEnabled) {
    return (
      <View style={[st.section, Shadow.card]}>
        <View style={st.gateHeader}>
          <Ionicons name="lock-closed" size={28} color={Colors.warning} />
          <Text style={st.gateTitle}>Base de connaissances IA (RAG)</Text>
        </View>
        <Text style={st.gateBody}>
          Chargez vos plaquettes, fiches techniques, conditions tarifaires (PDF, DOCX, URL) et
          l'IA d'EtOH répondra à toutes les questions sur vos produits, marchés et services en
          s'appuyant sur VOS vrais documents — au lieu d'inventer.
        </Text>
        <Text style={[st.gateBody, { fontFamily: Fonts.bodyMedium, marginTop: 8 }]}>
          Disponible à partir du plan Pro (19€/mois). Activable en 1 clic ci-dessous.
        </Text>
        <Pressable
          onPress={() => router.push("/subscription")}
          style={st.upgradeBtn}
          testID="rag-upgrade-btn"
        >
          <Ionicons name="rocket-outline" size={16} color="#fff" />
          <Text style={st.upgradeBtnText}>Passer en Pro</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View>
      {/* Header + quota */}
      <View style={st.section}>
        <View style={st.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={st.h2}>Base de connaissances</Text>
            <Text style={st.helper}>
              {userDocs.length}
              {maxDocs === -1 ? "" : ` / ${maxDocs}`} documents indexés
              {globalDocs.length > 0 ? `  ·  ${globalDocs.length} docs EtOH inclus` : ""}
            </Text>
          </View>
          <View style={st.planChip}>
            <Ionicons name="checkmark-circle" size={12} color={Colors.success} />
            <Text style={st.planChipText}>{features?.plan_name}</Text>
          </View>
        </View>
        {quotaFull ? (
          <Text style={st.quotaWarn}>
            Quota atteint. Passez en Business pour des documents illimités.
          </Text>
        ) : null}
      </View>

      {/* Source selector */}
      <View style={st.section}>
        <View style={st.modeRow}>
          {(["upload", "url", "text"] as const).map((m) => (
            <Pressable
              key={m}
              onPress={() => setMode(m)}
              style={[st.modeBtn, mode === m && st.modeBtnActive]}
              testID={`rag-mode-${m}`}
            >
              <Ionicons
                name={m === "upload" ? "cloud-upload-outline" : m === "url" ? "link" : "create-outline"}
                size={14}
                color={mode === m ? "#fff" : Colors.textSecondary}
              />
              <Text style={[st.modeText, mode === m && { color: "#fff" }]}>
                {m === "upload" ? "Fichier" : m === "url" ? "URL" : "Texte"}
              </Text>
            </Pressable>
          ))}
        </View>

        {mode === "upload" ? (
          <View style={st.uploadBox}>
            <Ionicons name="cloud-upload-outline" size={36} color={Colors.textMuted} />
            <Text style={st.uploadHint}>PDF ou DOCX, 15 MB max</Text>
            <Pressable
              onPress={pickAndUploadFile}
              disabled={uploading || quotaFull}
              style={[st.primaryBtn, (uploading || quotaFull) && { opacity: 0.5 }]}
              testID="rag-pick-file"
            >
              {uploading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="document-attach-outline" size={16} color="#fff" />
                  <Text style={st.primaryBtnText}>Sélectionner un fichier</Text>
                </>
              )}
            </Pressable>
          </View>
        ) : null}

        {mode === "url" ? (
          <View style={{ gap: 8 }}>
            <TextInput
              value={urlInput}
              onChangeText={setUrlInput}
              placeholder="https://… (article, fiche produit, blog)"
              placeholderTextColor={Colors.textMuted}
              autoCapitalize="none"
              keyboardType="url"
              style={st.input}
              testID="rag-url-input"
            />
            <TextInput
              value={urlName}
              onChangeText={setUrlName}
              placeholder="Nom du document (optionnel)"
              placeholderTextColor={Colors.textMuted}
              style={st.input}
            />
            <Pressable
              onPress={ingestUrl}
              disabled={uploading || !urlInput.trim() || quotaFull}
              style={[
                st.primaryBtn,
                (uploading || !urlInput.trim() || quotaFull) && { opacity: 0.5 },
              ]}
              testID="rag-url-submit"
            >
              {uploading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="cloud-download-outline" size={16} color="#fff" />
                  <Text style={st.primaryBtnText}>Indexer cette URL</Text>
                </>
              )}
            </Pressable>
          </View>
        ) : null}

        {mode === "text" ? (
          <View style={{ gap: 8 }}>
            <TextInput
              value={textName}
              onChangeText={setTextName}
              placeholder="Titre du document"
              placeholderTextColor={Colors.textMuted}
              style={st.input}
            />
            <TextInput
              value={textInput}
              onChangeText={setTextInput}
              placeholder="Collez ici votre texte (CGV, argumentaire, fiche…)"
              placeholderTextColor={Colors.textMuted}
              multiline
              style={[st.input, { height: 140, textAlignVertical: "top" }]}
              testID="rag-text-input"
            />
            <Pressable
              onPress={ingestText}
              disabled={uploading || textInput.trim().length < 30 || !textName.trim() || quotaFull}
              style={[
                st.primaryBtn,
                (uploading || textInput.trim().length < 30 || !textName.trim() || quotaFull) && {
                  opacity: 0.5,
                },
              ]}
              testID="rag-text-submit"
            >
              {uploading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Ionicons name="cloud-upload-outline" size={16} color="#fff" />
                  <Text style={st.primaryBtnText}>Indexer ce texte</Text>
                </>
              )}
            </Pressable>
          </View>
        ) : null}
      </View>

      {/* Documents list */}
      <View style={st.section}>
        <Text style={st.h3}>Mes documents</Text>
        {userDocs.length === 0 ? (
          <Text style={st.emptyHint}>
            Aucun document indexé pour l'instant. Ajoutez votre première plaquette ou fiche
            technique ci-dessus 👆
          </Text>
        ) : (
          userDocs.map((doc) => (
            <View key={doc.doc_id} style={st.docRow} testID={`rag-doc-${doc.doc_id}`}>
              <Ionicons
                name={(ICON_BY_TYPE[doc.source_type] as any) || "document-text"}
                size={22}
                color={Colors.studio}
              />
              <View style={{ flex: 1 }}>
                <Text style={st.docName} numberOfLines={1}>
                  {doc.name}
                </Text>
                <Text style={st.docMeta}>
                  {doc.source_type.toUpperCase()} · {doc.chunk_count} morceaux · {doc.char_count.toLocaleString("fr-FR")} caractères
                </Text>
              </View>
              <Pressable
                onPress={() => removeDoc(doc)}
                hitSlop={10}
                style={st.deleteBtn}
                testID={`rag-delete-${doc.doc_id}`}
              >
                <Ionicons name="trash-outline" size={18} color={Colors.error} />
              </Pressable>
            </View>
          ))
        )}
        {globalDocs.length > 0 ? (
          <>
            <Text style={[st.h3, { marginTop: Spacing.lg }]}>Base de connaissances EtOH</Text>
            <Text style={st.helper}>Documents fournis par EtOH, accessibles à tous.</Text>
            {globalDocs.map((doc) => (
              <View key={doc.doc_id} style={[st.docRow, { backgroundColor: Colors.studioSoft }]}>
                <Ionicons name="globe-outline" size={20} color={Colors.studio} />
                <View style={{ flex: 1 }}>
                  <Text style={st.docName} numberOfLines={1}>
                    {doc.name}
                  </Text>
                  <Text style={st.docMeta}>
                    EtOH · {doc.source_type.toUpperCase()} · {doc.chunk_count} morceaux
                  </Text>
                </View>
              </View>
            ))}
          </>
        ) : null}
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  section: {
    backgroundColor: Colors.bgSecondary,
    borderRadius: Radii.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  headerRow: { flexDirection: "row", alignItems: "center", marginBottom: 4 },
  h2: { fontFamily: Fonts.headingBold, fontSize: 18, color: Colors.text },
  h3: { fontFamily: Fonts.headingBold, fontSize: 15, color: Colors.text, marginBottom: 6 },
  helper: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textSecondary, marginTop: 2 },
  planChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: Colors.bg,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  planChipText: { fontFamily: Fonts.bodyMedium, fontSize: 11, color: Colors.success },
  quotaWarn: {
    fontFamily: Fonts.body,
    fontSize: 12,
    color: Colors.warning,
    marginTop: 8,
  },
  modeRow: { flexDirection: "row", gap: 8, marginBottom: Spacing.md },
  modeBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 10,
    borderRadius: Radii.md,
    backgroundColor: Colors.bgTertiary,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  modeBtnActive: { backgroundColor: Colors.studio, borderColor: Colors.studio },
  modeText: { fontFamily: Fonts.bodyMedium, fontSize: 13, color: Colors.textSecondary },
  uploadBox: {
    paddingVertical: Spacing.lg,
    alignItems: "center",
    gap: Spacing.sm,
    borderWidth: 2,
    borderColor: Colors.border,
    borderStyle: "dashed",
    borderRadius: Radii.md,
  },
  uploadHint: { fontFamily: Fonts.body, fontSize: 12, color: Colors.textMuted },
  input: {
    backgroundColor: Colors.bg,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radii.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: Fonts.body,
    fontSize: 14,
    color: Colors.text,
  },
  primaryBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: Colors.brandPrimary,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: Radii.md,
  },
  primaryBtnText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 14 },
  emptyHint: {
    fontFamily: Fonts.body,
    fontSize: 13,
    color: Colors.textMuted,
    fontStyle: "italic",
    paddingVertical: 12,
    textAlign: "center",
  },
  docRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: Radii.md,
    backgroundColor: Colors.bg,
    marginBottom: 6,
  },
  docName: { fontFamily: Fonts.bodyMedium, fontSize: 14, color: Colors.text },
  docMeta: { fontFamily: Fonts.body, fontSize: 11, color: Colors.textMuted, marginTop: 2 },
  deleteBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  gateHeader: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 8 },
  gateTitle: { fontFamily: Fonts.headingBold, fontSize: 18, color: Colors.text },
  gateBody: { fontFamily: Fonts.body, fontSize: 14, color: Colors.textSecondary, lineHeight: 20 },
  upgradeBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: Colors.hex5,
    paddingVertical: 12,
    paddingHorizontal: 18,
    borderRadius: Radii.md,
    marginTop: Spacing.md,
    alignSelf: "flex-start",
  },
  upgradeBtnText: { color: "#fff", fontFamily: Fonts.bodyBold, fontSize: 14 },
});
