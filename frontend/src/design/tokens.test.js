import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const baseCss = readFileSync("src/design/base.css", "utf8");
const tokensCss = readFileSync("src/design/tokens.css", "utf8");

const rootFontSize = 16;

function declarations(source) {
  return new Map(
    [...source.matchAll(/([\w-]+)\s*:\s*([^;]+);/g)].map((match) => [
      match[1],
      match[2].trim(),
    ]),
  );
}

function ruleDeclarations(selector) {
  const start = baseCss.indexOf(`${selector} {`);
  if (start < 0) {
    throw new Error(`Missing CSS rule: ${selector}`);
  }

  const bodyStart = baseCss.indexOf("{", start) + 1;
  const bodyEnd = baseCss.indexOf("}", bodyStart);
  return declarations(baseCss.slice(bodyStart, bodyEnd));
}

const tokenValues = declarations(tokensCss);

function resolveToken(value) {
  const tokenName = value.match(/^var\((--[\w-]+)\)$/)?.[1];
  if (!tokenName) {
    return value;
  }

  const resolved = tokenValues.get(tokenName);
  if (!resolved) {
    throw new Error(`Missing token: ${tokenName}`);
  }
  return resolved;
}

function hexChannels(color) {
  const match = color.match(/^#([0-9a-f]{6})$/i);
  if (!match) {
    throw new Error(`Expected six-digit hex color, received: ${color}`);
  }

  return [
    Number.parseInt(match[1].slice(0, 2), 16),
    Number.parseInt(match[1].slice(2, 4), 16),
    Number.parseInt(match[1].slice(4, 6), 16),
  ];
}

function relativeLuminance(color) {
  const channels = hexChannels(color).map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  });

  return (
    channels[0] * 0.2126 +
    channels[1] * 0.7152 +
    channels[2] * 0.0722
  );
}

function contrastRatio(foreground, background) {
  const lighter = Math.max(
    relativeLuminance(foreground),
    relativeLuminance(background),
  );
  const darker = Math.min(
    relativeLuminance(foreground),
    relativeLuminance(background),
  );

  return (lighter + 0.05) / (darker + 0.05);
}

describe("visual tokens", () => {
  it("keeps literal product colors out of component CSS", () => {
    const literalColors =
      baseCss.match(
        /#[0-9a-f]{3,8}\b|(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch)\s*\(|\b(?:white|black)\b(?!-)/gi,
      ) ?? [];

    expect(literalColors).toEqual([]);
  });

  it("keeps compact task status text at the readable type baseline", () => {
    const fontSize = resolveToken(
      ruleDeclarations(".task-status").get("font-size") ?? "",
    );
    const remValue = Number.parseFloat(fontSize);

    expect(fontSize.endsWith("rem")).toBe(true);
    expect(remValue * rootFontSize).toBeGreaterThanOrEqual(12);
  });

  it.each(["success", "warning", "danger"])(
    "keeps %s task status contrast at 4.5:1 or higher",
    (tone) => {
      const rule = ruleDeclarations(`.task-status[data-tone="${tone}"]`);
      const foreground = resolveToken(rule.get("color") ?? "");
      const background = resolveToken(rule.get("background") ?? "");

      expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5);
    },
  );

  it("defines explicit dark tokens and lets auto follow dark system preference", () => {
    expect(tokensCss).toMatch(/:root\[data-theme="dark"\]\s*\{/);
    expect(tokensCss).toMatch(
      /@media\s*\(prefers-color-scheme:\s*dark\)[\s\S]*:root\[data-theme="auto"\]/,
    );
    expect(tokensCss).toMatch(
      /:root\[data-theme="dark"\][\s\S]*--color-canvas:\s*#[0-9a-f]{6}/i,
    );
  });
});
