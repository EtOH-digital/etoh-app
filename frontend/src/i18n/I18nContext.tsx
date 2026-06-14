import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as Localization from "expo-localization";

import { storage } from "@/src/utils/storage";
import { Lang, LANGUAGES, TRANSLATIONS } from "@/src/i18n/translations";

const STORAGE_KEY = "etoh.lang";

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => Promise<void>;
  ready: boolean;
  hasPickedLang: boolean;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<Ctx | null>(null);

function detectDeviceLang(): Lang {
  try {
    const locales = Localization.getLocales();
    const code = (locales?.[0]?.languageCode || "en").toLowerCase();
    if (code === "fr") return "fr";
    if (code === "pt") return "pt";
    if (code === "es") return "es";
  } catch {
    // ignore
  }
  return "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("fr");
  const [ready, setReady] = useState(false);
  const [hasPickedLang, setHasPickedLang] = useState(false);

  useEffect(() => {
    (async () => {
      const stored = await storage.getItem<string>(STORAGE_KEY, "");
      if (stored && LANGUAGES.some((l) => l.code === stored)) {
        setLangState(stored as Lang);
        setHasPickedLang(true);
      } else {
        setLangState(detectDeviceLang());
        setHasPickedLang(false);
      }
      setReady(true);
    })();
  }, []);

  const setLang = useCallback(async (l: Lang) => {
    setLangState(l);
    setHasPickedLang(true);
    await storage.setItem(STORAGE_KEY, l);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const dict = TRANSLATIONS[lang] || TRANSLATIONS.fr;
      let text = dict[key];
      if (text === undefined) {
        // Fallback chain: FR > EN > key
        text = TRANSLATIONS.fr[key] ?? TRANSLATIONS.en[key] ?? key;
      }
      if (vars) {
        Object.entries(vars).forEach(([k, v]) => {
          text = text.replace(new RegExp(`{${k}}`, "g"), String(v));
        });
      }
      return text;
    },
    [lang]
  );

  const value = useMemo<Ctx>(
    () => ({ lang, setLang, ready, hasPickedLang, t }),
    [lang, setLang, ready, hasPickedLang, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Defensive fallback for hot-reload edge cases.
    return {
      lang: "fr",
      setLang: async () => {},
      ready: true,
      hasPickedLang: false,
      t: (key) => TRANSLATIONS.fr[key] ?? key,
    };
  }
  return ctx;
}

export function useT() {
  return useI18n().t;
}
