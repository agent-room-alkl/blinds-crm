<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
defineProps<{demo:boolean;deliveryEnabled:boolean}>();
const {locale}=useI18n();
const tx=(zh:string,en:string)=>locale.value==='zh'?zh:en;
const sections=computed(()=>[
  {title:tx('1 · 客户与账号','1 · Customers & accounts'),path:'/crm/customers',steps:[
    tx('在“客户资料”搜索并选择公司；资料、登录账号、订单、账款返利均属于同一个客户。','Search and select a company under Customers. Profile, portal account, orders and accounts belong to the same customer.'),
    tx('管理员通过“新增客户并开通账号”创建公司和唯一门户账号。已有公司不要重复创建；邮箱缺失可待补，未知地址保留待补标记。','An admin creates a company and its single portal account together. Do not duplicate an existing company. Missing email/address details can remain marked incomplete.'),
    tx('“登录账号”查看用户名；现有密码不显示。客户登录门户后，只能看本公司的订单和账款。','Portal account shows the username, never the existing password. Customer portal access is restricted to that company.') ]},
  {title:tx('2 · 客户下单与价格','2 · Customer orders & pricing'),path:'/crm/projects',steps:[
    tx('客户门户按“选系列 → 窗户列表 → 尺寸与配置 → 核对提交”下单。官网五个系列可选；Deluxe仍是暂定价格，不能作为已确认商业报价。','The portal follows Series → Windows → Size & configuration → Review & submit. Five website series are available. Deluxe remains provisional and is not a confirmed commercial quote.'),
    tx('尺寸单位为毫米；数量是同规格窗数量，扇数是每个窗的面板数。填完必填项并得到价格后进入下一扇。缺项会列明字段。','Dimensions are in millimetres. Quantity counts identical windows; panels are per window. Complete required fields and obtain a price before continuing. Missing fields are named.'),
    tx('提交前核对订单名称、施工地址和每扇窗。提交后状态为待审核，尚未收款、未向供应商下单。','Check project name, site address and every window before submitting. A submitted order awaits review; no payment or supplier order is implied.') ]},
  {title:tx('3 · 审核与定金','3 · Review & deposit'),path:'/crm/projects',steps:[
    tx('选择订单，在“计价与审核”核对价格版本和配置。待审核时可记录有说明的价格调整；审核后价格冻结。','Select an order and check its version and configuration under Pricing & review. Documented adjustments are allowed before acceptance; accepted prices are frozen.'),
    tx('“确认接收”接受审核，并生成60%定金发票草稿（按既定规则向上取整到分）。这不代表定金已收，也不会直接发送发票邮件。','Accept review creates a 60% deposit invoice draft, rounded up to cents. It does not confirm receipt or automatically email the invoice.'),
    tx('“定金已收”是独立的收款记录动作。演示中可走流程；正式业务必须先核实实际到账。系统不会扣款或转账。','Deposit received is a separate receipt record. The demo can exercise the workflow; real operations require verified funds. The system does not charge or transfer money.') ]},
  {title:tx('4 · 供应商与采购导出','4 · Suppliers & purchasing'),path:'/crm/providers',steps:[
    tx('“供应商”管理共享供应商及其专用Excel导出模板。当前由付款/报价抬头整理的候选方，不等于已经确认的工厂。','Suppliers manages shared suppliers and their Excel export templates. Candidates inferred from payment/quotation issuers are not confirmed manufacturers.'),
    tx('在订单“供应商与导出”选择已启用供应商、导出模板版本并保存分配；填写供应商参考号后记录下单。定金未收等前置条件会被拦截。','Under an order’s Supplier & files, assign an active supplier and template revision. Record the supplier reference and order placement. Prerequisites such as deposit receipt are enforced.'),
    tx('导出模板修改要“基于此版创建新版本”，不覆盖旧版。基本模板和生产资料草稿未经工厂格式确认；导出不是发邮件。','Create a new export revision instead of overwriting an old one. Basic templates and production drafts are not factory-verified formats. Exporting downloads a file; it does not send email.') ]},
  {title:tx('5 · 在途、到货与交付','5 · Transit, arrival & delivery'),path:'/crm/projects',steps:[
    tx('订单列表勾选后出现批量工具条。批量标在途会逐单检查前置状态并返回结果。','Selecting orders reveals batch actions. Marking transit validates each order and reports its outcome.'),
    tx('在“明细与履约”填写本批到货/交付数量再记录。到货累计不能超过订购，交付累计不能超过已到货；不是把输入数字当总数量覆盖。','Enter quantities for this arrival/delivery batch. Total arrivals cannot exceed orders, and deliveries cannot exceed arrivals. Batch quantities add to the recorded totals.'),
    tx('到货记录会生成通知记录；演示模式只允许发给管理员测试邮箱，服务未就绪时只记录未发送。部分到货不代表全部交付或可以直接开尾款。','Arrival creates a notification record. Demo mail can go only to the owner test mailbox; without mail service it is recorded as not sent. Partial arrival does not imply full delivery or balance-invoice eligibility.') ]},
  {title:tx('6 · 发票、结算与返利','6 · Invoices, settlement & rebates'),path:'/crm/finance',steps:[
    tx('订单页只显示本单发票。跨订单结算、客户账本和返利统一在“账款与返利”；先选择公司再勾选来源订单/发票。','Order pages show their own invoices. Cross-order settlement, customer ledgers and rebates live under Accounts & rebates. Select the company before choosing sources.'),
    tx('尾款草稿只接受同公司、同币种且已全部交付、定金已收的订单，并使用已保存的定金扣减。生成草稿、发送记录、确认收款是不同动作。','Balance drafts require fully delivered, deposit-received orders in one company and currency. Stored deposits are deducted. Draft creation, sending and receipt confirmation are distinct actions.'),
    tx('返利只录入已确认的月度金额、来源订单和确认依据。查看已用/余额及抵扣记录；同一来源订单不能重复计算，未配置阶梯公式不会自动算返利。','Record confirmed monthly rebates with source orders and evidence. Track used/remaining amounts and allocations. Duplicate sources are blocked; no unconfirmed tier formula is calculated.') ]},
  {title:tx('7 · 共享价表与历史追溯','7 · Shared pricing & history'),path:'/crm/pricing',steps:[
    tx('“定价与模板”管理商业价格规则；“供应商”内的输出模板管理工作表与栏目格式，两者不要混用。','Pricing & templates manages commercial rules; supplier export templates manage worksheets and columns. They serve different purposes.'),
    tx('价表版本显示引用订单和明确配置的适用供应商，点击短订单号可回到原单。启用新价表只影响后续计价，不改已审核订单。','Each pricing version lists actual order usage and explicitly configured supplier applicability. Click an order number to open it. Activation affects future pricing, not accepted orders.'),
    tx('“操作记录”保存审核、采购和导出版本等事件。供应商停用后不能用于新操作；历史引用仍保留。','Activity retains review, purchasing and export-revision events. Inactive suppliers cannot be used for new operations; historical references remain.') ]},
  {title:tx('8 · 产品、看板与系统设置','8 · Products, analytics & settings'),path:'/crm/products',steps:[
    tx('产品目录按官网五个系列维护图片、名称与规格；修改展示资料不会改写已保存的订单价格。','Maintain images, names and specifications for the five website series. Catalogue edits do not rewrite saved order prices.'),
    tx('分析看板目前明确标为示例数据，不能作为真实销售、收款或利润报告。','Analytics is currently labelled sample data and is not a real sales, receipts or profit report.'),
    tx('系统设置由管理员管理内部用户和权限，并查看发件服务状态。演示邮件限定管理员本人收发；客户不会收到。','Admins manage staff access and view mail service status under Settings. Demo email is limited to the owner as sender and recipient; customers receive none.') ]},
]);
</script>

