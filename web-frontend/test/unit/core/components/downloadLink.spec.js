import { flushPromises } from '@vue/test-utils'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import DownloadLink from '@baserow/modules/core/components/DownloadLink'
import { readFileSync } from 'node:fs'

/**
 * The point of these: a download that cannot work must say why. Before the preflight
 * a plain link rendered the server's error page where the file should have been, and
 * the XHR path saved the error body under the file's own name.
 */
describe('DownloadLink', () => {
  let wrapper = null
  let originalFetch = null

  const mountLink = (props = {}) =>
    mountSuspended(DownloadLink, {
      props: {
        url: 'http://localhost:8000/api/database/export/1/download/?token=abc',
        filename: 'my export.csv',
        loadingClass: 'button--loading',
        ...props,
      },
      slots: { default: 'Download' },
    })

  const respondWith = (status) => {
    global.fetch = vi.fn().mockResolvedValue({ ok: status === 200, status })
  }

  beforeEach(() => {
    originalFetch = global.fetch
    // jsdom does not implement navigation, and the component creates a temporary
    // anchor to start the download.
    HTMLAnchorElement.prototype.click = vi.fn()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  test('renders plain text instead of a link when there is no file yet', async () => {
    wrapper = await mountLink({ url: null })

    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.text()).toContain('Download')
  })

  test('keeps the download name in the query string', async () => {
    wrapper = await mountLink()

    expect(wrapper.vm.href).toContain('dl=my+export.csv')
    expect(wrapper.vm.href).toContain('token=abc')
  })

  test('navigates once the preflight passes', async () => {
    respondWith(200)
    wrapper = await mountLink()

    await wrapper.find('a').trigger('click')
    await flushPromises()

    expect(global.fetch).toHaveBeenCalledWith(
      wrapper.vm.href,
      expect.objectContaining({ method: 'HEAD' })
    )
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled()
  })

  test('a file that aged out is reported as expired', async () => {
    respondWith(410)
    const onError = vi.fn()
    wrapper = await mountLink({ onError })

    await wrapper.find('a').trigger('click')
    await flushPromises()

    expect(onError).toHaveBeenCalled()
    expect(onError.mock.calls[0][0].status).toBe(410)
    // The browser must not be sent to an error page.
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })

  test.each([
    [500, 'downloadLink.storageTitle'],
    [503, 'downloadLink.storageTitle'],
    [401, 'downloadLink.linkExpiredTitle'],
    [403, 'downloadLink.linkExpiredTitle'],
    [418, 'downloadLink.failedTitle'],
  ])('a %i is shown as %s', async (status, expectedTitleKey) => {
    respondWith(status)
    wrapper = await mountLink()
    const dispatch = vi.spyOn(wrapper.vm.$store, 'dispatch').mockResolvedValue()

    await wrapper.find('a').trigger('click')
    await flushPromises()

    // `$t` yields the key in this harness, which is what pins the mapping.
    expect(dispatch).toHaveBeenCalledWith(
      'toast/error',
      expect.objectContaining({ title: expectedTitleKey })
    )
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })

  test('the storage message blames the server, not the missing file', () => {
    // Read from disk: the i18n plugin compiles a plain json import into message
    // functions, and this asserts on the copy itself.
    const en = JSON.parse(readFileSync('modules/core/locales/en.json', 'utf8'))
    const { storageMessage, storageTitle } = en.downloadLink

    // The whole point of the change: a file the server lost is a server side
    // problem and must never read as "file not found".
    expect(storageTitle.toLowerCase()).not.toContain('not found')
    expect(storageMessage.toLowerCase()).not.toContain('not found')
    expect(storageMessage).toContain('administrator')
    expect(storageMessage).toContain('file storage')
  })
})
