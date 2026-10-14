"""Native phone Notes composer: compiled draft rules/state, backend parity and bridge contract.

No request reaches a backend here and no saved note is created or changed.
"""
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'tools/native_pc_bridge'
CPP = (BRIDGE / 'Sub01HomeDeviceBridge.cpp').read_text()
HEADER = (BRIDGE / 'Sub01HomeDeviceBridge.h').read_text()


def backend_accepts(title, text):
    """The rule both the device proxy and /api/home/phone/action enforce for save_note."""
    if not isinstance(title, str) or len(title) > 120 or not isinstance(text, str) or len(text) > 2000 or not text.strip():
        return False
    return len((title.strip() + '\n' if title.strip() else '') + text.strip()) <= 2000


def test_backend_rule_is_the_one_mirrored():
    proxy = (ROOT / 'scripts/home_device_proxy.py').read_text()
    api = (ROOT / 'home_api.py').read_text()
    assert "len(title) > 120" in proxy and "len(text) > 2000 or not text.strip()" in proxy
    assert "len((title.strip() + '\\n' if title.strip() else '') + text.strip()) > 2000" in proxy
    assert "if len(combined) > 2000:" in api and "combined = title + '\\n' + text if title else text" in api


def compile_and_run(tmp, source):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    cpp, exe = Path(tmp) / 'note.cpp', Path(tmp) / 'note'
    cpp.write_text(source)
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', f'-I{BRIDGE}', str(cpp), '-o', str(exe)], check=True, capture_output=True)
    return subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout


def test_draft_check_matches_backend_on_boundaries_and_random_drafts():
    rng = random.Random(20261014)
    pieces = ['', ' ', '\n', '\t', 'a', 'word ', ' x ', '\r\n']
    cases = [('', ''), ('', '   '), ('', 'a'), ('T' * 120, 'a'), ('T' * 121, 'a'), ('', 'b' * 2000), ('', 'b' * 2001),
             ('T' * 120, 'b' * 1879), ('T' * 120, 'b' * 1880), ('  ', 'b' * 2000), ('  T  ', '  ' + 'b' * 1998 + '  '),
             ('T' * 119, '\n' + 'b' * 1880 + '\n'), (' ' * 120, ' ' * 1990 + 'x')]
    for _ in range(400):
        title = ''.join(rng.choice(pieces) for _ in range(rng.randrange(0, 40)))
        text = ''.join(rng.choice(pieces) for _ in range(rng.randrange(0, 60)))
        if rng.random() < .3:
            title += 'T' * rng.randrange(80, 130)
        if rng.random() < .3:
            text += 'b' * rng.randrange(1800, 2100)
        cases.append((title, text))
    lines = []
    for title, text in cases:
        enc = lambda s: ','.join(str(ord(c)) for c in s) or '0'
        lines.append(f'{{const char16_t T[]={{{enc(title)}}};const char16_t X[]={{{enc(text)}}};'
                     f'std::printf("%d\\n",int(Sub01CheckNote(T,{len(title)},X,{len(text)})));}}')
    with tempfile.TemporaryDirectory() as tmp:
        out = compile_and_run(tmp, '#include <cstdio>\n#include "Sub01NoteDraft.h"\nint main(){\n' + '\n'.join(lines) + '\nreturn 0;}\n')
    results = [int(v) for v in out.split()]
    assert len(results) == len(cases)
    for (title, text), code in zip(cases, results):
        assert (code == 0) == backend_accepts(title, text), (len(title), len(text), code)
    # The specific refusal is named (Ok, EmptyText, TitleTooLong, TextTooLong, CombinedTooLong).
    assert results[:13] == [1, 1, 0, 0, 2, 0, 3, 0, 4, 0, 3, 0, 0]


