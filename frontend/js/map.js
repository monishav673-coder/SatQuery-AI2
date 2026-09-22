/* ============================================================
   SATQUERY AI — Leaflet Map Module
   ============================================================ */

let analysisMap = null;
let coordMarker = null;

/**
 * Initialise the analysis input map inside #map-container.
 * @param {number} lat - initial latitude (default: 20.5937 — India centre)
 * @param {number} lon - initial longitude (default: 78.9629)
 * @param {number} zoom - initial zoom level
 */
function initAnalysisMap(lat = 20.5937, lon = 78.9629, zoom = 4) {
  if (analysisMap) return;   // already initialised

  const container = document.getElementById('map-container');
  if (!container || typeof L === 'undefined') return;

  analysisMap = L.map('map-container', {
    center: [lat, lon],
    zoom,
    zoomControl: true,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(analysisMap);

  // Click to set coordinates
  analysisMap.on('click', function (e) {
    const { lat, lng } = e.latlng;
    setMapMarker(lat, lng);
    // Fill coordinate inputs if present
    const latInput = document.getElementById('coord-lat');
    const lonInput = document.getElementById('coord-lon');
    if (latInput) latInput.value = lat.toFixed(6);
    if (lonInput) lonInput.value = lng.toFixed(6);
    reverseGeocodeDisplay(lat, lng);
  });
}

/**
 * Place or move the coordinate marker on the map.
 */
function setMapMarker(lat, lon) {
  if (!analysisMap) return;

  if (coordMarker) {
    coordMarker.setLatLng([lat, lon]);
  } else {
    coordMarker = L.marker([lat, lon], {
      icon: L.divIcon({
        className: '',
        html: `<div style="
          width:20px;height:20px;
          background:linear-gradient(135deg,#00d4ff,#7c3aed);
          border-radius:50% 50% 50% 0;
          transform:rotate(-45deg);
          border:2px solid #fff;
          box-shadow:0 2px 8px rgba(0,212,255,0.5);
        "></div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 20],
      }),
    }).addTo(analysisMap);
  }

  analysisMap.flyTo([lat, lon], Math.max(analysisMap.getZoom(), 10), {
    animate: true, duration: 1.2,
  });
}

/**
 * Reverse-geocode coordinates and display place name in #coord-place.
 */
async function reverseGeocodeDisplay(lat, lon) {
  const placeEl = document.getElementById('coord-place');
  if (!placeEl) return;

  placeEl.classList.remove('hidden');
  placeEl.textContent = 'Looking up location...';

  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
      { headers: { 'User-Agent': 'SATQUERY-AI/1.0' } }
    );
    const data = await resp.json();
    const name = data.display_name || `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
    placeEl.textContent = `📍 ${name}`;
  } catch (_) {
    placeEl.textContent = `📍 ${lat.toFixed(4)}°, ${lon.toFixed(4)}°`;
  }
}

/**
 * Called when "Preview Location on Map" button is clicked.
 */
async function previewCoordinates() {
  const lat = parseFloat(document.getElementById('coord-lat')?.value);
  const lon = parseFloat(document.getElementById('coord-lon')?.value);

  const latErr = document.getElementById('lat-error');
  const lonErr = document.getElementById('lon-error');
  if (latErr) latErr.classList.add('hidden');
  if (lonErr) lonErr.classList.add('hidden');

  let valid = true;
  if (isNaN(lat) || lat < -90 || lat > 90) {
    if (latErr) { latErr.textContent = 'Latitude must be between −90 and 90.'; latErr.classList.remove('hidden'); }
    valid = false;
  }
  if (isNaN(lon) || lon < -180 || lon > 180) {
    if (lonErr) { lonErr.textContent = 'Longitude must be between −180 and 180.'; lonErr.classList.remove('hidden'); }
    valid = false;
  }
  if (!valid) return;

  if (!analysisMap) initAnalysisMap(lat, lon, 10);
  setMapMarker(lat, lon);
  await reverseGeocodeDisplay(lat, lon);
}

/**
 * Destroy the map instance (call before reinitialising).
 */
function destroyMap() {
  if (analysisMap) {
    analysisMap.remove();
    analysisMap = null;
    coordMarker = null;
  }
}
