# Data Visualization Guide for Agent-Built Work

> **Draft for issue #231.** Hand this file to an agent along with your request.
> Part 1 applies to any RRCHNM project. Part 2 is specific to the Religious Ecologies API. Part 3 is a prompt template.
> File paths in this guide are in the `relec-django` repository. An agent working elsewhere can't read them, so everything it needs is written out here.

---

## Part 1: House style (all projects)

### Default stack

Use these unless the request names something else. They match what our sites already load, so an agent's output can drop into a page without a build step.

| Need | Library | On the site (`static/vendor/`) | Outside the site (exact-version CDN) |
|---|---|---|---|
| Charts (bar, line, dot, area, small multiples) | Observable Plot 0.6.19 | `plot-0.6.19/plot.min.js` | `https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.19/+esm` |
| Data wrangling, scales, custom SVG, anything Plot can't do | D3 7.9.2 | `d3-7.9.2/d3.esm.min.js` | `https://cdn.jsdelivr.net/npm/d3@7.9.2/+esm` |
| Interactive point maps | Leaflet 1.9.4 (+ `leaflet.markercluster` 1.4.1 for dense points) | `leaflet-1.9.4/`, `leaflet.markercluster-1.4.1/` | `https://unpkg.com/leaflet@1.9.4/dist/` |
| Static choropleths and thematic maps | Observable Plot `geo` mark, or D3 `geoPath` | as above | as above |

- **Published work loads local copies.** Anything that ships on religiousecologies.org loads its libraries from `static/vendor/` in `relec-django`, never from a CDN, so a chart keeps working when a CDN changes or disappears. `static/vendor/README.md` lists the versions and how to update them.
- **Plain ES modules, no bundler.** Resolve bare imports with an import map in the page (the Religious Ecologies blog template already includes this one). Always include the `"d3"` entry: Plot's module imports it.

  ```html
  {% load static %}
  <script type="importmap">
  { "imports": {
      "@observablehq/plot": "{% static 'vendor/plot-0.6.19/plot.min.js' %}",
      "d3": "{% static 'vendor/d3-7.9.2/d3.esm.min.js' %}"
  } }
  </script>
  ```
- **Outside the site** (a stand-alone page, a notebook, a prototype), a CDN is fine if the URL names the exact version, as in the last column. Never use a range (`@7`, `@0.6`) or `latest`: the CDN then serves whatever is newest, and the chart can change without anyone touching it.
- **Reach for Plot first.** Drop to raw D3 only for layouts Plot lacks (force, hierarchy, custom interaction). Don't add a new charting library (Chart.js, Vega, Highcharts) without asking.
- **Exploratory work** (not for the website) can use whatever the analyst prefers: Python (pandas + Altair or matplotlib) or R (tidyverse + ggplot2). The design and data rules below still apply.

### Design rules

1. **One chart, one question.** The title states the finding or the question ("Methodists outnumbered Baptists in most Ohio counties"), not the field names ("membership by denomination").
2. **Label everything a reader needs:** axis titles with units, a direct label or legend for every color, and a caption naming the source, the year and any filters (e.g. "approved schedules only").
3. **Honest scales.** Bar and area charts start at zero. If you use a log scale, say so in the axis title. Don't truncate axes to exaggerate a difference.
4. **Color with purpose.**
   - Project accent: `#0060b1` (Religious Ecologies blue). Use it for the single series or the highlighted item.
   - Categories: Plot's built-in `observable10` or `tableau10` scheme, at most about 8 categories. Group the rest as "Other".
   - Continuous values: a sequential scheme (`blues`, `viridis`). Use a diverging scheme only when there's a meaningful midpoint.
   - Never use color as the only cue. Pair it with labels, position or shape.
5. **Normalize when comparing places.** Raw counts mostly track population. For maps and cross-place comparisons, use rates or shares (members per 1,000 residents, share of congregations) unless the point is raw size.
6. **Responsive sizing.** Read the container width (`el.clientWidth`) and derive height from it. Don't hard-code a pixel width wider than about 800.
7. **Tooltips add detail; they don't replace labels.** Plot's `tip: true` is fine. Anything essential must be visible without hovering.

### Accessibility