def test_save_outcome_and_composer_state_compiled():
    source = r'''
#include <initializer_list>
#include "Sub01NoteDraft.h"
#define CHECK(c,n) if(!(c))return n;
int main(){
 CHECK(Sub01NoteSaveOutcome(200,true)==ESub01NoteSave::Saved,1)
 CHECK(Sub01NoteSaveOutcome(200,false)==ESub01NoteSave::Failed,2)   // HTTP 200 alone is not success
 CHECK(Sub01NoteSaveOutcome(409,false)==ESub01NoteSave::Stale,3)
 CHECK(Sub01NoteSaveOutcome(400,false)==ESub01NoteSave::Rejected,4)
 for(int Code:{0,403,413,500,502,503})CHECK(Sub01NoteSaveOutcome(Code,true)==ESub01NoteSave::Failed,5)
 FSub01NoteComposer C;
 CHECK(!C.TryOpen(false,true,true)&&!C.TryOpen(true,false,true)&&!C.TryOpen(true,true,false)&&!C.Open,6)
 CHECK(!C.TryBeginSave(ESub01NoteCheck::Ok),7)                        // closed: nothing sent
 CHECK(C.TryOpen(true,true,true)&&C.Open,8)
 CHECK(!C.TryBeginSave(ESub01NoteCheck::EmptyText)&&!C.Saving,9)       // invalid draft: nothing sent
 unsigned long long A=C.TryBeginSave(ESub01NoteCheck::Ok);CHECK(A&&C.Saving,10)
 CHECK(!C.TryBeginSave(ESub01NoteCheck::Ok),11)                        // one save at a time
 CHECK(!C.Finish(A+1,ESub01NoteSave::Saved)&&C.Saving,12)             // not this request's reply
 CHECK(!C.Finish(A,ESub01NoteSave::Stale)&&C.Open&&!C.Saving,13)      // stale: draft and editor kept
 unsigned long long B=C.TryBeginSave(ESub01NoteCheck::Ok);
 CHECK(!C.Finish(B,ESub01NoteSave::Rejected)&&C.Open,14)
 B=C.TryBeginSave(ESub01NoteCheck::Ok);CHECK(!C.Finish(B,ESub01NoteSave::Failed)&&C.Open,15)
 B=C.TryBeginSave(ESub01NoteCheck::Ok);CHECK(C.Finish(B,ESub01NoteSave::Saved)&&!C.Open&&!C.Saving,16)  // only now clear
 CHECK(C.TryOpen(true,true,true),17)
 B=C.TryBeginSave(ESub01NoteCheck::Ok);C.Reset();                      // privacy/EndPlay during a save
 CHECK(!C.Open&&!C.Saving&&!C.Finish(B,ESub01NoteSave::Saved),18)     // the late success is ignored
 CHECK(C.TryOpen(true,true,true),19)
 B=C.TryBeginSave(ESub01NoteCheck::Ok);C.Close();                      // Escape while saving keeps the draft
 CHECK(!C.Open&&C.Finish(B,ESub01NoteSave::Saved),20)                  // a confirmed save still clears it
 return 0;}
'''
    with tempfile.TemporaryDirectory() as tmp:
        compile_and_run(tmp, source)


