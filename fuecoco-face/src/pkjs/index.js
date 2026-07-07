/**
 * Runs on the phone (PebbleKit JS), not the watch. Fetches the current weather code
 * for the phone's GPS location from Open-Meteo (free, no API key) and relays it to
 * the watch as a single WMO weather code integer via AppMessage. The watch maps that
 * code to a small icon in src/c/fuecoco.c — see weather_code_to_condition().
 */

function fetchWeather() {
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + pos.coords.latitude +
                '&longitude=' + pos.coords.longitude + '&current=weather_code';

      var xhr = new XMLHttpRequest();
      xhr.onload = function () {
        if (xhr.status !== 200) {
          console.log('Open-Meteo request failed: ' + xhr.status);
          return;
        }
        var json = JSON.parse(xhr.responseText);
        var code = json.current && json.current.weather_code;
        if (typeof code === 'number') {
          Pebble.sendAppMessage({ WEATHER_CODE: code }, function () {}, function (e) {
            console.log('Failed to send weather code: ' + JSON.stringify(e));
          });
        }
      };
      xhr.onerror = function () {
        console.log('Open-Meteo request errored');
      };
      xhr.open('GET', url, true);
      xhr.send();
    },
    function (err) {
      console.log('Geolocation error: ' + err.message);
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
