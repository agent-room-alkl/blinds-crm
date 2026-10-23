// Named shutter add-ons. The server applies prices; these labels only record the choice.
export interface AddonChoice {
  value: string;
  label_zh: string;
  label_en: string;
  fixed?: string;
  per_sqm?: string;
  percent?: string;
}

export interface Addon {
  key: string;
  label_zh: string;
  label_en: string;
  exclude?: string[];
  choices: AddonChoice[];
}

export const ADDONS: Addon[] = [
  { key: "tracked_bifold", label_zh: "轨道对开", label_en: "Tracked bifold", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$350/件", label_en: "Yes, +$350 each" }] },
  { key: "tracked_sliding", label_zh: "轨道推拉", label_en: "Tracked sliding", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$400/件", label_en: "Yes, +$400 each" }] },
  { key: "stained_colour", label_zh: "染色", label_en: "Stained colour", exclude: ["Shutters_PVC", "Shutters_PVC_Eco", "Shutters_Pinewood"], choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$20/㎡", label_en: "Yes, +$20/sqm" }] },
  { key: "stainless_hinges", label_zh: "不锈钢合页", label_en: "Stainless hinges", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$10/㎡", label_en: "Yes, +$10/sqm" }] },
  { key: "hidden_hinges", label_zh: "隐藏合页", label_en: "Hidden hinges", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$40/㎡", label_en: "Yes, +$40/sqm" }] },
  { key: "hidden_tilt_rod", label_zh: "隐藏拉杆", label_en: "Hidden tilt rod", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$40/㎡", label_en: "Yes, +$40/sqm" }] },
  { key: "tier_on_tier", label_zh: "上下分段", label_en: "Tier on tier", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+10%", label_en: "Yes, +10%" }] },
  { key: "double_closure", label_zh: "双闭合", label_en: "Double closure", exclude: ["Shutters_PVC", "Shutters_PVC_Eco"], choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$35/㎡", label_en: "Yes, +$35/sqm" }] },
  { key: "shaped_cutout", label_zh: "异形/法式门开孔", label_en: "Shaped / French door cut out", choices: [
    { value: "no", label_zh: "不要", label_en: "No" }, { value: "yes", label_zh: "要，+$300/件", label_en: "Yes, +$300 each" }] },
  { key: "extra_installation", label_zh: "额外安装", label_en: "Extra installation", choices: [
    { value: "none", label_zh: "无", label_en: "None" },
    { value: "concrete", label_zh: "水泥墙", label_en: "Concrete wall" },
    { value: "height", label_zh: "高空", label_en: "High access" },
    { value: "tile", label_zh: "瓷砖", label_en: "Tile" }] },
];

const ADDON_KEYS = new Set(ADDONS.map((addon) => addon.key));

export function addonsFor(sourceCode?: string): Addon[] {
  if (sourceCode && !sourceCode.startsWith("Shutters_")) return [];
  return ADDONS.map((addon) => ({
    ...addon,
    choices: addon.exclude?.includes(sourceCode || "") ? addon.choices.filter((choice) => choice.value === "no" || choice.value === "none") : addon.choices,
  }));
}

export function withoutAddons(options: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(options).filter(([key]) => !ADDON_KEYS.has(key)));
}

export function describeAddons(options: Record<string, string> | undefined, locale: string): string[] {
  return ADDONS.flatMap((addon) => {
    const value = options?.[addon.key];
    if (!value || value === "no" || value === "none") return [];
    const choice = addon.choices.find((item) => item.value === value);
    const label = locale === "zh" ? addon.label_zh : addon.label_en;
    const picked = choice ? (locale === "zh" ? choice.label_zh : choice.label_en) : value;
    return [`${label}: ${picked}`];
  });
}

export function describeConfiguredAddons(options: Record<string, string> | undefined, locale: string, definitions: Addon[] = []): string[] {
  return definitions.flatMap((addon) => {
    const value = options?.[addon.key];
    if (!value || value === "no" || value === "none") return [];
    const choice = addon.choices.find((item) => item.value === value);
    if (!choice) return [];
    const label = locale === "zh" ? addon.label_zh : addon.label_en;
    const picked = locale === "zh" ? choice.label_zh : choice.label_en;
    return [`${label}: ${picked}`];
  });
}

export function leadText(lead: unknown): string {
  if (!lead) return "";
  if (typeof lead === "string") return lead;
  if (typeof lead === "object" && lead && "text" in lead) return String((lead as { text?: string }).text || "");
  return "";
}