- Wrap each chart in `<figure>` with a `<figcaption>`.
- Give the SVG or canvas `role="img"` and an `aria-label` that states the takeaway. In Plot, pass the `ariaLabel` option, which always lands on the chart's SVG. `Plot.plot` returns a `<figure>` wrapper instead of an SVG when a legend, title or caption is set, so set `role` on the chart SVG inside it, not on the wrapper.
- Provide a text alternative for the data: a `<details>` element holding a small table or list.
- Check contrast in both light and dark page themes. Don't rely on Plot's default black text on a dark background.

### Historical-data rules

These matter more than visual polish.

- **Blank is not zero.** A null means the form left the field blank or it was illegible. Drop or flag nulls; never coerce them to 0 in sums or averages. Report how many records were excluded.
- **Use period boundaries.** County and state lines changed. Map 1926 data onto 1926 boundaries (AHCB, below), never modern shapefiles.
- **Say what's in the sample.** Transcription is ongoing. A chart built from partial data must say so ("N of M schedules transcribed as of DATE").
- **Use the source's categories.** Show denominations and families as the data names them. Don't merge or rename categories without saying so in the caption.
- **Cite the dataset and the date you pulled it** in the caption or notes.

### Code shape for a web visualization

One module per chart, with the target element ID as a constant. Fetch or import the data, build the chart, then append it. Handle loading and failure visibly.

```javascript
import * as Plot from "@observablehq/plot";

const TARGET = "membership-by-family"; // matches <div id="..."> in the page
const el = document.getElementById(TARGET);
el.textContent = "Loading…";

try {
  const rows = await loadRows(); // see Part 2 for fetching from the API
  const width = el.clientWidth || 640;
  const chart = Plot.plot({
    width,
    height: Math.round(width * 0.6),
    marginLeft: 120,
    ariaLabel: "Total 1926 membership by denominational family",
    x: { label: "Members →", grid: true },
    y: { label: null },
    marks: [
      Plot.barX(rows, Plot.groupY({ x: "sum" }, { y: "family", x: "members", fill: "#0060b1", sort: { y: "-x" }, tip: true })),
      Plot.ruleX([0]),
    ],
  });
  chart.setAttribute("role", "img"); // chart is the SVG here: no legend, title or caption
  el.replaceChildren(chart);
} catch (err) {
  el.textContent = "This chart could not load its data.";
  console.error(err);
}
```

For blog posts on religiousecologies.org, work in the `relec-django` repository and follow its `docs/INTERACTIVE_VISUALIZATIONS.md` for file locations and the `<figure class="viz-interactive">` markup.

---

## Part 2: Religious Ecologies data sources

### Which source to use

| Goal | Source |
|---|---|
| Congregation-level records (one row per church), filtered subsets, maps | **Religious Ecologies API**: `https://religiousecologies.org/census/api/` |
| City-level membership totals by denomination | **RRCHNM data API**: `https://data.chnm.org/relcensus/city-membership?year=1926` (optionally `&denomination=` or `&denominationFamily=`) |
| Historical boundaries for maps | **AHCB on the data API**: states `https://data.chnm.org/ahcb/states/1926-07-04/`, counties `https://data.chnm.org/ahcb/counties/1926-05-08/state-code/<xx>/` |
| A full national dataset for offline analysis | Ask a developer for the CSV export (`manage.py export_congregations_csv`). Don't page through the whole API. |

The API sends CORS headers for `/census/api/*`, so browser code on any origin can call it. It's read-only and needs no key.

### Endpoints

Interactive docs: `https://religiousecologies.org/census/api/docs/`. The API root (`/census/api/`) lists every endpoint, filter and example.

- `GET /census/api/religious-bodies/`: congregations (paginated).
- `GET /census/api/religious-bodies/{id}/`: one congregation.
- `GET /census/api/religious-bodies/denomination_families/`: families with counts.
- `GET /census/api/denominations/`: the denomination list (`family_census`,
  `family_relec`, `search`).
- `GET /census/api/denominations/families/`: distinct census and RelEc families.
- `GET /census/api/denominations/by_family/?family_relec=Adventist`

### `religious-bodies` filters

| Parameter | Meaning |
|---|---|
| `denomination` | Denomination ID (integer) |
| `family_census` / `family_relec` | Family name (census or RelEc taxonomy) |
| `exclude_families` | Comma-separated census families to exclude |
| `transcription_status` | `approved` returns verified records only. **Use it by default** (see the field notes). |
| `urban_rural` | `urban` or `rural` |
| `bounds` | `south,west,north,east` bounding box |
| `has_location` | `true` / `false`: has a populated place with coordinates |
| `corrected` | `true` / `false`: the latest review saved a person's correction |
| `search` | Name, address, or census code |
| `ordering` | `name` or `census_record__schedule_id` (prefix `-` to reverse) |
| `view` | `map`: a smaller response. Despite the name, use it for any chart that doesn't need pastors or raw transcriptions. |
| `page`, `page_size` | Default 100, maximum 5000 |

