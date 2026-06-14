import { ReactNode } from "react";
import { Text, View, Linking, StyleSheet, TextStyle, ViewStyle } from "react-native";

import { Colors, Fonts, Spacing } from "@/src/theme";

type Props = {
  text: string;
  /** Style applied to base body text (color, fontSize, fontFamily, lineHeight). */
  style?: TextStyle;
  /** Wrapper container style. */
  containerStyle?: ViewStyle;
  /** Accent color for links (defaults to brandPrimary). */
  linkColor?: string;
};

/**
 * Lightweight Markdown renderer for chat replies.
 *
 * Supports:
 *   # Heading 1            → big bold
 *   ## Heading 2           → medium bold
 *   ### Heading 3          → small bold
 *   **bold**, *italic*, _italic_
 *   - bullet, * bullet     → "• "
 *   1. numbered            → "1. "
 *   [text](url)            → tappable link
 *   `inline code`          → mono-ish background
 *   ---                    → divider
 *   blank line             → vertical gap
 *
 * No external dependency.
 */
export default function MarkdownText({ text, style, containerStyle, linkColor }: Props) {
  const accent = linkColor || Colors.brandPrimary;
  const base: TextStyle = style || {
    color: Colors.text,
    fontSize: 15,
    lineHeight: 22,
    fontFamily: Fonts.body,
  };

  // Pre-strip stray ``` fences (rare for Coach/Studio/Pilot but possible).
  const cleaned = (text || "").replace(/^```[a-zA-Z]*\s*\n?/gm, "").replace(/```$/gm, "");

  const lines = cleaned.split("\n");
  const blocks: ReactNode[] = [];

  lines.forEach((rawLine, i) => {
    const line = rawLine.replace(/\s+$/, "");

    // Divider
    if (/^---+$/.test(line.trim())) {
      blocks.push(<View key={i} style={s.divider} />);
      return;
    }
    // Empty line → spacer
    if (line.trim() === "") {
      blocks.push(<View key={i} style={{ height: 8 }} />);
      return;
    }

    // Headings
    let m = line.match(/^(#{1,3})\s+(.*)$/);
    if (m) {
      const level = m[1].length;
      const headStyle: TextStyle =
        level === 1
          ? { fontSize: (base.fontSize || 15) + 5, fontFamily: Fonts.headingBold, marginTop: 4, marginBottom: 4 }
          : level === 2
          ? { fontSize: (base.fontSize || 15) + 2, fontFamily: Fonts.headingBold, marginTop: 4, marginBottom: 2 }
          : { fontSize: (base.fontSize || 15), fontFamily: Fonts.bodyMedium, fontWeight: "700", marginTop: 2 };
      blocks.push(
        <Text key={i} style={[base, headStyle]} selectable>
          {renderInline(m[2], base, accent)}
        </Text>
      );
      return;
    }

    // Bullet list  ( - foo  or  * foo )
    m = line.match(/^\s*[-*]\s+(.*)$/);
    if (m) {
      blocks.push(
        <View key={i} style={s.bulletRow}>
          <Text style={[base, { width: 16 }]} selectable>
            {"• "}
          </Text>
          <Text style={[base, { flex: 1 }]} selectable>
            {renderInline(m[1], base, accent)}
          </Text>
        </View>
      );
      return;
    }

    // Numbered list  ( 1. foo )
    m = line.match(/^\s*(\d+)\.\s+(.*)$/);
    if (m) {
      blocks.push(
        <View key={i} style={s.bulletRow}>
          <Text style={[base, { width: 22 }]} selectable>
            {`${m[1]}. `}
          </Text>
          <Text style={[base, { flex: 1 }]} selectable>
            {renderInline(m[2], base, accent)}
          </Text>
        </View>
      );
      return;
    }

    // Plain paragraph
    blocks.push(
      <Text key={i} style={base} selectable>
        {renderInline(line, base, accent)}
      </Text>
    );
  });

  return <View style={containerStyle}>{blocks}</View>;
}

// ---------------------------------------------------------------------------
// Inline parser  — handles **bold**, *italic* / _italic_, `code`, [link](url)
// ---------------------------------------------------------------------------
function renderInline(text: string, base: TextStyle, accent: string): ReactNode {
  if (!text) return null;

  const tokens: ReactNode[] = [];
  // Order matters: links first (they may contain * or _), then bold, then italic, then code.
  const regex = /(\[[^\]]+\]\([^)]+\)|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;

  let lastIndex = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIndex) {
      tokens.push(<Text key={`t${key++}`}>{text.slice(lastIndex, m.index)}</Text>);
    }
    const raw = m[0];
    if (raw.startsWith("[")) {
      const lm = raw.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (lm) {
        const label = lm[1];
        const url = lm[2];
        tokens.push(
          <Text
            key={`t${key++}`}
            style={{ color: accent, textDecorationLine: "underline" }}
            onPress={() => {
              Linking.openURL(url).catch(() => {});
            }}
          >
            {label}
          </Text>
        );
      } else {
        tokens.push(<Text key={`t${key++}`}>{raw}</Text>);
      }
    } else if (raw.startsWith("**") || raw.startsWith("__")) {
      tokens.push(
        <Text key={`t${key++}`} style={{ fontFamily: Fonts.bodyMedium, fontWeight: "700" }}>
          {raw.slice(2, -2)}
        </Text>
      );
    } else if (raw.startsWith("`")) {
      tokens.push(
        <Text
          key={`t${key++}`}
          style={{
            fontFamily: Fonts.body,
            backgroundColor: Colors.bgTertiary,
            paddingHorizontal: 4,
            borderRadius: 4,
            fontSize: (base.fontSize || 15) - 1,
          }}
        >
          {raw.slice(1, -1)}
        </Text>
      );
    } else if (raw.startsWith("*") || raw.startsWith("_")) {
      tokens.push(
        <Text key={`t${key++}`} style={{ fontStyle: "italic" }}>
          {raw.slice(1, -1)}
        </Text>
      );
    } else {
      tokens.push(<Text key={`t${key++}`}>{raw}</Text>);
    }
    lastIndex = m.index + raw.length;
  }
  if (lastIndex < text.length) {
    tokens.push(<Text key={`t${key++}`}>{text.slice(lastIndex)}</Text>);
  }
  return tokens;
}

const s = StyleSheet.create({
  bulletRow: { flexDirection: "row", alignItems: "flex-start", marginVertical: 1 },
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginVertical: Spacing.sm,
    width: "100%",
  },
});
