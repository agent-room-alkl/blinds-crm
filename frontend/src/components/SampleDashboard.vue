<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const nzd = (value: number) => new Intl.NumberFormat("en-NZ", { style: "currency", currency: "NZD", maximumFractionDigits: 0 }).format(value);
const pct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;

// ---- One sample dataset. Every number on this page is derived from it. ----
const SERIES = [
  { id: "A", zh: "系列 A（主力款）", en: "Series A (core)", units: 440 },
  { id: "B", zh: "系列 B", en: "Series B", units: 62 },
  { id: "C", zh: "系列 C", en: "Series C", units: 24 },
  { id: "D", zh: "系列 D", en: "Series D", units: 14 },
  { id: "E", zh: "系列 E", en: "Series E", units: 10 },
];
// Shipments: freight is shared by units, duty by declared (purchase) value, purchase cost converted at that batch's rate.
const BATCHES = [
  { id: 1, label: "Batch 1", freight: 1800, duty: 1350, fx: 0.215 },
  { id: 2, label: "Batch 2", freight: 2100, duty: 1500, fx: 0.223 },
];
const ORDERS = [
  { id: "V0000101", customer: "Harbour Interiors", series: "A", units: 18, revenue: 9400, purchaseCny: 26790, batch: 1, rebate: 78 },
  { id: "V0000102", customer: "Kauri Blinds Ltd", series: "A", units: 24, revenue: 12600, purchaseCny: 35910, batch: 1, rebate: 153 },
  { id: "V0000103", customer: "Southern Shade Co", series: "B", units: 6, revenue: 4300, purchaseCny: 12255, batch: 1, rebate: 0 },
  { id: "V0000104", customer: "Harbour Interiors", series: "A", units: 12, revenue: 6300, purchaseCny: 17955, batch: 1, rebate: 53 },
  { id: "V0000105", customer: "Kauri Blinds Ltd", series: "A", units: 30, revenue: 15400, purchaseCny: 43890, batch: 2, rebate: 186 },
  { id: "V0000106", customer: "Westgate Windows", series: "A", units: 21, revenue: 10900, purchaseCny: 31065, batch: 2, rebate: 90 },
  { id: "V0000107", customer: "Southern Shade Co", series: "C", units: 8, revenue: 6800, purchaseCny: 19380, batch: 2, rebate: 0 },
  { id: "V0000108", customer: "Westgate Windows", series: "B", units: 9, revenue: 5600, purchaseCny: 15960, batch: 2, rebate: 45 },
];
// Illustrative tiers only. The real rebate rule has not been confirmed.
const SAMPLE_TIERS = [
  { from: 10000, rate: 0.03 },
  { from: 5000, rate: 0.02 },
];
const FUNNEL = [
  { zh: "待审核", en: "Awaiting review", n: 4 },
  { zh: "待收定金", en: "Deposit outstanding", n: 2 },
  { zh: "待向供应商下单", en: "To order from supplier", n: 3 },
  { zh: "在途", en: "In transit", n: 3 },
  { zh: "已到货待交付", en: "Arrived, not delivered", n: 2 },
  { zh: "已交付待开尾款", en: "Delivered, balance open", n: 6 },
];

// ---- Derived figures ----
const seriesTotal = SERIES.reduce((sum, s) => sum + s.units, 0);
const seriesShare = computed(() => {
  let offset = 0;
  return SERIES.map((s, i) => {
    const share = s.units / seriesTotal;
    const row = { ...s, share, dash: `${share * 100} ${100 - share * 100}`, offset: -offset, tone: i };
    offset += share * 100;
    return row;
  });
});
const top = computed(() => seriesShare.value[0]);