def block(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def test_editor_keys_reach_text_widgets_and_never_the_operator():
    processor = block(CPP, 'class FSub01DeviceInput:public IInputProcessor{', '\n};')
    down = block(processor, 'bool HandleKeyDownEvent(', ' bool HandleKeyUpEvent(')
    composing = block(down, 'if(B->IsComposingNote()){', '\n  }\n')
    # While composing, only Escape (close, keep draft) and Ctrl+Enter (save) are taken; all else passes through.
    assert composing.strip().endswith('return false;')
    assert 'if(K==EKeys::Escape){B->CloseNoteComposer(false);return true;}' in composing
    assert 'if(K==EKeys::Enter&&Event.IsControlDown()){B->SubmitNoteComposer();return true;}' in composing
    assert 'PhoneAction' not in composing and 'BackSpace' not in composing
    # The composing check runs before any phone key action (Backspace=back, Enter=close_notice).
    assert down.index('B->IsComposingNote()') < down.index('PhoneAction(TEXT("back"))')
    up = block(processor, 'bool HandleKeyUpEvent(', ' bool HandleMouseMoveEvent(')
    assert up.index('B->IsComposingNote())return false;') < up.index('SetPongDirection')
    assert '!Bridge->IsComposingNote()' in block(processor, 'bool HandleMouseMoveEvent(', '}')
    # N opens on release, so its character is not typed into the new editor.
    assert 'if(K==EKeys::N)NotePressed=true;' in down and 'OpenNoteComposer' not in down
    assert 'if(Event.GetKey()==EKeys::N&&NotePressed){NotePressed=false;if(B->GetFocusedDevice()==TEXT("phone"))B->OpenNoteComposer();return true;}' in up
    # Game input is UI-only while editing (no WASD movement), and restored after.
    opening = block(CPP, 'bool USub01HomeDeviceBridge::OpenNoteComposer(){', '\nvoid USub01HomeDeviceBridge::ReadNoteDraft')
    assert 'FInputModeUIOnly Mode;Mode.SetWidgetToFocus(NoteTextBox);' in opening and 'Player->SetInputMode(Mode);' in opening
    closing = block(CPP, 'void USub01HomeDeviceBridge::CloseNoteComposer(bool Discard){', '\nvoid USub01HomeDeviceBridge::ShowNoteStatus')
    assert 'Player->SetInputMode(FInputModeGameOnly());' in closing


def test_editor_opens_only_on_notes_and_privacy_erases_every_draft():
    opening = block(CPP, 'bool USub01HomeDeviceBridge::OpenNoteComposer(){', '\nvoid USub01HomeDeviceBridge::ReadNoteDraft')
    assert "NoteComposer.TryOpen(!Private&&!LocalPrivacy&&!Token.IsEmpty(),PhoneApp==TEXT(\"notes\"),!PhoneFrameId.IsEmpty())" in opening
    poll = block(CPP, 'void USub01HomeDeviceBridge::Poll(){', '\nvoid USub01HomeDeviceBridge::FetchFrame')
    assert 'PhoneApp.Empty();' in poll and 'if(Screen.PhoneAppFrame&&State->TryGetObjectField(TEXT("phone_screen"),PhoneScreen)' in poll
    # Clear() runs on backend privacy, unknown state, local privacy and EndPlay; it erases first.
    clear = block(CPP, 'void USub01HomeDeviceBridge::Clear(){', '\n')
    assert clear.startswith('CloseNoteComposer(true);PhoneApp.Empty();++Generation;')
    assert 'void USub01HomeDeviceBridge::EndPlay(const EEndPlayReason::Type Reason){Clear();' in CPP
    assert 'void USub01HomeDeviceBridge::SetLocalPrivacy(bool Hidden){if(Hidden==LocalPrivacy)return;LocalPrivacy=Hidden;if(Hidden)Clear();}' in CPP
    assert 'if(!PublicHome(State)){Clear();return;}' in poll
    closing = block(CPP, 'void USub01HomeDeviceBridge::CloseNoteComposer(bool Discard){', '\nvoid USub01HomeDeviceBridge::ShowNoteStatus')
    assert 'if(Discard){NoteComposer.Reset();DraftTitle.Empty();DraftText.Empty();NoteStatusText.Empty();}' in closing
    # Editor text is erased from the widgets and the widget removed in every close.
    for step in ('NoteTitleBox->SetText(FText::GetEmpty());', 'NoteTextBox->SetText(FText::GetEmpty());',
                 'RemoveViewportWidgetContent(NoteWidget.ToSharedRef());', 'NoteWidget.Reset();'):
        assert step in closing
    # Releasing focus closes the editor but keeps the draft.
    assert 'void USub01HomeDeviceBridge::ReleaseFocus(){if(NoteComposer.Open)CloseNoteComposer(false);' in CPP


def test_save_uses_authenticated_action_and_reports_only_confirmed_success():
    save = block(CPP, 'void USub01HomeDeviceBridge::PhoneSaveNote(', '\nbool USub01HomeDeviceBridge::OpenNoteComposer')
    assert 'Sub01CheckNote(*Title,size_t(Title.Len()),*Text,size_t(Text.Len()))' in save
    assert "if(PhoneFrameId.IsEmpty()||PhoneApp!=TEXT(\"notes\"))" in save
    for field in ('TEXT("action"),TEXT("save_note")', 'TEXT("frame_id"),PhoneFrameId', 'TEXT("text"),Text'):
        assert field in save
    assert 'if(!Title.TrimStartAndEnd().IsEmpty())B->SetStringField(TEXT("title"),Title);' in save
    assert 'Action(TEXT("phone"),B,[this,Id](int32 Code,const FString& Reply){' in save
    reply = save.split('Action(TEXT("phone"),B,', 1)[1]
    # JSON ok:true is read only from a 200 reply; superseded replies are dropped before anything else.
    assert 'if(Code==200&&FJsonSerializer::Deserialize(' in reply and 'TryGetBoolField(TEXT("ok"),Ok)' in reply
    assert reply.index('if(!NoteComposer.Saving||Id!=NoteComposer.Request)return;') < reply.index('Sub01NoteSaveOutcome(Code,Ok)')
    # The draft is emptied only inside the confirmed-save branch.
    assert reply.count('DraftTitle.Empty();DraftText.Empty();') == 1
    assert 'if(NoteComposer.Finish(Id,Outcome)){DraftTitle.Empty();DraftText.Empty();CloseNoteComposer(false);}' in reply
    action = block(CPP, 'void USub01HomeDeviceBridge::Action(', '\nvoid USub01HomeDeviceBridge::PhoneAction')
    # Same authenticated loopback action route; every path answers the caller once or not at all after privacy.
    assert 'R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/action"));' in action
    assert 'R->SetHeader(TEXT("X-Admin-Token"),Token);' in action
    assert 'if(Private||LocalPrivacy||Token.IsEmpty()){if(*Result)(*Result)(0,FString());return;}' in action
    assert 'if(Epoch!=Generation)return;(*Result)(' in action
    assert 'if(!R->ProcessRequest()&&*Result)(*Result)(0,FString());' in action
    assert 'if(!PublicHome(Before)){Clear();return;}' in action   # privacy: Clear resets the composer


def test_header_declarations_and_staging():
    for decl in ('void PhoneSaveNote(const FString& Title,const FString& Text);', 'bool OpenNoteComposer();',
                 'void CloseNoteComposer(bool Discard);', 'void SubmitNoteComposer();',
                 'bool IsComposingNote()const{return NoteComposer.Open;}',
                 'void Action(FName Device,const TSharedPtr<FJsonObject>& Body,TFunction<void(int32,const FString&)> Done=nullptr);'):
        assert decl in HEADER
    assert '#include "Sub01NoteDraft.h"' in HEADER
    stage = (ROOT / 'tools/stage_unreal_home_runtime.py').read_text()
    assert "'Sub01DeviceScreenPolicy.h','Sub01NoteDraft.h']" in stage
    # Every Slate widget used has its header.
    for widget, include in (('SEditableTextBox', 'Widgets/Input/SEditableTextBox.h'), ('SMultiLineEditableTextBox', 'Widgets/Input/SMultiLineEditableTextBox.h'),
                            ('SButton', 'Widgets/Input/SButton.h'), ('STextBlock', 'Widgets/Text/STextBlock.h'),
                            ('SVerticalBox', 'Widgets/SBoxPanel.h'), ('SBorder', 'Widgets/Layout/SBorder.h'), ('SBox', 'Widgets/Layout/SBox.h')):
        assert re.search(rf'\b{widget}\b', CPP) and f'#include "{include}"' in CPP
