# Branding

Operators can change the web-frontend's look without rebuilding the image:

- the app name in the browser title and the interface texts
- any color of the design palette
- the UI font
- the logo, favicons and built-in icons
- where the logo and the in-app help links point
- whether the attribution footer is shown at all
- translated texts
- additional CSS

The web-frontend server reads everything from a **branding directory** at
runtime. Nothing is required: with no directory, or an empty one, the built-in
defaults are used.

## The branding directory

The web-frontend reads the directory named by `BASEROW_BRANDING_DIR`, which
defaults to `/baserow/branding`. In the all-in-one image the default is
`$DATA_DIR/branding`, i.e. `/baserow/data/branding` on the data volume.

```
branding/
├── branding.json     app name, colors, font, translations, links
├── theme.css         extra CSS, loaded after the built-in styles
├── img/              logo and favicon overrides
│   ├── logo.svg          main logo (176×29)
│   ├── logoOnly.svg      square mark (30×30), used in notifications
│   ├── favicon_16.png
│   ├── favicon_32.png
│   ├── favicon_48.png
│   └── favicon_192.png
├── icons/            overrides for the built-in `baserow-icon-*` icons (24×24 SVG masks)
└── files/            any other assets referenced from theme.css, e.g. fonts
```

A copy of this layout lives in `deploy/branding-example/`.

Files in `img/` and `icons/` replace the built-in file with the same name; any
file you don't provide keeps its default. All assets are served from
`/_branding/assets/<folder>/<file>`. Allowed file types are svg, png, jpg,
webp, gif, ico, woff, woff2, ttf and otf.

### branding.json

```json
{
  "appName": "Acme Data",
  "colors": {
    "color-primary-500": "#0f766e",
    "palette-neutral-1200": "#1f2933"
  },
  "fontFamily": "'Brand Sans', sans-serif",
  "siteUrl": "https://acme.example",
  "docsUrl": "https://docs.acme.example",
  "siteTitle": "Acme Data",
  "showAttribution": true,
  "messages": {
    "en": { "some": { "translation": { "key": "Replacement text" } } }
  }
}
```

- **`appName`**: the product name, `Saveroom` by default. It is shown in the
  browser tab (`Page | Acme Data`) and wherever the interface names the
  product ("Welcome to Acme Data", "New to Acme Data?"): those translations
  link to the `app.name` key, which this value fills in every language. Max 64
  characters. The backend's emails and API docs only see the
  `BASEROW_BRANDING_APP_NAME` environment variable, not `branding.json`, so set
  the variable to rename those too.
- **`colors`**: overrides color tokens. Two kinds of names are accepted:
  - Palette tokens (`palette-<hue>-<step>`) are the raw scale. Hues are
    `neutral`, `blue`, `green`, `red`, `cyan`, `yellow`, `magenta` and
    `purple`. Overriding a palette token recolors everything built on it.
  - Semantic tokens (`color-<role>-<step>`) cover `primary`, `neutral`,
    `success`, `warning`, `error`, `yellow`, `purple`, `pink`, `brown` and
    `cyan`. Overriding one changes only that role.

  The complete list, with defaults, is in
  `web-frontend/modules/core/assets/scss/colors.scss`. To rebrand the primary
  color, override the whole `palette-blue-*` scale, or the `color-primary-*`
  tokens.

  Values must be CSS colors: hex, `rgb()`, `hsl()`, `oklch()` and similar, or
  named colors. Unknown tokens and invalid values are ignored with a warning in
  the web-frontend logs.
- **`fontFamily`**: a CSS `font-family` value for the whole UI. Load custom
  fonts with `@font-face` in `theme.css`.
- **`siteUrl`**: where the attribution logo links to — the sidebar footer, the
  header of a publicly shared view, and the "Powered by" block on public form
  views.
