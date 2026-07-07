#include <pebble.h>

static Window *s_main_window;

static TextLayer *s_time_layer;
static TextLayer *s_date_layer;

static GBitmap *s_fuecoco_bitmap;
static BitmapLayer *s_fuecoco_layer;

static void update_display() {
  time_t now = time(NULL);
  struct tm *t = localtime(&now);

  static char s_time_buf[8];
  strftime(s_time_buf, sizeof(s_time_buf),
           clock_is_24h_style() ? "%H:%M" : "%I:%M", t);
  text_layer_set_text(s_time_layer, s_time_buf);

  static char s_date_buf[16];
  strftime(s_date_buf, sizeof(s_date_buf), "%a %d %b", t);
  text_layer_set_text(s_date_layer, s_date_buf);
}

static void tick_handler(struct tm *tick_time, TimeUnits units_changed) {
  update_display();
}

static void main_window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  window_set_background_color(window, GColorWhite);

  // Time — top of screen
  s_time_layer = text_layer_create(GRect(0, 0, 144, 46));
  text_layer_set_background_color(s_time_layer, GColorClear);
  text_layer_set_text_color(s_time_layer, GColorBlack);
  text_layer_set_font(s_time_layer, fonts_get_system_font(FONT_KEY_LECO_42_NUMBERS));
  text_layer_set_text_alignment(s_time_layer, GTextAlignmentCenter);
  layer_add_child(root, text_layer_get_layer(s_time_layer));

  // Date — just below the time, still well clear of the character art below
  s_date_layer = text_layer_create(GRect(0, 46, 144, 20));
  text_layer_set_background_color(s_date_layer, GColorClear);
  text_layer_set_text_color(s_date_layer, GColorBlack);
  text_layer_set_font(s_date_layer, fonts_get_system_font(FONT_KEY_GOTHIC_18_BOLD));
  text_layer_set_text_alignment(s_date_layer, GTextAlignmentCenter);
  layer_add_child(root, text_layer_get_layer(s_date_layer));

  // Fuecoco — dominant character art below the time/date, centered horizontally
  s_fuecoco_bitmap = gbitmap_create_with_resource(RESOURCE_ID_IMAGE_FUECOCO);
  s_fuecoco_layer = bitmap_layer_create(GRect(31, 68, 82, 98));
  bitmap_layer_set_bitmap(s_fuecoco_layer, s_fuecoco_bitmap);
  bitmap_layer_set_compositing_mode(s_fuecoco_layer, GCompOpAssign);
  layer_add_child(root, bitmap_layer_get_layer(s_fuecoco_layer));

  update_display();
}

static void main_window_unload(Window *window) {
  text_layer_destroy(s_time_layer);
  text_layer_destroy(s_date_layer);

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
  update_display();
}

static void deinit() {
  window_destroy(s_main_window);
}

int main(void) {
  init();
  app_event_loop();
  deinit();
}
