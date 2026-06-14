import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { Platform, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Colors } from "@/src/theme";
import { useT } from "@/src/i18n/I18nContext";

const TAB_COLORS: Record<string, string> = {
  index: Colors.text,
  coach: Colors.coach,
  studio: Colors.studio,
  pilot: Colors.pilot,
  profile: Colors.text,
};

function TabIcon({
  name,
  color,
  size,
  letter,
}: {
  name?: keyof typeof Ionicons.glyphMap;
  color: string;
  size: number;
  letter?: string;
}) {
  if (letter) {
    return (
      <View style={[styles.letter, { borderColor: color }]}>
        <Text style={[styles.letterText, { color }]}>{letter}</Text>
      </View>
    );
  }
  return <Ionicons name={name!} size={size} color={color} />;
}

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const t = useT();
  return (
    <Tabs
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarShowLabel: true,
        tabBarActiveTintColor: TAB_COLORS[route.name] || Colors.text,
        tabBarInactiveTintColor: Colors.textMuted,
        tabBarStyle: {
          backgroundColor: Colors.bgSecondary,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          paddingBottom: Math.max(insets.bottom, Platform.OS === "ios" ? 0 : 8),
          paddingTop: 8,
          height: 60 + insets.bottom,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "500" },
      })}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tabs.home"),
          tabBarIcon: ({ color, size }) => <TabIcon name="home-outline" color={color} size={size} />,
          tabBarButtonTestID: "nav-home-button",
        }}
      />
      <Tabs.Screen
        name="coach"
        options={{
          title: t("tabs.coach"),
          tabBarIcon: ({ color }) => <TabIcon letter="C" color={color} size={22} />,
          tabBarButtonTestID: "nav-coach-button",
        }}
      />
      <Tabs.Screen
        name="studio"
        options={{
          title: t("tabs.studio"),
          tabBarIcon: ({ color }) => <TabIcon letter="S" color={color} size={22} />,
          tabBarButtonTestID: "nav-studio-button",
        }}
      />
      <Tabs.Screen
        name="pilot"
        options={{
          title: t("tabs.pilot"),
          tabBarIcon: ({ color }) => <TabIcon letter="P" color={color} size={22} />,
          tabBarButtonTestID: "nav-pilot-button",
        }}
      />
      <Tabs.Screen
        name="hub"
        options={{
          title: t("tabs.hub"),
          tabBarIcon: ({ color }) => <TabIcon letter="H" color={color} size={22} />,
          tabBarButtonTestID: "nav-hub-button",
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  letter: {
    width: 24, height: 24, borderRadius: 6,
    borderWidth: 1.5,
    alignItems: "center", justifyContent: "center",
  },
  letterText: { fontSize: 12, fontWeight: "700" },
});
