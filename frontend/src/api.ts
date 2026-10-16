export type ApiProduct = {
  image_url?: string;
  image_urls?: string[];
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

const materialPhotos = {
  aluminium: "/images/aluminium.jpg",
  timber: "/images/vera-timber-detail.png",
  composite: "/images/composite.jpg",
} as const;

export function materialPhoto(product: ApiProduct) {
  return product.image_urls?.[0] || product.image_url || materialPhotos[materialTone(product)];
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
