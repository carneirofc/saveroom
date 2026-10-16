<template>
  <div class="build-info">
    <Alert v-if="error" type="error" class="build-info__unavailable">
      <template #title>{{ $t('buildInfo.unavailableTitle') }}</template>
      {{ $t('buildInfo.unavailableMessage') }}
    </Alert>
    <div v-for="row in rows" :key="row.key" class="build-info__row">
      <div class="build-info__name">{{ row.name }}</div>
      <div class="build-info__value">
        <span class="build-info__value-text" :title="row.title">{{
          row.value
        }}</span>
        <a
          v-if="row.copyable"
          class="build-info__copy"
          @click.prevent="copy(row.copyValue)"
        >
          {{ $t('action.copy') }}
          <Copied ref="copied"></Copied>
        </a>
      </div>
    </div>
    <div v-if="frontendLabel" class="build-info__frontend">
      {{ $t('buildInfo.webFrontendBuild', { build: frontendLabel }) }}
    </div>
    <Alert v-if="buildsDiffer" type="warning" class="build-info__mismatch">
      <template #title>{{ $t('buildInfo.mismatchTitle') }}</template>
      {{
        $t('buildInfo.mismatchMessage', {
          backend: backendLabel,
          frontend: frontendLabel,
        })
      }}
    </Alert>
    <div v-if="showCredits" class="build-info__credits">
      <div class="build-info__credits-line">
        {{ $t('buildInfo.creditsFork') }}
        <a :href="credits.forkUrl" target="_blank" rel="noopener noreferrer">{{
          $t('buildInfo.forkRepository')
        }}</a>
      </div>
      <div class="build-info__credits-line">
        {{ $t('buildInfo.creditsUpstream') }}
        <a
          :href="credits.upstreamUrl"
          target="_blank"
          rel="noopener noreferrer"
          >{{ $t('buildInfo.upstreamProject') }}</a
        >
      </div>
      <div class="build-info__credits-line">
        {{ $t('buildInfo.creditsLicense') }}
        <a
          :href="credits.licenseUrl"
          target="_blank"
          rel="noopener noreferrer"
          >{{ $t('buildInfo.license') }}</a
        >
      </div>
    </div>
  </div>
</template>

<script>
import { copyToClipboard } from '@baserow/modules/database/utils/clipboard'
import {
  buildLabel,
  buildTitle,
  formatBuildDate,
  isSameBuild,
  shortCommit,
} from '@baserow/modules/core/utils/buildInfo'
import {
  BRANDING_DEFAULTS,
  PROJECT_CREDITS,
} from '@baserow/modules/core/brandingDefaults'

export default {
  name: 'BuildInfo',
  props: {
    /**
     * The backend build, as returned by the admin build info endpoint. Null
     * while it is still loading.
     */
    backend: {
      required: false,
      type: Object,
      default: null,
    },
    /**
     * Whether the request for the backend build failed. A backend that is older
     * than this web-frontend has no endpoint to answer it, which is itself a
     * half-upgraded deployment worth stating.
     */
    error: {
      required: false,
      type: Boolean,
      default: false,
    },
  },
  data() {
    return { credits: PROJECT_CREDITS }
  },
  computed: {
    /**
     * Credits do not depend on the backend, so they render even when its build
     * could not be read. They are attribution, so the branding can hide them.
     */
    showCredits() {
      return (
        this.$branding?.showAttribution ?? BRANDING_DEFAULTS.showAttribution
      )
    },
    /**
     * The web-frontend build, which unlike the backend one needs no request: it
     * is baked into this bundle.
     */
    frontend() {
      return this.$buildInfo
    },
    frontendLabel() {
      return buildLabel(this.frontend)
    },
    backendLabel() {
      return buildLabel(this.backendBuild)
    },
    backendBuild() {
      if (this.backend === null) {
        return null
      }
      return {
        version: this.backend.version,
        commit: this.backend.commit,
        buildDate: this.backend.build_date,
      }
    },
    /**
     * A backend and a web-frontend built from different commits mean only half
     * of the deployment was upgraded, which is exactly what this panel exists
     * to make visible.
     */
    buildsDiffer() {
      return (
        this.backendBuild !== null &&
        !isSameBuild(this.backendBuild, this.frontend)
      )
    },
    rows() {
      const build = this.backendBuild
      if (build === null) {
        return []
      }

      const version = build.version || ''
      const commit = build.commit || ''
      const buildDate = formatBuildDate(build.buildDate)

      const rows = [
        {
          key: 'version',
          name: this.$t('buildInfo.applicationVersion'),
          value: version || this.$t('buildInfo.developmentBuild'),
          title: buildTitle(build),
        },
      ]

      // A development build has no commit and no build date to show, and an
      // empty row reads as a broken one.
      if (commit !== '') {
        rows.push({
          key: 'commit',
          name: this.$t('buildInfo.commit'),
          value: shortCommit(commit),
          title: commit,
          copyable: true,
          copyValue: commit,
        })
      }

      if (buildDate !== '') {
        rows.push({
          key: 'buildDate',
          name: this.$t('buildInfo.buildDate'),
          value: buildDate,
        })
      }

      if (this.backend.baserow_version) {
        rows.push({
          key: 'baserowVersion',
          name: this.$t('buildInfo.baserowCoreVersion'),
          value: this.backend.baserow_version,
        })
      }

      return rows
    },
  },
  methods: {
    copy(value) {
      copyToClipboard(value)
      // Only the commit row renders a Copied, but refs in a v-for are an array.
      const copied = Array.isArray(this.$refs.copied)
        ? this.$refs.copied[0]
        : this.$refs.copied
      copied?.show()
    },
  },
}
</script>
