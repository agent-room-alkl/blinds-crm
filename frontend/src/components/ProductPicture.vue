<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue';
import {session} from '../crm-api';
const props=withDefaults(defineProps<{src:string;alt?:string;loading?:'lazy'|'eager'}>(),{alt:'',loading:'lazy'});
const url=ref(''),failed=ref(false);let objectUrl='',controller:AbortController|null=null;
function release(){controller?.abort();controller=null;if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=''}}
watch(()=>props.src,async value=>{release();url.value='';failed.value=false;if(!value)return;if(!value.startsWith('/api/media/')){url.value=value;return}const current=new AbortController();controller=current;try{const response=await fetch(value,{headers:session.token?{Authorization:`Bearer ${session.token}`}:{},signal:current.signal});if(!response.ok)throw new Error('Image preview unavailable');const blob=await response.blob();if(current.signal.aborted)return;objectUrl=URL.createObjectURL(blob);url.value=objectUrl}catch{if(!current.signal.aborted)failed.value=true}},{immediate:true});
onBeforeUnmount(release);
</script>
<template><img v-if="url" :src="url" :alt="alt" :loading="loading"/><span v-else class="product-picture-placeholder" role="img" :aria-label="alt">{{failed?'Image unavailable':'…'}}</span></template>
<style scoped>.product-picture-placeholder{display:grid;place-items:center;background:#edf1ed;color:#68766e;font-size:11px;min-width:40px;min-height:50px}</style>
