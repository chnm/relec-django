/**
 * Cascading populated place filter for CensusSchedule admin.
 *
 * When a county is selected, the populated_place autocomplete is filtered
 * to only show places within that county. Clearing the county also clears
 * the populated place selection.
 */
(function ($) {
    "use strict";

    $(document).ready(function () {
        const $county = $("#id_county");
        const $place = $("#id_populated_place");

        if (!$county.length || !$place.length) {
            return;
        }

        // Clear populated place whenever county changes
        $county.on("change", function () {
            $place.val(null).trigger("change");
        });

        // Before each autocomplete search, inject county_id into the request
        $place.on("select2:open", function () {
            const select2Instance = $place.data("select2");
            if (!select2Instance) return;

            const ajax = select2Instance.options.options.ajax;
            if (!ajax || ajax._countyPatched) return;

            const originalData = ajax.data;
            ajax.data = function (params) {
                const result = originalData ? originalData.call(this, params) : { term: params.term || "" };
                const countyId = $county.val();
                if (countyId) {
                    result.county_id = countyId;
                }
                return result;
            };
            ajax._countyPatched = true;
        });
    });
})(django.jQuery);
