<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ClipboardCheck, Package, Percent, Receipt, ShoppingCart, Truck } from "lucide-vue-next";

defineProps<{ demo: boolean; deliveryEnabled: boolean }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

const steps = computed(() => [
  {
    icon: ShoppingCart,
    name: tx("客户下单", "Customer order"),
    hint: tx("门户配置并提交", "Configured in portal"),
    path: "/crm/projects",
    points: [
      tx("客户在门户选系列，逐扇配置窗户（尺寸为毫米），价格随选项实时显示。", "The customer picks a series and configures each window (millimetres). The price updates as options change."),
      tx("提交后订单状态是“待审核”：还没收款，也没向供应商下单。", "A submitted order is “awaiting review”: nothing is paid and nothing is ordered from the supplier yet."),
    ],
    note: tx("缺少必填项时页面会列出具体字段，补齐后才能进入下一扇窗。", "Missing required fields are listed by name; complete them to continue."),
  },
  {
    icon: ClipboardCheck,
    name: tx("审核与定金", "Review & deposit"),
    hint: tx("确认接收 → 定金发票", "Accept → deposit invoice"),
    path: "/crm/projects",
    points: [
      tx("选中订单，在“计价与审核”核对价格版本和配置（尺寸超限、扇数不对等技术问题在这里拦截）。", "Select the order and check price version and configuration under Pricing & review (out-of-spec sizes and wrong panel counts are caught here)."),
      tx("点“确认接收”生成 60% 定金发票草稿（向上取整到分）。审核后价格冻结。", "Accepting creates a 60% deposit invoice draft, rounded up to the cent. Prices are frozen after review."),
      tx("“定金已收”是单独的记录动作，核实到账后再点；发送发票也是单独一步。", "“Deposit received” is a separate record, clicked only after the money is confirmed; sending the invoice is another separate step."),
    ],
    note: tx("系统不会扣款或转账，只记录你确认的结果。", "The system never charges or transfers money; it only records what you confirm."),
  },
  {
    icon: Truck,
    name: tx("供应商下单", "Supplier order"),
    hint: tx("导出 Excel · 标为已下单", "Export Excel · mark as ordered"),
    path: "/crm/providers",
    points: [
      tx("到“供应商与导出”核对自动带出的供应商和模板，点“下载供应商订单 Excel”，分配同时被保存。", "Under Supplier & files, check the preselected supplier and template, then download the supplier Excel; the assignment is saved at the same time."),
      tx("定金确认后下载供应商订单，再点“标为已下单”。订单号就是客户订单号，不用另填供应商号。", "After the deposit is confirmed, download the supplier order, then click Mark as ordered. The order number is the customer's; no separate supplier number."),
    ],
    note: tx("没有正式工厂模板时导出的只是通用草稿，需要人工核对；导出本身不会发邮件。", "Without a confirmed factory template the export is a generic draft to be checked by hand; exporting never sends email."),
  },
  {
    icon: Package,
    name: tx("在途·到货·交付", "Transit, arrival, delivery"),
    hint: tx("按批次记录实际数量", "Record real batch quantities"),
    path: "/crm/projects",
    points: [
      tx("供应商发货后，在订单列表勾选订单，批量标记“在途”。", "After the supplier ships, tick the orders in the list and mark them in transit in one action."),
      tx("在“明细与履约”右侧填“本次到货/本次交付”的实际数量再记录；左边的“累计”是已记录总数，提交后右侧会清空。", "In Lines & fulfilment, enter the real “this batch” arrival or delivery quantity and record it. The cumulative columns on the left show what is already recorded; the inputs clear after submit."),
      tx("到货会生成通知记录；到货不能超过订购，交付不能超过已到货。", "Arrival creates a notification record. Arrivals cannot exceed the order and deliveries cannot exceed arrivals."),
    ],
    note: tx("部分到货不等于已交付，也还不能开尾款。", "Partial arrival is not delivery and does not allow a balance invoice yet."),
  },
  {
    icon: Receipt,
    name: tx("尾款发票", "Balance invoice"),
    hint: tx("合并多单 · 先出草稿", "Combine orders · draft first"),
    path: "/crm/finance",
    points: [
      tx("在“账款与返利”勾选同一公司、同币种、每一行都已到货且定金已收的订单，点“生成尾款草稿”。", "Under Accounts & rebates, tick orders of one company and currency where every line has arrived and the deposit is received, then click Create balance draft."),
      tx("金额 = 订单总额 − 已存定金，再扣早于本月的已确认返利；“规则说明”按所选订单自动生成，可以修改。", "Amount = order total − stored deposit, then confirmed rebate balances from earlier months. The rule note is generated from the selected orders and can be edited."),
      tx("草稿检查无误后再单独发送，收到款项后点“确认尾款收款”。", "Review the draft, send it as a separate step, and click Confirm balance receipt once the money has arrived."),
    ],
    note: tx("生成草稿不会发给客户。", "Creating the draft sends nothing to the customer."),
  },
  {
    icon: Percent,
    name: tx("返利", "Rebate"),
    hint: tx("只录入已确认金额", "Confirmed amounts only"),
    path: "/crm/finance",
    points: [
      tx("在“返利”页填年月、金额、来源订单和确认依据，记入后可在下个月的尾款里自动抵扣。", "On the Rebates tab enter the month, amount, source orders and evidence; it is then deducted automatically from later balance invoices."),
      tx("同一来源订单不能重复计入；页面显示已用和余额。", "A source order cannot be counted twice; used and remaining amounts are shown."),
    ],
    note: tx("原始 Excel 里没有返利公式，所以系统不会自动算阶梯。需要的参数见 docs/REBATE-RULE-INPUTS.md。", "The source Excel has no rebate formula, so tiers are not calculated automatically. Required inputs are listed in docs/REBATE-RULE-INPUTS.md."),
  },
]);

