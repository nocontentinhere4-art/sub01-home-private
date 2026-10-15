"""Privacy, acknowledgement and physical-input wiring for the actual Slate UI.

These source contracts complement existing real HTTP/privacy tests; they do not
claim that the UI compiled or a browser page was opened in native runtime.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CPP=(ROOT/'tools/native_pc_bridge/Sub01HomeDeviceBridge.cpp').read_text()


def block(start,end):return CPP.split(start,1)[1].split(end,1)[0]


def test_address_ui_requires_real_focused_phone_browser_and_public_frame():
    opening=block('bool USub01HomeDeviceBridge::OpenPhoneAddress(){','\nvoid USub01HomeDeviceBridge::SubmitPhoneAddress')
    for gate in ['Private||LocalPrivacy||Token.IsEmpty()', 'FocusedDevice!=TEXT("phone")', 'PhoneApp!=TEXT("browser")', 'PhoneFrameId.IsEmpty()', '!GEngine||!GEngine->GameViewport']:
        assert gate in opening
    assert opening.index('return false;')<opening.index('AddressOpen=true;')
    assert 'FInputModeUIOnly' in opening and 'SetWidgetToFocus(AddressBox)' in opening
    assert 'https://example.com' in opening


def test_address_submission_is_bounded_frame_bound_and_acknowledged():
    submit=block('void USub01HomeDeviceBridge::SubmitPhoneAddress(){','\nvoid USub01HomeDeviceBridge::ClosePhoneAddress')
    for required in ['AddressPending','Private||LocalPrivacy','PhoneFrameId.IsEmpty()', 'AddressDraft.Len()>2048','https://','SetStringField(TEXT("frame_id"),PhoneFrameId)', 'Action(TEXT("phone"),Body', 'Request!=AddressRequest','Code==200&&Ok']:
        assert required in submit
    assert submit.index('AddressDraft.Len()>2048')<submit.index('Action(TEXT("phone"),Body')
    assert 'Your address is kept' in submit
    assert 'system(' not in submit and 'NativePhoneNavigate(' not in submit


def test_privacy_erases_address_and_invalidates_async_callbacks():
    closing=CPP.split('void USub01HomeDeviceBridge::ClosePhoneAddress(bool Discard){',1)[1]
    assert 'if(Discard)AddressDraft.Empty();' in closing
    assert 'AddressPending=false;++AddressRequest;' in closing
    assert 'RemoveViewportWidgetContent' in closing and 'AddressBox.Reset();' in closing
    clear=block('void USub01HomeDeviceBridge::Clear(){','\nvoid USub01HomeDeviceBridge::SetLocalPrivacy')
    assert 'ClosePhoneAddress(true);' in clear
    poll=block('void USub01HomeDeviceBridge::Poll(){','\nvoid USub01HomeDeviceBridge::FetchFrame')
    assert 'if(AddressOpen&&PhoneApp!=TEXT("browser"))ClosePhoneAddress(false);' in poll


def test_address_uses_released_key_and_text_input_precedes_device_shortcuts():
    processor=block('class FSub01DeviceInput:public IInputProcessor{','\n};')
    down=processor.split('bool HandleKeyDownEvent(',1)[1].split('bool HandleKeyUpEvent(',1)[0]
    assert down.index('IsComposingAddress()')<down.index('PhoneAction(')
    address=down.split('if(B->IsComposingAddress()){',1)[1].split('\n  }',1)[0]
    assert 'SubmitPhoneAddress()' in address and 'ClosePhoneAddress(false)' in address
    assert 'return false;' in address
    up=processor.split('bool HandleKeyUpEvent(',1)[1]
    assert 'EKeys::B&&AddressPressed' in up and 'B->OpenPhoneAddress()' in up
