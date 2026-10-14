export type ApiProduct = {
  image_url?: string;
  published?: boolean;
  unit?: string;
  width_min?: number | null;
  width_max?: number | null;
  height_min?: number | null;
  height_max?: number | null;
  colors?: string[];
  controls?: string[];
  id: number;
  name_zh: string;
  name_en: string;
  material_zh: string;
  material_en: string;
  description_zh: string;
  description_en: string;
  category: string;
  sample: boolean;
};

export type InquiryPayload = {
  company: string;
  contact_name: string;
  channel: string;
  locale: "zh" | "en";
  product_id: number | null;
  quantity: number | null;
  width: number | null;
  height: number | null;
  unit: "mm" | "inch" | null;
  expected_date: string;
  notes: string;
  submission_key: string;
  source: "website";
};

export type ConversationPayload = {
  company: string;
  contact_name: string;
  channel: string;
  locale: "zh" | "en";
  weekday_slot: string;
  notes: string;
  submission_key: string;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || `HTTP ${response.status}`);
  }
  return text ? (JSON.parse(text) as T) : ({} as T);
}

const materialPhotos = {
  aluminium: "/images/aluminium.jpg",
  timber: "/images/vera-timber-detail.png",
  composite: "/images/composite.jpg",
} as const;

export function materialPhoto(product: ApiProduct) {
  return product.image_url || materialPhotos[materialTone(product)];
}

export function materialTone(product: ApiProduct): "aluminium" | "timber" | "composite" {
  const hay = `${product.category} ${product.name_en} ${product.material_en} ${product.material_zh}`.toLowerCase();
  if (hay.includes("timber") || hay.includes("wood") || hay.includes("木")) return "timber";
  if (hay.includes("composite") || hay.includes("复合")) return "composite";
  return "aluminium";
}

export async function listProducts() {
  const response = await fetch("/api/products");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as ApiProduct[];
}

export function createInquiry(body: InquiryPayload) {
  return postJson<{ id?: number; reference?: string }>("/api/inquiries", body);
}

export function createConversation(body: ConversationPayload) {
  return postJson<{ id?: number; reference?: string }>("/api/conversations", body);
}
