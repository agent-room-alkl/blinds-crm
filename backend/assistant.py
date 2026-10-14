"""Read-only, deterministic assistance. Never presents rules as a connected model."""
from datetime import datetime, timedelta

def build_assistance(inquiry, customer, quotes, orders, tone):
    zh=customer.get('locale',inquiry['locale'])=='zh'
    tx=lambda z,e:z if zh else e
    sources=[];facts=[]
    def add(kind,record_id,label,excerpt,text):
        sid=f'{kind}:{record_id}'
        sources.append({'id':sid,'type':kind,'record_id':record_id,'label':label,'excerpt':str(excerpt)[:1600]})
        facts.append({'text':text,'source_ids':[sid]})
        return sid
    name=(customer.get('contacts') or [{}])[0].get('name') or inquiry['contact_name']
    add('customer',customer['id'],tx('当前客户档案','Current customer file'),customer.get('notes',''),tx(f"客户：{customer['company']}；沟通语言：{'中文' if zh else '英文'}",f"Customer: {customer['company']}; preferred language: {'Chinese' if zh else 'English'}"))
    spec=[]
    if inquiry.get('product_id'):spec.append(tx('产品编号','Product ID')+' '+str(inquiry['product_id']))
    if inquiry.get('width') and inquiry.get('height'):spec.append(f"{inquiry['width']} × {inquiry['height']} {inquiry.get('unit') or ''}")
    if inquiry.get('quantity'):spec.append(tx('数量','Quantity')+' '+str(inquiry['quantity']))
    add('inquiry',inquiry['id'],tx('原始询价','Original inquiry'),inquiry.get('notes',''),tx('已记录需求：','Recorded requirements: ')+(' / '.join(spec) or tx('规格待确认','Specifications to confirm')))
    if inquiry.get('expected_date'):facts.append({'text':tx('客户交期意向（未承诺）：','Requested timing (not promised): ')+inquiry['expected_date'],'source_ids':[f"inquiry:{inquiry['id']}"]})
    follows=sorted(inquiry.get('followups',[]),key=lambda x:x['id'])
    for f in follows[-3:]:add('followup',f['id'],tx('跟进记录','Follow-up')+f" #{f['id']}",f['note'],tx('沟通原文：','Recorded note: ')+f['note'][:360])
    quote=quotes[-1] if quotes else None
    if quote:
        v=quote['versions'][-1]
        add('quote',quote['id'],f"Q-{quote['id']} / v{v['version']}",f"{v['currency']} {v['total']}",tx('最新人工报价：','Latest manually entered quote: ')+f"Q-{quote['id']}/v{v['version']} · {v['currency']} {v['total']}")
    stage={'confirmed':('已确认','Confirmed'),'production':('生产中','In production'),'ready':('待发货','Ready to ship'),'delivered':('已交付','Delivered')}
    order=orders[-1] if orders else None
    if order:add('order',order['id'],tx('订单','Order')+f" #{order['id']}",order['status'],tx('订单记录状态：','Recorded order status: ')+tx(*stage.get(order['status'],(order['status'],order['status']))))
    missing=[]
    for key,label in [('product_id',('产品','product')),('quantity',('数量','quantity'))]:
        if not inquiry.get(key):missing.append(tx(*label))
    if not inquiry.get('width') or not inquiry.get('height') or not inquiry.get('unit'):missing.append(tx('尺寸与单位','dimensions and unit'))
    if not inquiry.get('expected_date'):missing.append(tx('交期意向','requested timing'))
    action=tx('核对订单记录并确认下一次沟通安排','Review the recorded order and confirm the next conversation') if order else tx('向客户确认缺项，再由销售核对报价','Confirm missing details with the customer, then have sales review pricing') if missing else tx('由销售复核规格与商务条款，再联系客户','Have sales review specifications and commercial terms, then contact the customer')
    scheduled=next((f['next_at'] for f in reversed(follows) if f.get('next_at')),None)
    proposed=datetime.now().replace(hour=10,minute=0,second=0,microsecond=0)+timedelta(days=2)
    while proposed.weekday()>4:proposed+=timedelta(days=1)
    summary=tx(f"询价 #{inquiry['id']}；{len(follows)}次跟进；"+('有订单记录' if order else '有人工报价' if quote else '尚无报价')+('；仍需确认'+ '、'.join(missing) if missing else '；原始规格已记录'),f"Inquiry #{inquiry['id']}; {len(follows)} follow-ups; "+('order recorded' if order else 'manual quote available' if quote else 'no quote yet')+('; still to confirm: '+', '.join(missing) if missing else '; original specifications recorded'))
    ask=tx('请确认：'+'、'.join(missing)+'。','Please confirm: '+', '.join(missing)+'.') if missing else tx('我们会复核已记录的规格与商务条款。','We will review the recorded specifications and commercial terms.')
    if order:ask=tx('我们将核对订单记录，并与您确认下一次沟通安排。','We will review the order record and confirm the next conversation with you.')
    greeting=tx(f'{name}，您好。',f'Dear {name},' if tone=='formal' else f'Hello {name},')
    reply=greeting+'\n\n'+tx(f'关于您的询价 #{inquiry["id"]}。',f'Regarding inquiry #{inquiry["id"]}. ')+ask
    if tone=='formal':reply+='\n\n'+tx('价格和交付安排以双方确认的报价及订单为准。感谢您的配合。','Pricing and delivery arrangements remain subject to the agreed quotation and order. Thank you.')
    return {'provider':'rules','model_connected':False,'locale':'zh' if zh else 'en','generated_at':datetime.now().isoformat(),'summary':summary,'facts':facts,'missing':missing,'next_action':action,'suggested_next_at':scheduled or proposed.isoformat(timespec='minutes'),'next_time_basis':'recorded' if scheduled else 'suggestion','reply':reply,'sources':sources}
