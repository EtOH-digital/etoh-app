/**
 * EtOH design tokens — single source of truth for colors, spacing, typography.
 */
export const Colors = {
  bg: "#FAFAF9",
  bgSecondary: "#FFFFFF",
  bgTertiary: "#F5F5F4",
  text: "#1C1917",
  textSecondary: "#57534E",
  textMuted: "#A8A29E",
  textInverse: "#FFFFFF",
  border: "#E7E5E4",
  divider: "#D6D3D1",
  success: "#15803d",
  warning: "#b45309",
  error: "#b91c1c",

  // Brand (matches the EtOH logo variants provided by the user)
  brandPrimary: "#1f3a5f", // EtOH navy used in default logo and Studio
  coach: "#c7263e",        // Coach — red
  coachDark: "#a61c31",
  studio: "#1f3a5f",       // Studio — dark navy
  studioDark: "#152a45",
  pilot: "#4ba3b7",        // Pilot — teal
  pilotDark: "#3d8697",

  // Soft surfaces (tinted backgrounds for module cards)
  coachSoft: "#FCEFF1",
  studioSoft: "#EAF0F7",
  pilotSoft: "#E8F4F7",
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
 * `Fonts.body` / `Fonts.bodyBold` for the rest of the UI.
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
    shadowOpacity: 0.05,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
};
