#pragma once
// Browser parity for what the native phone and TV may show, as pure decisions
// with no engine types (tests compile this header with a plain C++ compiler).
// Sources: web/house/phone_screen.mjs (a page only while he is on the phone)
// and web/house/home.js minecraftBitmapPainter (Minecraft only with a frame).
struct FSub01DeviceScreenInputs{
 bool PublicHome=false;        // fresh /devices/state, privacy false, local privacy off
 bool PhoneActivity=false;     // home.activity == "phone"
 bool PhoneFrame=false;        // phone_browser_screen.frame_id is present
 bool PhoneAppFrame=false;     // a current phone app frame identity (backend producer; schema pending)
 bool MinecraftSelected=false; // home.console_game == "minecraft"
 bool MinecraftEnabled=false;  // minecraft.enabled
 bool MinecraftFrame=false;    // minecraft.has_frame
};
// Which actual phone frame may be shown: the browser page only while he uses the
// phone or an operator physically focuses it; otherwise the backend's app frame (home screen, notes, messages) if any.
enum class ESub01PhoneFrame{None,BrowserPage,AppFrame};
inline ESub01PhoneFrame Sub01PhoneFrame(const FSub01DeviceScreenInputs& In,bool PhysicalPhoneFocus=false){
 if(!In.PublicHome)return ESub01PhoneFrame::None;
 if((In.PhoneActivity||PhysicalPhoneFocus)&&In.PhoneFrame)return ESub01PhoneFrame::BrowserPage;
 return In.PhoneAppFrame?ESub01PhoneFrame::AppFrame:ESub01PhoneFrame::None;
}
// The TV requests a Minecraft JPEG only when the selected game has a live frame;
// otherwise it stays blank instead of polling a 404 every tick.
inline bool Sub01TVFetchesMinecraft(const FSub01DeviceScreenInputs& In){
 return In.PublicHome&&In.MinecraftSelected&&In.MinecraftEnabled&&In.MinecraftFrame;
}
