<template>
  <v-footer class="app-footer">
    <span class="left">
      {{ year }} ©
    </span>

    <span class="center">
        Code and Issues on 
        <a :href="github">Github</a>
    </span>

    <span class="right">
      v{{ version }}
    </span>
  </v-footer>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()

// replace with import.meta.env if you inject version
const version = "0.0.1"

const github = "https://github.com/JulianFlesch/mp-builder-2"
</script>

<style scoped>
.app-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: rgb(var(--v-theme-onSurface));
  flex-shrink: 0;
  backdrop-filter: blur(6px);
}

.app-footer a {
      color:inherit;
}
</style>