const current = ref(0);
const step = computed(() => steps.value[current.value]);
const more = computed(() => [
  { label: tx("客户资料", "Customers"), path: "/crm/customers" },
  { label: tx("定价知识库", "Pricing knowledge"), path: "/crm/pricing" },
  { label: tx("产品目录", "Product catalogue"), path: "/crm/products" },
  { label: tx("分析看板", "Dashboard"), path: "/crm/dashboard" },
]);

function move(delta: number) {
  current.value = (current.value + delta + steps.value.length) % steps.value.length;
  document.getElementById(`guide-step-${current.value}`)?.focus();
}
</script>

<template>
  <section class="guide">
    <header>
      <h1>{{ tx("后台操作指南", "CRM operating guide") }}</h1>
      <p>{{ tx("按业务顺序走一遍：点流程图里的每一步，下面会说明具体怎么操作。", "Follow the workflow from left to right. Click a step to see exactly what to do.") }}</p>
      <p v-if="demo" class="demo-note">
        {{ tx("演示模式：客户不会收到邮件。", "Demo mode: customers receive no email.") }}
        {{ deliveryEnabled ? tx("演示邮件只会发到管理员测试邮箱。", "Demo mail goes only to the owner test mailbox.") : tx("发信服务未就绪，发送只记录“未发送”。", "Mail service is not ready; sends are only recorded as not sent.") }}
      </p>
    </header>

    <ol class="flow" :aria-label="tx('业务流程', 'Business workflow')">
      <li v-for="(item, index) in steps" :key="item.name" :class="{ done: index < current, active: index === current }">
        <button
          :id="`guide-step-${index}`"
          type="button"
          :aria-pressed="index === current"
          :aria-controls="'guide-detail'"
          @click="current = index"
          @keydown.right.prevent="move(1)"
          @keydown.left.prevent="move(-1)"
        >
          <span class="badge"><component :is="item.icon" :size="22" aria-hidden="true" /></span>
          <span class="num">{{ index + 1 }}</span>
          <strong>{{ item.name }}</strong>
          <small>{{ item.hint }}</small>
        </button>
      </li>
    </ol>

    <article id="guide-detail" class="detail" aria-live="polite">
      <p class="eyebrow">{{ tx(`第 ${current + 1} 步 / 共 ${steps.length} 步`, `Step ${current + 1} of ${steps.length}`) }}</p>
      <h2>{{ step.name }}</h2>
      <ul>
        <li v-for="point in step.points" :key="point">{{ point }}</li>
      </ul>
      <p class="note">{{ step.note }}</p>
      <div class="actions">
        <button type="button" class="ghost" :disabled="current === 0" @click="move(-1)">← {{ tx("上一步", "Previous") }}</button>
        <RouterLink class="open" :to="step.path">{{ tx("打开对应模块", "Open this workspace") }} →</RouterLink>
        <button type="button" class="ghost" :disabled="current === steps.length - 1" @click="move(1)">{{ tx("下一步", "Next") }} →</button>
      </div>
    </article>

    <p class="more">
      <span>{{ tx("其他模块：", "Also: ") }}</span>
      <RouterLink v-for="item in more" :key="item.path" :to="item.path">{{ item.label }}</RouterLink>
    </p>

    <details class="faq">
      <summary>{{ tx("常见问题", "Common questions") }}</summary>
      <dl>
        <dt>{{ tx("下一步没有进入？", "Cannot continue?") }}</dt>
        <dd>{{ tx("先看缺项提示和价格预览；必填配置、有效尺寸和价格都要完成。", "Check the missing-field list and the price preview; required options, valid sizes and a price are needed.") }}</dd>
        <dt>{{ tx("操作被拒绝？", "An action was refused?") }}</dt>
        <dd>{{ tx("核对订单状态、定金、供应商是否启用和本批数量，不要反复提交。", "Check order state, deposit, supplier availability and batch quantities. Do not resubmit repeatedly.") }}</dd>
        <dt>{{ tx("保存报错？", "Save failed?") }}</dt>
        <dd>{{ tx("保留已填内容，记下订单号、按钮和错误提示再反馈；没看到成功提示就当作没保存。", "Keep what you entered and report the order number, button and message. Treat it as unsaved until success is shown.") }}</dd>
      </dl>
    </details>
  </section>
