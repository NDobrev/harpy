const LINEAR_THRESHOLD = 0.04045;

function channel(hexPair: string): number {
  const value = Number.parseInt(hexPair, 16) / 255;
  return value <= LINEAR_THRESHOLD ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

export function luminance(hexColor: string): number {
  const hex = hexColor.replace("#", "");
  return (
    0.2126 * channel(hex.slice(0, 2)) +
    0.7152 * channel(hex.slice(2, 4)) +
    0.0722 * channel(hex.slice(4, 6))
  );
}

export function contrastRatio(first: string, second: string): number {
  const lighter = Math.max(luminance(first), luminance(second));
  const darker = Math.min(luminance(first), luminance(second));
  return (lighter + 0.05) / (darker + 0.05);
}
