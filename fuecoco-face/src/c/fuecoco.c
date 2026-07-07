#include <pebble.h>

static Window *s_main_window;

static Layer *s_battery_module_layer;
static int s_battery_level;

static TextLayer *s_time_layer;

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

static void tick_handler(struct tm *tick_time, TimeUnits units_changed) {
  update_time();
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
