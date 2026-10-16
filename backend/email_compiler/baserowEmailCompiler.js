'use strict'

const mjml2html = require('mjml')
const fs = require('fs')
const { Eta } = require('eta')
const path = require('path')
const { globSync } = require('glob')
const chokidar = require('chokidar')

const BASEROW_BACKEND_SRC_DIR = path.join(__dirname, '..', 'src')
const MJML_FILE_SEARCH_ROOT = process.env.MJML_FILE_SEARCH_ROOT
  ? process.env.MJML_FILE_SEARCH_ROOT
  : BASEROW_BACKEND_SRC_DIR
const MJML_ETA_SUFFIX = '.mjml.eta'
const ETA_LAYOUT_SUFFIX = '.layout.eta'
// glob patterns always use forward slashes, even on Windows.
const MJML_ETA_FILE_GLOB = `${MJML_FILE_SEARCH_ROOT.split(path.sep).join('/')}/**/*${MJML_ETA_SUFFIX}`

/**
 * Given a .mjml.eta file first renders the eta template to get a .mjml file and then
 * renders the mjml file to a normal html django template file.
 *
 * @param mjmlEtaFile The path to the .mjml.eta file.
 */
async function compileEtaAndMjml(mjmlEtaFile) {
  const Reset = '\x1B[0m'
  const FgGreen = '\x1B[32m'

  console.log(`Compiling ${mjmlEtaFile}`)
  // Eta only resolves templates inside `views`, and resolves relative
  // layout(path) statements against the calling template's own path. Rendering
  // the file by name (not as a string) under the search root lets templates
  // use layouts from parent directories, e.g. layout('../base.layout.eta').
  const eta = new Eta({ views: MJML_FILE_SEARCH_ROOT, cache: false })

  const relativeName = path.relative(MJML_FILE_SEARCH_ROOT, mjmlEtaFile)
  const mjmlText = eta.render(`./${relativeName}`, {})

  const { html } = await mjml2html(mjmlText, {
    validationLevel: 'strict',
    beautify: true,
  })

  const targetHtmlFile = mjmlEtaFile.replace(MJML_ETA_SUFFIX, '.html')
  console.log(
    `${FgGreen}Writing compiled email template to ${targetHtmlFile}${Reset}`
  )
  fs.writeFileSync(targetHtmlFile, html)
}

async function compileAll() {
  for (const file of globSync(MJML_ETA_FILE_GLOB).sort()) {
    await compileEtaAndMjml(file)
  }
}

/**
 * Compiles every *.mjml.eta file once, and in watch mode keeps recompiling on
 * changes to *.mjml.eta and *.layout.eta files.
 *
 * We use the simple javascript eta templating engine to first extend any base layout
 * files as MJML does not come with any built in templating. Secondly we use MJML to
 * convert the MJML files into html ready to be used as a Django template.
 *
 * @param args If command line arg is watch then continually watches the files,
 * otherwise just runs templating/compiling once over matching files and exits.
 */
async function main(args) {
  const watchMode = args.length > 0 && args[0] === 'watch'

  await compileAll()

  if (watchMode) {
    console.log(
      `Watching and recompiling *${MJML_ETA_SUFFIX} and *${ETA_LAYOUT_SUFFIX}` +
        ` files under ${MJML_FILE_SEARCH_ROOT}`
    )
    // chokidar no longer supports globs: watch the root and filter by suffix.
    chokidar
      .watch(MJML_FILE_SEARCH_ROOT, {
        ignoreInitial: true,
        ignored: (file, stats) =>
          stats?.isFile() &&
          !file.endsWith(MJML_ETA_SUFFIX) &&
          !file.endsWith(ETA_LAYOUT_SUFFIX),
      })
      .on('all', async (event, file) => {
        if (event !== 'add' && event !== 'change') return
        if (file.endsWith(ETA_LAYOUT_SUFFIX)) {
          console.log(`Layout file changed (${file})`)
          await compileAll()
        } else {
          await compileEtaAndMjml(file)
        }
      })
  }
}

main(process.argv.slice(2)).catch((error) => {
  console.error(error)
  process.exit(1)
})