### Response shape

```json
{
  "count": 1234,
  "denominations": ["Methodist Episcopal Church", "..."],
  "next": "https://…/religious-bodies/?page=2…",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "First Methodist Episcopal Church",
      "census_code": "2-7",
      "division": "…",
      "schedule_id": "1",
      "has_location": true,
      "location_details": {
        "lat": 39.1, "lon": -84.5,
        "city_name": "…", "map_name": "…", "place_id": 123,
        "county_name": "…", "county_ahcb": "mes_androscoggin", "state_name": "ME",
        "address": "…", "urban_rural_code": "U"
      },
      "denomination_details": {
        "id": 7, "denomination_id": "…", "name": "…",
        "family_census": "…", "family_relec": "…"
      },
      "membership_details": {
        "male_members": 120, "female_members": 180, "total_members": 300,
        "members_under_13": 40, "members_13_and_older": 260, "total_by_age": 300,
        "sunday_school_num_scholars": 95
      },
      "num_edifices": 1,
      "has_pastors_residence": true,
      "finances": {
        "expenditures": 4200.0, "benevolences": 600.0, "total_expenditures": 4800.0,
        "edifice_value": 25000.0, "edifice_debt": 0.0,
        "residence_value": 6000.0, "residence_debt": null
      },
      "urls": { "self": "https://…/census/record/123/", "image": "https://…" }
    }
  ]
}
```

The full (non-`map`) response also includes `pastors`, `num_assistant_pastors`, `respondent`, `processing`, `marginalia`, `transcriptions`, and `reconciliation`. Only request them if the chart needs them. `transcriptions` in particular holds raw transcription output, which is large and rarely useful for charts.

The values above are illustrative. Fetch one record with `?page_size=1` to see real ones before writing parsing code.

### Field notes that trip people up

- **`membership_details` can be null** (not transcribed yet), and so can any field inside it. `null` means blank on the form, not zero.
- **`total_members` vs `total_by_age`**: two totals from different form questions. They don't always agree. Pick one and say which in the caption.
- **`urban_rural_code`** is `U`, `R`, or `null`. A `U+` value (a `U` written with a plus) is being added; treat it as urban unless the analysis is about the plus. The `urban_rural=urban` filter returns both. Many records have no code at all.
- **Location is the populated place, not the street address.** `lat`/`lon` are the town's coordinates, so many congregations share a point. Cluster or aggregate; don't jitter points to imply street-level precision.
- **`county_ahcb`** is the key that joins to AHCB county boundaries. **`state_name`** holds the two-letter state code (`"ME"`), not the full name.
- **`schedule_id` is a string and is not unique.** Many records share the same value. Use `id` as the record key. `urls.self` links to the record's public page and `urls.image` to the scanned schedule.
- **Two family taxonomies.** `family_census` is the Census Bureau's 1926 grouping; `family_relec` is the project's own. Say which one a chart uses.
- **Family filters can return rows whose `denomination_details` say otherwise.** `family_census` and `family_relec` match on either the congregation's denomination or the denomination printed on its schedule, but the response shows only the first. When you filter by family, label the rows with the family you asked for; don't regroup them by `denomination_details`, which can be null or name another family.
- **Transcription status.** Default to `transcription_status=approved`. As of November 2026 about 12,000 of 228,000 records are approved, and most of the rest are untranscribed stubs with a null name and null membership and finances. Query without the filter only to get the denominator: the two `count` values give "N of M records transcribed" for the caption.
- **Responses are cached for up to an hour**, so a newly approved record may not appear straight away.

### Fetching responsibly

The API is shared with the public site and runs on modest resources.

- Start every new query with `page_size=10` to check the shape and `count`.
- Filter on the server (family, state bounds, status) rather than downloading everything and filtering in the browser.
- Use `view=map` for charts as well as maps. It leaves out the heaviest fields.
- Use a `page_size` of 1000 or less and fetch pages one at a time. Don't fire them in parallel.
- For a published page, don't page through the API on every visit. Save the rows to a static `*.data.js` or JSON file and load that.

