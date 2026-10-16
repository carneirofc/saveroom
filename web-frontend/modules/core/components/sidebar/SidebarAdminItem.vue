<template>
  <li
    class="tree__item"
    :class="{
      active: $route.matched.some(({ name }) => name === adminType.routeName),
    }"
  >
    <div class="tree__action sidebar__action">
      <nuxt-link :to="{ name: adminType.routeName }" class="tree__link">
        <i class="tree__icon" :class="adminType.iconClass"></i>
        <span class="tree__link-text">
          <span class="sidebar__item-name">{{ adminType.getName() }}</span>
        </span>
      </nuxt-link>
    </div>
  </li>
</template>

<script>
export default {
  name: 'SidebarAdminItem',
  props: {
    adminType: {
      required: true,
      type: Object,
    },
  },
}
</script>
