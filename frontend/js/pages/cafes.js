/**
 * Quiet Work Cafés Page Initializer (Section 11 & Section 50).
 */

import { api } from "../api.js";
import { NearbyExplorerController } from "../components/nearby-explorer.js";

document.addEventListener("DOMContentLoaded", () => {
  const explorer = new NearbyExplorerController({
    pageType: "cafes",
    historyTitlePrefix: "Quiet Work Cafés",
    emptyPromptLabel: "cafés",
    fetchApiMethod: (payload, signal) => api.searchCafes(payload, signal),
    mapContainerId: "cafesMap",
    resultsContainerId: "cafesCardsGrid",
    chipsContainerId: "cafesFilterChips",
    routePanelId: "cafesRoutePanel",
    searchFormId: "cafesSearchForm",
    locationInputId: "cafesLocationInput",
    radiusSelectId: "cafesRadiusSelect",
    btnUseLocationId: "btnCafesUseLocation"
  });

  explorer.init();
});
