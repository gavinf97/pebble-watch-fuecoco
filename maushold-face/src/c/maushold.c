#include <pebble.h>
#include "message_keys.auto.h"

static Window *s_main_window;

static Layer *s_info_bar_layer;
static int s_battery_level;

static TextLayer *s_time_layer;

static Layer *s_weather_icon_layer;
static GBitmap *s_weather_bitmap;      // only the current icon is ever resident
static uint32_t s_weather_resource;    // what s_weather_bitmap holds, 0 = nothing loaded

static GBitmap *s_scene_bitmap;
static BitmapLayer *s_scene_layer;

// Latest reading from the phone. Everything except the code is new relative to the Fuecoco
// face, which only ever received a WMO code.
static bool s_have_weather = false;
static int s_weather_code = 0;
static int s_weather_temp = 0;
static int s_weather_is_day = 1;
static int s_weather_cloud = 0;        // % cover
static int s_weather_wind = 0;         // km/h

#define WIND_THRESHOLD_KMH 38          // Beaufort 6 — "strong breeze", worth showing

static void update_time() {
  time_t now = time(NULL);
  struct tm *t = localtime(&now);

  static char s_time_buf[8];
  strftime(s_time_buf, sizeof(s_time_buf),
           clock_is_24h_style() ? "%H:%M" : "%I:%M", t);
  text_layer_set_text(s_time_layer, s_time_buf);
}

static void request_weather_update() {
  DictionaryIterator *iter;
  if (app_message_outbox_begin(&iter) == APP_MSG_OK) {
    dict_write_uint8(iter, MESSAGE_KEY_REQUEST_WEATHER, 1);
    app_message_outbox_send();
  }
}

static void tick_handler(struct tm *tick_time, TimeUnits units_changed) {
  update_time();
  // Refresh weather every 30 minutes — plenty fresh without hammering the API
  if (tick_time->tm_min % 30 == 0) {
    request_weather_update();
  }
}

// Maps a reading to one of the icon sprites.
// https://open-meteo.com/en/docs — "WMO Weather interpretation codes"
//
// Two things this does that a plain code switch cannot:
//
//   * Day/night. Codes 0-2 say nothing about whether the sun is up, so a single "clear"
//     icon is wrong half the time. is_day picks the sun or the moon variant.
//   * Cloud cover. Open-Meteo reports the quiet end of the scale bluntly — a sky that is
//     40% covered and one that is 95% covered can both arrive as code 3. Since codes 0-3
//     are what's showing most days here, deferring to the measured percentage is where
//     most of the added nuance actually comes from.
static uint32_t weather_resource_id(void) {
  if (!s_have_weather) {
    return RESOURCE_ID_IMAGE_WX_NODATA;
  }

  const int code = s_weather_code;
  const bool day = (s_weather_is_day != 0);

  // Precipitation and obscuration first — these are unambiguous, and cloud cover is
  // irrelevant once it's actually raining on you.
  switch (code) {
    case 45: case 48:                     return RESOURCE_ID_IMAGE_WX_FOG;
    case 51: case 53: case 55:            return RESOURCE_ID_IMAGE_WX_DRIZZLE;
    case 56: case 57:                     return RESOURCE_ID_IMAGE_WX_FRZ_DRIZZLE;
    case 61: case 63: case 80: case 81:   return RESOURCE_ID_IMAGE_WX_RAIN;
    case 65: case 82:                     return RESOURCE_ID_IMAGE_WX_RAIN_HEAVY;
    case 66: case 67:                     return RESOURCE_ID_IMAGE_WX_SLEET;
    case 71: case 73: case 77: case 85:   return RESOURCE_ID_IMAGE_WX_SNOW;
    case 75: case 86:                     return RESOURCE_ID_IMAGE_WX_SNOW_HEAVY;
    case 95:                              return RESOURCE_ID_IMAGE_WX_STORM;
    case 96: case 99:                     return RESOURCE_ID_IMAGE_WX_STORM_HAIL;
    default: break;
  }

  // Dry sky (codes 0-3). A strong wind is the most notable thing about an otherwise
  // uneventful sky, so it takes the icon.
  if (s_weather_wind >= WIND_THRESHOLD_KMH) {
    return RESOURCE_ID_IMAGE_WX_WIND;
  }

  int cover = s_weather_cloud;
  if (cover <= 0) {
    // No cover reading came through — fall back to the code's own coarse banding.
    cover = (code == 0) ? 0 : (code == 1) ? 30 : (code == 2) ? 65 : 95;
  }

  if (cover < 12)  return day ? RESOURCE_ID_IMAGE_WX_SUN       : RESOURCE_ID_IMAGE_WX_MOON;
  if (cover < 50)  return day ? RESOURCE_ID_IMAGE_WX_SUN_HAZE  : RESOURCE_ID_IMAGE_WX_MOON_HAZE;
  if (cover < 85)  return day ? RESOURCE_ID_IMAGE_WX_SUN_CLOUD : RESOURCE_ID_IMAGE_WX_MOON_CLOUD;
  return RESOURCE_ID_IMAGE_WX_CLOUD;
}

