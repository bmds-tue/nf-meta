<script setup lang="ts">
defineProps({
  name: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <svg v-if="name === 'play'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M8 5v14l11-7z" fill="currentColor" />
  </svg>

  <svg v-else-if="name === 'stop'" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
    <path
      fill="currentColor"
      d="M8 16h8V8H8zm4 6q-2.075 0-3.9-.788t-3.175-2.137q-1.35-1.35-2.137-3.175T2 12q0-2.075.788-3.9t2.137-3.175q1.35-1.35 3.175-2.137T12 2q2.075 0 3.9.788t3.175 2.137q1.35 1.35 2.138 3.175T22 12q0 2.075-.788 3.9t-2.137 3.175q-1.35 1.35-3.175 2.138T12 22"
    />
  </svg>

  <svg v-else-if="name === 'horizontal'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M2,12 L22,12" stroke="currentColor" stroke-width="2" />
    <path d="M7,7 L2,12 L7,17" stroke="currentColor" stroke-width="2" fill="none" />
    <path d="M17,7 L22,12 L17,17" stroke="currentColor" stroke-width="2" fill="none" />
  </svg>

  <svg v-else-if="name === 'vertical'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M12,2 L12,22" stroke="currentColor" stroke-width="2" />
    <path d="M7,7 L12,2 L17,7" stroke="currentColor" stroke-width="2" fill="none" />
    <path d="M7,17 L12,22 L17,17" stroke="currentColor" stroke-width="2" fill="none" />
  </svg>

  <svg v-else-if="name === 'shuffle'" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
    <path
      fill="currentColor"
      d="M14 20v-2h2.6l-3.175-3.175L14.85 13.4L18 16.55V14h2v6zm-8.6 0L4 18.6L16.6 6H14V4h6v6h-2V7.4zm3.775-9.425L4 5.4L5.4 4l5.175 5.175z"
    />
  </svg>

  <svg v-else-if="name === 'add'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M11 5h2v14h-2zM5 11h14v2H5z" fill="currentColor" />
  </svg>

  <svg v-else-if="name === 'save'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <!-- Arrow down -->
    <path d="M11 3h2v10l3.5-3.5 1.4 1.4L12 17.8 6.1 10.9l1.4-1.4L11 13z" fill="currentColor"/>
    <!-- Bottom bar -->
    <path d="M5 19h14v2H5z" fill="currentColor"/>
  </svg>

  <svg v-else-if="name === 'open'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <g transform="rotate(180 12 10)">
      <path d="M11 3h2v10l3.5-3.5 1.4 1.4L12 17.8 6.1 10.9l1.4-1.4L11 13z" fill="currentColor"/>
    </g>
    <path d="M5 19h14v2H5z" fill="currentColor"/>
  </svg>

  <svg v-else-if="name === 'options'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <circle cx="6" cy="12" r="2" fill="currentColor"/>
    <circle cx="12" cy="12" r="2" fill="currentColor"/>
    <circle cx="18" cy="12" r="2" fill="currentColor"/>
  </svg>

  <svg v-else-if="name === 'undo'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path
        d="M12 5a7 7 0 0 1 0 14H7v-2h5a5 5 0 0 0 0-10H8.8l2.6 2.6L10 11 5 6l5-5 1.4 1.4L8.8 5z"
        fill="currentColor"
    />
  </svg>

  <svg v-else-if="name === 'redo'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path
        d="M12 5a7 7 0 0 0 0 14h5v-2h-5a5 5 0 0 1 0-10h3.2l-2.6 2.6L14 11l5-5-5-5-1.4 1.4L15.2 5z"
        fill="currentColor"
    />
  </svg>

  <svg v-else-if="name === 'split'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <!-- Left pane -->
    <rect x="3" y="5" width="7" height="14" rx="1.5" fill="currentColor"/>
  
    <!-- Right pane -->
    <rect x="14" y="5" width="7" height="14" rx="1.5" fill="currentColor"/>
  
    <!-- Divider -->
    <rect x="11" y="5" width="2" height="14" fill="currentColor"/>
  </svg>

  <svg v-else-if="name === 'edit'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <!-- Pencil body -->
    <path d="M3 17.25V21h3.75L19.81 7.94l-3.75-3.75L3 17.25z" fill="currentColor"/>
    <!-- Pencil tip -->
    <path d="M20.71 6.04a1 1 0 0 0 0-1.41l-1.34-1.34a1 1 0 0 0-1.41 0l-1.13 1.13 3.75 3.75 1.13-1.13z" fill="currentColor"/>
  </svg>

  <svg v-else-if="name === 'close'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
  </svg>

  <svg v-else-if="name === 'collapse'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 15l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>

  <svg v-else-if="name === 'expand'" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</template>