</template>

<style scoped>
.guide { max-width: 1100px; margin: 0 auto; color: #203b30; font-size: 14px; line-height: 1.65; }
.guide h1 { font-size: 24px !important; line-height: 1.3 !important; margin: 0 0 6px !important; }
.guide header p { margin: 4px 0; color: #4d6256; }
.demo-note { display: inline-block; margin-top: 8px !important; padding: 6px 12px; border-radius: 999px; background: #e6f1ea; color: #17523a !important; font-size: 13px; }

.flow { list-style: none; margin: 22px 0 0; padding: 0; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0; }
.flow li { position: relative; padding: 0 6px; }
.flow li:not(:last-child)::after { content: ""; position: absolute; top: 34px; left: calc(50% + 34px); right: calc(-50% + 34px); height: 2px; background: #cddbd1; }
.flow li.done:not(:last-child)::after { background: #0f6e5c; }
.flow button { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 4px 10px; background: transparent; border: 0; border-radius: 12px; color: inherit; cursor: pointer; text-align: center; min-height: 44px; }
.flow button:hover .badge { border-color: #0f6e5c; }
.flow button:focus-visible { outline: 3px solid #7fb7a3; outline-offset: 2px; }
.badge { position: relative; z-index: 1; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; background: #fff; border: 2px solid #cddbd1; color: #4d6256; transition: all .15s; }
.num { font-size: 11px; font-weight: 700; color: #7b8c81; letter-spacing: .06em; }
.flow strong { font-size: 14px; line-height: 1.3; }
.flow small { font-size: 12px; color: #64766b; line-height: 1.35; }
.flow li.done .badge { background: #e6f1ea; border-color: #0f6e5c; color: #0f6e5c; }
.flow li.active .badge { background: #0f6e5c; border-color: #0f6e5c; color: #fff; box-shadow: 0 0 0 6px rgba(15, 110, 92, .16); }
.flow li.active strong { color: #0f6e5c; }

.detail { margin-top: 14px; padding: 22px 24px; background: #fff; border: 1px solid #d4e1d8; border-radius: 14px; box-shadow: 0 8px 28px rgba(27, 36, 33, .06); }
.eyebrow { margin: 0 0 2px; font-size: 12px; letter-spacing: .08em; color: #64766b; }
.detail h2 { margin: 0 0 10px; font-size: 20px; }
.detail ul { margin: 0; padding-left: 20px; }
.detail li { padding: 4px 0; }
.note { margin: 12px 0 0; padding: 10px 14px; border-left: 3px solid #0f6e5c; background: #f2f7f4; border-radius: 0 8px 8px 0; color: #34503f; }
.actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-top: 18px; }
.actions .open { display: inline-flex; align-items: center; min-height: 44px; padding: 0 20px; border-radius: 10px; background: #0f6e5c; color: #fff; text-decoration: none; font-weight: 600; }
.actions .ghost { min-height: 44px; padding: 0 14px; background: transparent; border: 1px solid #cddbd1; border-radius: 10px; color: #203b30; cursor: pointer; }
.actions .ghost:disabled { opacity: .4; cursor: default; }

.more { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 16px; margin: 16px 2px 0; color: #4d6256; }
.more a { color: #17523a; min-height: 44px; display: inline-flex; align-items: center; text-decoration: underline; }
.faq { margin-top: 8px; padding: 4px 18px; background: #fff; border: 1px solid #d4e1d8; border-radius: 12px; }
.faq summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; font-weight: 600; }
.faq dt { font-weight: 600; margin-top: 8px; }
.faq dd { margin: 2px 0 8px; }

@media (max-width: 800px) {
  .flow { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .flow li { padding: 0; }
  .flow li:not(:last-child)::after { top: 62px; bottom: -4px; left: 31px; right: auto; width: 2px; height: auto; }
  .flow button { flex-direction: row; text-align: left; gap: 12px; padding: 6px 8px; }
  .flow button strong, .flow button small { display: block; }
  .flow button .num { display: none; }
  .flow button .badge { flex: none; width: 48px; height: 48px; }
  .flow button { display: grid; grid-template-columns: 48px minmax(0, 1fr); column-gap: 12px; align-items: center; justify-items: start; }
  .flow button .badge { grid-row: 1 / span 2; }
  .detail { padding: 16px; }
  .actions { justify-content: center; }
  .actions .open { order: -1; width: 100%; justify-content: center; }
}
</style>