const orders = computed(() =>
  ORDERS.map((o) => {
    const batch = BATCHES.find((b) => b.id === o.batch)!;
    const mates = ORDERS.filter((x) => x.batch === o.batch);
    const purchase = o.purchaseCny * batch.fx;
    const freight = (batch.freight * o.units) / mates.reduce((s, x) => s + x.units, 0);
    const duty = (batch.duty * o.purchaseCny) / mates.reduce((s, x) => s + x.purchaseCny, 0);
    const profit = o.revenue - purchase - freight - duty - o.rebate;
    return { ...o, purchase, freight, duty, profit, margin: profit / o.revenue };
  }),
);
const totals = computed(() => {
  const revenue = orders.value.reduce((s, o) => s + o.revenue, 0);
  const profit = orders.value.reduce((s, o) => s + o.profit, 0);
  return { revenue, profit, margin: profit / revenue, units: orders.value.reduce((s, o) => s + o.units, 0), count: orders.value.length };
});
const best = computed(() => [...orders.value].sort((a, b) => b.margin - a.margin)[0]);
const worst = computed(() => [...orders.value].sort((a, b) => a.margin - b.margin)[0]);

const batches = computed(() =>
  BATCHES.map((b) => {
    const rows = orders.value.filter((o) => o.batch === b.id);
    const revenue = rows.reduce((s, o) => s + o.revenue, 0);
    const profit = rows.reduce((s, o) => s + o.profit, 0);
    const units = rows.reduce((s, o) => s + o.units, 0);
    const purchase = rows.reduce((s, o) => s + o.purchase, 0);
    return { ...b, revenue, profit, units, margin: profit / revenue, freightPerUnit: b.freight / units, dutyRate: b.duty / rows.reduce((s, o) => s + o.purchaseCny, 0), purchaseShare: purchase / revenue };
  }),
);
const fxSpread = computed(() => (batches.value[1].fx - batches.value[0].fx) / batches.value[0].fx);

const customers = computed(() => {
  const names = [...new Set(ORDERS.map((o) => o.customer))];
  return names
    .map((name) => {
      const spend = ORDERS.filter((o) => o.customer === name).reduce((s, o) => s + o.revenue, 0);
      const tier = SAMPLE_TIERS.find((t) => spend >= t.from);
      const next = [...SAMPLE_TIERS].reverse().find((t) => spend < t.from);
      return { name, spend, rate: tier?.rate ?? 0, rebate: spend * (tier?.rate ?? 0), next, progress: next ? spend / next.from : 1 };
    })
    .sort((a, b) => b.spend - a.spend);
});
const funnelMax = Math.max(...FUNNEL.map((f) => f.n));
const stackParts = [
  { key: "purchase", zh: "采购成本", en: "Purchase" },
  { key: "freight", zh: "运费分摊", en: "Freight" },
  { key: "duty", zh: "关税分摊", en: "Duty" },
  { key: "rebate", zh: "返利抵扣", en: "Rebate" },
  { key: "profit", zh: "利润", en: "Profit" },
] as const;
</script>

