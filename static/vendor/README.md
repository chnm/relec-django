# Vendored JavaScript libraries

Local copies of the third-party libraries the site's pages load, so published
visualizations don't depend on a CDN staying up or serving the same file.
Templates reference them with `{% static 'vendor/...' %}`.

| Directory | Version | Files | Source |
|---|---|---|---|
| `d3-7.9.2/` | 7.9.2 | `d3.min.js` (global `d3`), `d3.esm.min.js` (ES module) | npm `d3`; the ES module is bundled, see below |
| `plot-0.6.19/` | 0.6.19 | `plot.min.js` (ES module; imports `"d3"`) | npm `@observablehq/plot`, `dist/plot.min.js` |
| `leaflet-1.9.4/` | 1.9.4 | `leaflet.js`, `leaflet.css`, `leaflet-src.esm.js`, `images/` | npm `leaflet`, `dist/` |
| `leaflet.markercluster-1.4.1/` | 1.4.1 | `leaflet.markercluster.js`, two CSS files | npm `leaflet.markercluster`, `dist/` |
| `chart.js-4.4.7/` | 4.4.7 | `chart.umd.js` | npm `chart.js`, `dist/` |

Every file is an unmodified copy from the npm package except `d3.esm.min.js`.
npm's `d3` has no self-contained ES module, so that one is bundled with esbuild.
Each directory keeps the library's license file.

`plot.min.js` imports the bare name `"d3"`, so any page that loads Plot needs
both entries in its import map (see `templates/pages/blog_detail.html`).

## Updating a library

Work in a temporary directory, not in this repository:

```bash
npm install --legacy-peer-deps --ignore-scripts d3@X.Y.Z @observablehq/plot@X.Y.Z leaflet@X.Y.Z leaflet.markercluster@X.Y.Z chart.js@X.Y.Z esbuild
npx esbuild d3 --bundle --format=esm --minify --outfile=d3.esm.min.js
```

Then:

1. Copy the files listed above into a new `name-version/` directory here.
2. Replace the old directory name in `templates/` (`grep -rn "vendor/name-" templates docs`).
3. For Leaflet, update the `integrity` hashes beside its tags:
   `openssl dgst -sha256 -binary leaflet.js | base64`.
4. Delete the old directory and update the table above.

The version is in the directory name so that browsers fetch the new file
instead of a cached old one.
