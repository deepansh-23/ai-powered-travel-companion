/**
 * Places Near You Page Initializer (Section 9 & Section 50).
 */

import { api } from "../api.js";
import { NearbyExplorerController } from "../components/nearby-explorer.js";

document.addEventListener("DOMContentLoaded", () => {
  const explorer = new NearbyExplorerController({
    pageType: "places",
    historyTitlePrefix: "Places Near You",
    emptyPromptLabel: "places",
    fetchApiMethod: (payload, signal) => api.searchPlaces(payload, signal),
    mapContainerId: "placesMap",
    resultsContainerId: "placesCardsGrid",
    chipsContainerId: "placesFilterChips",
    routePanelId: "placesRoutePanel",
    searchFormId: "placesSearchForm",
    locationInputId: "placesLocationInput",
    radiusSelectId: "placesRadiusSelect",
    btnUseLocationId: "btnPlacesUseLocation"
  });

  explorer.init();
});
