<script setup lang="ts">
import { useI18n } from "vue-i18n";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const cards: [string, string, string][] = [
  ["待审核", "Awaiting review", "4"],
  ["待收定金", "Deposit outstanding", "2"],
  ["在途", "In transit", "3"],
  ["未结尾款", "Open balance", "6"],
];
</script>

<template>
  <section class="card sample-board">
    <p class="banner">{{ tx("示例数据。不是真实经营指标。", "Sample data. These are not live business figures.") }}</p>
    <h2>{{ tx("分析看板", "Dashboard") }}</h2>
    <p>{{ tx("用来核对布局。真实统计要等核心订单流程完成后再接。利润、成本分摊和客户评级不在这一版。", "This checks the layout. Live figures wait until the core order flow is finished. Profit, cost allocation and customer ratings are not in this version.") }}</p>
    <div class="metrics">
      <article v-for="card in cards" :key="card[0]">
        <span>{{ tx(card[0], card[1]) }}</span>
        <strong>{{ card[2] }}</strong>
      </article>
    </div>
    <h3>{{ tx("产品系列销量（示例）", "Sales by series (sample)") }}</h3>
    <ul>
      <li><span>{{ tx("系列 A", "Series A") }}</span><span>80%</span></li>
      <li><span>{{ tx("系列 B", "Series B") }}</span><span>12%</span></li>
      <li><span>{{ tx("其余系列", "Other series") }}</span><span>8%</span></li>
    </ul>
    <p class="note">{{ tx("比例只说明布局，不代表客户当前销量。环比和同比不在本页。", "The split only shows the layout. It is not the customer’s current sales. Period-on-period growth is not on this page.") }}</p>
  </section>
</template>

<style scoped>
.banner { background: #1b2421; color: white; display: inline-block; padding: 6px 10px; font-size: 13px; }
.sample-board h2 { margin: 16px 0 8px; }
.sample-board p, .note { color: #54645c; line-height: 1.6; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }
article { background: #f5f4f0; padding: 16px; }
article span { display: block; font-size: 13px; color: #54645c; }
article strong { display: block; font-size: 28px; margin-top: 8px; }
ul { list-style: none; padding: 0; }
li { display: flex; justify-content: space-between; border-top: 1px solid var(--line, #dedbd5); padding: 10px 0; }
@media (max-width: 800px) { .metrics { grid-template-columns: 1fr 1fr; } }
</style>