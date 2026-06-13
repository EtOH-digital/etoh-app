/**
 * ModuleHeader — sticky header shown at the top of each module screen.
 * Displays the module-specific EtOH logo + a credits chip on the right.
 */
import { View, Text, StyleSheet, Image, ImageSourcePropType } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Colors, Fonts, Radii, Spacing } from "@/src/theme";
import { useAuth } from "@/src/auth/AuthContext";

type Props = {
  logo: ImageSourcePropType;
  accent: string;          // color of the credits chip border + bolt
  softAccent: string;      // bg color of the chip
  rightSlot?: React.ReactNode;
};

export function ModuleHeader({ logo, accent, softAccent, rightSlot }: Props) {
  const { user } = useAuth();
  return (
    <View style={s.header}>
      <Image source={logo} style={s.logo} resizeMode="contain" />
      <View style={{ flex: 1 }} />
      {rightSlot}
      <View
        style={[s.chip, { borderColor: accent, backgroundColor: softAccent }]}
        testID="module-credits-chip"
      >
        <Ionicons name="flash" size={11} color={accent} />
        <Text style={[s.chipText, { color: accent }]}>{user?.credits ?? 0}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.bgSecondary,
  },
  logo: { width: 110, height: 44 },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: Radii.pill,
    borderWidth: 1,
  },
  chipText: { fontFamily: Fonts.bodyMedium, fontWeight: "700", fontSize: 12 },
});
