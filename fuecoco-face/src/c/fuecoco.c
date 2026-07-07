#include <pebble.h>
#include "message_keys.auto.h"

static Window *s_main_window;

static Layer *s_battery_module_layer;
static int s_battery_level;

static TextLayer *s_time_layer;

static Layer *s_weather_icon_layer;
// -1 = no data yet (nothing drawn until the phone's first reading arrives)
#define WEATHER_UNKNOWN -1
#define WEATHER_CLEAR    0
#define WEATHER_CLOUDY   1
#define WEATHER_RAIN     2
#define WEATHER_SNOW     3
#define WEATHER_STORM    4
static int s_weather_condition = WEATHER_UNKNOWN;

static GBitmap *s_fuecoco_bitmap;
static BitmapLayer *s_fuecoco_layer;

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

// Maps an Open-Meteo/WMO weather code to one of our five icon categories.
// https://open-meteo.com/en/docs — "WMO Weather interpretation codes"
static int weather_code_to_condition(int code) {
  if (code == 0) return WEATHER_CLEAR;
  if (code <= 3 || code == 45 || code == 48) return WEATHER_CLOUDY;
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return WEATHER_RAIN;
  if ((code >= 71 && code <= 77) || code == 85 || code == 86) return WEATHER_SNOW;
  if (code >= 95) return WEATHER_STORM;
  return WEATHER_CLOUDY;
}

// Small (12x12) weather icon. Kept deliberately simple/bold — there's no room
// for detail at this size, so each condition is just a couple of shapes.
static void weather_icon_update_proc(Layer *layer, GContext *ctx) {
  if (s_weather_condition == WEATHER_UNKNOWN) {
    return; // no data yet — draw nothing rather than guess
  }

  GRect bounds = layer_get_bounds(layer);
  int w = bounds.size.w;
  int h = bounds.size.h;
  graphics_context_set_fill_color(ctx, GColorBlack);
  graphics_context_set_stroke_color(ctx, GColorBlack);

  if (s_weather_condition == WEATHER_CLEAR) {
    // Sun: filled circle + four short cardinal rays. Proportional to the
    // layer's own size so shrinking/growing the icon doesn't need retuning.
    GPoint center = GPoint(w / 2, h / 2);
    int r = (w < h ? w : h) / 3;
    if (r < 2) r = 2;
    graphics_fill_circle(ctx, center, r);
    graphics_draw_line(ctx, GPoint(center.x, 0), GPoint(center.x, 1));
    graphics_draw_line(ctx, GPoint(center.x, h - 2), GPoint(center.x, h - 1));
    graphics_draw_line(ctx, GPoint(0, center.y), GPoint(1, center.y));
    graphics_draw_line(ctx, GPoint(w - 2, center.y), GPoint(w - 1, center.y));
    return;
  }

  // Everything else starts from the same simple cloud blob, sized to leave
  // room below for an accent (rain/snow/storm) when one is needed.
  bool has_accent = (s_weather_condition != WEATHER_CLOUDY);
  int cloud_h = has_accent ? (h * 3) / 5 : (h * 4) / 5;
  if (cloud_h < 3) cloud_h = 3;
  int cloud_y = has_accent ? 0 : (h - cloud_h) / 2;
  GRect cloud = GRect(1, cloud_y, w - 2, cloud_h);
  graphics_fill_rect(ctx, cloud, cloud_h / 2, GCornersAll);

  if (!has_accent) {
    return; // WEATHER_CLOUDY — cloud blob alone is enough
  }

  int accent_top = cloud_y + cloud_h;
  int x1 = w / 4;
  int x2 = w / 2;
  int x3 = (w * 3) / 4;

  switch (s_weather_condition) {
    case WEATHER_RAIN:
      graphics_draw_line(ctx, GPoint(x1, accent_top), GPoint(x1 - 1, h - 1));
      graphics_draw_line(ctx, GPoint(x2, accent_top), GPoint(x2 - 1, h - 1));
      graphics_draw_line(ctx, GPoint(x3, accent_top), GPoint(x3 - 1, h - 1));
      break;
    case WEATHER_SNOW: {
      int y = accent_top + (h - accent_top) / 2;
      graphics_fill_rect(ctx, GRect(x1, y, 1, 1), 0, GCornerNone);
      graphics_fill_rect(ctx, GRect(x2, y, 1, 1), 0, GCornerNone);
      graphics_fill_rect(ctx, GRect(x3, y, 1, 1), 0, GCornerNone);
      break;
    }
    case WEATHER_STORM:
      graphics_draw_line(ctx, GPoint(x2, accent_top), GPoint(x1, (accent_top + h) / 2));
      graphics_draw_line(ctx, GPoint(x1, (accent_top + h) / 2), GPoint(x2, (accent_top + h) / 2));
      graphics_draw_line(ctx, GPoint(x2, (accent_top + h) / 2), GPoint(x1, h - 1));
      break;
    default:
      break;
  }
}

