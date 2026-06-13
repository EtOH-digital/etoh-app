import { useState } from "react";

import { Colors } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import ChatScreen, { SendHelpers } from "@/src/components/ChatScreen";

const SUGGESTIONS = [
  "Comment vendre plus en restaurants ?",
  "Veille : tendances vin bio en Allemagne 2026",
  "Comment trouver des importateurs en Belgique ?",
  "Veille : concurrents en Champagne premium",
];

export default function Coach() {
  const { user } = useAuth();
  const [sessionId, setSessionId] = useState<string | undefined>();

  const handleSend = async (text: string, helpers: SendHelpers) => {
    const lang = user?.business_profile?.language || "fr";
    const needsResearch =
      /\b(tendance|tendances|march[ée]|concurrent|concurrence|veille|nouveau|2024|2025|2026|importateur|distributeur|trend|market|competitor)\b/i.test(
        text
      );
    const endpoint = needsResearch ? "/coach/research" : "/coach/message";
    const body = needsResearch
      ? { query: text, language: lang }
      : { session_id: sessionId, message: text, language: lang };
    const data = await apiFetch<any>(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (needsResearch) {
      const sourcesBlock = (data.sources || [])
        .map((s: any) => `- ${s.title} — ${s.url}`)
        .join("\n");
      const reply = `🔎 Veille web (Tavily)\n\n${data.synthesis}${
        sourcesBlock ? "\n\nSources :\n" + sourcesBlock : ""
      }`;
      helpers.appendAssistant({ role: "assistant", content: reply, copyable: true });
    } else {
      setSessionId(data.session_id);
      helpers.appendAssistant({ role: "assistant", content: data.reply, copyable: true });
    }
  };

  return (
    <ChatScreen
      testID="coach"
      color={Colors.coach}
      logo={require("../../assets/brand/coach.png")}
      emptyTitle="Que voulez-vous savoir ?"
      emptySub="Demandez à votre Coach IA n'importe quelle question commerciale, marché ou stratégie."
      suggestions={SUGGESTIONS}
      placeholder="Posez votre question…"
      onSend={handleSend}
    />
  );
}
