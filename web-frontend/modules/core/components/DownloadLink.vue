<template>
  <span v-if="!url" :class="unavailableClass">
    <slot :loading="false"></slot>
  </span>
  <a
    v-else
    :href="href"
    target="_blank"
    :download="filename"
    :class="{ [loadingClass]: loading }"
    @click="onClick($event)"
  >
    <slot :loading="loading"></slot>
  </a>
</template>

<script>
/**
 * A link to a file the server generated for us.
 *
 * Every download is checked before the browser is sent to it. Without that check a
 * failure is invisible: a plain link renders the error page where the file should
 * have been, and the XHR path used to save the error body under the file's own name.
 * Since the checks distinguish a file that expired from a storage the server cannot
 * reach, the message can say which of the two happened.
 */
export default {
  name: 'DownloadLink',
  props: {
    /**
     * Null while the file does not exist (yet), in which case the link renders as
     * plain, non-interactive text rather than throwing on an empty URL.
     */
    url: {
      type: String,
      required: false,
      default: null,
    },
    filename: {
      type: String,
      required: true,
    },
    onError: {
      type: Function,
      required: false,
      default: null,
    },
    loadingClass: {
      type: String,
      required: true,
    },
    unavailableClass: {
      type: String,
      required: false,
      default: '',
    },
  },
  data() {
    return { loading: false }
  },
  computed: {
    downloadXHR() {
      return `${this.$config.public.downloadFileViaXhr}` === '1'
    },
    href() {
      if (!this.url) {
        return ''
      }

      const url = new URL(this.url, window.location.origin)
      // The API download endpoints set the name themselves; `dl` is only needed by
      // the file server in front of the media directory.
      if (!url.searchParams.has('dl')) {
        url.searchParams.set('dl', this.filename)
      }
      return url.toString()
    },
  },
  methods: {
    /**
     * Asks the server whether the download would work, without transferring the file.
     * The status code is enough to tell the cases apart, and a browser never exposes
     * a HEAD response body anyway.
     */
    async preflight() {
      const response = await fetch(this.href, {
        method: 'HEAD',
        cache: 'no-store',
      })

      if (!response.ok) {
        throw new DownloadError(response.status)
      }
    },
    async download() {
      // We are using fetch here to avoid extra header
      // as we need to add them to CORS later
      const response = await fetch(this.href, {
        // Needed to prevent chrome not sending the Origin header in the actual GET
        // request. Without this header S3 will not respond with will not respond with
        // the correct CORS headers
        cache: 'no-store',
      })

      if (!response.ok) {
        throw new DownloadError(response.status)
      }

      const blob = await response.blob()
      const data = window.URL.createObjectURL(blob)

      // Create temporary anchor element to trigger the download
      const a = document.createElement('a')
      a.style = 'display: none'
      a.href = data
      a.target = '_blank'
      a.download = this.filename
      document.body.appendChild(a)
      a.onclick = (e) => {
        // prevent modal/whatever closing
        e.stopPropagation()
      }
      a.click()

      setTimeout(function () {
        // Remove the element
        document.body.removeChild(a)
        // Release resource on after triggering the download
        window.URL.revokeObjectURL(data)
      }, 500)
    },
    /**
     * Hands the browser the checked link so it streams the file straight to disk,
     * instead of buffering an archive that can be gigabytes into a blob.
     */
    navigate() {
      const a = document.createElement('a')
      a.style = 'display: none'
      a.href = this.href
      a.download = this.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    },
    async onClick(event) {
      event.preventDefault()
      event.stopPropagation()

      if (!this.url || this.loading) {
        return
      }

      this.loading = true
      try {
        await this.preflight()

        if (this.downloadXHR) {
          await this.download()
        } else {
          this.navigate()
        }
      } catch (error) {
        this.handleError(error)
      } finally {
        this.loading = false
      }
    },
    handleError(error) {
      if (this.onError) {
        this.onError(error)
        return
      }

      const { title, message } = downloadErrorMessage(this, error)
      this.$store.dispatch('toast/error', { title, message })
    },
  },
}

/**
 * A download that the server refused. The status is what tells the cases apart: the
 * download endpoints answer 410 for a file that aged out and 5xx for a server that
 * lost or cannot reach its own file storage.
 */
export class DownloadError extends Error {
  constructor(status) {
    super(`The download failed with status ${status}.`)
    this.name = 'DownloadError'
    this.status = status
  }
}

/**
 * Turns a failed download into something the reader can act on. A file the server
 * lost is never reported as missing: that is a misconfigured instance, and saying so
 * is the difference between a user retrying forever and an administrator fixing it.
 */
export function downloadErrorMessage(component, error) {
  const status = error instanceof DownloadError ? error.status : null

  if (status === 410) {
    return {
      title: component.$t('downloadLink.expiredTitle'),
      message: component.$t('downloadLink.expiredMessage'),
    }
  }

  if (status === 500 || status === 503) {
    return {
      title: component.$t('downloadLink.storageTitle'),
      message: component.$t('downloadLink.storageMessage'),
    }
  }

  if (status === 401 || status === 403) {
    return {
      title: component.$t('downloadLink.linkExpiredTitle'),
      message: component.$t('downloadLink.linkExpiredMessage'),
    }
  }

  return {
    title: component.$t('downloadLink.failedTitle'),
    message: component.$t('downloadLink.failedMessage'),
  }
}
</script>
