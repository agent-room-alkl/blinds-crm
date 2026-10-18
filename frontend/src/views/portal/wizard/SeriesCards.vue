<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

interface Product {
  id: number;
  name_zh: string;
  name_en: string;
  source_code?: string;
  material_zh?: string;
  material_en?: string;
  image_url?: string;
  orderable?: boolean;
  scope?: string;
  price_rule?: any;
}

const props = defineProps<{
  modelValue: number | null;
  catalog: Product[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: number): void;
  (e: "next"): void;
}>();

// Series metadata from spec
const SERIES_META = {
  Shutters_PVC_Eco: {
    order: 1,
    label_zh: "VERA Eco",
    label_en: "VERA Eco",
    material_zh: "PVC",
    material_en: "PVC",
    tagline_zh: "入门级 PVC。实用可靠。",
    tagline_en: "Entry-level PVC. Practical and reliable.",
    positioning_zh: "入门级防潮选择，适合大批量项目和潮湿区域。",
    positioning_en: "Entry-level moisture-resistant option for high-volume projects and wet areas.",
    tags_zh: "潮湿区域 · 租赁项目 · 实用规格",
    tags_en: "Wet areas · rental projects · practical specification",
    warranty_years: 5,
    color_count: 1,
  },
  Shutters_PVC: {
    order: 2,
    label_zh: "VERA Classic",
    label_en: "VERA Classic",
    material_zh: "高级 PVC",
    material_en: "PVC Premium",
    tagline_zh: "升级 PVC，精致表面处理。",
    tagline_en: "Upgraded PVC with a refined finish.",
    positioning_zh: "高级 PVC 选择，质保更长，表面处理更精致。",
    positioning_en: "Premium PVC option with longer warranty and a more refined finish.",
    tags_zh: "浴室 · 厨房 · 家庭住宅",
    tags_en: "Bathrooms · kitchens · family homes",
    warranty_years: 20,
    color_count: 8,
  },
  Shutters_Pinewood: {
    order: 3,
    label_zh: "VERA Natural",
    label_en: "VERA Natural",
    material_zh: "松木",
    material_en: "Pinewood",
    tagline_zh: "真实木材。入门级价格。",
    tagline_en: "Real timber. Entry-level pricing.",
    positioning_zh: "实惠的真实木材选择，适合注重价值的住宅项目。",
    positioning_en: "Accessible real-timber option for value-driven residential jobs.",
    tags_zh: "入门实木 · 预算意识住宅",
    tags_en: "Entry real wood · budget-conscious homes",
    warranty_years: 5,
    color_count: 8,
  },
  Shutters_Basswood: {
    order: 4,
    label_zh: "VERA Prime",
    label_en: "VERA Prime",
    material_zh: "椴木",
    material_en: "Basswood",
    tagline_zh: "行业标准。一致且多用途。",
    tagline_en: "The trade standard. Consistent and versatile.",
    positioning_zh: "主流行业标准木材系列，适合日常住宅供应。",
    positioning_en: "Mainstream trade-standard timber range for everyday residential supply.",
    tags_zh: "标准住宅 · 多用途转售",
    tags_en: "Standard residential · versatile resale",
    warranty_years: 10,
    color_count: 18,
  },
  VERA_Ashwood_provisional: {
    order: 5,
    label_zh: "VERA Deluxe",
    label_en: "VERA Deluxe",
    material_zh: "白蜡木",
    material_en: "Ashwood",
    tagline_zh: "独特纹理。高级等级。",
    tagline_en: "Distinctive grain. Premium grade.",
    positioning_zh: "高级纹理导向表面处理，适合建筑和展示导向项目。",
    positioning_en: "Premium grain-led finish for architectural and presentation-led projects.",
    tags_zh: "高端住宅 · 设计导向项目",
    tags_en: "Premium homes · design-led projects",
    warranty_years: 10,
    color_count: 10,
    provisional: true,
  },
};

const orderedSeries = computed(() => {
  const shutters = props.catalog.filter(
    (p) => p.source_code && (p.source_code in SERIES_META || p.source_code === 'VERA_Ashwood_display')
  );
  return shutters
    .sort((a, b) => {
      // Normalize old Ashwood code for sorting
      const codeA = a.source_code === 'VERA_Ashwood_display' ? 'VERA_Ashwood_provisional' : a.source_code;
      const codeB = b.source_code === 'VERA_Ashwood_display' ? 'VERA_Ashwood_provisional' : b.source_code;
      const orderA = SERIES_META[codeA as keyof typeof SERIES_META]?.order || 99;
      const orderB = SERIES_META[codeB as keyof typeof SERIES_META]?.order || 99;
      return orderA - orderB;
    })
    .map((p) => {
      // Use provisional metadata for old display code
      const code = p.source_code === 'VERA_Ashwood_display' ? 'VERA_Ashwood_provisional' : p.source_code;
      const meta = SERIES_META[code as keyof typeof SERIES_META];
      return { ...p, ...meta };
    });
});

