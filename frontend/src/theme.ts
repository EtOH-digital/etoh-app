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

  // Brand
  coach: "#c7263e",
  coachDark: "#a61c31",
  studio: "#1a365d",
  studioDark: "#11243f",
  pilot: "#4ba3b7",
  pilotDark: "#3d8697",

  // Surfaces
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

export const Fonts = {
  heading: "serif", // Cormorant fallback to system serif (no font files bundled)
  body: "System",
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