<template>
  <section class="db">
    <header class="db-head">
      <div>
        <p class="eyebrow">VERA · {{ tx("分析看板", "ANALYTICS") }}</p>
        <h2>{{ tx("利润与销售分析", "Profit & sales analytics") }}</h2>
        <p class="sub">{{ tx("按 10/15 会议需求做的演示：看每个订单赚了多少、哪款卖得好、利润为什么波动、客户本月采购和返利。", "A demo built from the 15 Oct meeting: profit per order, what sells, why profit moves, and customer monthly purchases and rebates.") }}</p>
      </div>
      <p class="banner" role="note"><strong>{{ tx("示例数据", "SAMPLE DATA") }}</strong>{{ tx("不是真实经营指标，也没有连接真实订单库。", "Not real business metrics and not connected to the real order database.") }}</p>
    </header>

    <div class="kpis">
      <article><span>{{ tx("订单", "Orders") }}</span><strong>{{ totals.count }}</strong><small>{{ totals.units }} {{ tx("扇窗", "windows") }}</small></article>
      <article><span>{{ tx("销售额", "Revenue") }}</span><strong>{{ nzd(totals.revenue) }}</strong><small>{{ tx("不含税示例", "sample, ex-GST") }}</small></article>
      <article class="accent"><span>{{ tx("利润", "Profit") }}</span><strong>{{ nzd(totals.profit) }}</strong><small>{{ tx("扣采购、运费、关税、返利后", "after purchase, freight, duty, rebate") }}</small></article>
      <article class="accent"><span>{{ tx("平均利润率", "Average margin") }}</span><strong>{{ pct(totals.margin) }}</strong><small>{{ tx(`${best.id} 最高 ${pct(best.margin)} · ${worst.id} 最低 ${pct(worst.margin)}`, `${best.id} best ${pct(best.margin)} · ${worst.id} lowest ${pct(worst.margin)}`) }}</small></article>
    </div>

    <div class="grid two">
      <section class="panel">
        <h3>{{ tx("各系列销量占比", "Sales share by series") }}</h3>
        <p class="lead">{{ tx(`${top.zh.split("（")[0]} 占 ${pct(top.share, 0)}：最常卖的就是它，其余系列只是把选择做全。`, `${top.en.split(" (")[0]} is ${pct(top.share, 0)} of units: the one that really sells; the rest complete the range.`) }}</p>
        <div class="donut-row">
          <svg viewBox="0 0 42 42" class="donut" role="img" :aria-label="tx('系列销量占比环形图', 'Series share donut')">
            <circle cx="21" cy="21" r="15.9155" fill="none" stroke="#e8efe9" stroke-width="6" />
            <circle v-for="s in seriesShare" :key="s.id" cx="21" cy="21" r="15.9155" fill="none" stroke-width="6" :class="`tone-${s.tone}`" :stroke-dasharray="s.dash" :stroke-dashoffset="s.offset + 25" />
            <text x="21" y="20.2" text-anchor="middle" class="donut-n">{{ pct(top.share, 0) }}</text>
            <text x="21" y="25.2" text-anchor="middle" class="donut-t">{{ tx("系列", "Series") }} {{ top.id }}</text>
          </svg>
          <ul class="legend">
            <li v-for="s in seriesShare" :key="s.id"><i :class="`tone-${s.tone}`"></i><span>{{ tx(s.zh, s.en) }}</span><b>{{ s.units }}</b><em>{{ pct(s.share) }}</em></li>
          </ul>
        </div>
        <p class="foot">{{ tx("按扇数统计。尺寸、边框、叶片宽度等选项不同，仍算同一款产品。", "Counted in windows. Different sizes, frames or louvre widths still count as the same product.") }}</p>
      </section>

      <section class="panel">
        <h3>{{ tx("订单状态漏斗", "Order pipeline") }}</h3>
        <p class="lead">{{ tx("每个阶段现在停着多少单，一眼看出卡在哪。", "How many orders sit at each stage, so a bottleneck shows at a glance.") }}</p>
        <ul class="funnel">
          <li v-for="(f, i) in FUNNEL" :key="f.en"><span class="fname">{{ tx(f.zh, f.en) }}</span><span class="fbar"><i :style="{ width: `${(f.n / funnelMax) * 100}%` }" :class="`step-${i}`"></i></span><b>{{ f.n }}</b></li>
        </ul>
      </section>
    </div>

    <section class="panel">
      <h3>{{ tx("每个订单的利润", "Profit per order") }}</h3>
      <p class="lead">{{ tx("运费按扇数、关税按申报价值分摊到订单；采购成本按该批次汇率折算。", "Freight is shared by windows and duty by declared value; purchase cost uses that shipment's exchange rate.") }}</p>
      <ul class="stack-legend"><li v-for="p in stackParts" :key="p.key"><i :class="`c-${p.key}`"></i>{{ tx(p.zh, p.en) }}</li></ul>
      <ul class="orders">
        <li v-for="o in orders" :key="o.id">
          <div class="who"><strong>{{ o.id }}</strong><span>{{ o.customer }} · {{ o.units }} {{ tx("扇", "win") }} · {{ tx("系列", "Series") }} {{ o.series }}</span></div>
          <div class="bar" role="img" :aria-label="`${o.id} ${tx('成本与利润构成', 'cost and profit breakdown')}`">
            <i class="c-purchase" :style="{ width: `${(o.purchase / o.revenue) * 100}%` }"></i>
            <i class="c-freight" :style="{ width: `${(o.freight / o.revenue) * 100}%` }"></i>
            <i class="c-duty" :style="{ width: `${(o.duty / o.revenue) * 100}%` }"></i>
            <i class="c-rebate" :style="{ width: `${(o.rebate / o.revenue) * 100}%` }"></i>
            <i class="c-profit" :style="{ width: `${(o.profit / o.revenue) * 100}%` }"></i>
          </div>
          <div class="res"><strong>{{ nzd(o.profit) }}</strong><span :class="{ low: o.margin < totals.margin - 0.03 }">{{ pct(o.margin) }}</span></div>
        </li>
      </ul>
    </section>

    <div class="grid two">
      <section class="panel">
        <h3>{{ tx("利润为什么会波动", "Why profit moves") }}</h3>
        <p class="lead">{{ tx("采购价和售价基本固定，波动来自运费、关税摊到每扇窗上的多少，以及汇率。", "Purchase and selling prices are stable; the swings come from freight and duty per window, and the exchange rate.") }}</p>
        <div class="batches">
          <article v-for="b in batches" :key="b.id">
            <header><strong>{{ b.label }}</strong><span class="m">{{ pct(b.margin) }}</span></header>
            <dl>
              <div><dt>{{ tx("汇率（NZD/CNY）", "Rate (NZD/CNY)") }}</dt><dd>{{ b.fx.toFixed(3) }}</dd></div>
              <div><dt>{{ tx("每扇运费", "Freight / window") }}</dt><dd>{{ nzd(b.freightPerUnit) }}</dd></div>
              <div><dt>{{ tx("关税占申报价值", "Duty on declared value") }}</dt><dd>{{ pct(b.dutyRate) }}</dd></div>
              <div><dt>{{ tx("利润", "Profit") }}</dt><dd>{{ nzd(b.profit) }}</dd></div>
            </dl>
          </article>
        </div>
        <p class="insight">{{ tx(`两批汇率相差 ${pct(fxSpread)}，约影响利润率 ${(batches[1].purchaseShare * fxSpread * 100).toFixed(1)} 个百分点；运费每扇从 ${nzd(batches[0].freightPerUnit)} 到 ${nzd(batches[1].freightPerUnit)}。`, `The two batches' rates differ by ${pct(fxSpread)}, worth about ${(batches[1].purchaseShare * fxSpread * 100).toFixed(1)} margin points; freight per window moves from ${nzd(batches[0].freightPerUnit)} to ${nzd(batches[1].freightPerUnit)}.`) }}</p>
      </section>

      <section class="panel">
        <h3>{{ tx("客户本月采购与返利", "Customer purchases & rebates") }}</h3>
        <p class="lead">{{ tx("选好订单就知道这个客户这个月买了多少、下月该返多少。", "See what each customer bought this month and what rebate they get next month.") }}</p>
        <ul class="cust">
          <li v-for="c in customers" :key="c.name">
            <div class="row"><strong>{{ c.name }}</strong><span>{{ nzd(c.spend) }}</span></div>
            <div class="meter" :aria-label="tx('距离下一档的进度', 'Progress to next tier')"><i :style="{ width: `${Math.min(100, c.progress * 100)}%` }"></i></div>
            <small>{{ c.rate ? tx(`示例档位 ${pct(c.rate, 0)} → 下月返利 ${nzd(c.rebate)}`, `Sample tier ${pct(c.rate, 0)} → next-month rebate ${nzd(c.rebate)}`) : tx("未达示例档位", "Below the sample tiers") }}<template v-if="c.next"> · {{ tx(`再采购 ${nzd(c.next.from - c.spend)} 升到 ${pct(c.next.rate, 0)}`, `${nzd(c.next.from - c.spend)} more reaches ${pct(c.next.rate, 0)}`) }}</template></small>
          </li>
        </ul>
        <p class="foot warn">{{ tx("档位（满 5,000 返 2%，满 10,000 返 3%）只是演示，真实返利规则还没有确认，系统不会自动按它结算。", "The tiers (2% from 5,000, 3% from 10,000) are illustrative. The real rebate rule is not confirmed, and the system does not settle using it.") }}</p>
      </section>
    </div>

    <p class="foot end">{{ tx("不含环比、同比增长：数据积累满几个月后再加。", "No month-on-month or year-on-year growth yet; it needs a few months of real data.") }}</p>
  </section>
