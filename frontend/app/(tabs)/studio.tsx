import { Colors } from "@/src/theme";
import { apiFetch } from "@/src/api/client";
import { useAuth } from "@/src/auth/AuthContext";
import ChatScreen, { SendHelpers } from "@/src/components/ChatScreen";

const SUGGESTIONS = [
  "Écris un post LinkedIn pour le lancement de notre nouveau millésime",
  "Rédige un email pour relancer un caviste après un salon",
  "Description premium d'un chardonnay biologique",
  "Message commercial pour un nouveau distributeur",
];

type Template =
  | "linkedin_post"
  | "email_campaign"
  | "sales_message"
  | "product_description"
  | "trade_show_followup"
  | "commercial_presentation";

/** Lightweight keyword-based template detection so the user can just chat. */
function detectTemplate(text: string): Template {
  const t = text.toLowerCase();
  if (/(linkedin|post|publication|réseau)/.test(t)) return "linkedin_post";
  if (/(email|mail|newsletter|campagne|relanc)/.test(t)) {
    return /salon|trade ?show|prowein|wine paris|vinexpo|foire/.test(t)
      ? "trade_show_followup"
      : "email_campaign";
  }
  if (/(description|fiche produit|cuvée|cépage|millésime)/.test(t)) return "product_description";
  if (/(présentation|deck|pitch|argumentaire)/.test(t)) return "commercial_presentation";
  return "sales_message";
}

/** Keyword-based tone detection. */
function detectTone(text: string): "professional" | "warm" | "premium" | "casual" {
  const t = text.toLowerCase();
  if (/(premium|luxe|haut de gamme|grand cru|prestige)/.test(t)) return "premium";
  if (/(chaleureux|amical|sympa|proche)/.test(t)) return "warm";
  if (/(direct|casual|décontracté|familier)/.test(t)) return "casual";
  return "professional";
}

export default function Studio() {
  const { user } = useAuth();

  const handleSend = async (text: string, helpers: SendHelpers) => {
    const lang = user?.business_profile?.language || "fr";
    const data = await apiFetch<{ content: string; template: string }>("/studio/generate", {
      method: "POST",
      body: JSON.stringify({
        template: detectTemplate(text),
        brief: text,
        tone: detectTone(text),
        language: lang,
      }),
    });
    helpers.appendAssistant({
      role: "assistant",
      content: data.content,
      copyable: true,
    });
  };

  return (
    <ChatScreen
      testID="studio"
      color={Colors.studio}
      logo={require("../../assets/brand/studio.png")}
      emptyTitle="Que voulez-vous créer ?"
      emptySub="Décrivez votre besoin (post, email, description…). Studio rédige dans votre voix de marque."
      suggestions={SUGGESTIONS}
      placeholder="Décrivez le contenu à générer…"
      onSend={handleSend}
    />
  );
}