<template>
  <section class="guide">
    <header><h1>{{ tx('后台操作指南','CRM operating guide') }}</h1><p>{{ tx('按业务顺序使用；菜单中的资料与账本可以随时独立打开。','Follow the workflow below. Shared records and ledgers are also available independently from the menu.') }}</p></header>
    <aside v-if="demo" class="guide-demo"><strong>{{ tx('当前为演示模式：客户不会收到邮件','Demo mode: customers receive no email') }}</strong><p>{{ deliveryEnabled ? tx('发件服务就绪时，演示邮件只从管理员测试邮箱发给同一邮箱。确认接收仍只产生发票草稿；发送是独立操作。','When mail is ready, demo messages go from the owner test mailbox to that same mailbox only. Accepting review still creates a draft; sending is separate.') : tx('发件服务尚未就绪。模拟发送与到货通知只保存“演示记录 · 未发送”，不会连接邮件服务器。确认接收只产生发票草稿。','Mail delivery is not ready. Simulated sends and arrival notifications are recorded as “Demo recorded · not sent” without contacting a mail server. Accepting review creates an invoice draft.') }}</p></aside>
    <nav aria-label="Guide contents"><a v-for="(section,index) in sections" :key="section.title" :href="'#guide-'+index">{{ section.title }}</a></nav>
    <article v-for="(section,index) in sections" :key="section.title" :id="'guide-'+index"><h2>{{ section.title }}</h2><ol><li v-for="step in section.steps" :key="step">{{ step }}</li></ol><RouterLink :to="section.path">{{ tx('打开对应模块','Open this workspace') }} →</RouterLink></article>
    <article><h2>{{ tx('常见问题','Common questions') }}</h2><dl><dt>{{ tx('下一步没有进入？','Cannot continue?') }}</dt><dd>{{ tx('先看缺项提示和价格预览；必填配置、有效尺寸和价格都需要完成。','Check missing fields and the price preview. Required options, valid dimensions and a price must be ready.') }}</dd><dt>{{ tx('操作被拒绝？','An action was refused?') }}</dt><dd>{{ tx('核对订单状态、定金、供应商启用状态和本批数量。不要反复提交来绕过条件。','Check order state, deposit, supplier availability and batch quantities. Repeated submission does not bypass prerequisites.') }}</dd><dt>{{ tx('保存报错？','Save failed?') }}</dt><dd>{{ tx('保留已填内容，记录短订单号、所点按钮和错误提示后反馈；未显示成功前不要认为已经保存。','Keep entered values and report the readable order number, action and error. Treat it as saved only after success is shown.') }}</dd></dl></article>
  </section>
</template>

<style scoped>
.guide{max-width:1100px;margin:0 auto;color:#203b30;font-size:14px;line-height:1.65}.guide h1{font-size:24px!important;line-height:1.3!important;margin:0 0 8px!important}.guide h2{font-size:18px;margin:0 0 12px}.guide p{margin:8px 0}.guide-demo,.guide article{background:white;border:1px solid #d4e1d8;border-radius:8px;padding:18px;margin-top:16px}.guide-demo{background:#edf6ef}.guide nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 16px;padding:12px 0}.guide a{color:#17523a;min-height:44px;text-decoration:underline}.guide li{padding:4px 0}.guide ol{padding-left:22px;margin:8px 0}.guide article{scroll-margin-top:16px}.guide dt{font-weight:600;margin-top:12px}.guide dd{margin:4px 0 8px}@media(max-width:700px){.guide nav{grid-template-columns:minmax(0,1fr)}.guide article,.guide-demo{padding:14px}}
</style>
