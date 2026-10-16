export default defineNuxtPlugin((nuxtApp) => {
  const { public: publicConfig } = useRuntimeConfig()

  // Identifies the web-frontend build itself: which release tag and commit this
  // bundle was built from. Empty in a development build, so every consumer has
  // to render that case as nothing rather than an empty value.
  //
  // Not to be confused with runtimeConfig.public.version, which is the version
  // of the Baserow codebase this fork tracks.
  nuxtApp.provide('buildInfo', {
    version: publicConfig.appVersion || '',
    commit: publicConfig.gitCommit || '',
    buildDate: publicConfig.buildDate || '',
  })
})
