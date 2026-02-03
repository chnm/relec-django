# Adding Interactive Visualizations to Blog Posts

This guide explains how to add interactive visualizations using Observable Plot to blog posts.

## Overview

Interactive visualizations use [Observable Plot](https://observablehq.com/plot/) for data visualization and are embedded directly in blog posts. The system uses ES6 modules with import maps to load Plot.js from CDN.

## Creating a New Interactive Visualization

### Step 1: Create Your Data File

Export your data as an ES6 module in `/static/viz/<project-name>/`:

```javascript
// /static/viz/my-project/my-data.data.js
export default [
  { year: 1926, city: "New York", population: 6000000 },
  { year: 1926, city: "Chicago", population: 3000000 },
  // ... more data
];
```

### Step 2: Create a Wrapper Visualization Script

Create a wrapper script that:
1. Imports Observable Plot
2. Imports your data
3. Has the target div ID **hardcoded**
4. Creates and appends the visualization

```javascript
// /static/viz/my-project/my-visualization-wrapper.js

import * as Plot from "@observablehq/plot";
import myData from "./my-data.data.js";

// IMPORTANT: Hardcode the div ID that matches your figure
const targetId = "my-unique-viz-id";

const width = 800;

// Create your Plot visualization
let myPlot = Plot.plot({
  width: width,
  height: 0.5 * width,
  x: { label: "Year" },
  y: { label: "Population" },
  marks: [
    Plot.dot(myData, {
      x: "year",
      y: "population",
      stroke: "blue",
      title: (d) => `${d.city}: ${d.population.toLocaleString()}`,
    }),
  ],
});

// Append to the target div
document.getElementById(targetId).appendChild(myPlot);
```

**Key Points:**
- The `targetId` must match the div ID you'll use in the HTML
- Use `@observablehq/plot` - this resolves via import map in the page template
- Relative imports (like `./my-data.data.js`) work fine in wrapper scripts

### Step 3: Add the Figure to Your Blog Post

In the Django admin, add the HTML figure to your blog post content:

```html
<figure class="viz-interactive">
  <h3>My Visualization Title</h3>
  <div id="my-unique-viz-id" class="viz-container"></div>
  <script type="module" src="/static/viz/my-project/my-visualization-wrapper.js"></script>
  <figcaption>Figure 1. Description of what this visualization shows...</figcaption>
</figure>
```

**Key Points:**
- The `div id` must match the `targetId` in your wrapper script
- Use descriptive, unique IDs (e.g., `denominational-diversity`, not just `viz1`)
- The script `src` path should point to your wrapper script
- Include a meaningful caption

## Multiple Visualizations on One Page

Each visualization needs:
1. A unique div ID
2. Its own wrapper script with that ID hardcoded
3. Its own data file (or they can share data files)

Example:

```html
<!-- First visualization -->
<figure class="viz-interactive">
  <h3>Population Growth</h3>
  <div id="population-growth" class="viz-container"></div>
  <script type="module" src="/static/viz/cities/population-wrapper.js"></script>
  <figcaption>Figure 1. Population growth over time.</figcaption>
</figure>

<!-- Second visualization -->
<figure class="viz-interactive">
  <h3>Religious Diversity</h3>
  <div id="religious-diversity" class="viz-container"></div>
  <script type="module" src="/static/viz/cities/diversity-wrapper.js"></script>
  <figcaption>Figure 2. Religious diversity by city.</figcaption>
</figure>
```

## File Organization

```
static/viz/
├── <project-name>/
│   ├── <data-name>.data.js          # Data exported as ES6 module
│   ├── <viz-name>-wrapper.js        # Wrapper with hardcoded div ID
│   └── <viz-name2>-wrapper.js       # Another visualization
```

## Migrating from Hugo Shortcodes

If you have old Hugo posts with `{{< fig-interactive >}}` shortcodes:

1. The shortcode converter will attempt to convert them automatically
2. However, you'll need to create wrapper scripts manually for each visualization
3. Update the generated HTML to use your wrapper script

Example Hugo shortcode:
```
{{< fig-interactive id="denominational-diversity"
    script="viz/cities-overview/denominational-diversity.js"
    caption="Figure 1. Description..."
    title="Visualization Title" >}}
```

Becomes:
```html
<figure class="viz-interactive">
  <h3>Visualization Title</h3>
  <div id="denominational-diversity" class="viz-container"></div>
  <script type="module" src="/static/viz/cities-overview/denominational-diversity-wrapper.js"></script>
  <figcaption>Figure 1. Description...</figcaption>
</figure>
```

## Styling

The blog template includes default styling for `.viz-interactive` figures:
- Light gray background
- Rounded borders
- Proper spacing and padding
- Centered titles
- Consistent caption formatting

## Observable Plot Resources

- [Observable Plot Documentation](https://observablehq.com/plot/)
- [Plot Examples Gallery](https://observablehq.com/@observablehq/plot-gallery)
- [Observable Plot on GitHub](https://github.com/observablehq/plot)

## Troubleshooting

### Visualization doesn't appear
- Check browser console for errors
- Verify the div ID matches between HTML and wrapper script
- Ensure static files are being served correctly
- Check that the script path is correct

### "Failed to resolve module" error
- Make sure you're using `@observablehq/plot` (not a local path)
- Check that relative imports use `./` prefix
- Verify data files are in the correct location

### Wrong visualization appears in div
- Each wrapper script must have a unique `targetId`
- Double-check your div IDs don't conflict
- Make sure each visualization has its own wrapper script

## Example: Complete Visualization

Here's a complete working example:

**Data file:** `/static/viz/example/cities.data.js`
```javascript
export default [
  { city: "New York", population: 6000000, denominations: 85 },
  { city: "Chicago", population: 3000000, denominations: 72 },
  { city: "Los Angeles", population: 1200000, denominations: 45 },
];
```

**Wrapper:** `/static/viz/example/cities-scatter-wrapper.js`
```javascript
import * as Plot from "@observablehq/plot";
import cities from "./cities.data.js";

const targetId = "cities-scatter";
const width = 800;

let plot = Plot.plot({
  width: width,
  height: 0.5 * width,
  x: { type: "log", label: "Population", tickFormat: "~s" },
  y: { label: "Number of Denominations" },
  grid: true,
  marks: [
    Plot.dot(cities, {
      x: "population",
      y: "denominations",
      stroke: "steelblue",
      title: (d) => d.city,
    }),
  ],
});

document.getElementById(targetId).appendChild(plot);
```

**HTML in blog post:**
```html
<figure class="viz-interactive">
  <h3>Religious Diversity vs. City Size</h3>
  <div id="cities-scatter" class="viz-container"></div>
  <script type="module" src="/static/viz/example/cities-scatter-wrapper.js"></script>
  <figcaption>
    Figure 1. This scatter plot shows the relationship between city population
    and the number of distinct religious denominations counted in 1926.
  </figcaption>
</figure>
```

## Summary Checklist

When adding a new interactive visualization:

- [ ] Create data file as ES6 module export
- [ ] Create wrapper script with hardcoded target ID
- [ ] Import `@observablehq/plot` in wrapper
- [ ] Use unique, descriptive div ID
- [ ] Add HTML figure to blog post content
- [ ] Match div ID in HTML with targetId in wrapper
- [ ] Test visualization in browser
- [ ] Check browser console for any errors
