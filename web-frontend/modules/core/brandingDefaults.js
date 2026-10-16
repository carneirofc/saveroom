/**
 * What the runtime branding falls back to when nothing is configured.
 *
 * Lives outside server/branding/ because both sides need it: the Nitro
 * handlers resolve the operator's values against it, and the client plugin
 * falls back to it when the branding config could not be fetched. Keep this
 * module free of node builtins so it can be bundled for the browser.
 */
export const BRANDING_DEFAULTS = {
  appName: 'Saveroom',
  siteUrl: 'https://github.com/carneirofc/baserow',
  docsUrl: 'https://github.com/carneirofc/baserow',
  siteTitle: 'Saveroom',
  showAttribution: true,
}

/**
 * Where this software comes from, credited on the admin version panel. Unlike
 * the values above these are not branding: an operator who rebrands the
 * instance still runs this fork, so they cannot be overridden, only hidden
 * along with the rest of the attribution through `showAttribution`.
 */
export const PROJECT_CREDITS = {
  forkUrl: 'https://github.com/carneirofc/baserow',
  licenseUrl: 'https://github.com/carneirofc/baserow/blob/develop/LICENSE',
  upstreamUrl: 'https://baserow.io',
}
