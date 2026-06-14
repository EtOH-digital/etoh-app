import { Colors } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import { useT, useI18n } from "@/src/i18n/I18nContext";
import ChatScreen, { SendHelpers } from "@/src/components/ChatScreen";

type Template =
  | "linkedin_post"
  | "email_campaign"
  | "sales_message"
  | "product_description"
  | "trade_show_followup"
  | "commercial_presentation";

function detectTemplate(text: string): Template {
  const t = text.toLowerCase();
  if (/(linkedin|post|publication|réseau|publicación)/.test(t)) return "linkedin_post";
  if (/(email|mail|newsletter|campagne|relanc|campanha|campaña)/.test(t)) {
    return /salon|trade ?show|prowein|wine paris|vinexpo|foire|feria|feira/.test(t)
      ? "trade_show_followup"
      : "email_campaign";
  }
  if (/(description|fiche produit|cuvée|cépage|millésime|añada|vintage|safra)/.test(t)) return "product_description";
  if (/(présentation|deck|pitch|argumentaire|presentación|apresentação)/.test(t)) return "commercial_presentation";
  return "sales_message";
}

function detectTone(text: string): "professional" | "warm" | "premium" | "casual" {
  const t = text.toLowerCase();
  if (/(premium|luxe|haut de gamme|grand cru|prestige|lujo)/.test(t)) return "premium";
  if (/(chaleureux|amical|sympa|proche|warm|friendly|cordial|amigável)/.test(t)) return "warm";
  if (/(direct|casual|décontracté|familier|informal)/.test(t)) return "casual";
  return "professional";
}

export default function Studio() {
  const { user } = useAuth();
  const t = useT();
  const { lang } = useI18n();

  const handleSend = async (text: string, helpers: SendHelpers) => {
    const apiLang = (user?.business_profile?.language || lang) as string;
    const data = await apiFetch<{ content: string; template: string }>("/studio/generate", {
      method: "POST",
      body: JSON.stringify({
        template: detectTemplate(text),
        brief: text,
        tone: detectTone(text),
        language: apiLang,
      }),
    });
    helpers.appendAssistant({ role: "assistant", content: data.content, copyable: true });
  };

  return (
    <ChatScreen
      testID="studio"
      color={Colors.studio}
      logo={require("../../assets/brand/studio.png")}
      emptyTitle={t("studio.empty.title")}
      emptySub={t("studio.empty.sub")}
      suggestions={[t("studio.sug.1"), t("studio.sug.2"), t("studio.sug.3"), t("studio.sug.4")]}
      placeholder={t("studio.placeholder")}
      onSend={handleSend}
    />
  );
}
