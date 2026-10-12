/**
 * 24/7 Medical Care Page Initializer (Section 12 & Section 50).
 */

import { api } from "../api.js";
import { NearbyExplorerController } from "../components/nearby-explorer.js";

document.addEventListener("DOMContentLoaded", () => {
  const explorer = new NearbyExplorerController({
    pageType: "medical",
    historyTitlePrefix: "24/7 Medical Care",
    emptyPromptLabel: "medical facilities",
    fetchApiMethod: (payload, signal) => api.searchMedical(payload, signal),
    mapContainerId: "medicalMap",
    resultsContainerId: "medicalCardsGrid",
    chipsContainerId: "medicalFilterChips",
    routePanelId: "medicalRoutePanel",
    searchFormId: "medicalSearchForm",
    locationInputId: "medicalLocationInput",
    radiusSelectId: "medicalRadiusSelect",
    btnUseLocationId: "btnMedicalUseLocation"
  });

  explorer.init();
});
