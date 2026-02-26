<template>
    <v-snackbar-queue v-model="messageStore.queue" closable="true"></v-snackbar-queue>
</template>

<script setup lang="ts">
import { useMessageStore } from '../store';    
const messageStore = useMessageStore()
</script>