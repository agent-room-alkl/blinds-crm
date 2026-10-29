// One place for how a customer reads an order's progress, shared by the order list and the order detail page.
export const ORDER_FLOW = [
  { key: "pending_review", zh: "已提交", en: "Submitted" },
  { key: "accepted", zh: "已确认", en: "Confirmed" },
  { key: "deposit_received", zh: "定金已到账", en: "Deposit received" },
  { key: "supplier_ordered", zh: "已向工厂下单", en: "Ordered" },
  { key: "in_transit", zh: "运输中", en: "In transit" },
  { key: "ready", zh: "已到货，可提取", en: "Ready for collection" },
  { key: "complete", zh: "已提取 / 完成", en: "Collected / complete" },
];

// Orders stored before the ready/complete statuses existed read back under their old names.
const LEGACY: Record<string, string> = { arrived: "ready", partially_arrived: "in_transit", delivered: "complete", partially_delivered: "ready" };

export function normalizeStatus(status: unknown): string {
  const value = typeof status === "string" ? status : "";
  return LEGACY[value] || value;
}

type Lang = "zh" | "en";
const lang = (locale: string): Lang => (locale === "zh" ? "zh" : "en");

export function statusLabel(order: { status?: string; payment_status?: string }, locale: string): string {
  const status = normalizeStatus(order?.status);
  if (status === "accepted" && order?.payment_status === "deposit_unpaid") return lang(locale) === "zh" ? "待付定金" : "Awaiting deposit";
  const step = ORDER_FLOW.find((item) => item.key === status);
  return step ? step[lang(locale)] : lang(locale) === "zh" ? "处理中" : "In progress";
}

export function paymentLabel(paymentStatus: string | undefined, locale: string): string {
  const zh = lang(locale) === "zh";
  if (paymentStatus === "paid") return zh ? "已结清" : "Paid";
  if (paymentStatus === "deposit_received") return zh ? "定金已收，尾款待付" : "Deposit received, balance due";
  if (paymentStatus === "deposit_unpaid") return zh ? "定金待付" : "Deposit due";
  return zh ? "付款处理中" : "Payment pending";
}

export function formatDate(iso: string | undefined, locale: string): string {
  if (!iso) return "";
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(lang(locale) === "zh" ? "zh-CN" : "en-NZ", { day: "numeric", month: "short", year: "numeric" });
}

// The server sends the lead time as English text; build the sentence here so Chinese customers read Chinese.
export function leadTimeLabel(lead: unknown, locale: string): string {
  const weeks = typeof lead === "object" && lead && "weeks" in lead ? String((lead as { weeks?: unknown }).weeks || "") : "";
  if (weeks) return lang(locale) === "zh" ? `定金到账后约 ${weeks} 周` : `${weeks} weeks after the deposit is received`;
  if (typeof lead === "string") return lead;
  return typeof lead === "object" && lead && "text" in lead ? String((lead as { text?: string }).text || "") : "";
}
