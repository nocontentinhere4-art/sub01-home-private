#pragma once
// Native Notes composer rules with no engine types (tests compile this header
// with a plain C++ compiler). The backend (POST /api/home/phone/action
// {action:"save_note",frame_id,title?,text}) is authoritative; these checks
// only refuse drafts it would refuse and decide what a reply means.
#include <cstddef>

enum class ESub01NoteCheck{Ok,EmptyText,TitleTooLong,TextTooLong,CombinedTooLong};
enum class ESub01NoteSave{Saved,Stale,Rejected,Failed};

template<class C> inline bool Sub01NoteSpace(C Ch){
 return Ch==C(' ')||Ch==C('\t')||Ch==C('\n')||Ch==C('\r')||Ch==C('\v')||Ch==C('\f');
}
// Length without leading/trailing whitespace (as the backend's str.strip()).
template<class C> inline std::size_t Sub01TrimmedLength(const C* Chars,std::size_t Length){
 if(!Chars)return 0;std::size_t Begin=0,End=Length;
 while(Begin<End&&Sub01NoteSpace(Chars[Begin]))++Begin;
 while(End>Begin&&Sub01NoteSpace(Chars[End-1]))--End;
 return End-Begin;
}
// Title at most 120, nonempty text at most 2000, and the saved note
// (trimmed title + newline + trimmed text) at most 2000 characters.
template<class C> inline ESub01NoteCheck Sub01CheckNote(const C* Title,std::size_t TitleLength,const C* Text,std::size_t TextLength){
 if(TitleLength>120)return ESub01NoteCheck::TitleTooLong;
 if(TextLength>2000)return ESub01NoteCheck::TextTooLong;
 const std::size_t Body=Sub01TrimmedLength(Text,TextLength);if(!Body)return ESub01NoteCheck::EmptyText;
 const std::size_t Heading=Sub01TrimmedLength(Title,TitleLength);
 return (Heading?Heading+1:0)+Body>2000?ESub01NoteCheck::CombinedTooLong:ESub01NoteCheck::Ok;
}
// Success only for HTTP 200 whose JSON says ok:true.
inline ESub01NoteSave Sub01NoteSaveOutcome(int Code,bool JsonOk){
 if(Code==200)return JsonOk?ESub01NoteSave::Saved:ESub01NoteSave::Failed;
 if(Code==409)return ESub01NoteSave::Stale;
 if(Code==400)return ESub01NoteSave::Rejected;
 return ESub01NoteSave::Failed;
}
inline const char* Sub01NoteMessage(ESub01NoteCheck Check){
 switch(Check){
  case ESub01NoteCheck::EmptyText:return "Write the note text before saving.";
  case ESub01NoteCheck::TitleTooLong:return "The title can be at most 120 characters.";
  case ESub01NoteCheck::TextTooLong:return "The note text can be at most 2000 characters.";
  case ESub01NoteCheck::CombinedTooLong:return "Title and text together can be at most 2000 characters.";
  default:return "";
 }
}
inline const char* Sub01NoteMessage(ESub01NoteSave Save){
 switch(Save){
  case ESub01NoteSave::Saved:return "Note saved.";
  case ESub01NoteSave::Stale:return "The phone changed. Open Notes again, then save; your draft is kept.";
  case ESub01NoteSave::Rejected:return "The note was not accepted; your draft is kept.";
  default:return "The note could not be saved; your draft is kept.";
 }
}
// Composer state. The owner keeps the draft text; this decides when it may be
// edited, sent, kept or cleared. A reply belongs only to the request it answers.
struct FSub01NoteComposer{
 bool Open=false,Saving=false;unsigned long long Request=0;
 // Only on the phone's own Notes app, with a current frame, while the home is public.
 bool TryOpen(bool PublicHome,bool NotesApp,bool HasFrame){
  if(!PublicHome||!NotesApp||!HasFrame)return false;Open=true;return true;
 }
 // Returns the request id for a valid draft, or 0 (nothing sent).
 unsigned long long TryBeginSave(ESub01NoteCheck Check){
  if(!Open||Saving||Check!=ESub01NoteCheck::Ok)return 0;Saving=true;return ++Request;
 }
 // True only when this reply confirms the save: then (and only then) clear the draft.
 bool Finish(unsigned long long Id,ESub01NoteSave Outcome){
  if(!Saving||Id!=Request)return false;Saving=false;
  if(Outcome!=ESub01NoteSave::Saved)return false;Open=false;return true;
 }
 // Close the editor and keep the draft (Escape, focus released).
 void Close(){Open=false;}
 // Privacy or EndPlay: the owner clears every draft; any late reply is ignored.
 void Reset(){Open=false;Saving=false;++Request;}
};