const aluminiumProduct = computed(() => {
  return props.catalog.find((p) => p.source_code === "Shutters_Aluminium");
});

function selectSeries(id: number) {
  emit("update:modelValue", id);
}

function proceed() {
  if (props.modelValue !== null) {
    emit("next");
  }
}
</script>

<template>
  <div class="series-step">
    <div class="step-intro">
      <p class="section-label">{{ tx("步骤 1 · 选系列", "STEP 1 · SERIES") }}</p>
      <h2>{{ tx("选择产品系列", "Choose Product Series") }}</h2>
      <p>{{ tx("选择默认系列。每扇窗可以在后续步骤中单独调整。", "Select the default series. Each window can be adjusted individually in later steps.") }}</p>
    </div>

    <div class="series-grid">
      <button
        v-for="series in orderedSeries"
        :key="series.id"
        type="button"
        class="series-card"
        :class="{ selected: modelValue === series.id }"
        @click="selectSeries(series.id)"
      >
        <div v-if="(series as any).provisional === true" class="provisional-badge">
          {{ tx("占位价 · 待确认", "Provisional · TBC") }}
        </div>
        <div v-if="series.image_url" class="series-image">
          <img :src="series.image_url" :alt="locale === 'zh' ? series.name_zh : series.name_en" />
        </div>
        <div class="series-content">
          <h3 class="series-title">
            {{ locale === "zh" ? series.label_zh : series.label_en }}
            <span class="series-material">{{ locale === "zh" ? series.material_zh : series.material_en }}</span>
          </h3>
          <p class="series-tagline">{{ locale === "zh" ? series.tagline_zh : series.tagline_en }}</p>
          <p class="series-positioning">{{ locale === "zh" ? series.positioning_zh : series.positioning_en }}</p>
          <div class="series-tags">{{ locale === "zh" ? series.tags_zh : series.tags_en }}</div>
          <div class="series-meta">
            <span>{{ series.warranty_years }} {{ tx("年质保", "yr warranty") }}</span>
            <span>{{ series.color_count }} {{ tx("色", "colors") }}</span>
          </div>
        </div>
        <div v-if="modelValue === series.id" class="check-mark">✓</div>
      </button>
    </div>

    <div v-if="aluminiumProduct" class="other-products">
      <p class="section-label">{{ tx("其他产品", "OTHER PRODUCTS") }}</p>
      <button
        type="button"
        class="series-card series-card-compact"
        :class="{ selected: modelValue === aluminiumProduct.id }"
        @click="selectSeries(aluminiumProduct.id)"
      >
        <div class="series-content">
          <h3 class="series-title">
            {{ locale === "zh" ? aluminiumProduct.name_zh : aluminiumProduct.name_en }}
          </h3>
          <p class="series-positioning">{{ tx("仅登录客户可见", "Available after login") }}</p>
        </div>
        <div v-if="modelValue === aluminiumProduct.id" class="check-mark">✓</div>
      </button>
    </div>

    <div class="step-actions">
      <button type="button" class="primary" :disabled="modelValue === null" @click="proceed">
        {{ tx("下一步 · 窗户列表", "Next · Windows") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.series-step {
  padding: 24px 0;
}

.step-intro {
  margin-bottom: 32px;
}

.step-intro h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 12px 0 16px;
  letter-spacing: 0.01em;
}

.step-intro p {
  font-size: 15px;
  line-height: 1.65;
  color: rgba(27, 36, 33, 0.72);
  max-width: 72ch;
}

.section-label {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--cord);
  font-weight: 600;
  margin-bottom: 8px;
  display: block;
}

.series-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
  margin-bottom: 48px;
}

.series-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border: 2px solid var(--line);
  border-radius: 8px;
  background: white;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
  overflow: hidden;
  min-height: 44px;
}

.series-card:hover {
  border-color: var(--cord);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(15, 110, 92, 0.15);
}

.series-card.selected {
  border-color: var(--cord);
  border-width: 2px;
  box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1);
}

.provisional-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  background: #f59e0b;
  color: white;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 4px;
  letter-spacing: 0.03em;
}

