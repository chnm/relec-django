import * as d3 from "d3";
import DenominationsMap from "./cities-map-local";  // Use local API version
import { updateURL, getInitialState, setDropDowns } from "./urls";

// Use local Django API instead of external API
// API base URL is set by Django template
const API_BASE = window.RELEC_API_BASE || "/census/api/";

// Load the data from local Django endpoints
const urls = [
  `${API_BASE}denominations/`,
  `${API_BASE}religious-bodies/city_membership/?year=1926&denomination=Protestant+Episcopal+Church`,
  `${API_BASE}religious-bodies/city_membership/?year=1926`,
  `${API_BASE}religious-bodies/denomination_families/`,
  "https://data.chnm.org/ne/globe?location=North+America",  // Keep external (Natural Earth data)
  "https://data.chnm.org/ahcb/states/1926-07-04/",  // Keep external (AHCB state boundaries)
];
const promises = [];
urls.forEach((url) => promises.push(d3.json(url)));

// Once all the data is loaded, initialize and render the visualizations
Promise.all(promises)
  .then((data) => {
    // Transform denomination_families response to match expected format
    // Django returns: { census_families: [...], relec_families: [...] }
    // Code expects: { family_relec: [{name: ...}] }
    const transformedData = [
      data[0],  // denominations (already correct format)
      data[1],  // cityMembership for specific denomination
      data[2],  // cityMembership aggregate
      {
        family_census: data[3].census_families,
        family_relec: data[3].relec_families.map(f => ({ name: f.name }))
      },
      data[4],  // northamerica
      data[5],  // states
    ];

    setup(transformedData);
  })
  .catch((e) => {
    console.error(
      `There has been a problem with your fetch operation: ${e.message}`,
    );
    console.error('Stack:', e.stack);
  });

