/**
 * Admin: readable view of a saved history record (itinerary, places, cafes, medical, area guide).
 * Replaces the raw JSON dump. Everything is escaped with admEscape; the raw data stays available
 * behind a "Show raw data" toggle for debugging. Loaded after admin.js.
 */

const aiMoney = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v)) ? '—' : '₹' + Math.round(Number(v)).toLocaleString('en-IN'));
const aiPill = (text) => text ? `<span class="adm-pill">${admEscape(text)}</span>` : '';
const aiRow = (label, value) => (value === null || value === undefined || value === '' ? '' :
  `<div class="adm-kv"><span class="adm-kv-k">${admEscape(label)}</span><span class="adm-kv-v">${value}</span></div>`);
const aiSection = (title, body) => body ? `<section class="adm-view-sec"><h4>${title}</h4>${body}</section>` : '';
const aiList = (arr) => Array.isArray(arr) && arr.length ? `<ul class="adm-view-list">${arr.map(x => `<li>${admEscape(typeof x === 'string' ? x : (x && (x.name || x.title)) || JSON.stringify(x))}</li>`).join('')}</ul>` : '';
const aiMap = (name, address) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([name, address].filter(Boolean).join(' '))}`;

function aiLeg(label, t) {
  if (!t) return '';
  const route = [t.origin, t.destination].filter(Boolean).map(admEscape).join(' → ');
  const times = [t.departure_time, t.arrival_time].filter(Boolean).map(admEscape).join(' → ');
  return aiRow(label, `${admEscape((t.mode || '').toUpperCase())} ${admEscape(t.operator || '')} ${admEscape(t.number || '')}` +
    `${route ? `<br><small>${route}</small>` : ''}${times ? `<br><small>${times}${t.duration_formatted ? ' · ' + admEscape(t.duration_formatted) : ''}</small>` : ''}` +
    `${t.price ? `<br><small>${aiMoney(t.price)} per person</small>` : ''}`);
}

function aiSegment(label, s) {
  if (!s) return '';
  const places = (s.places || []).map(p => `<li><b>${admEscape(p.name)}</b>${p.category ? ` <small>(${admEscape(p.category)})</small>` : ''}${p.address ? `<br><small>${admEscape(p.address)}</small>` : ''}</li>`).join('');
  if (!places && !s.title) return '';
  return `<div class="adm-seg"><div class="adm-seg-h">${label} <span>${admEscape(s.time_window || '')}</span></div>` +
    `<div>${admEscape(s.title || '')}</div>${places ? `<ul class="adm-view-list">${places}</ul>` : ''}</div>`;
}
function aiMeal(label, f) {
  if (!f || f.skipped || !f.name) return '';
  return `<div class="adm-seg"><div class="adm-seg-h">🍴 ${label}</div><div><b>${admEscape(f.name)}</b>${f.cuisine ? ` <small>(${admEscape(f.cuisine)})</small>` : ''}${f.recommendation ? `<br><small>Try: ${admEscape(f.recommendation)}</small>` : ''}</div></div>`;
}

function aiRenderItinerary(p) {
  const days = Array.isArray(p.days) ? p.days : [];
  const hotels = (p.selected_hotels && p.selected_hotels.length ? p.selected_hotels : (p.selected_hotel ? [p.selected_hotel] : []));
  const cb = p.cost_breakdown || {};
  let html = `<div class="adm-pills">${aiPill(p.source && p.destination ? `${p.source} → ${p.destination}` : p.destination)}` +
    `${aiPill(p.departure_date ? `${p.departure_date}${p.return_date ? ' to ' + p.return_date : ''}` : '')}` +
    `${aiPill(p.duration_days ? p.duration_days + ' day(s)' : '')}${aiPill(p.travelers_count || p.travellers ? (p.travelers_count || p.travellers) + ' traveller(s)' : '')}` +
    `${aiPill(p.pace)}${aiPill(p.data_mode === 'mock' ? 'Mock data' : '')}</div>`;
  if (p.trip_overview) html += `<p class="adm-view-note">${admEscape(p.trip_overview)}</p>`;

  html += aiSection('✈️ Transport', aiLeg('Outbound', p.selected_outbound_transport) + aiLeg('Return', p.selected_return_transport)
    + (p.transfers || []).map(t => aiRow(`${t.from_area} → ${t.to_area}`, t.choice ? `${admEscape(t.choice.mode)} ${admEscape(t.choice.operator || '')} ${admEscape(t.choice.number || '')}${t.choice.departure_time ? `<br><small>${admEscape(t.choice.departure_time)} → ${admEscape(t.choice.arrival_time || '')}</small>` : ''}` : `about ${admEscape(t.distance_km)} km`)).join(''));
  html += aiSection('🏨 Stays', hotels.map(h => aiRow(h.area || 'Hotel', `<b>${admEscape(h.name || '')}</b>${h.rating ? ' · ★ ' + admEscape(h.rating) : ''}${h.nightly_price ? ' · ' + aiMoney(h.nightly_price) + ' / night' : ''}${h.address ? `<br><small>${admEscape(h.address)}</small>` : ''}`)).join(''));
  html += aiSection('💰 Budget', aiRow('Estimated total', cb.overall_total_estimate != null ? aiMoney(cb.overall_total_estimate) : admEscape(p.estimated_budget_total || ''))
    + aiRow('Per person', cb.per_person_estimate != null ? aiMoney(cb.per_person_estimate) : '') + aiRow('Outbound fare', cb.outbound_transport_price ? aiMoney(cb.outbound_transport_price) : '')
    + aiRow('Return fare', cb.return_transport_price ? aiMoney(cb.return_transport_price) : '') + aiRow('Hotels', cb.hotel_total_price ? aiMoney(cb.hotel_total_price) : ''));

  html += aiSection(`📅 Day by day (${days.length})`, days.map(d => `
    <div class="adm-day">
      <div class="adm-day-h">Day ${admEscape(d.day_number)}${d.area ? ' · ' + admEscape(d.area) : ''}: ${admEscape(d.theme || '')}</div>
      ${(d.notes || []).map(n => `<div class="adm-seg adm-note">${admEscape(n.title || '')}: ${admEscape((n.lines || []).slice(0, 2).join(' '))}</div>`).join('')}
      ${aiSegment('🌅 Morning', d.morning)}${aiMeal('Lunch', d.food_stop_lunch)}${aiSegment('☀️ Afternoon', d.afternoon)}${aiMeal('Dinner', d.food_stop_dinner)}${aiSegment('🌙 Evening', d.evening)}
      ${d.return_to_hotel && d.return_to_hotel.hotel_name ? `<div class="adm-seg">🏨 Back to ${admEscape(d.return_to_hotel.hotel_name)}${d.return_to_hotel.leave_at ? ' around ' + admEscape(d.return_to_hotel.leave_at) : ''}</div>` : ''}
    </div>`).join(''));
  if (!days.length) html += '<p class="adm-view-note">This saved record has no day-by-day schedule.</p>';
  return html;
}

function aiRenderPlaces(p, type) {
  let list = Array.isArray(p.places) ? p.places : Array.isArray(p.items) ? p.items : Array.isArray(p.results) ? p.results : Array.isArray(p) ? p : [];
  const center = p.center || {};
  const head = `<div class="adm-pills">${aiPill(p.location || p.query || center.name || p.area_input || '')}${aiPill(p.radius_km ? p.radius_km + ' km radius' : '')}${aiPill(list.length + ' result(s)')}${aiPill(type)}</div>`;
  if (!list.length) return head + '<p class="adm-view-note">No places are listed in this saved record.</p>';
  return head + `<div class="adm-place-grid">${list.slice(0, 60).map((x, i) => {
    const name = x.name || 'Unnamed place', addr = x.address || x.formatted_address || '';
    const bits = [x.category, x.rating ? '★ ' + x.rating : '', x.distance_text || (x.distance_km != null ? x.distance_km + ' km' : ''), x.is_open_24_7 ? '24/7' : '', x.service_type].filter(Boolean).map(admEscape).join(' · ');
    return `<div class="adm-place"><b>${i + 1}. ${admEscape(name)}</b>${bits ? `<div><small>${bits}</small></div>` : ''}${addr ? `<div><small>${admEscape(addr)}</small></div>` : ''}${x.phone ? `<div><small>📞 ${admEscape(x.phone)}</small></div>` : ''}<a href="${admEscape(aiMap(name, addr))}" target="_blank" rel="noopener noreferrer">🗺️ Map ↗</a></div>`;
  }).join('')}</div>${list.length > 60 ? `<p class="adm-view-note">Showing the first 60 of ${list.length}.</p>` : ''}`;
}

function aiRenderArea(p) {
  const text = p.character_summary || p.summary;
  let html = `<div class="adm-pills">${aiPill(p.area_input || p.area || '')}${aiPill(p.region || '')}</div>`;
  if (text) html += `<p class="adm-view-note">${admEscape(text)}</p>`;
  if (p.quick_facts) html += aiSection('Quick facts', Object.entries(p.quick_facts).map(([k, v]) => aiRow(k.replace(/_/g, ' '), admEscape(v))).join(''));
  const sections = Array.isArray(p.sections) ? p.sections : Object.values(p.sections || {});
  html += aiSection('Sections', sections.map(s => `<div class="adm-seg"><b>${admEscape(s.title || 'Section')}</b><div>${admEscape(s.summary || s.content || '')}</div></div>`).join(''));
  html += aiSection('Advantages', aiList(p.advantages)) + aiSection('Limitations', aiList(p.limitations)) + aiSection('Who it suits', aiList(p.suitability));
  if (!text && !sections.length) html += '<p class="adm-view-note">Only the area name was saved for this record.</p>';
  return html;
}

/** Any other shape: readable key/value rows instead of a JSON dump (nested values are summarised). */
function aiRenderGeneric(p) {
  const entries = Object.entries(p || {});
  if (!entries.length) return '<p class="adm-view-note">This record has no saved details.</p>';
  return entries.map(([k, v]) => {
    let shown;
    if (Array.isArray(v)) shown = v.length ? aiList(v.slice(0, 20)) || `${v.length} item(s)` : '—';
    else if (v && typeof v === 'object') shown = Object.entries(v).slice(0, 12).map(([a, b]) => `${admEscape(a.replace(/_/g, ' '))}: ${admEscape(typeof b === 'object' ? '…' : b)}`).join('<br>') || '—';
    else shown = admEscape(v);
    return aiRow(k.replace(/_/g, ' '), shown);
  }).join('');
}

function admRenderRecordView(featureType, payload) {
  const type = String(featureType || '').toLowerCase();
  const p = payload || {};
  try {
    if (type === 'itinerary' || Array.isArray(p.days)) return aiRenderItinerary(p);
    if (type === 'places' || type === 'cafes' || type === 'medical') return aiRenderPlaces(p, type);
    if (type === 'area') return aiRenderArea(p);
  } catch (err) {
    console.warn('Readable view failed, falling back:', err);
  }
  return aiRenderGeneric(p);
}

function admToggleRaw(btn) {
  const box = btn.parentElement.querySelector('.adm-json-wrap');
  if (!box) return;
  box.hidden = !box.hidden;
  btn.textContent = box.hidden ? 'Show raw data' : 'Hide raw data';
}