- **`docsUrl`**: where the in-app documentation and help links point: the
  dashboard resource cards, the automation docs button, the email tester, the
  role and element-visibility help links.

  Both must be `http(s)` URLs or root-relative paths (`/docs`). Anything else,
  `javascript:` above all, is ignored with a warning: these values go straight
  into a link.
- **`siteTitle`**: the `title` and `alt` text on the attribution logo. Falls
  back to `appName`, then to `Saveroom`. Max 160 characters.
- **`showAttribution`**: set to `false` to remove the attribution entirely —
  the sidebar footer logo, the shared-view header logo, the public form
  "Powered by" block and the fork and upstream credits on the admin version
  panel all stop rendering.
- **`messages`**: translation overrides per locale, using the same keys as
  `web-frontend/**/locales/<locale>.json`. The "Powered by" label is
  `formViewPoweredBy.poweredBy` in the database module.

### theme.css

Plain CSS that is loaded after the built-in styles and the generated color
variables, so it can override anything. Reference your own assets from
`files/`:

```css
@font-face {
  font-family: 'Brand Sans';
  src: url('/_branding/assets/files/fonts/BrandSans-Regular.woff2') format('woff2');
}

.logo img {
  height: 24px;
}
```

### Environment variables

These take precedence over `branding.json`, and empty values count as unset:

| Variable | Purpose |
| --- | --- |
| `BASEROW_BRANDING_DIR` | Branding directory path (default `/baserow/branding`). |
| `BASEROW_BRANDING_APP_NAME` | Overrides `appName`. Also read by the backend, for the name in emails and the API docs title; give it to the backend and Celery containers as well. |
| `BASEROW_BRANDING_COLORS` | JSON object merged over `colors`, e.g. `{"color-primary-500":"#0f766e"}`. |
| `BASEROW_BRANDING_SITE_URL` | Overrides `siteUrl`. |
| `BASEROW_BRANDING_DOCS_URL` | Overrides `docsUrl`. |
| `BASEROW_BRANDING_SITE_TITLE` | Overrides `siteTitle`. |
| `BASEROW_BRANDING_SHOW_ATTRIBUTION` | Overrides `showAttribution`; `true`/`false`. |

## Applying changes

No restart is needed. The server re-reads the directory at most every two
seconds, so a page reload picks up edits. Asset responses carry a one-minute
cache with an ETag.

## Deployment

### Docker Compose

Mount the directory read-only into the `web-frontend` service. The volume is
shown commented out in the root `docker-compose.yaml`:

```yaml
  web-frontend:
    volumes:
      - ./branding:/baserow/branding:ro
```

### All-in-one image

Put the files in `branding/` inside the data volume (`/baserow/data/branding`),
or mount a directory there.

### Helm

Set the `branding` values. The chart renders them into a ConfigMap mounted at
`/baserow/branding`:

```yaml
branding:
  appName: "Acme Data"
  colors:
    color-primary-500: "#0f766e"
  fontFamily: ""
  siteUrl: "https://acme.example"
  docsUrl: "https://docs.acme.example"
  siteTitle: "Acme Data"
  showAttribution: true
  messages: {}
  themeCss: |
    .logo img { height: 24px; }
  files:
    img/logo.svg: "<base64 of logo.svg>"
  faviconBase64: "<base64 of favicon.ico>"   # also served at /favicon.ico
```

A ConfigMap holds at most about 1 MiB. For larger asset sets, create a
PersistentVolumeClaim holding a complete branding directory and set
`branding.existingClaim`. The inline values are then ignored, except
`faviconBase64`.

## Scope and limits

- Plugins that register their own logo component
  (`getLogoComponent()`) still take precedence over `img/logo.svg`.
- A form view's own "show logo" setting still applies: `showAttribution` only
  ever hides the block further, it never forces it back on.
- Icons from the Iconoir icon font (`iconoir-*` classes) are font glyphs and
  cannot be swapped file by file; restyle or hide them with `theme.css`.
- Application Builder sites keep their per-application theme settings.
- Backend-rendered content, such as emails, is not affected.