function setup(data) {
  const citiesMap = new DenominationsMap(
    "#chrono-map",
    {
      denominations: data[0],
      cityMembership: data[1],
      denominationAggregate: data[2],
      denominationFamilies: data[3],
      northamerica: data[4],
      states: data[5],
    },
    { width: 1000, height: 525 },
  );
  citiesMap.render();

  // Get initial state from the query params. We use this in the event that someone
  // shares a URL set to a specific state. If the URL is invalid, then we use the default
  // state.
  let initialState = getInitialState();
  if (initialState === null) {
    initialState = [1926, "All denominations", "Adventist", "Congregations"];
  }

  // We build the dropdown menus from the data and add event listeners to them
  // Add the options to the dropdowns
  const options = {
    year: [1926],  // Only 1926 data available currently
    denomination: ["All denominations", ...data[0].map((d) => d.short_name || d.name)],
    denominationFamily: [
      "All denomination families",
      ...data[3].family_relec.map((d) => d.name),
    ],
    countSelection: ["Congregations", "Members"],
  };

  // intitialState denomination (initialState[2]) needs to be filtered where a denomination is only displayed if it
  // is part of a denominationFamily. We do this by getting the selected denominationFamily
  // either from initialState, and then filtering the denomination array
  // to only include the denominations that are part of the selected denominationFamily. We need to
  // match exactly the denominationFamily with family_relec.name, so we use the indexOf method.
  const denominationFamily =
    initialState[2] === "All denomination families"
      ? "All denomination families"
      : data[3].family_relec.filter(
          (d) => d.name.indexOf(initialState[2]) !== -1,
        )[0]?.name || "All denomination families";
  console.log("denom family", denominationFamily);

  // Filter the denominations based on the denominationFamily
  let filteredDenominationOptions = [
    "All denominations",
    ...data[0].map((d) => d.short_name || d.name),
  ];
  if (denominationFamily !== "All denomination families") {
    filteredDenominationOptions = [
      "All denominations",
      ...data[0]
        .filter((d) => (d.family_relec || "").includes(denominationFamily))
        .map((d) => d.short_name || d.name),
    ];
  }

  // Sort the short_name alphabetically except for "All denominations"
  filteredDenominationOptions.sort((a, b) => {
    if (a === "All denominations") {
      return -1;
    } else if (b === "All denominations") {
      return 1;
    } else {
      return a.localeCompare(b);
    }
  });

  // Build each of the dropdown elements.
  d3.select("#year-dropdown")
    .append("label")
    .text("Select a year")
    .append("select")
    .attr("id", "year_selection")
    .selectAll("option")
    .data(options.year)
    .join("option")
    .attr("value", (d) => d)
    .text((d) => d)
    .property("selected", (d) => d === 1926);

  d3.select("#counts-dropdown")
    .append("label")
    .text("Select a count total")
    .append("select")
    .attr("id", "count_selection")
    .selectAll("option")
    .data(options.countSelection)
    .join("option")
    .attr("value", (d) => d)
    .text((d) => d)
    .property("selected", (d) => d === initialState[3]);

  const denominationFamilyDropdownValues = d3
    .select("#denomination-family-dropdown")
    .append("label")
    .text("Select a denomination family")
    .append("select")
    .attr("name", "denomination-family-selection");

  const denominationDropdownValues = d3
    .select("#denomination-dropdown")
    .append("label")
    .text("Select a denomination")
    .append("select")
    .attr("name", "denomination-selection");

  // Set the initial state of the dropdown menus
  denominationDropdownValues
    .selectAll("option")
    .data(filteredDenominationOptions)
    .join("option")
    .attr("value", (d) => d)
    .text((d) => d);

  denominationFamilyDropdownValues
    .selectAll("option")
    .data(options.denominationFamily)
    .join("option")
    .attr("value", (d) => d)
    .text((d) => d);

  // Add event listener to the family dropdown. When a user changes the family dropdown value,
  // we need to update the denomination dropdown with the appropriate values. These then persist
  // whether the user changes the dropdown or uses the URL params. We need an exact match, so we
  // use the indexOf method instead of includes().
  denominationFamilyDropdownValues.on("change", function () {
    const denominationFamilySelection = d3.select(this).node().value;
    const filteredDenominations = data[0].filter(
      (d) => (d.family_relec || "") === denominationFamilySelection,
    );
    const filteredDenominationOptions = [
      "All denominations",
      ...filteredDenominations.map((d) => d.short_name || d.name),
    ];

    // sort the short_name alphabetically except for "All denominations"
    filteredDenominationOptions.sort((a, b) => {
      if (a === "All denominations") {
        return -1;
      } else if (b === "All denominations") {
        return 1;
      } else {
        return a.localeCompare(b);
      }
    });
    denominationDropdownValues.selectAll("option").remove();
    denominationDropdownValues
      .selectAll("option")
      .data(filteredDenominationOptions)
      .join("option")
      .attr("value", (d) => d)
      .text((d) => d);
  });

  // This function updates the map, the URL/browser history and the citation.
  // It is defined here so that `citiesMap` is available to it.
  const updateAll = (
    year,
    denomination,
    denominationFamily,
    countSelection,
  ) => {
    citiesMap.update(year, denomination, denominationFamily, countSelection);
    updateURL(year, denomination, denominationFamily, countSelection);
    setDropDowns(year, denomination, denominationFamily, countSelection);
  };

  // Now update everything for the first time based on that initial state.
  // For the first time we have to set the dropdowns too.
  updateAll(initialState[0], initialState[1], initialState[2], initialState[3]);
  setDropDowns(
    initialState[0],
    initialState[1],
    initialState[2],
    initialState[3],
  );

  // Listen for changes to the filter options and return them to update() and re-render the map.
  d3.selectAll(".filterSelection").on("change", async () => {
    let year = d3.select("#year-dropdown option:checked").text();
    const denomination = d3
      .select("#denomination-dropdown option:checked")
      .text();
    const denominationFamily = d3
      .select("#denomination-family-dropdown option:checked")
      .text();
    const countSelection = d3.select("#counts-dropdown option:checked").text();

    // Convert year from string to number
    year = parseInt(year, 10);

    updateAll(year, denomination, denominationFamily, countSelection);
  });
}
