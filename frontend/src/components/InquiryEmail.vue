<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue';
import { request } from '../crm-api';
const props=defineProps<{inquiry:{id:number;company:string;contact_name:string;channel:string};locale:string}>();
const tx=(z:string,e:string)=>props.locale==='zh'?z:e;
const open=ref(false),busy=ref(false),error=ref(''),success=ref('');
const config=ref({configured:false,sender:''});
const form=reactive({recipient:'',subject:'',body:''});
const emit=defineEmits<{sent:[]}>();
function reset(){open.value=false;error.value='';success.value='';form.recipient=props.inquiry.channel.match(/[^\s/<>]+@[^\s/<>]+\.[^\s/<>]+/)?.[0]||'';form.subject=tx(`VERA · ${props.inquiry.company} 项目询价`,`VERA · ${props.inquiry.company} inquiry`);form.body='';}
watch(()=>props.inquiry.id,reset,{immediate:true});
onMounted(async()=>{try{config.value=await request('email/config')}catch{error.value=tx('无法读取邮件设置','Could not load email settings')}});
async function send(){if(busy.value)return;busy.value=true;error.value='';success.value='';try{await request(`inquiries/${props.inquiry.id}/email`,form);success.value=tx('邮件已提交给邮件服务器，发送记录已保存。','Email accepted by the mail server. Activity recorded.');open.value=false;emit('sent')}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{busy.value=false}}
</script>
<template>
  <div class="email-action"><button type="button" class="secondary" :aria-expanded="open" @click="open=!open">{{tx('发送邮件','Send email')}}</button></div>
  <p v-if="success" class="email-success" role="status">{{success}}</p>
  <section v-if="open" class="email-editor"><header><div><h3>{{tx('邮件回复','Email reply')}}</h3><p>{{config.configured?tx('发件人：','From: ')+config.sender:tx('邮件尚未启用，请先由管理员配置发件服务。','Email delivery is not enabled. Ask an administrator to configure it.')}}</p></div><button type="button" class="secondary" @click="open=false">{{tx('收起','Close')}}</button></header><form @submit.prevent="send"><label>{{tx('收件人','To')}}<input v-model="form.recipient" type="email" required autocomplete="email" /></label><label>{{tx('主题','Subject')}}<input v-model="form.subject" required maxlength="200" /></label><label>{{tx('正文','Message')}}<textarea v-model="form.body" required maxlength="10000" :placeholder="tx('写下要发送给客户的内容…','Write your message to the customer…')" /></label><p v-if="error" class="email-error" role="alert">{{error}}</p><footer><span>{{tx('点击发送后将向此收件人发送邮件，并保存跟进记录。','Sending delivers this message to the recipient and records the activity.')}}</span><button :disabled="busy||!config.configured">{{busy?tx('发送中…','Sending…'):tx('发送邮件','Send email')}}</button></footer></form></section>
</template>
<style scoped>
.email-action{display:inline-block}.email-action button,.email-editor button{min-height:40px;padding:8px 14px;border:1px solid #d3ddd6;background:#fff;border-radius:4px;color:#1b2421;font:500 12px var(--font-body)}.email-editor{width:100%;box-sizing:border-box;margin:18px 0 24px;border:1px solid #dbe3de;border-radius:6px;padding:20px;background:#fafcfb}.email-editor header{display:flex;justify-content:space-between;align-items:start;gap:16px}.email-editor h3{font-size:16px;margin:0 0 6px}.email-editor p{font-size:12px;color:#65736a;margin:0 0 12px}.email-editor label{display:block;font-size:12px;margin-top:14px}.email-editor input,.email-editor textarea{display:block;width:100%;margin-top:6px;padding:10px 12px;border:1px solid #d3ddd6;border-radius:4px;font:14px var(--font-body);background:#fff;box-sizing:border-box}.email-editor textarea{min-height:180px;resize:vertical}.email-editor footer{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:18px}.email-editor footer span{font-size:11px;color:#65736a;max-width:380px}.email-editor footer button{background:#0f6e5c;color:white;border-color:#0f6e5c;flex:none}.email-editor button:disabled{opacity:.5;cursor:default}.email-error{color:#8c2f2f!important}.email-success{color:#0f6e5c;font-size:13px}@media(max-width:600px){.email-editor{padding:16px}.email-editor footer{align-items:stretch;flex-direction:column}}
</style>