static void weather_icon_update_proc(Layer *layer, GContext *ctx) {
  uint32_t wanted = weather_resource_id();
  if (wanted != s_weather_resource || s_weather_bitmap == NULL) {
    if (s_weather_bitmap) {
      gbitmap_destroy(s_weather_bitmap);
    }
    s_weather_bitmap = gbitmap_create_with_resource(wanted);
    s_weather_resource = wanted;
  }
  if (s_weather_bitmap) {
    graphics_context_set_compositing_mode(ctx, GCompOpAssign);
    graphics_draw_bitmap_in_rect(ctx, s_weather_bitmap, layer_get_bounds(layer));
  }
}

static void inbox_received_callback(DictionaryIterator *iterator, void *context) {
  Tuple *t;
  bool changed = false;

  if ((t = dict_find(iterator, MESSAGE_KEY_WEATHER_CODE))) {
    s_weather_code = (int)t->value->int32;
    s_have_weather = true;
    changed = true;
  }
  if ((t = dict_find(iterator, MESSAGE_KEY_WEATHER_TEMP))) {
    s_weather_temp = (int)t->value->int32;
    changed = true;
  }
  if ((t = dict_find(iterator, MESSAGE_KEY_WEATHER_IS_DAY))) {
    s_weather_is_day = (int)t->value->int32;
    changed = true;
  }
  if ((t = dict_find(iterator, MESSAGE_KEY_WEATHER_CLOUD))) {
    s_weather_cloud = (int)t->value->int32;
    changed = true;
  }
  if ((t = dict_find(iterator, MESSAGE_KEY_WEATHER_WIND))) {
    s_weather_wind = (int)t->value->int32;
    changed = true;
  }

  if (changed) {
    if (s_weather_icon_layer) layer_mark_dirty(s_weather_icon_layer);
    if (s_info_bar_layer) layer_mark_dirty(s_info_bar_layer);   // temperature lives there
  }
}

// Single bordered "module": "Battery" label, bar, and the current temperature — boxed
// together so it reads as one distinct segment of the face. The temperature sits directly
// above the weather icon so the two read as one right-hand weather column.
static void info_bar_update_proc(Layer *layer, GContext *ctx) {
  GRect bounds = layer_get_bounds(layer);

  // Outer box
  graphics_context_set_stroke_color(ctx, GColorBlack);
  graphics_draw_rect(ctx, GRect(0, 0, bounds.size.w, bounds.size.h));

  // "Battery" label, left side — bold. Measure the actual rendered text height and center
  // it exactly (font line-height padding otherwise throws off any fixed offset guess).
  GFont label_font = fonts_get_system_font(FONT_KEY_GOTHIC_14_BOLD);
  GRect text_box = GRect(6, 0, 52, bounds.size.h);
  GSize text_size = graphics_text_layout_get_content_size(
      "Battery", label_font, text_box, GTextOverflowModeTrailingEllipsis, GTextAlignmentLeft);
  // Measured content size still includes a few px of font leading below the visible ink,
  // so nudge up slightly from the naive centered position.
  text_box.origin.y = (bounds.size.h - text_size.h) / 2 - 3;
  text_box.size.h = text_size.h;

  graphics_context_set_text_color(ctx, GColorBlack);
  graphics_draw_text(ctx, "Battery", label_font, text_box,
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentLeft, NULL);

  // Bar — fills/depletes with charge, no percent text. Shortened from the Fuecoco face's
  // 74px to free the right-hand end of the bar for the temperature.
  GRect bar = GRect(62, (bounds.size.h - 8) / 2, 44, 8);
  graphics_draw_rect(ctx, bar);
  int inner_w = bar.size.w - 2;
  int fill_w = (inner_w * s_battery_level) / 100;
  if (fill_w > 0) {
    graphics_context_set_fill_color(ctx, GColorBlack);
    graphics_fill_rect(ctx, GRect(bar.origin.x + 1, bar.origin.y + 1, fill_w, bar.size.h - 2),
                       0, GCornerNone);
  }

  // Temperature, right-aligned to the same 6px inset as the label on the left.
  static char s_temp_buf[8];
  if (s_have_weather) {
    snprintf(s_temp_buf, sizeof(s_temp_buf), "%d°", s_weather_temp);
  } else {
    snprintf(s_temp_buf, sizeof(s_temp_buf), "--°");
  }
  GRect temp_box = GRect(bounds.size.w - 6 - 32, text_box.origin.y, 32, text_box.size.h);
  graphics_draw_text(ctx, s_temp_buf, label_font, temp_box,
                     GTextOverflowModeTrailingEllipsis, GTextAlignmentRight, NULL);
}

