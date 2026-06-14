import { useState } from "react";

import { Colors } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import { useT, useI18n } from "@/src/i18n/I18nContext";
import ChatScreen, { SendHelpers } from "@/src/components/ChatScreen";

export default function Coach() {
  const { user } = useAuth();
  const t = useT();
  const { lang } = useI18n();
  const [sessionId, setSessionId] = useState<string | undefined>();

  const handleSend = async (text: string, helpers: SendHelpers) => {
    const apiLang = (user?.business_profile?.language || lang) as string;
    const needsResearch =
      /\b(tendance|tendances|march[ée]|concurrent|concurrence|veille|nouveau|2024|2025|2026|importateur|distributeur|trend|market|competitor|tendencia|mercado|importador|distribuidor|tendência|concorrente)\b/i.test(
        text
      );
    const endpoint = needsResearch ? "/coach/research" : "/coach/message";
    const body = needsResearch
      ? { query: text, language: apiLang }
      : { session_id: sessionId, message: text, language: apiLang };
    const data = await apiFetch<any>(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (needsResearch) {
      const sourcesBlock = (data.sources || [])
        .map((s: any) => `- ${s.title} — ${s.url}`)
        .join("\n");
      const reply = `🔎 ${data.synthesis}${sourcesBlock ? "\n\nSources :\n" + sourcesBlock : ""}`;
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
      emptyTitle={t("coach.empty.title")}
      emptySub={t("coach.empty.sub")}
      suggestions={[t("coach.sug.1"), t("coach.sug.2"), t("coach.sug.3"), t("coach.sug.4")]}
      placeholder={t("coach.placeholder")}
      onSend={handleSend}
    />
  );
}
