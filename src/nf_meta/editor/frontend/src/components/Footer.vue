<template>
  <footer class="app-footer">
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
  </footer>
</template>

<script setup lang="ts">
const year = new Date().getFullYear()

// replace with import.meta.env if you inject version
const version = "0.0.1"

const github = "https://github.com/JulianFlesch/mp-builder-2"
</script>

<style scoped>
.app-footer {
  height: 25px;

  display: flex;
  align-items: center;
  justify-content: space-between;

  padding: 0 12px;

  font-size: 12px;
  color: #cbd5e1;

  background-color: #2d3748cf;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);

  flex-shrink: 0;

  backdrop-filter: blur(6px);
}

/* optional subtle feel */
.app-footer span {
  opacity: 0.8;
}

.app-footer a {
      color:inherit;
}
</style>