static void battery_callback(BatteryChargeState state) {
  s_battery_level = state.charge_percent;
  if (s_info_bar_layer) {
    layer_mark_dirty(s_info_bar_layer);
  }
}

static void main_window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  window_set_background_color(window, GColorWhite);

  // Scene first, so everything else composites on top of it. (The Fuecoco face added its
  // character bitmap last, which meant the opaque white of GCompOpAssign painted over
  // anything sharing its GRect and forced the weather icon into a cramped corner.)
  s_scene_bitmap = gbitmap_create_with_resource(RESOURCE_ID_IMAGE_MAUSHOLD_SCENE);
  s_scene_layer = bitmap_layer_create(GRect(0, 61, 144, 107));
  bitmap_layer_set_bitmap(s_scene_layer, s_scene_bitmap);
  bitmap_layer_set_compositing_mode(s_scene_layer, GCompOpAssign);
  layer_add_child(root, bitmap_layer_get_layer(s_scene_layer));

  // Info bar — "Battery" label, bar and temperature together in one bordered box.
  // Side margins match the top margin (1px) so spacing is even all round.
  s_info_bar_layer = layer_create(GRect(1, 1, 142, 18));
  layer_set_update_proc(s_info_bar_layer, info_bar_update_proc);
  layer_add_child(root, s_info_bar_layer);

  // Time — centred within the left 118px rather than the full width, to leave the
  // right-hand slot free for the weather icon. LECO_42_NUMBERS lays "HH:MM" out at 116px
  // (measured on the emulator: 26px per digit, 12px for the colon), so anything narrower
  // than that truncates the minutes to an ellipsis. 118 leaves 2px of slack; the remaining
  // 26 go to the icon, which is why it sits flush to the right edge.
  s_time_layer = text_layer_create(GRect(0, 19, 118, 42));
  text_layer_set_background_color(s_time_layer, GColorClear);
  text_layer_set_text_color(s_time_layer, GColorBlack);
  text_layer_set_font(s_time_layer, fonts_get_system_font(FONT_KEY_LECO_42_NUMBERS));
  text_layer_set_text_alignment(s_time_layer, GTextAlignmentCenter);
  layer_add_child(root, text_layer_get_layer(s_time_layer));

  // Weather icon — right of the time, vertically centred in that band, sitting directly
  // under the temperature reading in the bar above.
  s_weather_icon_layer = layer_create(GRect(118, 27, 26, 26));
  layer_set_update_proc(s_weather_icon_layer, weather_icon_update_proc);
  layer_add_child(root, s_weather_icon_layer);

  s_battery_level = battery_state_service_peek().charge_percent;
  update_time();
}

static void main_window_unload(Window *window) {
  layer_destroy(s_info_bar_layer);

  text_layer_destroy(s_time_layer);

  layer_destroy(s_weather_icon_layer);
  if (s_weather_bitmap) {
    gbitmap_destroy(s_weather_bitmap);
    s_weather_bitmap = NULL;
  }

  bitmap_layer_destroy(s_scene_layer);
  gbitmap_destroy(s_scene_bitmap);
}

static void init() {
  s_main_window = window_create();
  window_set_window_handlers(s_main_window, (WindowHandlers) {
    .load = main_window_load,
    .unload = main_window_unload,
  });
  window_stack_push(s_main_window, true);

  tick_timer_service_subscribe(MINUTE_UNIT, tick_handler);
  battery_state_service_subscribe(battery_callback);

  // Register AppMessage callbacks before opening, per Pebble's recommended order
  app_message_register_inbox_received(inbox_received_callback);
  app_message_open(256, 128);
  request_weather_update();

  update_time();
}

static void deinit() {
  tick_timer_service_unsubscribe();
  battery_state_service_unsubscribe();
  window_destroy(s_main_window);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
