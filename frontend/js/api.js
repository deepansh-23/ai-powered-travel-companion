/**
 * Smart Local Guide - API Client
 * Centralized fetch handler for all backend endpoints.
 */

const BASE_URL = (window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "";

class ApiClient {
  async _request(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    const defaultHeaders = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers
      }
    };

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        let errorMsg = `Server error (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errorMsg = errData.detail;
          }
        } catch (_) {}
        // Session expired / not verified: ask the CAPTCHA gate to reappear
        if (response.status === 403 && /human verification/i.test(errorMsg)) {
          window.dispatchEvent(new CustomEvent("slg:captcha-required"));
        }
        throw new Error(errorMsg);
      }
      return await response.json();
    } catch (err) {
      if (err.name === "AbortError") {
        throw err; // Allow abort to be handled by caller
      }
      throw err;
    }
  }

  // Health
  checkHealth() {
    return this._request("/api/health", { method: "GET" });
  }

  // Places Search
  searchPlaces(payload, signal) {
    return this._request("/api/places/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Cafes Search
  searchCafes(payload, signal) {
    return this._request("/api/cafes/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Medical Search
  searchMedical(payload, signal) {
    return this._request("/api/medical/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Routing (Section 50.5 & 50.7)
  getRoute(origin, destination, mode = "walking", signal) {
    return this._request("/api/route", {
      method: "POST",
      body: JSON.stringify({
        origin: { latitude: origin.lat, longitude: origin.lon },
        destination: { latitude: destination.lat, longitude: destination.lon },
        mode
      }),
      signal
    });
  }

  // Itinerary
  generateItinerary(payload, signal) {
    return this._request("/api/itinerary/generate", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Area Guide
  summarizeArea(payload, signal) {
    return this._request("/api/area/summarize", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // History
  getHistory(featureType = "all") {
    const q = featureType && featureType !== "all" ? `?feature_type=${encodeURIComponent(featureType)}` : "";
    return this._request(`/api/history${q}`, { method: "GET" });
  }

  createHistory(item) {
    return this._request("/api/history", {
      method: "POST",
      body: JSON.stringify(item)
    });
  }

  deleteHistory(id) {
    return this._request(`/api/history/${encodeURIComponent(id)}`, {
      method: "DELETE"
    });
  }

  // Transport (Section 6, 7, 9)
  searchTransport(payload, signal) {
    return this._request("/api/transport/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Provider booking options for a selected flight (Section 11)
  getFlightBookingOptions(bookingToken, searchParams) {
    return this._request("/api/transport/flight-booking", {
      method: "POST",
      body: JSON.stringify({ booking_token: bookingToken, search_params: searchParams })
    });
  }

  // Hotels (Section 7A)
  searchHotels(payload, signal) {
    return this._request("/api/hotel/search", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  getHotelDetails(payload, signal) {
    return this._request("/api/hotel/details", {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    });
  }

  // Feedback & Reviews (Section 24)
  getFeedback() {
    return this._request("/api/feedback", { method: "GET" });
  }

  // One review for several services (saved once per selected service)
  submitFeedbackMulti(payload) {
    return this._request("/api/feedback/multi", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  submitFeedback(payload) {
    return this._request("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }

  // CAPTCHA (Section 25)
  getCaptchaConfig() {
    return this._request("/api/captcha/config", { method: "GET" });
  }

  getCaptchaStatus() {
    return this._request("/api/captcha/status", { method: "GET" });
  }

  verifyCaptcha(token) {
    return this._request("/api/captcha/verify", {
      method: "POST",
      body: JSON.stringify({ token })
    });
  }

  // Exports & Binary PDF Download (Section 23)
  async downloadPdf(title, content) {
    const url = `${BASE_URL}/api/export/pdf`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, content })
    });
    if (!response.ok) {
      let errMsg = `Failed to generate PDF (${response.status})`;
      try {
        const errJson = await response.json();
        if (errJson && errJson.detail) errMsg = errJson.detail;
      } catch (_) {}
      throw new Error(errMsg);
    }
    return await response.blob();
  }

  exportPdf(title, content) {
    return this.downloadPdf(title, content);
  }

  exportAudio(text) {
    return this._request("/api/export/audio", {
      method: "POST",
      body: JSON.stringify({ text })
    });
  }
}


export const api = new ApiClient();
