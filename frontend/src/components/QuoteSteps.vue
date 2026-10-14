<script setup lang="ts">
import { computed } from 'vue';
const props = defineProps<{ current: number; locale: string }>();
const emit = defineEmits<{ select: [step: number] }>();
const zh = computed(() => props.locale === 'zh');
const steps = computed(() => zh.value
  ? [{ title: '报价条件', detail: '语言、币种与有效期' }, { title: '产品明细', detail: '规格、数量与人工单价' }, { title: '金额与条款', detail: '核对费用并保存报价' }]
  : [{ title: 'Quote terms', detail: 'Language, currency & validity' }, { title: 'Product details', detail: 'Specifications, quantity & price' }, { title: 'Amounts & terms', detail: 'Review charges and save' }]);
</script>

<template>
  <nav class="quote-flow" :aria-label="zh ? '报价编辑流程' : 'Quote editing steps'">
    <ol>
      <li v-for="(step, index) in steps" :key="index" :class="{ complete: current > index + 1, current: current === index + 1 }">
        <button type="button" :aria-current="current === index + 1 ? 'step' : undefined" @click="emit('select', index + 1)">
          <span class="step-number" aria-hidden="true"><svg v-if="current > index + 1" viewBox="0 0 20 20" fill="none"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg><template v-else>{{ index + 1 }}</template></span>
          <span class="step-copy"><strong>{{ step.title }}</strong><small>{{ step.detail }}</small></span>
        </button>
      </li>
    </ol>

  </nav>
</template>

<style scoped>
.quote-flow{margin:16px 0 28px}.quote-flow ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;list-style:none;margin:0;padding:0;border-bottom:2px solid #e4eae6}.quote-flow li{position:relative;min-width:0;border-bottom:2px solid transparent;margin-bottom:-2px}.quote-flow li.current,.quote-flow li.complete{border-bottom-color:#0f6e5c}.quote-flow button{display:flex;align-items:center;gap:10px;width:100%;min-height:72px;padding:12px 16px;background:transparent;color:#758078;border:0;border-radius:0;text-align:left;font:inherit;cursor:pointer}.quote-flow li.current{background:#f4f8f5}.step-number{display:grid;place-items:center;flex:none;width:28px;height:28px;border:1px solid #d0dad3;border-radius:50%;font-size:12px;font-weight:600;background:#fff}.step-number svg{width:16px;height:16px}.step-copy{display:flex;flex-direction:column;gap:4px;min-width:0}.step-copy strong{font-size:13px;font-weight:600;line-height:1.4}.step-copy small{font-size:11px;line-height:1.5}.current .step-number{background:#0f6e5c;border-color:#0f6e5c;color:#fff}.complete .step-number{border-color:#bed5c6;color:#0f6e5c;background:#edf5ef}.current .step-copy strong,.complete .step-copy strong{color:#1b2421}.quote-flow button:focus-visible{outline:2px solid #0f6e5c;outline-offset:-4px}.quote-flow button:hover{background:#f4f8f5}@media(max-width:600px){.quote-flow{margin:12px 0 22px}.quote-flow button{min-height:72px;padding:10px 5px;flex-direction:column;gap:6px;text-align:center}.step-copy small{display:none}.step-copy strong{font-size:11px}.step-number{width:24px;height:24px;font-size:11px}}
</style>
