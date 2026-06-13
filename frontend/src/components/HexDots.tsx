/**
 * HexDots — the 6-color hexagon row from the EtOH master logo.
 * Used as a brand signature decoration (login, footers, splash).
 */
import { View, StyleSheet } from "react-native";
import { Colors } from "@/src/theme";

const HEX_COLORS = [
  Colors.hex1,
  Colors.hex2,
  Colors.hex3,
  Colors.hex4,
  Colors.hex5,
  Colors.hex6,
];

export function HexDots({ size = 10, gap = 14 }: { size?: number; gap?: number }) {
  return (
    <View style={[styles.row, { gap }]} testID="brand-hex-dots">
      {HEX_COLORS.map((c, i) => (
        <View
          key={i}
          style={[
            styles.dot,
            {
              width: size,
              height: size * 1.15,
              backgroundColor: c,
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "center" },
  // Slightly hexagonal feel via large border radius + 6/12 ratio handled by parent
  dot: { borderRadius: 2.5, transform: [{ rotate: "0deg" }] },
});