</template>

<style scoped>
.db { color: #1b2421; max-width: 1180px; margin: 0 auto; }
.eyebrow { margin: 0 0 4px; font-size: 11px; letter-spacing: .12em; color: #64766b; }
.db-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; flex-wrap: wrap; padding-bottom: 18px; }
.db-head h2 { margin: 0 !important; font-size: 26px !important; line-height: 1.2; }
.sub { margin: 6px 0 0; max-width: 620px; font-size: 13px; line-height: 1.6; color: #5d6d63; }
.banner { margin: 0; display: grid; gap: 2px; max-width: 320px; padding: 10px 16px; border-radius: 12px; background: #1b2421; color: #e8efe9; font-size: 12px; line-height: 1.5; }
.banner strong { letter-spacing: .14em; color: #f2c46d; }

.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.kpis article { padding: 18px 20px; border-radius: 16px; background: #fff; border: 1px solid #e1e8e3; display: grid; gap: 4px; }
.kpis span { font-size: 12px; color: #64766b; }
.kpis strong { font-size: 28px; line-height: 1.15; font-variant-numeric: tabular-nums; }
.kpis small { font-size: 11.5px; color: #8a998f; line-height: 1.4; }
.kpis .accent { background: #0f6e5c; border-color: #0f6e5c; }
.kpis .accent span, .kpis .accent small { color: rgba(255, 255, 255, .78); }
.kpis .accent strong { color: #fff; }

.grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.panel { margin-top: 16px; padding: 22px 24px; border-radius: 16px; background: #fff; border: 1px solid #e1e8e3; min-width: 0; }
.grid.two .panel { margin-top: 0; }
.panel h3 { margin: 0 0 4px; font-size: 17px; }
.lead { margin: 0 0 16px; font-size: 13px; line-height: 1.6; color: #5d6d63; }
.foot { margin: 14px 0 0; font-size: 12px; line-height: 1.6; color: #7b8c81; }
.foot.warn { padding: 8px 12px; border-radius: 8px; background: #fbf3e2; color: #7a5a24; }
.foot.end { text-align: center; }

.tone-0 { stroke: #0f6e5c; background: #0f6e5c; }
.tone-1 { stroke: #3fa58b; background: #3fa58b; }
.tone-2 { stroke: #8cc7b5; background: #8cc7b5; }
.tone-3 { stroke: #c4a46a; background: #c4a46a; }
.tone-4 { stroke: #c9d3cc; background: #c9d3cc; }
.donut-row { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.donut { width: 190px; height: 190px; flex: none; }
.donut circle { transition: stroke-dasharray .4s; }
.donut-n { font-size: 6.4px; font-weight: 700; fill: #0f6e5c; }
.donut-t { font-size: 2.6px; fill: #64766b; }
.legend { list-style: none; margin: 0; padding: 0; flex: 1 1 200px; display: grid; gap: 4px; }
.legend li { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto 52px; align-items: center; gap: 10px; min-height: 34px; font-size: 13px; border-bottom: 1px solid #eef2ef; }
.legend i { width: 12px; height: 12px; border-radius: 4px; }
.legend b { font-variant-numeric: tabular-nums; }
.legend em { font-style: normal; text-align: right; color: #64766b; font-variant-numeric: tabular-nums; }

.funnel { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.funnel li { display: grid; grid-template-columns: 124px minmax(0, 1fr) 28px; align-items: center; gap: 12px; font-size: 13px; }
.fbar { height: 22px; border-radius: 6px; background: #eef2ef; overflow: hidden; }
.fbar i { display: block; height: 100%; border-radius: 6px; background: #0f6e5c; }
.step-0 { opacity: 1; } .step-1 { opacity: .9; } .step-2 { opacity: .8; } .step-3 { opacity: .7; } .step-4 { opacity: .6; } .step-5 { opacity: .5; }
.funnel b { text-align: right; font-variant-numeric: tabular-nums; }

.stack-legend { list-style: none; margin: 0 0 12px; padding: 0; display: flex; gap: 6px 18px; flex-wrap: wrap; font-size: 12px; color: #4d6256; }
.stack-legend li { display: flex; align-items: center; gap: 6px; }
.stack-legend i { width: 12px; height: 12px; border-radius: 3px; }
.c-purchase { background: #7d9a8e; } .c-freight { background: #e0b066; } .c-duty { background: #c06f45; } .c-rebate { background: #9486bd; } .c-profit { background: #0f6e5c; }
.orders { list-style: none; margin: 0; padding: 0; display: grid; }
.orders li { display: grid; grid-template-columns: minmax(180px, 250px) minmax(0, 1fr) 120px; align-items: center; gap: 20px; padding: 12px 0; border-top: 1px solid #eef2ef; }
.who { display: grid; gap: 2px; min-width: 0; }
.who strong { font-size: 14px; }
.who span { font-size: 12px; color: #64766b; overflow-wrap: anywhere; }
.bar { display: flex; height: 22px; border-radius: 6px; overflow: hidden; background: #eef2ef; }
.bar i { display: block; height: 100%; }
.res { display: grid; text-align: right; }
.res strong { font-size: 15px; font-variant-numeric: tabular-nums; }
.res span { font-size: 12.5px; color: #0f6e5c; font-weight: 600; }
.res span.low { color: #b3541f; }

.batches { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.batches article { padding: 14px 16px; border-radius: 12px; background: #f4f8f5; border: 1px solid #e1e8e3; }
.batches header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.batches .m { font-size: 22px; font-weight: 700; color: #0f6e5c; font-variant-numeric: tabular-nums; }
.batches dl { margin: 0; display: grid; gap: 6px; }
.batches dl div { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px; }
.batches dt { color: #64766b; letter-spacing: 0; text-transform: none; font-size: 12.5px; }
.batches dd { margin: 0; font-size: 12.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
.insight { margin: 14px 0 0; padding: 10px 14px; border-left: 3px solid #0f6e5c; background: #f2f7f4; border-radius: 0 8px 8px 0; font-size: 13px; line-height: 1.6; color: #34503f; }

.cust { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.cust .row { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; }
.cust .row span { font-variant-numeric: tabular-nums; font-weight: 600; }
.meter { height: 8px; border-radius: 999px; background: #eef2ef; margin: 6px 0 4px; overflow: hidden; }
.meter i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #3fa58b, #0f6e5c); }
.cust small { font-size: 12px; color: #64766b; line-height: 1.5; }

@media (max-width: 900px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid.two { grid-template-columns: minmax(0, 1fr); }
  .orders li { grid-template-columns: minmax(0, 1fr) auto; gap: 8px 14px; }
  .orders .bar { grid-column: 1 / -1; order: 3; }
}
@media (max-width: 560px) {
  .kpis strong { font-size: 22px; }
  .panel { padding: 18px 16px; }
  .donut { width: 160px; height: 160px; margin: 0 auto; }
  .funnel li { grid-template-columns: 96px minmax(0, 1fr) 24px; gap: 8px; }
  .batches { grid-template-columns: minmax(0, 1fr); }
}
@media (prefers-reduced-motion: reduce) { .donut circle { transition: none; } }
</style>
