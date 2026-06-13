/**
 * EtOH design tokens — single source of truth for colors, spacing, typography.
 * Aligned with etoh.io brand identity (master EtOH logo + 6 hex accents).
 */
export const Colors = {
  // Surfaces (warm off-white, very subtle)
  bg: "#FAFAF7",
  bgSecondary: "#FFFFFF",
  bgTertiary: "#F2F1ED",
  text: "#1C1917",
  textSecondary: "#4F4B47",
  textMuted: "#9A938C",
  textInverse: "#FFFFFF",
  border: "#E7E4DE",
  divider: "#D6D2CB",
  success: "#15803d",
  warning: "#b45309",
  error: "#b91c1c",

  // Brand (matches the EtOH logo variants provided by the user)
  brandPrimary: "#2B2B2B",   // CTA dark grey — used for primary buttons
  brandPrimarySoft: "#F2F1ED",

  // Module colors — sampled from the official logos
  coach: "#c7263e",          // EtOH Coach — red
  coachDark: "#9c1c30",
  studio: "#1f3a5f",         // EtOH Studio — navy
  studioDark: "#11243f",
  pilot: "#4ba3b7",          // EtOH Pilot — teal
  pilotDark: "#3d8697",

  // Soft tinted surfaces
  coachSoft: "#FBEBED",
  studioSoft: "#E9EFF6",
  pilotSoft: "#E5F2F5",

  // Hexagon accent palette (from EtOH master logo, left → right)
  hex1: "#c8163e",   // red
  hex2: "#f7a01e",   // orange
  hex3: "#4ba3b7",   // teal
  hex4: "#d0d534",   // yellow-green
  hex5: "#c41867",   // magenta
  hex6: "#1f3a5f",   // navy
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const Radii = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  pill: 999,
};

/**
 * Font tokens. Family names match the keys passed to `useFonts(...)` in
 * the root layout. Use `Fonts.headingBold` for any heading/title and
 * `Fonts.body` / `Fonts.bodyMedium` for the rest of the UI.
 */
export const Fonts = {
  heading: "ExpletusSans_400Regular",
  headingBold: "ExpletusSans_700Bold",
  body: "Lato_400Regular",
  bodyMedium: "Lato_700Bold",
  bodyBold: "Lato_900Black",
};

export const Shadow = {
  card: {
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
};
