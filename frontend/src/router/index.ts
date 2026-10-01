import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/days', name: 'Days', component: () => import('../views/Days.vue') },
  { path: '/segments', name: 'Segments', component: () => import('../views/Segments.vue') },
  { path: '/vendors', name: 'Vendors', component: () => import('../views/Vendors.vue') },
  { path: '/tension', name: 'Tension', component: () => import('../views/Tension.vue') },
  { path: '/map', name: 'Map', component: () => import('../views/Map.vue') },
  { path: '/rejected', name: 'Rejected', component: () => import('../views/Rejected.vue') },
  { path: '/pillars', name: 'Pillars', component: () => import('../views/Pillars.vue') },
  { path: '/', redirect: '/tension' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
