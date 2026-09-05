/**
 * Runs on the phone (PebbleKit JS), not the watch. Fetches current conditions for the
 * phone's GPS location from Open-Meteo (free, no API key) and relays them to the watch via
 * AppMessage. The watch turns the reading into an icon in src/c/maushold.c — see
 * weather_resource_id().
 *
 * The Fuecoco face sent a single WMO code. This sends five fields, because the code alone
 * can't distinguish day from night, can't tell a hazy sky from a socked-in one, and carries
 * no temperature at all:
 *
 *   weather_code     the WMO code, as before
 *   temperature_2m   rounded to a whole degree for the info bar
 *   is_day           picks the sun or moon variant of every clear/cloudy icon
 *   cloud_cover      grades codes 0-3, which are otherwise a very blunt instrument
 *   wind_speed_10m   promotes an otherwise-unremarkable sky to the windy icon
 */

var API = 'https://api.open-meteo.com/v1/forecast';
var FIELDS = 'weather_code,temperature_2m,is_day,cloud_cover,wind_speed_10m';
var POS_KEY = 'lastPosition';
var RETRY_MS = 60 * 1000;

function cachePosition(coords) {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify({ lat: coords.latitude, lon: coords.longitude }));
  } catch (e) {
    // Storage being unavailable is not worth failing the fetch over.
  }
}

function cachedPosition() {
  try {
    var raw = localStorage.getItem(POS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function send(current) {
  Pebble.sendAppMessage({
    WEATHER_CODE: current.weather_code,
    WEATHER_TEMP: Math.round(current.temperature_2m),
    WEATHER_IS_DAY: current.is_day,
    WEATHER_CLOUD: Math.round(current.cloud_cover),
    WEATHER_WIND: Math.round(current.wind_speed_10m)
  }, function () {}, function (e) {
    console.log('Failed to send weather: ' + JSON.stringify(e));
  });
}

function fetchFor(lat, lon, allowRetry) {
  var url = API + '?latitude=' + lat + '&longitude=' + lon +
            '&current=' + FIELDS +
            '&temperature_unit=celsius&wind_speed_unit=kmh';

  var xhr = new XMLHttpRequest();
  var failed = function (why) {
    console.log('Open-Meteo ' + why);
    // One retry only. Beyond that the watch keeps showing its last good reading, which is
    // more useful than blanking the face over a momentary loss of signal.
    if (allowRetry) {
      setTimeout(function () { fetchFor(lat, lon, false); }, RETRY_MS);
    }
  };

  xhr.onload = function () {
    if (xhr.status !== 200) {
      failed('request failed: ' + xhr.status);
      return;
    }
    try {
      var current = JSON.parse(xhr.responseText).current;
      if (current && typeof current.weather_code === 'number') {
        send(current);
      } else {
        failed('response had no current conditions');
      }
    } catch (e) {
      failed('response was not valid JSON');
    }
  };
  xhr.onerror = function () { failed('request errored'); };
  xhr.open('GET', url, true);
  xhr.send();
}

function fetchWeather() {
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      cachePosition(pos.coords);
      fetchFor(pos.coords.latitude, pos.coords.longitude, true);
    },
    function (err) {
      // A GPS fix can fail indoors or with the screen locked. Weather at the last known
      // position is far closer to the truth than no weather at all.
      var last = cachedPosition();
      if (last) {
        console.log('Geolocation error (' + err.message + '), using last known position');
        fetchFor(last.lat, last.lon, true);
      } else {
        console.log('Geolocation error: ' + err.message);
      }
    },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 10 * 60 * 1000 }
  );
}

Pebble.addEventListener('ready', function () {
  fetchWeather();
});

Pebble.addEventListener('appmessage', function (e) {
  if (e.payload.REQUEST_WEATHER) {
    fetchWeather();
  }
});