.series-image {
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: rgba(27, 36, 33, 0.04);
}

.series-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.series-content {
  padding: 20px;
  flex: 1;
}

.series-title {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 8px;
  letter-spacing: 0.01em;
  color: var(--ink);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.series-material {
  font-size: 14px;
  font-weight: 500;
  color: rgba(27, 36, 33, 0.6);
}

.series-tagline {
  font-size: 14px;
  font-weight: 500;
  color: var(--cord);
  margin: 0 0 12px;
  line-height: 1.5;
}

.series-positioning {
  font-size: 14px;
  line-height: 1.6;
  color: rgba(27, 36, 33, 0.72);
  margin: 0 0 12px;
}

.series-tags {
  font-size: 12px;
  line-height: 1.5;
  color: rgba(27, 36, 33, 0.6);
  margin: 0 0 12px;
  padding: 8px 12px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 4px;
}

.series-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(27, 36, 33, 0.72);
}

.check-mark {
  position: absolute;
  top: 12px;
  left: 12px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--cord);
  color: white;
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
}

.other-products {
  margin-bottom: 48px;
}

.series-card-compact {
  max-width: 500px;
}

.series-card-compact .series-content {
  padding: 16px 20px;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

button.primary {
  min-height: 48px;
  padding: 12px 32px;
  background: var(--cord);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
}

button.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button.primary:hover:not(:disabled) {
  background: #0c7a67;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 110, 92, 0.3);
}

@media (max-width: 1024px) {
  .series-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 700px) {
  .series-grid {
    grid-template-columns: 1fr;
  }

  .series-card-compact {
    max-width: 100%;
  }
}

.series-step{padding:0}.step-intro{margin:0 0 12px}.step-intro h2{margin:4px 0;font-size:20px}.step-intro p{margin:4px 0;line-height:1.45}.section-label{margin:0 0 4px}
.series-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 12px}.series-content{padding:14px;min-width:0}.series-title{font-size:15px;margin:0 0 6px;flex-direction:row;flex-wrap:wrap;gap:4px 8px;padding-right:20px}.series-material{font-size:12px}.series-tagline{margin:0 0 6px;font-size:13px}.series-positioning{margin:0 0 6px;font-size:13px;line-height:1.45}.series-tags{margin:0 0 8px;padding:4px 6px;font-size:12px}.series-meta{font-size:12px;gap:12px}.check-mark{top:8px;left:auto;right:8px;width:22px;height:22px;font-size:13px}.provisional-badge{position:static;align-self:flex-start;margin:8px 12px 0;padding:2px 6px;font-size:12px;color:#573600;background:#fff1ce}.series-image{max-height:80px}.other-products{display:flex;align-items:center;gap:12px;margin:0 0 12px}.other-products>.section-label{margin:0}.series-card-compact{min-width:240px;max-width:none}.series-card-compact .series-content{padding:8px 12px}.series-card-compact .series-title{margin-bottom:2px}.series-card-compact .series-positioning{margin:0}.step-actions{padding-top:10px;gap:8px}button.primary{min-height:44px;padding:8px 20px}
@media(max-width:700px){.series-grid{grid-template-columns:1fr;gap:8px}.series-content{padding:12px}.other-products{display:block}.other-products>.section-label{margin-bottom:6px}.series-card-compact{width:100%;min-width:0}.step-intro p{font-size:13px}}

.series-card{padding:0;align-items:stretch}.series-content{width:100%}.series-card-compact .series-content{padding:8px 12px}

@media(max-width:700px){.series-grid .series-tagline,.series-grid .series-positioning,.series-grid .series-tags{display:none}.series-grid .series-title{margin-bottom:6px}.series-grid .series-content{padding:10px 12px}.series-grid{gap:6px}}

@media(max-width:700px){.step-intro>.section-label,.step-intro>p:not(.section-label),.other-products>.section-label{display:none}.step-intro{margin-bottom:8px}.series-grid .series-content{padding:8px 12px}.other-products{margin-bottom:8px}}

.series-image{position:absolute;left:12px;top:12px;width:88px;height:70px;aspect-ratio:auto;border-radius:4px}.series-card:has(.series-image) .series-content{padding-left:112px}.series-card:has(.provisional-badge) .series-image{top:44px}
@media(max-width:700px){.series-image{left:auto;right:34px;top:9px;width:44px;height:44px}.series-card:has(.series-image) .series-content{padding-left:12px;padding-right:84px}.series-card:has(.provisional-badge) .series-image{top:36px}}
</style>