```javascript
const API = "https://religiousecologies.org/census/api/religious-bodies/";

async function fetchAll(params) {
  let url = `${API}?${new URLSearchParams({ page_size: 1000, ...params })}`;
  const rows = [];
  while (url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
    const page = await res.json();
    rows.push(...page.results);
    url = page.next; // sequential on purpose
  }
  return rows;
}

// Example: approved Lutheran congregations, flattened for Plot
const rows = (await fetchAll({ family_relec: "Lutheran", transcription_status: "approved", view: "map" }))
  .filter((d) => d.membership_details?.total_members != null)
  .map((d) => ({
    name: d.name,
    denomination: d.denomination_details?.name,
    state: d.location_details?.state_name,
    county: d.location_details?.county_ahcb,
    lat: d.location_details?.lat,
    lon: d.location_details?.lon,
    members: d.membership_details.total_members,
  }));
```

### Joining to county boundaries

1. Fetch the AHCB counties GeoJSON for the state and date you need.
2. Aggregate congregations by `location_details.county_ahcb`.
3. Join on the feature's top-level `id` (e.g. `"ohs_medina"`), not a `properties` field. It matches `county_ahcb` (e.g. `"mes_androscoggin"`). `properties` holds `name` (upper case), `state_terr`, `state_code` and `area_sqmi`; use `area_sqmi` for density.
4. Draw with `Plot.geo` (choropleth) or a Leaflet `L.geoJSON` layer.
5. Report counties with no matching congregations as "no data", not 0.

```javascript
const counties = await (await fetch("https://data.chnm.org/ahcb/counties/1926-05-08/state-code/oh/")).json();
const byCounty = d3.rollup(rows, (v) => d3.sum(v, (d) => d.members), (d) => d.county);
// Density, not raw totals (design rule 5). Counties with no congregations stay undefined: "no data".
const density = (f) => (byCounty.has(f.id) ? byCounty.get(f.id) / f.properties.area_sqmi : undefined);
const plot = Plot.plot({
  projection: { type: "albers-usa", domain: counties },
  ariaLabel: "Lutheran members per square mile by Ohio county, 1926",
  color: { scheme: "blues", legend: true, label: "Members per square mile", unknown: "#ddd" },
  marks: [Plot.geo(counties, { fill: density, stroke: "white", tip: true, title: (f) => f.properties.name })],
});
```

### City-level aggregates

`https://data.chnm.org/relcensus/city-membership?year=1926&denominationFamily=Lutheran`
returns one row per city and group:
`{year, group, city, state, denominations, churches, members, population_1926, lon, lat}`.
`population_1926` makes per-capita rates easy. Prefer this over aggregating
congregation records yourself whenever city totals are enough.

---

## Part 3: Prompt template

Copy this, fill in the brackets, and give it to the agent along with this file.

```text
Follow the attached data visualization guide (docs/DATA_VIZ_GUIDE.md in relec-django).

Goal: [the question the chart should answer, in one sentence]
Audience and destination: [blog post on religiousecologies.org / slide / exploratory notebook / stand-alone data visualization]
Data: [filters, e.g. family_relec=Baptist, transcription_status=approved, state bounds]
Chart: [your idea, or "recommend one"]
Constraints: [size, must work on mobile, static image needed, etc.]

Before writing chart code:
1. Fetch one page with page_size=10 and report the count and the fields you plan to use.
2. Say how you'll handle null values and which membership total you'll use.
3. Propose the chart type and title, then wait for my OK. Flag it if the count is over 20,000.

Deliver: the module file(s), the <figure> HTML, the caption text (with source,
date pulled and filters), and a note listing how many records were excluded and why.
```

### Review checklist

- [ ] The title states the finding or question.
- [ ] Axes, units, legend and caption are present; the caption names the source, the date pulled and the filters.
- [ ] Nulls are excluded (not zeroed), and the count of excluded records is reported.
- [ ] Places are compared with rates or shares, unless raw size is the point.
- [ ] 1926 AHCB boundaries are used for maps.
- [ ] Libraries load from `static/vendor/` on the site, or from an exact-version CDN URL elsewhere; there's no new dependency without sign-off.
- [ ] The API was queried with filters, sequential pages and `page_size` ≤ 1000.
- [ ] Only approved records are charted, or the caption says otherwise.
- [ ] `role="img"`, an `aria-label` and a text fallback are present; it was checked in light and dark themes.
- [ ] It works at phone width.