static void inbox_received_callback(DictionaryIterator *iterator, void *context) {
  Tuple *code_tuple = dict_find(iterator, MESSAGE_KEY_WEATHER_CODE);
  if (code_tuple) {
    s_weather_condition = weather_code_to_condition((int)code_tuple->value->int32);
    if (s_weather_icon_layer) {
      layer_mark_dirty(s_weather_icon_layer);
    }
  }
}

// Single bordered "module": "Battery" label on the left, bar on the right —
// boxed together so it reads as one distinct segment of the face.
static void battery_module_update_proc(Layer *layer, GContext *ctx) {
  GRect bounds = layer_get_bounds(layer);

  // Outer box
  graphics_context_set_stroke_color(ctx, GColorBlack);
  graphics_draw_rect(ctx, GRect(0, 0, bounds.size.w, bounds.size.h));

  // "Battery" label, left side — bold. Measure the actual rendered text height
  // and center it exactly (font line-height padding otherwise throws off any
  // fixed offset guess), rather than assuming a fixed offset.
  GFont battery_font = fonts_get_system_font(FONT_KEY_GOTHIC_14_BOLD);
  GRect text_box = GRect(6, 0, 52, bounds.size.h);
  GSize text_size = graphics_text_layout_get_content_size(
      "Battery", battery_font, text_box, GTextOverflowModeTrailingEllipsis, GTextAlignmentLeft);
  // Measured content size still includes a few px of font leading below the
  // visible ink, so nudge up slightly from the naive centered position.
  text_box.origin.y = (bounds.size.h - text_size.h) / 2 - 3;
  text_box.size.h = text_size.h;

  graphics_context_set_text_color(ctx, GColorBlack);
  graphics_draw_text(ctx, "Battery", battery_font, text_box,
                      GTextOverflowModeTrailingEllipsis, GTextAlignmentLeft, NULL);

  // Bar, right side, close behind the label — fills/depletes with charge, no percent text
  GRect bar = GRect(62, (bounds.size.h - 8) / 2, bounds.size.w - 62 - 6, 8);
  graphics_draw_rect(ctx, bar);
  int inner_w = bar.size.w - 2;
  int fill_w = (inner_w * s_battery_level) / 100;
  if (fill_w > 0) {
    graphics_context_set_fill_color(ctx, GColorBlack);
    graphics_fill_rect(ctx, GRect(bar.origin.x + 1, bar.origin.y + 1, fill_w, bar.size.h - 2), 0, GCornerNone);
  }
}

static void battery_callback(BatteryChargeState state) {
  s_battery_level = state.charge_percent;
  if (s_battery_module_layer) {
    layer_mark_dirty(s_battery_module_layer);
  }
}

static void main_window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  window_set_background_color(window, GColorWhite);

  // Battery module — "Battery" label + bar together in one bordered box.
  // Side margins match the top margin (1px) so spacing is even all round.
  s_battery_module_layer = layer_create(GRect(1, 1, 142, 18));
  layer_set_update_proc(s_battery_module_layer, battery_module_update_proc);
  layer_add_child(root, s_battery_module_layer);

  // Time — raised to sit right under the battery module, with more room
  // left before the character art below
  s_time_layer = text_layer_create(GRect(0, 19, 144, 42));
  text_layer_set_background_color(s_time_layer, GColorClear);
  text_layer_set_text_color(s_time_layer, GColorBlack);
  text_layer_set_font(s_time_layer, fonts_get_system_font(FONT_KEY_LECO_42_NUMBERS));
  text_layer_set_text_alignment(s_time_layer, GTextAlignmentCenter);
  layer_add_child(root, text_layer_get_layer(s_time_layer));

  // Weather icon — small, below the time's right-hand (minutes) digits.
  // Fuecoco is drawn *after* this (see below) with an opaque background, so
  // the icon must sit fully clear of its GRect (x>=113), not just clear of
  // its ink, or Fuecoco's white background paints over/cuts off the icon.
  s_weather_icon_layer = layer_create(GRect(115, 78, 21, 21));
  layer_set_update_proc(s_weather_icon_layer, weather_icon_update_proc);
  layer_add_child(root, s_weather_icon_layer);

  // Fuecoco — unchanged position/size
  s_fuecoco_bitmap = gbitmap_create_with_resource(RESOURCE_ID_IMAGE_FUECOCO);
  s_fuecoco_layer = bitmap_layer_create(GRect(31, 68, 82, 98));
  bitmap_layer_set_bitmap(s_fuecoco_layer, s_fuecoco_bitmap);
  bitmap_layer_set_compositing_mode(s_fuecoco_layer, GCompOpAssign);
  layer_add_child(root, bitmap_layer_get_layer(s_fuecoco_layer));

  s_battery_level = battery_state_service_peek().charge_percent;
  update_time();
}

static void main_window_unload(Window *window) {
  layer_destroy(s_battery_module_layer);

  text_layer_destroy(s_time_layer);

  layer_destroy(s_weather_icon_layer);

  bitmap_layer_destroy(s_fuecoco_layer);
  gbitmap_destroy(s_fuecoco_bitmap);
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
  app_message_open(128, 128);
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
