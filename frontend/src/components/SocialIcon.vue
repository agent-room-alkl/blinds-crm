<script setup lang="ts">
defineProps<{name:string}>();
</script>
<template>
<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="currentColor"><path v-if="name==='Facebook'" d="M14.5 22v-8.2h2.8l.4-3.2h-3.2v-2c0-.9.3-1.5 1.6-1.5h1.7V4.2c-.3 0-1.3-.2-2.5-.2-2.5 0-4.1 1.5-4.1 4.2v2.4H8.5v3.2h2.7V22z"/><path v-else d="M15.8 3c.3 2.2 1.6 3.5 4.2 3.8v3.4a9 9 0 0 1-4.2-1.3v7a5.9 5.9 0 1 1-5.8-5.8l.6.1v3.5a2.5 2.5 0 1 0 1.7 2.4V3z"/></svg>
</template>
