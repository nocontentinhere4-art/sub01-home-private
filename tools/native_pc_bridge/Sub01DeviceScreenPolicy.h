#pragma once
// Browser parity for what the native phone and TV may show, as pure decisions
// with no engine types (tests compile this header with a plain C++ compiler).
// Sources: web/house/phone_screen.mjs (a page only while he is on the phone)
// and web/house/home.js minecraftBitmapPainter (Minecraft only with a frame).
struct FSub01DeviceScreenInputs{
 bool PublicHome=false;        // fresh /devices/state, privacy false, local privacy off
 bool PhoneActivity=false;     // home.activity == "phone"
 bool PhoneFrame=false;        // phone_browser_screen.frame_id is present
 bool MinecraftSelected=false; // home.console_game == "minecraft"
 bool MinecraftEnabled=false;  // minecraft.enabled
 bool MinecraftFrame=false;    // minecraft.has_frame
};
// The phone shows the actual browser page only while he uses the phone.
inline bool Sub01PhoneShowsPage(const FSub01DeviceScreenInputs& In){
 return In.PublicHome&&In.PhoneActivity&&In.PhoneFrame;
}
// The TV requests a Minecraft JPEG only when the selected game has a live frame;
// otherwise it stays blank instead of polling a 404 every tick.
inline bool Sub01TVFetchesMinecraft(const FSub01DeviceScreenInputs& In){
 return In.PublicHome&&In.MinecraftSelected&&In.MinecraftEnabled&&In.MinecraftFrame;
}
