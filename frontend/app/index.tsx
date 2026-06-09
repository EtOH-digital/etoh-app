import { Redirect } from "expo-router";
import { useAuth } from "@/src/auth/AuthContext";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { Colors } from "@/src/theme";

export default function Index() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <View style={styles.c}>
        <ActivityIndicator color={Colors.coach} size="large" />
      </View>
    );
  }
  return <Redirect href={user ? "/(tabs)" : "/(auth)/login"} />;
}

const styles = StyleSheet.create({
  c: { flex: 1, backgroundColor: Colors.bg, alignItems: "center", justifyContent: "center" },
});
