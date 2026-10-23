"""`-Sub01StreamerVisual` v2 installer (tools/native_streamer_visual_v2/install.py) on copies of the pod sources.

No engine here. The installer runs on copies of the pod files in a temporary directory: dry run, real install, refusal
of a second install, refusal of a missing anchor (nothing written), brace/marker checks and the v1 contract.

Compile coverage: the repo's stub shim (tools/native_adapters_ue_shim.py, used by check_native_adapters_compile_closure)
covers the freshly staged module only and cannot express the pod sources (FPoseContext(proxy), ForEachBoneIndex,
native_cinematic_proxy.inc, JSON writers, ...). So this test brings its own syntax stub (STUB below, NOT Unreal Engine),
reuses the closure checker's literal stripper, compilers and UE-like warning flags, and compiles with -fsyntax-only:
the whole patched FSub01HandsProxy + NativePostEvaluateAnimation against the whole patched Sub01HomeHands.h, and the
whole patched TickPrivateStreamerVisual + every v2 method against the patched streamer fields of Sub01HomeLab.h.
Engine API signatures are only checked against the stub. A small driver then RUNS the patched character logic
(debounce, sway/nod bounds, determinism, monitor framing, 1 s camera blend) with the stub's real math.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / 'tools/native_streamer_visual_v2/install.py'
SOURCE = Path(os.environ.get('SUB01_STREAMER_V2_SOURCE',
                             '/tmp/claude-0/-home-user/2e1bb17a-3c9c-5a3e-a624-f8c5a84eac68/scratchpad/native-src'))
PATCHED = ('Sub01HomeLab.cpp', 'Sub01HomeLab.h', 'Sub01HomeHands.cpp', 'Sub01HomeHands.h')
NEEDED = PATCHED + ('Sub01PCBridge.h',)
MARKER = '// SUB01_STREAMER_VISUAL_V2'

sys.path.insert(0, str(ROOT / 'tools'))
import check_native_adapters_compile_closure as closure  # noqa: E402  (strip, brace_walk, compilers, flags)

pytestmark = pytest.mark.skipif(not all((SOURCE / n).is_file() for n in NEEDED),
                                reason=f'pod source copies not found in {SOURCE} (set SUB01_STREAMER_V2_SOURCE)')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lf(path: Path) -> str:
    return path.read_bytes().decode('utf-8').replace('\r\n', '\n')


def install(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod(tmp_path) -> Path:
    target = tmp_path / 'src'
    shutil.copytree(SOURCE, target)
    return target


@pytest.fixture(scope='module')
def patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('patched') / 'src'
    shutil.copytree(SOURCE, target)
    code, report = install(target)
    assert code == 0, report
    return target


# ------------------------------------------------------------------------------------------------ installer
def test_dry_run_plans_every_anchor_once_and_writes_nothing(pod):
    before = {p.name: sha(p) for p in pod.iterdir()}
    code, report = install(pod, '--dry-run')
    assert code == 0 and report['status'] == 'planned', report
    assert report['edits'] and all(e['count'] == 1 for e in report['edits'])
    assert {p.name: sha(p) for p in pod.iterdir()} == before
    for name in PATCHED:
        assert report['files'][name]['before_sha256'] == before[name]
        assert report['files'][name]['after_sha256'] != before[name]


def test_install_writes_exactly_the_planned_bytes(pod):
    before = {p.name: sha(p) for p in pod.iterdir()}
    code, planned = install(pod, '--dry-run')
    code, report = install(pod)
    assert code == 0 and report['status'] == 'applied', report
    for name in PATCHED:
        assert sha(pod / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod / name).read_bytes()
        ending = report['files'][name]['line_ending']
        assert raw.count(b'\r\n') == (raw.count(b'\n') if ending == 'CRLF' else 0)  # the file's own convention kept
    for name in set(before) - set(PATCHED):  # bridges, Build.cs, ini, seat header: untouched
        assert sha(pod / name) == before[name]
    assert not [p for p in pod.iterdir() if p.name.endswith('.v2tmp')]


def test_second_install_is_refused_and_changes_nothing(pod):
    assert install(pod)[0] == 0
    after = {p.name: sha(p) for p in pod.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, report = install(pod, *extra)
        assert code == 2 and report['status'] == 'refused' and 'already' in report['reason']
    assert {p.name: sha(p) for p in pod.iterdir()} == after


def test_missing_anchor_refuses_without_writing_any_file(pod):
    hands = pod / 'Sub01HomeHands.cpp'
    hands.write_bytes(hands.read_bytes().replace(b'Current.SetAccumulatedTime(.7f)', b'Current.SetAccumulatedTime(.75f)', 1))
    before = {p.name: sha(p) for p in pod.iterdir()}
    code, report = install(pod)
    assert code == 2 and 'anchor missing in Sub01HomeHands.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod.iterdir()} == before  # Sub01HomeLab.* had valid anchors and are untouched too


def test_pc_bridge_focus_query_is_required(pod):
    bridge = pod / 'Sub01PCBridge.h'
    bridge.write_bytes(bridge.read_bytes().replace(b'bool HasOperatorFocus() const', b'bool HasFocus() const'))
    code, report = install(pod)
    assert code == 2 and 'HasOperatorFocus' in report['reason']


def test_mixed_line_endings_are_refused(pod):
    header = pod / 'Sub01HomeHands.h'
    raw = header.read_bytes()
    header.write_bytes(raw.replace(b'\r\n', b'\n', 1) if b'\r\n' in raw else raw.replace(b'\n', b'\r\n', 1))
    code, report = install(pod)
    assert code == 2 and 'mixed line endings' in report['reason']


# ------------------------------------------------------------------------------------------------ patched text
def test_patched_files_balanced_and_marked(patched):
    for name in PATCHED:
        before, after = lf(SOURCE / name), lf(patched / name)
        assert closure.brace_walk(closure.strip(after)) == closure.brace_walk(closure.strip(before)), name
        assert after.count(MARKER + ' BEGIN') == after.count(MARKER + ' END') <= 1
        assert MARKER in after and MARKER not in before
        for opener, closer in ('()', '[]'):
            s = closure.strip(after)
            assert s.count(opener) - s.count(closer) == closure.strip(before).count(opener) - closure.strip(before).count(closer)


def test_v1_contract_unchanged(patched):
    cpp, proxy = lf(patched / 'Sub01HomeLab.cpp'), lf(patched / 'Sub01HomeHands.cpp')
    original = lf(SOURCE / 'Sub01HomeLab.cpp')
    tick = cpp[cpp.index('bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){'):]
    tick = tick[:tick.index('\nvoid ASub01HomeCharacter::ConfigureBedroomTVPlayer(){')]
    # every original line of the streamer branch survives verbatim, except the v1-only schema/source line (now v1 || v2)
    # and the per-tick focus release (now only when focused)
    old = original[original.index('bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){'):]
    old = old[:old.index('\nvoid ASub01HomeCharacter::ConfigureBedroomTVPlayer(){')]
    changed = {line for line in old.split('\n') if line not in tick.split('\n')}
    assert changed == {
        ' NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);',
        '   J->TryGetStringField(TEXT("schema"),Schema)&&Schema==TEXT("sub01.private-streamer-visual-event.v1")&&',
        '   J->TryGetStringField(TEXT("source"),Source)&&Source==TEXT("human_vagon_observation")&&J->TryGetStringField(TEXT("source_frame_id"),Frame)&&!Frame.IsEmpty()&&Frame.Len()<=128&&'}
    assert ' NativeSeatVerified=false;if(PCBridge&&PCBridge->HasOperatorFocus())PCBridge->SetOperatorFocus(false);' in tick
    assert '(Schema==TEXT("sub01.private-streamer-visual-event.v1")&&Source==TEXT("human_vagon_observation")&&J->TryGetStringField(TEXT("source_frame_id"),Frame)&&!Frame.IsEmpty()&&Frame.Len()<=128)' in tick
    for check in ('S.st_uid==getuid()&&!(S.st_mode&0077)', 'PID==FPlatformProcess::GetCurrentProcessId()', 'Start==PrivateSettingsStartTicks()',
                  'Epoch-At<=2', 'Until-At<=2', 'FMath::Abs(Yaw)<=20', 'FMath::Abs(Pitch)<=10', 'Nod>=0&&Nod<=1',
                  '"sub01.native-streamer-visual-receipt.v1"', 'R9_Sitting.R9_Sitting', 'SUB01_STREAMER_VISUAL_STARTED'):
        assert check in tick, check
    assert '  if(StreamerVisualActive&&!StreamerV2){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(.7f);Current.SetPlayRate(0);Progress=1;}' in proxy
    assert 'if(StreamerVisualSchemaVersion!=2){StreamerVisualActiveClip=StreamerVisualClip;StreamerVisualCameraTarget=TEXT("spectator");if(Anim)Anim->StreamerVisualV2=false;}' in cpp


def test_v2_contract_in_source(patched):
    cpp, header = lf(patched / 'Sub01HomeLab.cpp'), lf(patched / 'Sub01HomeLab.h')
    hands_h, proxy = lf(patched / 'Sub01HomeHands.h'), lf(patched / 'Sub01HomeHands.cpp')
    for text in ('Schema==TEXT("sub01.private-streamer-visual-event.v2")&&Source==TEXT("streamer_agent")',
                 'SUB01_STREAMER_VISUAL_CLIP_MISSING %s', 'Now-StreamerVisualStateAt>=.6', 'Wanted==TEXT("reacting")',
                 'Camera==TEXT("spectator")||Camera==TEXT("monitor")', 'Monitor(217,-367.67,114.75)', 'Pivot(214,-289,116)',
                 'Pivot+Facing*-70.+Side*45.+FVector(0,0,45)', '2*PI*.22*', '.6*FMath::Sin(W-1.1)',
                 'TEXT("schema_version")', 'TEXT("state")', 'TEXT("clip")', 'PCBridge->HasOperatorFocus()',
                 '/SupportedWebsite.SupportedWebsite', '/SupportedDeskTyping.SupportedDeskTyping', '/AuthoredReach.AuthoredReach'):
        assert text in cpp, text
    for state in ('idle', 'reading', 'typing', 'mouse', 'talking', 'reacting'):
        assert f'State!=TEXT("{state}")' in cpp
    assert 'UPROPERTY() TArray<TObjectPtr<UAnimSequence>> StreamerVisualV2Clips;' in header
    assert 'UPROPERTY() TObjectPtr<UAnimSequence> StreamerVisualActiveClip;' in header
    assert 'UPROPERTY(Transient) TObjectPtr<UAnimSequence> StreamerVisualFreezeSequence;' in hands_h
    # no new raw UObject pointer members: proxy keys are const void-like and only compared
    v2_proxy = proxy[proxy.index(MARKER + ' BEGIN'):proxy.index(MARKER + ' END')]
    assert 'const UAnimSequenceBase* Key=nullptr' in v2_proxy and 'Key->' not in v2_proxy
    # bones found like Head: exact name first, then a name ending with it; compact index checked like the head code
    assert 'Ref.FindBoneIndex(FName(Names[K]))' in v2_proxy and 'EndsWith(Names[K])' in v2_proxy
    assert v2_proxy.count('Compact.GetInt()') == 2


# ------------------------------------------------------------------------------------------------ compile
STUB = r'''#pragma once
// Syntax/runtime stub for tests/test_native_streamer_visual_v2.py: NOT Unreal Engine. Signatures mirror UE 5 (LWC
// doubles, TCHAR = char16_t on Linux, TObjectPtr, same-type FMath templates, compile-time printf checks for UE_LOG).
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <cfloat>
#include <cstdio>
#include <deque>
#include <memory>
#include <string>
#include <type_traits>
#include <initializer_list>
#include <utility>
#ifndef WITH_EDITOR
#define WITH_EDITOR 0
#endif
typedef std::int8_t int8; typedef std::uint8_t uint8; typedef std::int16_t int16; typedef std::uint16_t uint16;
typedef std::int32_t int32; typedef std::uint32_t uint32; typedef long long int64; typedef unsigned long long uint64;
typedef char16_t TCHAR;
#define TEXT(x) u##x
#define UCLASS(...)
#define USTRUCT(...)
#define UPROPERTY(...)
#define UFUNCTION(...)
#define SUB01HOMELAB_API
#define INDEX_NONE (-1)
#define PI (3.1415926535897932f)
class UClass;
class UAnimInstance;
// Only USub01HomeHandsInstance uses GENERATED_BODY in these units; its Super is UAnimInstance.
#define GENERATED_BODY() public: static UClass* StaticClass(){return nullptr;} typedef UAnimInstance Super; private:
namespace StubFormat {
enum class EArg { Int, Float, TStr, Ptr, Other };
template<class T> consteval EArg KindOf() {
 using U = std::remove_cvref_t<T>;
 if constexpr (std::is_same_v<U, bool> || std::is_integral_v<U> || std::is_enum_v<U>) return EArg::Int;
 else if constexpr (std::is_floating_point_v<U>) return EArg::Float;
 else if constexpr (std::is_array_v<U>) return std::is_same_v<std::remove_cv_t<std::remove_extent_t<U>>, TCHAR> ? EArg::TStr : EArg::Other;
 else if constexpr (std::is_pointer_v<U>) return std::is_same_v<std::remove_cv_t<std::remove_pointer_t<U>>, TCHAR> ? EArg::TStr : EArg::Ptr;
 else return EArg::Other;
}
void FormatArgumentMismatch();
void FormatArgumentCount();
template<class... T> struct TFormat {
 const TCHAR* Text;
 template<class S> consteval TFormat(const S& Literal) : Text(Literal) {
  constexpr EArg Kinds[] = {KindOf<T>()..., EArg::Other};
  const std::size_t Count = sizeof...(T);
  std::size_t Arg = 0;
  for (const TCHAR* P = Text; *P; ++P) {
   if (*P != u'%') continue;
   ++P;
   if (*P == u'%') continue;
   while (*P == u'-' || *P == u'+' || *P == u' ' || *P == u'#' || *P == u'0') ++P;
   while (*P >= u'0' && *P <= u'9') ++P;
   if (*P == u'.') { ++P; while (*P >= u'0' && *P <= u'9') ++P; }
   while (*P == u'l' || *P == u'h' || *P == u'z') ++P;
   if (Arg >= Count) FormatArgumentCount();
   const EArg Have = Kinds[Arg++];
   switch (*P) {
    case u'd': case u'i': case u'u': case u'x': case u'c': if (Have != EArg::Int) FormatArgumentMismatch(); break;
    case u'f': case u'e': case u'g': if (Have != EArg::Float) FormatArgumentMismatch(); break;
    case u's': if (Have != EArg::TStr) FormatArgumentMismatch(); break;
    case u'p': break;
    default: FormatArgumentMismatch();
   }
  }
  if (Arg != Count) FormatArgumentCount();
 }
};
template<class... T> void Log(TFormat<std::type_identity_t<T>...>, T&&...) {}
enum class EVerbosity { Fatal, Error, Warning, Display, Log, Verbose };
struct FCategory {};
}
inline StubFormat::FCategory LogTemp;
#define UE_LOG(Category, Verbosity, Format, ...) do { (void)&Category; (void)::StubFormat::EVerbosity::Verbosity; ::StubFormat::Log(Format __VA_OPT__(,) __VA_ARGS__); } while (0)
template<class T> class TArray {
 std::deque<T> Data;
public:
 TArray() = default;
 TArray(std::initializer_list<T> Items) : Data(Items) {}
 int32 Num() const { return int32(Data.size()); }
 bool IsValidIndex(int32 I) const { return I >= 0 && I < Num(); }
 int32 Add(const T& Item) { Data.push_back(Item); return Num() - 1; }
 void Reset() { Data.clear(); }
 void Empty() { Data.clear(); }
 void SetNum(int32 N) { Data.resize(std::size_t(N)); }
 void Init(const T& Value, int32 N) { Data.assign(std::size_t(N), Value); }
 T& operator[](int32 I) { return Data[std::size_t(I)]; }
 const T& operator[](int32 I) const { return Data[std::size_t(I)]; }
 T& Last() { return Data.back(); }
 const T& Last() const { return Data.back(); }
 auto begin() { return Data.begin(); } auto end() { return Data.end(); }
 auto begin() const { return Data.begin(); } auto end() const { return Data.end(); }
};
template<class T> class TSharedRef { public: std::shared_ptr<T> Ptr; T* operator->() const { return Ptr.get(); } T& operator*() const { return *Ptr; } };
template<class T> class TSharedPtr {
public:
 std::shared_ptr<T> Ptr;
 TSharedPtr() = default;
 TSharedPtr(std::nullptr_t) {}
 template<class U> TSharedPtr(const TSharedRef<U>& Ref) : Ptr(Ref.Ptr) {}
 bool IsValid() const { return bool(Ptr); }
 explicit operator bool() const { return bool(Ptr); }
 T* operator->() const { return Ptr.get(); }
 T* Get() const { return Ptr.get(); }
 void Reset() { Ptr.reset(); }
};
template<class T, class... A> TSharedRef<T> MakeShared(A&&... Args) { TSharedRef<T> Ref; Ref.Ptr = std::make_shared<T>(std::forward<A>(Args)...); return Ref; }
class FString {
 std::u16string Data;
public:
 FString() = default;
 FString(const TCHAR* Text) : Data(Text ? Text : u"") {}
 const TCHAR* operator*() const { return Data.c_str(); }
 bool IsEmpty() const { return Data.empty(); }
 int32 Len() const { return int32(Data.size()); }
 void Empty() { Data.clear(); }
 bool EndsWith(const TCHAR* Suffix) const { std::u16string S(Suffix); return Data.size() >= S.size() && Data.compare(Data.size() - S.size(), S.size(), S) == 0; }
 bool Contains(const TCHAR* Needle) const { auto Lower = [](std::u16string S) { for (auto& C : S) if (C >= u'A' && C <= u'Z') C = TCHAR(C + 32); return S; }; return Lower(Data).find(Lower(Needle)) != std::u16string::npos; }
 FString& operator+=(const FString& S) { Data += S.Data; return *this; }
 FString& operator+=(const TCHAR* S) { Data += S; return *this; }
 friend bool operator==(const FString& A, const FString& B) { return A.Data == B.Data; }
 friend bool operator==(const FString& A, const TCHAR* B) { return A.Data == B; }
 friend bool operator!=(const FString& A, const FString& B) { return A.Data != B.Data; }
 friend bool operator!=(const FString& A, const TCHAR* B) { return A.Data != B; }
};
class FName {
 FString Text;
public:
 FName() = default;
 FName(const TCHAR* Name) : Text(Name) {}
 FString ToString() const { return Text; }
 friend bool operator==(const FName& A, const FName& B) { return A.Text == B.Text; }
 friend bool operator!=(const FName& A, const FName& B) { return !(A == B); }
};
inline const FName NAME_None;
namespace EAxis { enum Type { None, X, Y, Z }; }
struct FRotator;
struct FVector {
 double X = 0, Y = 0, Z = 0;
 static const FVector ZeroVector, OneVector, UpVector, ForwardVector;
 FVector() = default;
 FVector(double InX, double InY, double InZ) : X(InX), Y(InY), Z(InZ) {}
 FVector operator+(const FVector& V) const { return {X + V.X, Y + V.Y, Z + V.Z}; }
 FVector operator-(const FVector& V) const { return {X - V.X, Y - V.Y, Z - V.Z}; }
 FVector operator-() const { return {-X, -Y, -Z}; }
 FVector operator*(double S) const { return {X * S, Y * S, Z * S}; }
 double GetMin() const { return std::fmin(X, std::fmin(Y, Z)); }
 double Size() const { return std::sqrt(X * X + Y * Y + Z * Z); }
 FVector GetSafeNormal() const { const double S = std::sqrt(X * X + Y * Y + Z * Z); return S > 0 ? FVector(X / S, Y / S, Z / S) : FVector(); }
 bool ContainsNaN() const { return !(std::isfinite(X) && std::isfinite(Y) && std::isfinite(Z)); }
 FRotator Rotation() const;
 FString ToString() const { return FString(); }
 static double DotProduct(const FVector& A, const FVector& B) { return A.X * B.X + A.Y * B.Y + A.Z * B.Z; }
 static FVector CrossProduct(const FVector& A, const FVector& B) { return {A.Y * B.Z - A.Z * B.Y, A.Z * B.X - A.X * B.Z, A.X * B.Y - A.Y * B.X}; }
 static double DistSquared(const FVector& A, const FVector& B) { const FVector D = A - B; return DotProduct(D, D); }
 static double Dist(const FVector& A, const FVector& B) { return std::sqrt(DistSquared(A, B)); }
};
inline const FVector FVector::ZeroVector{0, 0, 0};
inline const FVector FVector::OneVector{1, 1, 1};
inline const FVector FVector::UpVector{0, 0, 1};
inline const FVector FVector::ForwardVector{1, 0, 0};
struct FQuat {
 double X = 0, Y = 0, Z = 0, W = 1;
 static const FQuat Identity;
 FQuat() = default;
 FQuat(double InX, double InY, double InZ, double InW) : X(InX), Y(InY), Z(InZ), W(InW) {}
 // UE order: A * B applies B first, then A.
 FQuat operator*(const FQuat& Q) const { return FQuat(W * Q.X + X * Q.W + Y * Q.Z - Z * Q.Y, W * Q.Y - X * Q.Z + Y * Q.W + Z * Q.X, W * Q.Z + X * Q.Y - Y * Q.X + Z * Q.W, W * Q.W - X * Q.X - Y * Q.Y - Z * Q.Z); }
 FQuat operator*(double S) const { return FQuat(X * S, Y * S, Z * S, W * S); }
 FQuat operator+(const FQuat& Q) const { return FQuat(X + Q.X, Y + Q.Y, Z + Q.Z, W + Q.W); }
 double SizeSquared() const { return X * X + Y * Y + Z * Z + W * W; }
 FQuat GetNormalized(double Tolerance = 1e-8) const { const double S = SizeSquared(); if (S < Tolerance) return Identity; const double I = 1 / std::sqrt(S); return FQuat(X * I, Y * I, Z * I, W * I); }
 FQuat Inverse() const { return FQuat(-X, -Y, -Z, W); }
 bool Equals(const FQuat& Q, double Tolerance = 1e-4) const { return (std::fabs(X - Q.X) <= Tolerance && std::fabs(Y - Q.Y) <= Tolerance && std::fabs(Z - Q.Z) <= Tolerance && std::fabs(W - Q.W) <= Tolerance) || (std::fabs(X + Q.X) <= Tolerance && std::fabs(Y + Q.Y) <= Tolerance && std::fabs(Z + Q.Z) <= Tolerance && std::fabs(W + Q.W) <= Tolerance); }
 FVector RotateVector(const FVector& V) const { const FVector Q(X, Y, Z); const FVector T = FVector::CrossProduct(Q, V) * 2.; return V + T * W + FVector::CrossProduct(Q, T); }  // UE formula
 FRotator Rotator() const;
 double AngularDistance(const FQuat& Q) const { return 2 * std::acos(std::fmin(1.0, std::fabs(X * Q.X + Y * Q.Y + Z * Q.Z + W * Q.W))); }
 static FQuat Slerp(const FQuat& A, const FQuat& B, double T) {  // UE Slerp_NotNormalized + normalize
  const double Raw = A.X * B.X + A.Y * B.Y + A.Z * B.Z + A.W * B.W, Cosom = Raw >= 0 ? Raw : -Raw; double S0, S1;
  if (Cosom < 0.9999) { const double Omega = std::acos(Cosom), InvSin = 1 / std::sin(Omega); S0 = std::sin((1 - T) * Omega) * InvSin; S1 = std::sin(T * Omega) * InvSin; } else { S0 = 1 - T; S1 = T; }
  S1 = Raw >= 0 ? S1 : -S1; return (A * S0 + B * S1).GetNormalized();
 }
};
inline const FQuat FQuat::Identity{0, 0, 0, 1};
struct FRotator {
 double Pitch = 0, Yaw = 0, Roll = 0;
 static const FRotator ZeroRotator;
 FRotator() = default;
 FRotator(double InPitch, double InYaw, double InRoll) : Pitch(InPitch), Yaw(InYaw), Roll(InRoll) {}
 FRotator& operator+=(const FRotator& R) { Pitch += R.Pitch; Yaw += R.Yaw; Roll += R.Roll; return *this; }
 FQuat Quaternion() const {  // UE FRotator::Quaternion
  const double H = 3.14159265358979323846 / 360; const double SP = std::sin(Pitch * H), CP = std::cos(Pitch * H), SY = std::sin(Yaw * H), CY = std::cos(Yaw * H), SR = std::sin(Roll * H), CR = std::cos(Roll * H);
  return FQuat(CR * SP * SY - SR * CP * CY, -CR * SP * CY - SR * CP * SY, CR * CP * SY - SR * SP * CY, CR * CP * CY + SR * SP * SY);
 }
 FString ToString() const { return FString(); }
};
inline const FRotator FRotator::ZeroRotator{0, 0, 0};
inline FRotator FVector::Rotation() const { const double D = 180 / 3.14159265358979323846; return FRotator(std::atan2(Z, std::sqrt(X * X + Y * Y)) * D, std::atan2(Y, X) * D, 0); }
inline FRotator FQuat::Rotator() const {  // UE FQuat::Rotator (non-singular branch, singular ones clamped to +-90 pitch)
 const double D = 180 / 3.14159265358979323846, Test = Z * X - W * Y, YawY = 2 * (W * Z + X * Y), YawX = 1 - 2 * (Y * Y + Z * Z);
 if (Test < -0.4999995) return FRotator(-90, std::atan2(YawY, YawX) * D, 0);
 if (Test > 0.4999995) return FRotator(90, std::atan2(YawY, YawX) * D, 0);
 return FRotator(std::asin(2 * Test) * D, std::atan2(YawY, YawX) * D, std::atan2(-2 * (W * X + Y * Z), 1 - 2 * (X * X + Y * Y)) * D);
}
struct FTransform {
 FQuat Rotation; FVector Translation{0, 0, 0}, Scale3D{1, 1, 1};
 static const FTransform Identity;
 FTransform() = default;
 FTransform(const FQuat& R, const FVector& T, const FVector& S = FVector(1, 1, 1)) : Rotation(R), Translation(T), Scale3D(S) {}
 FQuat GetRotation() const { return Rotation; }
 void SetRotation(const FQuat& Q) { Rotation = Q; }
 void SetTranslation(const FVector& V) { Translation = V; }
 FVector GetTranslation() const { return Translation; }
 FVector GetScale3D() const { return Scale3D; }
 FRotator Rotator() const { return Rotation.Rotator(); }
 FVector GetUnitAxis(EAxis::Type Axis) const { return Rotation.RotateVector(Axis == EAxis::X ? FVector(1, 0, 0) : Axis == EAxis::Y ? FVector(0, 1, 0) : FVector(0, 0, 1)); }
 bool ContainsNaN() const { return Translation.ContainsNaN(); }
 void NormalizeRotation() { Rotation = Rotation.GetNormalized(); }
 void Blend(const FTransform& A, const FTransform& B, float Alpha) {  // UE: lerp translation/scale, slerp rotation
  Translation = A.Translation + (B.Translation - A.Translation) * Alpha; Scale3D = A.Scale3D + (B.Scale3D - A.Scale3D) * Alpha; Rotation = FQuat::Slerp(A.Rotation, B.Rotation, Alpha);
 }
 FTransform operator*(const FTransform& Other) const {  // UE: this first, then Other
  const FVector Scaled(Translation.X * Other.Scale3D.X, Translation.Y * Other.Scale3D.Y, Translation.Z * Other.Scale3D.Z);
  return FTransform(Other.Rotation * Rotation, Other.Rotation.RotateVector(Scaled) + Other.Translation, FVector(Scale3D.X * Other.Scale3D.X, Scale3D.Y * Other.Scale3D.Y, Scale3D.Z * Other.Scale3D.Z));
 }
 bool Equals(const FTransform& Other, double Tolerance = 1e-4) const {
  return Rotation.Equals(Other.Rotation, Tolerance) && std::fabs(Translation.X - Other.Translation.X) <= Tolerance && std::fabs(Translation.Y - Other.Translation.Y) <= Tolerance && std::fabs(Translation.Z - Other.Translation.Z) <= Tolerance
   && std::fabs(Scale3D.X - Other.Scale3D.X) <= Tolerance && std::fabs(Scale3D.Y - Other.Scale3D.Y) <= Tolerance && std::fabs(Scale3D.Z - Other.Scale3D.Z) <= Tolerance;
 }
 FString ToString() const { return FString(); }
};
inline const FTransform FTransform::Identity{};
struct FMath {
 template<class T> static constexpr T Abs(T A) { return A < 0 ? -A : A; }
 template<class T> static constexpr T Min(T A, T B) { return A < B ? A : B; }
 template<class T> static constexpr T Max(T A, T B) { return A < B ? B : A; }
 template<class T> static constexpr T Clamp(T X, T Lo, T Hi) { return X < Lo ? Lo : (Hi < X ? Hi : X); }
 template<class T> static constexpr T SmoothStep(T A, T B, T X) { if (X < A) return T(0); if (X >= B) return T(1); const T F = (X - A) / (B - A); return F * F * (T(3) - T(2) * F); }
 template<class T, class U> static T Lerp(const T& A, const T& B, const U& Alpha) { return A + (B - A) * Alpha; }
 static bool IsFinite(double X) { return std::isfinite(X); }
 static double FloorToDouble(double X) { return std::floor(X); }
 static double Sin(double X) { return std::sin(X); }
 static double Sqrt(double X) { return std::sqrt(X); }
 template<class T> static constexpr T RadiansToDegrees(T R) { return R * T(180 / 3.14159265358979323846); }
 static FRotator RInterpTo(const FRotator& Current, const FRotator&, float, float) { return Current; }
};
class FJsonObject {
public:
 bool TryGetStringField(const FString&, FString&) const { return false; }
 bool TryGetNumberField(const FString&, double&) const { return false; }
 bool HasField(const FString&) const { return false; }
 void SetStringField(const FString&, const FString&) {}
 void SetNumberField(const FString&, double) {}
 void SetBoolField(const FString&, bool) {}
};
template<class C = TCHAR> class TJsonReader {};
template<class C = TCHAR> class TJsonWriter {};
template<class C = TCHAR> struct TJsonReaderFactory { static TSharedRef<TJsonReader<C>> Create(const FString&) { return {}; } };
template<class C = TCHAR> struct TJsonWriterFactory { static TSharedRef<TJsonWriter<C>> Create(FString*) { return {}; } };
struct FJsonSerializer {
 template<class C> static bool Deserialize(const TSharedRef<TJsonReader<C>>&, TSharedPtr<FJsonObject>&) { return false; }
 template<class C> static bool Serialize(const TSharedRef<FJsonObject>&, const TSharedRef<TJsonWriter<C>>&) { return true; }
};
struct FCommandLine { static const TCHAR* Get() { return u""; } };
struct FParse { static bool Param(const TCHAR*, const TCHAR*) { return false; } };
struct FPlatformTime { static inline double StubNow = 0; static double Seconds() { return StubNow; } };
struct FPlatformProcess { static uint32 GetCurrentProcessId() { return 0; } };
struct FDateTime { static FDateTime UtcNow() { return {}; } int64 ToUnixTimestamp() const { return 0; } int32 GetMillisecond() const { return 0; } };
struct FFileHelper { static bool LoadFileToString(FString&, const TCHAR*) { return false; } static bool SaveStringToFile(const FString&, const TCHAR*) { return false; } };
#define UTF8_TO_TCHAR(x) ((void)(x), u"")
#define TCHAR_TO_UTF8(x) ((void)(x), "")
class UObject { public: virtual ~UObject() = default; FString GetPathName() const { return FString(); } FString GetName() const { return FString(); } };
template<class T> class TObjectPtr {
 T* Ptr = nullptr;
public:
 TObjectPtr() = default;
 TObjectPtr(std::nullptr_t) {}
 TObjectPtr(T* P) : Ptr(P) {}
 T* Get() const { return Ptr; }
 operator T*() const { return Ptr; }
 T* operator->() const { return Ptr; }
 explicit operator bool() const { return Ptr != nullptr; }
 friend bool operator==(const TObjectPtr& A, const TObjectPtr& B) { return A.Ptr == B.Ptr; }
};
inline UObject* StubCastTarget = nullptr;  // a driver names the one object Cast<> may return (no RTTI/typeinfo needed from the unit)
template<class T> T* Cast(UObject* Object) { return Object && Object == StubCastTarget ? static_cast<T*>(Object) : nullptr; }
template<class T> T* LoadObject(UObject*, const TCHAR*) { return nullptr; }
class USkeleton : public UObject {};
class UMorphTarget : public UObject {};
struct FReferenceSkeleton;
class USkeletalMesh : public UObject { public: USkeleton* GetSkeleton() const { return nullptr; } const FReferenceSkeleton& GetRefSkeleton() const; const TArray<TObjectPtr<UMorphTarget>>& GetMorphTargets() const { static TArray<TObjectPtr<UMorphTarget>> None; return None; } };
class UAnimSequenceBase : public UObject { public: virtual float GetPlayLength() const { return 0; } USkeleton* GetSkeleton() const { return nullptr; } };
namespace ERootMotionRootLock { enum Type { RefPose, AnimFirstFrame, Zero }; }
template<class E> class TEnumAsByte { uint8 Value = 0; public: TEnumAsByte() = default; TEnumAsByte(E V) : Value(uint8(V)) {} E GetValue() const { return E(Value); } };
class UAnimSequence : public UAnimSequenceBase { public: bool bEnableRootMotion = false, bForceRootLock = false; TEnumAsByte<ERootMotionRootLock::Type> RootMotionRootLock; };
struct FByteProperty { uint8 GetPropertyValue_InContainer(const void*, int32 = 0) const { return 0; } };
template<class T> T* FindFProperty(const UClass*, FName) { return nullptr; }
enum class ETeleportType : uint8 { None, TeleportPhysics, ResetPhysics };
struct FHitResult {};
struct FAttachmentTransformRules { static const FAttachmentTransformRules KeepWorldTransform; };
inline const FAttachmentTransformRules FAttachmentTransformRules::KeepWorldTransform{};
class UWorld : public UObject { public: float GetDeltaSeconds() const { return 0; } };
class UActorComponent : public UObject {};
struct FBoxSphereBounds { FVector Origin, BoxExtent; double SphereRadius = 0; FString ToString() const { return FString(); } };
class USceneComponent : public UActorComponent {
public:
 FTransform StubWorld, StubRelative; FRotator StubRotation; FBoxSphereBounds Bounds; float BoundsScale = 1; int32 StubBoundsUpdates = 0;
 void UpdateBounds() { ++StubBoundsUpdates; }
 const FTransform& GetComponentTransform() const { return StubWorld; }
 const FTransform& GetRelativeTransform() const { return StubRelative; }
 void SetRelativeTransform(const FTransform& T, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { StubRelative = T; }
 FVector GetComponentLocation() const { return StubWorld.Translation; }
 bool AttachToComponent(USceneComponent*, const FAttachmentTransformRules&) { return true; }
 void SetUsingAbsoluteRotation(bool) {}
 void SetWorldLocation(const FVector& L) { StubWorld.Translation = L; }
 void SetWorldRotation(const FRotator& R) { StubRotation = R; }
 void SetWorldLocationAndRotation(const FVector& L, const FRotator& R) { StubWorld.Translation = L; StubRotation = R; }
 void SetWorldTransform(const FTransform& T, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { StubWorld = T; }
 void SetVisibility(bool) {}
};
class USkeletalMeshComponent : public USceneComponent {
public:
 int32 StubHeadIndex = INDEX_NONE; FVector StubHead; UAnimInstance* StubAnim = nullptr;
 USkeletalMesh* GetSkeletalMeshAsset() const { return nullptr; }
 int32 GetBoneIndex(FName) const { return StubHeadIndex; }
 FVector GetBoneLocation(FName) const { return StubHead; }
 FTransform GetBoneTransform(int32) const { return FTransform(FQuat::Identity, StubHead, FVector(1, 1, 1)); }
 UAnimInstance* GetAnimInstance() const { return StubAnim; }
 void UnHideBoneByName(FName) {}
 void ShowMaterialSection(int32, int32, bool, int32) {}
 void SetAnimInstanceClass(UClass*) {}
};
class UCameraComponent : public USceneComponent { public: float FieldOfView = 90; void SetFieldOfView(float F) { FieldOfView = F; } };
class UCharacterMovementComponent : public UActorComponent { public: void StopMovementImmediately() {} void DisableMovement() {} };
class AController : public UObject { public: void SetControlRotation(const FRotator&) {} };
class AActor : public UObject {
public:
 UWorld* GetWorld() const { return nullptr; }
 USceneComponent* GetRootComponent() const { return nullptr; }
 bool SetActorLocationAndRotation(FVector, FRotator, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { return true; }
 template<class T> T* FindComponentByClass() const { return nullptr; }
};
class APawn : public AActor { public: TObjectPtr<AController> Controller; bool bUseControllerRotationYaw = true; };
class ACharacter : public APawn { public: UCharacterMovementComponent* GetCharacterMovement() const { return nullptr; } };
class FAnimInstanceProxy;
class UAnimInstance : public UObject {
public:
 static UClass* StaticClass() { return nullptr; }
 AActor* GetOwningActor() const { return nullptr; }
 UWorld* GetWorld() const { return nullptr; }
 virtual void NativePostEvaluateAnimation() {}
protected:
 template<class T> T& GetProxyOnGameThread() { static T* Proxy = nullptr; return *Proxy; }
 virtual FAnimInstanceProxy* CreateAnimInstanceProxy() { return nullptr; }
 virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
};
struct FAnimationInitializeContext { explicit FAnimationInitializeContext(FAnimInstanceProxy*) {} };
struct FAnimationCacheBonesContext { explicit FAnimationCacheBonesContext(FAnimInstanceProxy*) {} };
struct FAnimationUpdateContext {};
struct FMeshPoseBoneIndex { explicit FMeshPoseBoneIndex(int32 I) : Index(I) {} int32 Index; int32 GetInt() const { return Index; } };
struct FCompactPoseBoneIndex { int32 Index = INDEX_NONE; int32 GetInt() const { return Index; } };
struct FReferenceSkeleton {
 int32 GetNum() const { return 0; }
 int32 GetParentIndex(int32) const { return INDEX_NONE; }
 int32 FindBoneIndex(const FName&) const { return INDEX_NONE; }
 FName GetBoneName(int32) const { return FName(); }
};
inline const FReferenceSkeleton& USkeletalMesh::GetRefSkeleton() const { static FReferenceSkeleton None; return None; }
struct FBoneContainer {
 const FReferenceSkeleton& GetReferenceSkeleton() const { static FReferenceSkeleton None; return None; }
 FCompactPoseBoneIndex MakeCompactPoseIndex(const FMeshPoseBoneIndex&) const { return {}; }
 FMeshPoseBoneIndex MakeMeshPoseIndex(const FCompactPoseBoneIndex&) const { return FMeshPoseBoneIndex(0); }
};
struct FCompactPose {
 const FBoneContainer& GetBoneContainer() const { static FBoneContainer None; return None; }
 FTransform& operator[](FCompactPoseBoneIndex) { static FTransform None; return None; }
 const FTransform& operator[](FCompactPoseBoneIndex) const { static FTransform None; return None; }
 int32 GetNumBones() const { return 0; }
 TArray<FCompactPoseBoneIndex> ForEachBoneIndex() const { return {}; }
};
struct FPoseContext { FAnimInstanceProxy* AnimInstanceProxy = nullptr; FCompactPose Pose; explicit FPoseContext(FAnimInstanceProxy* InProxy) : AnimInstanceProxy(InProxy) {} };
struct FAnimNode_Base {
 virtual ~FAnimNode_Base() = default;
 virtual void Initialize_AnyThread(const FAnimationInitializeContext&) {}
 virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext&) {}
 virtual void Update_AnyThread(const FAnimationUpdateContext&) {}
 virtual void Evaluate_AnyThread(FPoseContext&) {}
};
struct FPoseLink { void SetLinkNode(FAnimNode_Base*) {} };
struct FAnimNode_SequencePlayerBase : FAnimNode_Base {
 UAnimSequenceBase* GetSequence() const { return nullptr; }
 bool SetSequence(UAnimSequenceBase*) { return true; }
 bool SetAccumulatedTime(float) { return true; }
 float GetAccumulatedTime() const { return 0; }
 bool SetPlayRate(float) { return true; }
 float GetPlayRate() const { return 1; }
 bool SetLoopAnimation(bool) { return true; }
 bool IsLooping() const { return true; }
};
struct FAnimNode_SequencePlayer : FAnimNode_SequencePlayerBase {};
struct FAnimNode_SequencePlayer_Standalone : FAnimNode_SequencePlayerBase {};
struct FAnimNode_TwoWayBlend : FAnimNode_Base { FPoseLink A, B; float Alpha = 0; };
class FAnimInstanceProxy {
public:
 explicit FAnimInstanceProxy(UAnimInstance*) {}
 virtual ~FAnimInstanceProxy() = default;
 virtual void Initialize(UAnimInstance*) {}
 virtual void PreUpdate(UAnimInstance*, float) {}
 virtual void CacheBones() {}
 virtual void Update(float) {}
 virtual void UpdateAnimationNode(const FAnimationUpdateContext&) {}
 virtual bool Evaluate(FPoseContext&) { return false; }
};
'''

CHARACTER = r'''#include "ue_stub.h"
#include "Sub01HomeHands.h"
#include <sys/stat.h>
#include <unistd.h>
class USub01PCBridge : public UActorComponent { public: void SetOperatorFocus(bool) {} bool HasOperatorFocus() const { return false; } };
class USub01HomeDeviceBridge : public UActorComponent { public: void ReleaseFocus() {} };
class ASub01HomeCharacter;
struct FSub01GhostViews { FSub01GhostViews(UWorld*, ASub01HomeCharacter*, USkeletalMeshComponent*, TArray<FName>) {} void Tick(float, bool, bool) {} };
class ASub01HomeCharacter : public ACharacter {
 public:
 // Stand-ins for the root members TickPrivateStreamerVisual touches; then the real (patched) streamer fields.
 TObjectPtr<USkeletalMeshComponent> FirstPersonBody; TObjectPtr<UCameraComponent> ViewCamera; TObjectPtr<USub01PCBridge> PCBridge;
 bool LiveHome=false,LiveHomeFresh=false,LiveHomePrivate=false,RouteActive=false,NativeSeatVerified=false,MinecraftFocused=false,NativePrivacyLast=false;
 FString HandsFailure; enum class EPrivateViewMode:uint8{Manual,Diagnostic,Live}; EPrivateViewMode PrivateViewMode=EPrivateViewMode::Manual;
 TSharedPtr<FSub01GhostViews> PrivateGhostViews;
 void ReleaseMinecraftTVInput(){} int64 PrivateSettingsStartTicks() const {return 0;} void UpdateActualKitchen(float){} void UpdateAuthenticDoors(float){}
 void PublishPrivateVisualMetrics(){} void UpdateNativePCPrivacy(){} void UpdateNativeCapture(){}
@@FIELDS@@
};
@@METHODS@@
@@TICK@@
'''

DRIVER = r'''
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 const FRotator Spectator(-13.64, -146.31, 0);
 C.StartStreamerVisualV2(Spectator);
 // monitor framing from the body basis: facing +Y (the import's forward), right = Up x facing, monitor centre in view
 CHECK(C.StreamerVisualMonitorAxis == TEXT("+Y"), 1);
 CHECK(Near(C.StreamerVisualMonitorLocation.X, 275.19, .05) && Near(C.StreamerVisualMonitorLocation.Y, -232.60, .05) && Near(C.StreamerVisualMonitorLocation.Z, 161, 1e-9), 2);
 CHECK(Near(C.StreamerVisualMonitorLook.Yaw, -113.31, .05) && Near(C.StreamerVisualMonitorLook.Pitch, -17.46, .05), 3);
 CHECK(C.StreamerVisualV2Clips.Num() == 3, 4);  // LoadObject is null in the stub: every slot falls back (frozen R9)
 // debounce: first change at once, then at most one per 0.6 s (latest wins), "reacting" at once; stale -> idle + spectator
 C.StreamerVisualEventAt = 100; C.AcceptStreamerVisualV2(2, TEXT("typing"), 1, TEXT("monitor"), 0); C.TickStreamerVisualV2(100);
 CHECK(C.StreamerVisualState == TEXT("typing") && C.StreamerVisualCameraTarget == TEXT("monitor"), 10);
 C.StreamerVisualEventAt = 100.2; C.AcceptStreamerVisualV2(2, TEXT("mouse"), 1, TEXT("monitor"), 0); C.TickStreamerVisualV2(100.2);
 C.StreamerVisualEventAt = 100.3; C.AcceptStreamerVisualV2(2, TEXT("reading"), 1, TEXT("monitor"), 0); C.TickStreamerVisualV2(100.59);
 CHECK(C.StreamerVisualState == TEXT("typing"), 11);
 C.TickStreamerVisualV2(100.61); CHECK(C.StreamerVisualState == TEXT("reading"), 12);
 C.StreamerVisualEventAt = 100.7; C.AcceptStreamerVisualV2(2, TEXT("reacting"), 1, TEXT("spectator"), .8); C.TickStreamerVisualV2(100.7);
 CHECK(C.StreamerVisualState == TEXT("reacting") && Near(C.StreamerVisualNodAt, 100.7, 1e-9) && Near(C.StreamerVisualNodGain, .8, 1e-6), 13);
 CHECK(C.StreamerVisualNod == 0, 14);  // v2 never uses the v1 per-event nod
 C.StreamerVisualEventAt = 100.8; C.AcceptStreamerVisualV2(2, TEXT("idle"), 1, TEXT("spectator"), 0); C.TickStreamerVisualV2(101.2);
 CHECK(C.StreamerVisualState == TEXT("reacting"), 15);
 C.TickStreamerVisualV2(101.31); CHECK(C.StreamerVisualState == TEXT("idle"), 16);
 C.StreamerVisualEventAt = 100.8; C.AcceptStreamerVisualV2(2, TEXT("typing"), 1, TEXT("monitor"), 0); C.TickStreamerVisualV2(102.9);
 CHECK(C.StreamerVisualState == TEXT("idle") && C.StreamerVisualCameraTarget == TEXT("spectator"), 17);  // event 2.1 s old
 // bounded, deterministic head motion: sway <= 1.5 deg; talking adds <= .9 pitch / .6 yaw; slow (small per-frame steps)
 ASub01HomeCharacter D; D.FirstPersonBody = &Body; D.ViewCamera = &Camera; D.StartStreamerVisualV2(Spectator);
 double MaxP = 0, MaxY = 0, MaxStep = 0, PrevP = 0; bool First = true;
 for (int K = 0; K < 24 * 3600; ++K) {
  const double T = 1000 + K / 24.;
  C.StreamerVisualEventAt = D.StreamerVisualEventAt = T; C.StreamerVisualIntensity = D.StreamerVisualIntensity = 1;
  C.StreamerVisualRequestedState = D.StreamerVisualRequestedState = TEXT("idle"); C.StreamerVisualNodAt = D.StreamerVisualNodAt = -10;
  const FRotator A = C.TickStreamerVisualV2(T), B = D.TickStreamerVisualV2(T);
  CHECK(A.Pitch == B.Pitch && A.Yaw == B.Yaw && A.Roll == 0, 20);
  MaxP = std::fmax(MaxP, std::fabs(A.Pitch)); MaxY = std::fmax(MaxY, std::fabs(A.Yaw));
  if (!First) MaxStep = std::fmax(MaxStep, std::fabs(A.Pitch - PrevP));
  PrevP = A.Pitch; First = false;
 }
 CHECK(MaxP <= 1.5 && MaxY <= 1.5 && MaxP > .5 && MaxY > .5, 21);
 CHECK(MaxStep < .05, 22);
 double TalkP = 0, TalkY = 0;  // talking = the same sway plus a bounded speech cadence (.9 deg pitch, .6 deg yaw)
 for (int K = 0; K < 24 * 600; ++K) {
  const double T = 5000 + K / 24.;
  C.StreamerVisualEventAt = D.StreamerVisualEventAt = T; C.StreamerVisualRequestedState = TEXT("talking"); C.StreamerVisualStateAt = -100;
  const FRotator A = C.TickStreamerVisualV2(T), B = D.TickStreamerVisualV2(T);
  TalkP = std::fmax(TalkP, std::fabs(A.Pitch - B.Pitch)); TalkY = std::fmax(TalkY, std::fabs(A.Yaw - B.Yaw));
 }
 CHECK(C.StreamerVisualState == TEXT("talking") && D.StreamerVisualState == TEXT("idle"), 23);
 CHECK(TalkP <= .9 + 1e-9 && TalkY <= .6 + 1e-9 && TalkP > .5 && TalkY > .5, 24);
 // camera: 1 s eased blend to the monitor framing and back; spectator is never touched while it holds
 Camera.StubWorld.Translation = FVector(334, -209, 151); C.StreamerVisualCameraAlpha = 0; C.StreamerVisualSchemaVersion = 2;
 C.StreamerVisualState = TEXT("idle"); C.StreamerVisualCameraTarget = TEXT("spectator"); C.ApplyStreamerVisualV2(0, .1f);
 CHECK(C.StreamerVisualCameraAlpha == 0, 30);
 C.StreamerVisualCameraTarget = TEXT("monitor");
 for (int K = 0; K < 5; ++K) C.ApplyStreamerVisualV2(0, .1f);
 CHECK(Near(C.StreamerVisualCameraAlpha, .5, 1e-5) && Near(Camera.StubWorld.Translation.X, (334 + 275.19) / 2, .1), 31);
 for (int K = 0; K < 6; ++K) C.ApplyStreamerVisualV2(0, .1f);
 CHECK(C.StreamerVisualCameraAlpha == 1 && Near(Camera.StubWorld.Translation.X, 275.19, .05) && Near(Camera.StubWorld.Translation.Z, 161, 1e-6), 32);
 C.StreamerVisualSchemaVersion = 1;  // a v1 event: back to the authored spectator view, exactly
 for (int K = 0; K < 11; ++K) C.ApplyStreamerVisualV2(0, .1f);
 CHECK(C.StreamerVisualCameraAlpha == 0 && Camera.StubWorld.Translation.X == 334 && Camera.StubWorld.Translation.Y == -209 && Camera.StubWorld.Translation.Z == 151, 33);
 // v1 acceptance switches the mode and leaves the v2 state alone
 C.AcceptStreamerVisualV2(1, TEXT(""), .5, TEXT("spectator"), 1); CHECK(C.StreamerVisualSchemaVersion == 1, 40);
 std::printf("ok\n");
 return 0;
}
'''

HANDS_INC = ' bool CinemaOwns=false;FAnimNode_TwoWayBlend CinemaBlend;Sub01Cinema::FPoseObservation CinemaObservation;\n' \
            ' void InitializeCinema(){} void PreUpdateCinema(USub01HomeHandsInstance*,float){} bool EvaluateCinema(FPoseContext&){return false;}\n'


def _block(text: str, start: str, end: str) -> tuple:
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j], text.count('\n', 0, i) + 1


def _function(text: str, head: str) -> tuple:
    i = text.index(head)
    s = closure.strip(text)
    depth, k = 0, s.index('{', i)
    while True:
        depth += {'{': 1, '}': -1}.get(s[k], 0)
        if depth == 0:
            return text[i:k + 1], text.count('\n', 0, i) + 1
        k += 1


def build_units(src: Path, work: Path, end: str = MARKER + ' END', driver: str = None, hands_driver: str = None) -> dict:
    """Translation units from the patched files; #line keeps diagnostics on the patched sources. `end` closes the
    streamer fields (Sub01HomeLab.h) and the appended methods (Sub01HomeLab.cpp): the v2 END, or the face END on top.
    `hands_driver` appends a main() to the proxy unit (static proxy helpers can be run without an instance)."""
    stub, hands_inc, char_inc = work / 'stub', work / 'hands_inc', work / 'char_inc'
    for d in (stub / 'Animation', hands_inc, char_inc):
        d.mkdir(parents=True, exist_ok=True)
    (stub / 'ue_stub.h').write_text(STUB)
    (stub / 'UObject').mkdir(exist_ok=True)
    for name in ('CoreMinimal.h', 'Animation/AnimInstance.h', 'UObject/UnrealType.h', 'Animation/MorphTarget.h'):
        (stub / name).write_text('#pragma once\n#include "ue_stub.h"\n')
    (stub / 'Sub01HomeHands.generated.h').write_text('#pragma once\n')
    (stub / 'native_cinematic_director.h').write_text('#pragma once\nnamespace Sub01Cinema { struct FPoseObservation {}; }\n')
    (hands_inc / 'native_cinematic_proxy.inc').write_text(HANDS_INC)
    (hands_inc / 'Sub01CapturedLayerClock.h').write_text(
        '#pragma once\nnamespace Sub01CapturedLayer { inline double AdvanceCapturedLayerTime(double,double,double,double,bool){return 0;} }\n')
    (hands_inc / 'Sub01HomeLab.h').write_text(
        '#pragma once\n#include "ue_stub.h"\nclass ASub01HomeCharacter : public ACharacter { public: void TickAuthoredCinematicReview(float){} };\n')
    hands_h, hands_cpp, header, cpp = (lf(src / n) for n in ('Sub01HomeHands.h', 'Sub01HomeHands.cpp', 'Sub01HomeLab.h', 'Sub01HomeLab.cpp'))
    for d in (hands_inc, char_inc):
        (d / 'Sub01HomeHands.h').write_text(f'#line 1 "{src / "Sub01HomeHands.h"}"\n' + hands_h)
    proxy, at = _block(hands_cpp, 'struct FSub01HandsProxy : FAnimInstanceProxy {',
                       'void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy){delete Proxy;}')
    hands_unit = ('#include "Sub01HomeHands.h"\n#include "Sub01HomeLab.h"\n#include "Sub01CapturedLayerClock.h"\n'
                  f'#line {at} "{src / "Sub01HomeHands.cpp"}"\n{proxy}\n')
    (work / 'hands.cpp').write_text(hands_unit)
    (work / 'hands_driver.cpp').write_text(hands_unit + (hands_driver or ''))
    fields, _ = _block(header, ' bool TickPrivateStreamerVisual(float Dt);', end)
    methods, m_at = _block(cpp, MARKER + ' BEGIN', end)
    tick, t_at = _function(cpp, 'bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){')
    unit = CHARACTER.replace('@@FIELDS@@', fields).replace(
        '@@METHODS@@', f'#line {m_at} "{src / "Sub01HomeLab.cpp"}"\n{methods}').replace(
        '@@TICK@@', f'#line {t_at} "{src / "Sub01HomeLab.cpp"}"\n{tick}')
    (work / 'character.cpp').write_text(unit)
    (work / 'driver.cpp').write_text(unit + (DRIVER if driver is None else driver))
    return {'hands': (work / 'hands.cpp', hands_inc), 'character': (work / 'character.cpp', char_inc),
            'driver': (work / 'driver.cpp', char_inc), 'hands_driver': (work / 'hands_driver.cpp', hands_inc), 'stub': stub}


COMPILERS = closure.compilers()


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_patched_cpp_compiles_syntax_only_against_stub(patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(patched, tmp_path)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_stub_compile_detects_errors(patched, tmp_path):
    """The check is not vacuous: a wrong UE_LOG format and an unknown engine member both fail."""
    broken = tmp_path / 'broken'
    shutil.copytree(patched, broken)
    cpp, hands = broken / 'Sub01HomeLab.cpp', broken / 'Sub01HomeHands.cpp'
    cpp.write_bytes(cpp.read_bytes().replace(b'clips=%d/3', b'clips=%s/3', 1))
    hands.write_bytes(hands.read_bytes().replace(b'StreamerV2Spine[K].Quaternion()', b'StreamerV2Spine[K].Quat()', 1))
    name, path, flags = COMPILERS[0]
    units = build_units(broken, tmp_path / 'work')
    for unit in ('hands', 'character'):
        source, include = units[unit]
        run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                             capture_output=True, text=True)
        assert run.returncode != 0 and str(broken) in run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_patched_character_logic_runs(patched, tmp_path):
    """Runs the patched StartStreamerVisualV2 / AcceptStreamerVisualV2 / TickStreamerVisualV2 / ApplyStreamerVisualV2."""
    name, path, _ = COMPILERS[0]
    units = build_units(patched, tmp_path)
    source, include = units['driver']
    binary = tmp_path / 'driver'
    build = subprocess.run([path, '-std=c++20', '-O1', f'-I{include}', '-isystem', str(units['stub']), str(source), '-o', str(binary)],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr[-6000:]
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ face camera + desk guard
FACE_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_face_camera.py'
FACE_MARKER = '// SUB01_STREAMER_VISUAL_V2_FACE'
FACE_END = FACE_MARKER + ' END'
V2_COPY = SOURCE.parent / 'native-src-v2'


def install_face(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(FACE_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod_v2(tmp_path) -> Path:
    target = tmp_path / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0
    return target


@pytest.fixture(scope='module')
def face_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('face') / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0
    code, report = install_face(target)
    assert code == 0, report
    return target


def test_v2_install_reproduces_the_pod_sources(pod_v2):
    """The face patch applies on top of the pod sources; they equal native-src-v2 (when that copy exists)."""
    if not V2_COPY.is_dir():
        pytest.skip(f'{V2_COPY} not available')
    for name in PATCHED:
        assert sha(pod_v2 / name) == sha(V2_COPY / name), name


def test_face_install_on_v2_plans_applies_and_refuses_twice(pod_v2):
    before = {p.name: sha(p) for p in pod_v2.iterdir()}
    code, planned = install_face(pod_v2, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == before
    code, report = install_face(pod_v2)
    assert code == 0 and report['status'] == 'applied'
    for name in PATCHED:
        assert report['files'][name]['before_sha256'] == before[name]
        assert sha(pod_v2 / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_v2 / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    for name in set(before) - set(PATCHED):
        assert sha(pod_v2 / name) == before[name]
    after = {p.name: sha(p) for p in pod_v2.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_face(pod_v2, *extra)
        assert code == 2 and 'already' in again['reason']
    assert install(pod_v2)[0] == 2  # nor can v2 be installed again on top
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == after


def test_face_install_refuses_without_v2(pod):
    before = {p.name: sha(p) for p in pod.iterdir()}
    code, report = install_face(pod)
    assert code == 2 and 'lacks the v2 install' in report['reason']
    assert {p.name: sha(p) for p in pod.iterdir()} == before


def test_face_missing_anchor_refuses_without_writing(pod_v2):
    lab = pod_v2 / 'Sub01HomeLab.cpp'
    lab.write_bytes(lab.read_bytes().replace(b'||Camera==TEXT("monitor"))', b'||Camera==TEXT("monitor")||false)', 1))
    before = {p.name: sha(p) for p in pod_v2.iterdir()}
    code, report = install_face(pod_v2)
    assert code == 2 and 'anchor missing in Sub01HomeLab.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == before


def test_face_patch_is_layered_on_v2(face_patched):
    for name in PATCHED:
        v2_text, face = lf(V2_COPY / name) if V2_COPY.is_dir() else None, lf(face_patched / name)
        assert face.count(FACE_MARKER + ' BEGIN') == face.count(FACE_END) == 1, name
        assert closure.brace_walk(closure.strip(face)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
        if v2_text is not None:  # every v2 line survives except these, which the face patch extends in place
            gone = sorted(line.strip()[:40] for line in v2_text.split('\n') if line not in face.split('\n'))
            expected = {'Sub01HomeLab.cpp': ['Camera=TEXT("spectator");if(J->HasField(', 'Receipt->SetStringField(TEXT("camera"),S',
                                             'const int32 Slot=StreamerVisualState==TE'],
                        'Sub01HomeHands.cpp': ['StreamerV2Probe.SetAccumulatedTime(Lengt']}  # probe poses pinned too
            assert gone == sorted(expected.get(name, [])), (name, gone)
    cpp, proxy = lf(face_patched / 'Sub01HomeLab.cpp'), lf(face_patched / 'Sub01HomeHands.cpp')
    for text in ('Camera==TEXT("face")', 'StreamerVisualFaceLocation=Monitor+FVector(0,0,28)-Facing*10.;', 'FMath::Lerp(65.f,42.f,Ease)',
                 'GetBoneIndex(TEXT("Head"))!=INDEX_NONE', 'Aim=BodyAt+FVector(0,0,120)', 'TEXT("face_camera_blend")', 'TEXT("camera_fov")',
                 'StreamerVisualDeskSlot(Anim,StreamerVisualState==TEXT("typing")?1:StreamerVisualState==TEXT("mouse")?2:0)',
                 'SUB01_STREAMER_VISUAL_CLIP_AUDIT', 'C->bEnableRootMotion', 'C->bForceRootLock', 'C->RootMotionRootLock.GetValue()',
                 'FindFProperty<FByteProperty>(UAnimInstance::StaticClass(),TEXT("RootMotionMode"))', 'TEXT("desk_offset_before_pin_cm")'):
        assert text in cpp, text
    # spectator/monitor blend of v2 kept verbatim; face is a separate layer called after it
    assert ' const float Goal=StreamerVisualCameraTarget==TEXT("monitor")?1.f:0.f;' in cpp
    assert ' }\n ApplyStreamerVisualFaceCamera(Dt); // SUB01_STREAMER_VISUAL_V2_FACE' in cpp
    for text in ('static constexpr double StreamerV2PinRadiusCm=8,', 'if(I>0){T=Reference;continue;}', 'PinStreamerV2(Output.Pose,true);',
                 'PinStreamerV2(Probe.Pose,false);', 'AuditStreamerV2Clips(Output);', 'Ref.FindBoneIndex(FName(TEXT("Hips")))'):
        assert text in proxy, text
    # the desk pin runs before hands/breathing/head (EvaluateStreamerV2) and before the phase match / blend
    eval_body = proxy[proxy.index('void EvaluateStreamerV2(FPoseContext& Output){'):]
    assert eval_body.index('PinStreamerV2(Output.Pose,true);') < eval_body.index('StreamerV2HandsValid=')
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    assert evaluate.index('PrepareStreamerV2Pin(Output)') < evaluate.index('MatchStreamerV2Phase(Output);') < evaluate.index('Blend.Evaluate_AnyThread(Output);')


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_face_patched_cpp_compiles_syntax_only_against_stub(face_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(face_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


FACE_DRIVER = r'''
#include <cstdlib>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N) { for (int K = 0; K < N; ++K) C.ApplyStreamerVisualV2(0, .1f); }
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle");
 // webcam above the monitor: centre + 28 cm up, 10 cm towards him along the facing (+Y axis of the body)
 CHECK(Near(C.StreamerVisualFaceLocation.X, 219.520, .01) && Near(C.StreamerVisualFaceLocation.Y, -357.993, .01) && Near(C.StreamerVisualFaceLocation.Z, 142.75, 1e-9), 1);
 // no Head bone: aim at body + (0,0,120); 1 s eased blend of location and FOV 65 -> 42
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 5);
 CHECK(C.StreamerVisualFaceAimSource == TEXT("body+120") && Near(C.StreamerVisualFaceLook.Yaw, 94.593, .01) && Near(C.StreamerVisualFaceLook.Pitch, -13.510, .01), 2);
 CHECK(Near(C.StreamerVisualFaceAlpha, .5, 1e-5) && Near(Camera.FieldOfView, 53.5, 1e-3) && Near(Camera.StubWorld.Translation.X, (334 + 219.52) / 2, .02), 3);
 Ticks(C, 6);
 CHECK(C.StreamerVisualFaceAlpha == 1 && Camera.FieldOfView == 42 && Near(Camera.StubWorld.Translation.Y, -357.993, .01) && Near(Camera.StubWorld.Translation.Z, 142.75, 1e-6), 4);
 // back to spectator: exactly the authored view and FOV 65, then nothing touches the camera
 C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 11);
 CHECK(C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334 && Camera.StubWorld.Translation.Y == -209 && Camera.StubWorld.Translation.Z == 151, 5);
 Camera.StubWorld.Translation = FVector(1, 2, 3); Ticks(C, 3); CHECK(Camera.StubWorld.Translation.X == 1, 6);
 Camera.StubWorld.Translation = FVector(334, -209, 151);
 // monitor -> face -> monitor: the v2 blend runs underneath, face ends exactly framed, monitor comes back with FOV 65
 C.StreamerVisualCameraTarget = TEXT("monitor"); Ticks(C, 11);
 CHECK(C.StreamerVisualCameraAlpha == 1 && C.StreamerVisualFaceAlpha == 0 && Near(Camera.StubWorld.Translation.X, 275.19, .05), 7);
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 11);
 CHECK(C.StreamerVisualCameraAlpha == 0 && C.StreamerVisualFaceAlpha == 1 && Near(Camera.StubWorld.Translation.X, 219.52, .01) && Camera.FieldOfView == 42, 8);
 C.StreamerVisualCameraTarget = TEXT("monitor"); Ticks(C, 11);
 CHECK(C.StreamerVisualCameraAlpha == 1 && C.StreamerVisualFaceAlpha == 0 && Near(Camera.StubWorld.Translation.X, 275.19, .05) && Camera.FieldOfView == 65, 9);
 // Head bone available: aim at it (re-aimed on each selection); an implausible Head location falls back to body + 120
 C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 11);
 Body.StubHeadIndex = 7; Body.StubHead = FVector(214, -290, 130);
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 1);
 CHECK(C.StreamerVisualFaceAimSource == TEXT("head") && Near(C.StreamerVisualFaceLook.Yaw, 94.641, .01) && Near(C.StreamerVisualFaceLook.Pitch, -10.587, .01), 10);
 C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 11); Body.StubHead = FVector(0, 0, 0);
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 1); CHECK(C.StreamerVisualFaceAimSource == TEXT("body+120"), 11);
 // a v1 event: the face layer fades out with the forced spectator target
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 11); CHECK(C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334, 12);
 // desk guard: clip choice from the proxy's audit (slots 0 sitting loop, 1 typing, 2 reach)
 USub01HomeHandsInstance Anim; UAnimSequence Sit, Type, Reach; C.StreamerVisualV2Clips.Reset(); C.StreamerVisualV2Clips.Add(&Sit); C.StreamerVisualV2Clips.Add(&Type); C.StreamerVisualV2Clips.Add(&Reach);
 CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 0 && C.StreamerVisualDeskSlot(&Anim, 1) == 0 && C.StreamerVisualDeskSlot(&Anim, 0) == 0, 20);  // before the audit
 CHECK(Anim.StreamerVisualAuditClips.Num() == 3 && Anim.StreamerVisualAuditClips[2].Get() == &Reach, 21);
 Anim.StreamerVisualAuditDone = true; Anim.StreamerVisualClipOffsetCm = {3.f, 5.f, 120.f}; Anim.StreamerVisualClipAngleDeg = {2.f, 4.f, 10.f};
 CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 0 && C.StreamerVisualDeskSlot(&Anim, 1) == 1 && C.StreamerVisualDeskSlot(&Anim, 0) == 0, 22);  // reach off-station
 Anim.StreamerVisualClipOffsetCm = {3.f, 5.f, 6.f}; Anim.StreamerVisualClipAngleDeg = {2.f, 4.f, 40.f};
 CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 0, 23);  // turned > 25 deg
 Anim.StreamerVisualClipAngleDeg = {2.f, 4.f, 10.f}; CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 2, 24);  // authored at the desk
 Anim.StreamerVisualClipOffsetCm = {30.f, 30.f, 6.f};
 CHECK(C.StreamerVisualDeskSlot(&Anim, 0) == -1 && C.StreamerVisualDeskSlot(&Anim, 1) == -1 && C.StreamerVisualDeskSlot(&Anim, 2) == 2, 25);  // -1 = frozen R9
 C.StreamerVisualV2Clips[2] = nullptr; CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 2, 26);  // missing clip: the v2 frozen-R9 rule
 CHECK(C.StreamerVisualDeskSlot(nullptr, 2) == 2, 27);
 std::printf("ok\n");
 return 0;
}
'''


def _run_driver(units: dict, tmp_path: Path, unit: str = 'driver') -> subprocess.CompletedProcess:
    name, path, _ = COMPILERS[0]
    source, include = units[unit]
    binary = tmp_path / f'{unit}-bin'
    build = subprocess.run([path, '-std=c++20', '-O1', f'-I{include}', '-isystem', str(units['stub']), str(source), '-o', str(binary)],
                           capture_output=True, text=True)
    assert build.returncode == 0, build.stderr[-6000:]
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_face_camera_and_desk_slot_logic_runs(face_patched, tmp_path):
    run = _run_driver(build_units(face_patched, tmp_path, end=FACE_END, driver=FACE_DRIVER), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v2_behaviour_unchanged_under_face_patch(face_patched, tmp_path):
    """The whole v2 driver (debounce, bounds, monitor framing, spectator/monitor blend) passes on the face-patched code."""
    run = _run_driver(build_units(face_patched, tmp_path, end=FACE_END), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ pin fix (per-clip drift guard)
PINFIX_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_pin_fix.py'
PINFIX_MARKER = '// SUB01_STREAMER_VISUAL_V2_PINFIX'
FACE_COPY = SOURCE.parent / 'native-src-v2-face'


def install_pinfix(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(PINFIX_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod_face(tmp_path) -> Path:
    target = tmp_path / 'face-src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0
    return target


@pytest.fixture(scope='module')
def pinfix_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('pinfix') / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0
    code, report = install_pinfix(target)
    assert code == 0, report
    return target


def test_face_install_reproduces_the_pod_sources(pod_face):
    if not FACE_COPY.is_dir():
        pytest.skip(f'{FACE_COPY} not available')
    for name in PATCHED:
        assert sha(pod_face / name) == sha(FACE_COPY / name), name


def test_pinfix_plans_applies_refuses_twice_and_needs_face(pod_face, pod_v2):
    before = {p.name: sha(p) for p in pod_face.iterdir()}
    code, planned = install_pinfix(pod_face, '--dry-run')
    assert code == 0 and all(e['count'] == 1 for e in planned['edits']) and {p.name: sha(p) for p in pod_face.iterdir()} == before
    code, report = install_pinfix(pod_face)
    assert code == 0 and report['status'] == 'applied'
    changed = {name for name in before if sha(pod_face / name) != before[name]}
    assert changed == {'Sub01HomeLab.cpp', 'Sub01HomeHands.cpp'}
    for name in changed:
        assert sha(pod_face / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_face / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_face.iterdir()}
    assert install_pinfix(pod_face)[0] == 2 and install_face(pod_face)[0] == 2
    assert {p.name: sha(p) for p in pod_face.iterdir()} == after
    v2_before = {p.name: sha(p) for p in pod_v2.iterdir()}
    code, refused = install_pinfix(pod_v2)
    assert code == 2 and 'lacks the face patch' in refused['reason'] and {p.name: sha(p) for p in pod_v2.iterdir()} == v2_before


def test_pinfix_text(pinfix_patched):
    cpp, proxy = lf(pinfix_patched / 'Sub01HomeLab.cpp'), lf(pinfix_patched / 'Sub01HomeHands.cpp')
    face_cpp = lf(FACE_COPY / 'Sub01HomeLab.cpp') if FACE_COPY.is_dir() else None
    desk = cpp[cpp.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot('):cpp.index(FACE_END, cpp.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot('))]
    assert 'Safe(' not in desk and 'return -1' not in desk and 'if(Slot==2){' in desk and 'SUB01_STREAMER_VISUAL_MOUSE_AS_SITTING_LOOP' in desk
    assert '(log only; per-clip drift guard)' in desk
    camera = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){'):cpp.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot(')]
    if face_cpp is not None:  # face camera byte-identical
        assert camera in face_cpp
    pin = proxy[proxy.index(' void PinStreamerV2('):proxy.index(FACE_END, proxy.index(' void PinStreamerV2('))]
    assert 'StreamerV2PinLocals' not in pin and 'StreamerV2PinPelvis' not in pin  # never R9 as the pin reference
    for text in ('StreamerV2ClipRef(Only?Only:Current.GetSequence())', 'Reference[I].Blend(From->Locals[I],To->Locals[I],Progress)',
                 'if(I>0){T=Reference[I];continue;}', 'Reference[0].GetTranslation()+Delta*(StreamerV2PinRadiusCm/Cm)'):
        assert text in pin, text
    assert 'const float At=Seq==StreamerV2Reference?StreamerV2ReferenceSeconds:0.f;' in proxy
    assert 'PinStreamerV2(Probe.Pose,false,Seq);' in proxy and 'PinStreamerV2(Output.Pose,true);' in proxy
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    assert evaluate.index('PrepareStreamerV2Pin(Output)') < evaluate.index('MatchStreamerV2Phase(Output);') < evaluate.index('Blend.Evaluate_AnyThread(Output);')
    for name in PATCHED:
        text = lf(pinfix_patched / name)
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_pinfix_cpp_compiles_syntax_only_against_stub(pinfix_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(pinfix_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


PINFIX_DRIVER = FACE_DRIVER[:FACE_DRIVER.index(' // desk guard:')] + r''' // pin fix: the R9 audit no longer chooses clips; mouse always plays the sitting loop
 USub01HomeHandsInstance Anim; UAnimSequence Sit, Type, Reach; C.StreamerVisualV2Clips.Reset(); C.StreamerVisualV2Clips.Add(&Sit); C.StreamerVisualV2Clips.Add(&Type); C.StreamerVisualV2Clips.Add(&Reach);
 CHECK(C.StreamerVisualDeskSlot(&Anim, 0) == 0 && C.StreamerVisualDeskSlot(&Anim, 1) == 1 && C.StreamerVisualDeskSlot(&Anim, 2) == 0, 30);
 CHECK(Anim.StreamerVisualAuditClips.Num() == 3, 31);
 Anim.StreamerVisualAuditDone = true; Anim.StreamerVisualClipOffsetCm = {116.1f, 116.1f, 19.4f}; Anim.StreamerVisualClipAngleDeg = {25.6f, 25.6f, 29.5f};
 CHECK(C.StreamerVisualDeskSlot(&Anim, 0) == 0 && C.StreamerVisualDeskSlot(&Anim, 1) == 1 && C.StreamerVisualDeskSlot(&Anim, 2) == 0, 32);  // field audit values
 C.StreamerVisualV2Clips[0] = nullptr; CHECK(C.StreamerVisualDeskSlot(&Anim, 2) == 0 && C.StreamerVisualDeskSlot(&Anim, 0) == 0, 33);  // missing: frozen R9 in Apply
 CHECK(C.StreamerVisualDeskSlot(nullptr, 2) == 0 && C.StreamerVisualDeskSlot(nullptr, 1) == 1, 34);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_pinfix_logic_runs_and_v2_face_unchanged(pinfix_patched, tmp_path):
    run = _run_driver(build_units(pinfix_patched, tmp_path / 'a', end=FACE_END, driver=PINFIX_DRIVER), tmp_path / 'a')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(build_units(pinfix_patched, tmp_path / 'b', end=FACE_END), tmp_path / 'b')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ no pin (measure only)
NOPIN_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_no_pin.py'
NOPIN_MARKER = '// SUB01_STREAMER_VISUAL_V2_NOPIN'


def install_nopin(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(NOPIN_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod_pinfix(tmp_path) -> Path:
    target = tmp_path / 'pinfix-src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0
    return target


@pytest.fixture(scope='module')
def nopin_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('nopin') / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0
    code, report = install_nopin(target)
    assert code == 0, report
    return target


def test_nopin_plans_applies_refuses_twice_and_needs_pinfix(pod_pinfix, pod_face):
    before = {p.name: sha(p) for p in pod_pinfix.iterdir()}
    code, planned = install_nopin(pod_pinfix, '--dry-run')
    assert code == 0 and len(planned['edits']) == 3 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_pinfix.iterdir()} == before
    code, report = install_nopin(pod_pinfix)
    assert code == 0 and report['status'] == 'applied' and report['pin'] == {'applied': False, 'measured': report['pin']['measured']}
    changed = {name for name in before if sha(pod_pinfix / name) != before[name]}
    assert changed == {'Sub01HomeHands.cpp'}
    name = 'Sub01HomeHands.cpp'
    assert sha(pod_pinfix / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
    raw = (pod_pinfix / name).read_bytes()
    assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_pinfix.iterdir()}
    assert install_nopin(pod_pinfix)[0] == 2 and install_pinfix(pod_pinfix)[0] == 2
    assert {p.name: sha(p) for p in pod_pinfix.iterdir()} == after
    face_before = {p.name: sha(p) for p in pod_face.iterdir()}
    code, refused = install_nopin(pod_face)
    assert code == 2 and 'lacks the pin fix' in refused['reason'] and {p.name: sha(p) for p in pod_face.iterdir()} == face_before


def test_nopin_text(nopin_patched):
    proxy = lf(nopin_patched / 'Sub01HomeHands.cpp')
    assert proxy.count(NOPIN_MARKER) == 3
    assert ' static constexpr bool StreamerV2PinEnabled=false;' in proxy
    pin = proxy[proxy.index(' void PinStreamerV2('):proxy.index(FACE_END, proxy.index(' void PinStreamerV2('))]
    record = pin.index('if(Record){FTransform Pelvis=FTransform::Identity;')
    gate = pin.index('if(!StreamerV2PinEnabled)return;')
    assert record < gate < pin.index('const auto& Bones=Composed.GetBoneContainer();')  # measured, then nothing moved
    assert 'applied=0 (measure only)' in proxy
    assert 'PinStreamerV2(Probe.Pose,false,Seq);' in proxy and 'PinStreamerV2(Output.Pose,true);' in proxy  # call sites untouched
    for name in PATCHED:
        text = lf(nopin_patched / name)
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
    for name in ('Sub01HomeLab.h', 'Sub01HomeLab.cpp', 'Sub01HomeHands.h'):  # byte-identical to the pin fix
        assert NOPIN_MARKER not in lf(nopin_patched / name)


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_nopin_cpp_compiles_syntax_only_against_stub(nopin_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(nopin_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_nopin_logic_runs_and_v2_face_pinfix_unchanged(nopin_patched, tmp_path):
    run = _run_driver(build_units(nopin_patched, tmp_path / 'a', end=FACE_END, driver=PINFIX_DRIVER), tmp_path / 'a')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(build_units(nopin_patched, tmp_path / 'b', end=FACE_END), tmp_path / 'b')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ mouth (voice server -> jaw bone / head emphasis)
MOUTH_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_mouth.py'
MOUTH_MARKER = '// SUB01_STREAMER_VISUAL_V2_MOUTH'
MOUTH_END = MOUTH_MARKER + ' END'


def install_mouth(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(MOUTH_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


def _stack(target: Path, *installers) -> dict:
    """Apply the installers in order; every one must succeed. Returns the last report."""
    report = None
    for step in installers:
        code, report = step(target)
        assert code == 0, report
    return report


@pytest.fixture(scope='module')
def mouth_on_v2(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('mouth-v2') / 'src'
    shutil.copytree(SOURCE, target)
    _stack(target, install, install_mouth)
    return target


@pytest.fixture(scope='module')
def mouth_on_all(tmp_path_factory) -> Path:
    """The pod stack (v2, face, pin fix, no pin) with the mouth layer last: what the coordinator builds."""
    target = tmp_path_factory.mktemp('mouth-all') / 'src'
    shutil.copytree(SOURCE, target)
    _stack(target, install, install_face, install_pinfix, install_nopin, install_mouth)
    return target


def test_mouth_install_plans_applies_and_refuses_twice(pod_v2):
    before = {p.name: sha(p) for p in pod_v2.iterdir()}
    code, planned = install_mouth(pod_v2, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == 9 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == before
    code, report = install_mouth(pod_v2)
    assert code == 0 and report['status'] == 'applied' and report['requires'] == MARKER
    assert report['layers_present'] == {'face': False, 'pin_fix': False, 'no_pin': False}
    assert report['rig']['lip_sync'] is False and report['rig']['found'].startswith('none')
    assert report['mouth']['file'] == '/home/unreal/.sub01-private/streamer/mouth.json' and report['mouth']['poll_hz_max'] == 30
    for name in PATCHED:
        assert report['files'][name]['before_sha256'] == before[name]
        assert sha(pod_v2 / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_v2 / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    for name in set(before) - set(PATCHED):
        assert sha(pod_v2 / name) == before[name]
    after = {p.name: sha(p) for p in pod_v2.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_mouth(pod_v2, *extra)
        assert code == 2 and again['status'] == 'refused' and 'already' in again['reason']
    assert install(pod_v2)[0] == 2
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == after


def test_mouth_install_refuses_without_v2(pod):
    before = {p.name: sha(p) for p in pod.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, report = install_mouth(pod, *extra)
        assert code == 2 and 'lacks the v2 install' in report['reason']
    assert {p.name: sha(p) for p in pod.iterdir()} == before


def test_mouth_missing_anchor_refuses_without_writing(pod_v2):
    hands = pod_v2 / 'Sub01HomeHands.cpp'
    hands.write_bytes(hands.read_bytes().replace(b'then breathing; head below', b'then breathing, head below', 1))
    before = {p.name: sha(p) for p in pod_v2.iterdir()}
    code, report = install_mouth(pod_v2)
    assert code == 2 and 'anchor missing in Sub01HomeHands.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_v2.iterdir()} == before  # Sub01HomeLab.* had valid anchors and are untouched too


def test_mouth_applies_in_every_layer_order(tmp_path):
    """Mouth after the pod stack (what the coordinator does) and mouth before the others: each layer applies exactly once."""
    orders = {'last': (install, install_face, install_pinfix, install_nopin),
              'first': (install, install_mouth, install_face, install_pinfix, install_nopin)}
    for label, steps in orders.items():
        target = tmp_path / label
        shutil.copytree(SOURCE, target)
        _stack(target, *steps)
        if label == 'last':
            code, report = install_mouth(target)
            assert code == 0 and report['layers_present'] == {'face': True, 'pin_fix': True, 'no_pin': True}
        for name in PATCHED:
            text = lf(target / name)
            assert text.count(MOUTH_MARKER + ' BEGIN') == text.count(MOUTH_END) == 1, (label, name)
            assert text.count(FACE_MARKER + ' BEGIN') == text.count(FACE_END) == 1, (label, name)
            assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), (label, name)
        for step in (install_mouth, install_face, install_pinfix, install_nopin, install):
            assert step(target)[0] == 2, label


def _mouth_blocks(text: str) -> set:
    lines = set()
    start = 0
    while True:
        i = text.find(MOUTH_MARKER + ' BEGIN', start)
        if i < 0:
            return lines
        j = text.index(MOUTH_END, i)
        lines.update(text[text.rfind('\n', 0, i) + 1:j].split('\n'))
        start = j


def test_mouth_text_and_other_layers_untouched(mouth_on_v2, mouth_on_all, patched, nopin_patched):
    for src, plain, end in ((mouth_on_v2, patched, MOUTH_END), (mouth_on_all, nopin_patched, FACE_END)):
        cpp, header = lf(src / 'Sub01HomeLab.cpp'), lf(src / 'Sub01HomeLab.h')
        hands_h, proxy = lf(src / 'Sub01HomeHands.h'), lf(src / 'Sub01HomeHands.cpp')
        for text in ('"/home/unreal/.sub01-private/streamer/mouth.json"', 'Schema==TEXT("sub01.streamer-mouth.v1")',
                     'StreamerVisualMouthPollAt=Now+1./30;', 'FMath::Abs(Epoch-Utc)<=0.5',
                     'S.st_uid==getuid()&&!(S.st_mode&0022)&&S.st_size>0&&S.st_size<=512', 'Open>=0&&Open<=1', 'FMath::Min(1.f,Dt*30.f)',
                     ' ApplyStreamerVisualMouth(Now,Epoch,Dt); // SUB01_STREAMER_VISUAL_V2_MOUTH', 'TEXT("mouth_open")', 'TEXT("mouth_energy")',
                     'TEXT("mouth_file_fresh")', 'TEXT("mouth_id")', 'TEXT("mouth_rig")', 'TEXT("jaw_bone")', 'TEXT("head_only")',
                     'SUB01_STREAMER_VISUAL_MOUTH_READY', 'SUB01_STREAMER_VISUAL_MOUTH_FILE_REJECTED'):
            assert text in cpp, text
        assert 'Receipt->SetBoolField(TEXT("facial_animation_or_lipsync"),false);' in cpp  # no lip sync is claimed
        assert 'void ApplyStreamerVisualMouth(double Now,double Epoch,float Dt);' in header
        assert 'UPROPERTY(Transient) float StreamerVisualMouthOpen=0;' in hands_h and 'UPROPERTY(Transient) int32 StreamerVisualMouthRig=0;' in hands_h
        mouth_proxy = proxy[proxy.index(MOUTH_MARKER + ' BEGIN'):proxy.index(MOUTH_END)]
        for text in ('TEXT("Jaw"),TEXT("jaw"),TEXT("JawRoot")', 'EndsWith(TEXT("Jaw"))', 'FName(TEXT("Head"))', '?12.:2.',
                     'FMath::Clamp(StreamerV2Mouth,0.f,1.f)', 'if(Compact.GetInt()<0)return;'):
            assert text in mouth_proxy, text
        assert 'Key->' not in mouth_proxy and 'UAnimSequence' not in mouth_proxy  # no raw UObject pointers in the proxy
        assert '  StreamerV2Mouth=Hands->StreamerVisualMouthOpen; // SUB01_STREAMER_VISUAL_V2_MOUTH' in proxy
        assert ' StreamerVisualMouthRig=Proxy.StreamerV2MouthRig; // SUB01_STREAMER_VISUAL_V2_MOUTH' in proxy
        # evaluated inside the streamer block, after the v2 reference/breathing pass and before the gaze offset reaches the Head
        evaluate = proxy[proxy.index('  if(StreamerVisualActive){\n'):]
        assert evaluate.index('if(StreamerV2)EvaluateStreamerV2(Output);') < evaluate.index('EvaluateStreamerV2Mouth(Output);') < evaluate.index('FindBoneIndex(TEXT("Head"))')
        # on the game thread: after the v2 clip/breathing/camera pass, before the receipt; the receipt line sits in the V2Anim block
        tick = cpp[cpp.index('bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){'):]
        assert tick.index('ApplyStreamerVisualV2(Now,Dt);') < tick.index('ApplyStreamerVisualMouth(Now,Epoch,Dt);') < tick.index('TEXT("mouth_open")')
        assert tick.index('{auto* V2Anim=') < tick.index('TEXT("mouth_open")') < tick.index('TEXT("camera_blend")')
        # the mouth block of Sub01HomeLab.cpp lies between the v2 END and whatever follows, so build_units(end=...) covers it
        assert cpp.index(MARKER + ' END') < cpp.index(MOUTH_MARKER + ' BEGIN') < cpp.index(MOUTH_END) <= cpp.index(end) + len(end)
        for name in PATCHED:  # every line of the stack without the mouth survives; every new line is the mouth layer
            before, after = lf(plain / name), lf(src / name)
            assert closure.brace_walk(closure.strip(after)) == closure.brace_walk(closure.strip(before)), name
            assert not [line for line in before.split('\n') if line not in after.split('\n')], name
            extra = [line for line in after.split('\n') if line not in before.split('\n')]
            blocks = _mouth_blocks(after)
            assert extra and all(MOUTH_MARKER in line or line in blocks for line in extra), (name, [l for l in extra if MOUTH_MARKER not in l and l not in blocks])


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
@pytest.mark.parametrize('stack', ['mouth_on_v2', 'mouth_on_all'])
def test_mouth_cpp_compiles_syntax_only_against_stub(request, tmp_path, compiler, unit, stack):
    src = request.getfixturevalue(stack)
    name, path, flags = compiler
    units = build_units(src, tmp_path, end=MOUTH_END if stack == 'mouth_on_v2' else FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


MOUTH_DRIVER = r'''
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
int main() {
 USkeletalMeshComponent Body; ASub01HomeCharacter C; C.FirstPersonBody = &Body;
 // the stub's lstat is the real one and the pod path does not exist here: every poll finds no file and closes the mouth
 C.StreamerVisualMouthTarget = 1; C.StreamerVisualMouthOpen = 1; C.StreamerVisualMouthFresh = true; C.ApplyStreamerVisualMouth(10, 1000, .05f);
 CHECK(C.StreamerVisualMouthTarget == 0 && C.StreamerVisualMouthFresh == false && C.StreamerVisualMouthOpen < 1, 1);
 CHECK(C.StreamerVisualMouthPollAt > 10 && Near(C.StreamerVisualMouthPollAt, 10 + 1. / 30, 1e-9), 2);  // at most 30 Hz
 // between polls the target holds and the open value approaches it at 30/s: Dt .02 -> 60 % of the gap per tick
 C.StreamerVisualMouthTarget = 1; C.StreamerVisualMouthOpen = 0; C.ApplyStreamerVisualMouth(10.01, 1000, .02f);
 CHECK(C.StreamerVisualMouthTarget == 1 && Near(C.StreamerVisualMouthOpen, .6, 1e-6), 3);
 for (int K = 0; K < 20; ++K) C.ApplyStreamerVisualMouth(10.02, 1000, .02f);
 CHECK(C.StreamerVisualMouthOpen > .99 && C.StreamerVisualMouthOpen <= 1, 4);
 // a target of 0 closes the mouth to exactly 0, not a lingering fraction
 C.StreamerVisualMouthTarget = 0; for (int K = 0; K < 20; ++K) C.ApplyStreamerVisualMouth(10.03, 1000, .02f);
 CHECK(C.StreamerVisualMouthOpen == 0, 5);
 // a large frame time never overshoots
 C.StreamerVisualMouthTarget = .4f; C.ApplyStreamerVisualMouth(10.03, 1000, .5f); CHECK(Near(C.StreamerVisualMouthOpen, .4, 1e-6), 6);
 // the next poll (no file) closes it again; nothing is logged as "ready" without an anim instance
 C.ApplyStreamerVisualMouth(10.04, 1000, .02f); CHECK(C.StreamerVisualMouthTarget == 0 && C.StreamerVisualMouthLogged == false, 7);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_mouth_logic_runs_and_earlier_layers_unchanged(mouth_on_v2, mouth_on_all, tmp_path):
    run = _run_driver(build_units(mouth_on_v2, tmp_path / 'a', end=MOUTH_END, driver=MOUTH_DRIVER), tmp_path / 'a')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(build_units(mouth_on_all, tmp_path / 'b', end=FACE_END, driver=MOUTH_DRIVER), tmp_path / 'b')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(build_units(mouth_on_v2, tmp_path / 'c', end=MOUTH_END), tmp_path / 'c')  # the v2 driver
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(build_units(mouth_on_all, tmp_path / 'd', end=FACE_END, driver=PINFIX_DRIVER), tmp_path / 'd')  # face + pin fix driver
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ seat fix (mesh component offset, measured face camera)
SEATFIX_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_seat_fix.py'
SEATFIX_MARKER = '// SUB01_STREAMER_VISUAL_V2_SEATFIX'
_SEATFIX_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_seatfix', SEATFIX_INSTALL)
seatfix = importlib.util.module_from_spec(_SEATFIX_SPEC)
_SEATFIX_SPEC.loader.exec_module(seatfix)


def install_seatfix(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(SEATFIX_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod_nopin(tmp_path) -> Path:
    target = tmp_path / 'nopin-src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0 and install_nopin(target)[0] == 0
    return target


@pytest.fixture(scope='module')
def seatfix_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('seatfix') / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0 and install_nopin(target)[0] == 0
    code, report = install_seatfix(target)
    assert code == 0, report
    return target


def test_seatfix_plans_applies_refuses_twice_and_needs_nopin(pod_nopin, pod_pinfix):
    before = {p.name: sha(p) for p in pod_nopin.iterdir()}
    code, planned = install_seatfix(pod_nopin, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == 14 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_nopin.iterdir()} == before
    code, report = install_seatfix(pod_nopin)
    assert code == 0 and report['status'] == 'applied'
    assert report['face']['fov'] == seatfix.FACE_FOV and report['seat']['controller_yaw'].startswith('bUseControllerRotationYaw=false')
    changed = {name for name in before if sha(pod_nopin / name) != before[name]}
    assert changed == set(PATCHED)
    for name in PATCHED:
        assert report['files'][name]['before_sha256'] == before[name]
        assert sha(pod_nopin / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_nopin / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_nopin.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_seatfix(pod_nopin, *extra)
        assert code == 2 and 'already' in again['reason']
    assert install_nopin(pod_nopin)[0] == 2 and install_pinfix(pod_nopin)[0] == 2 and install_face(pod_nopin)[0] == 2 and install(pod_nopin)[0] == 2
    assert {p.name: sha(p) for p in pod_nopin.iterdir()} == after
    pinfix_before = {p.name: sha(p) for p in pod_pinfix.iterdir()}
    code, refused = install_seatfix(pod_pinfix)
    assert code == 2 and 'lacks the no-pin patch' in refused['reason'] and {p.name: sha(p) for p in pod_pinfix.iterdir()} == pinfix_before


def test_seatfix_missing_anchor_refuses_without_writing(pod_nopin):
    hands = pod_nopin / 'Sub01HomeHands.cpp'
    hands.write_bytes(hands.read_bytes().replace(b'PinStreamerV2(Output.Pose,true); // SUB01_STREAMER_VISUAL_V2_FACE: desk pin',
                                                 b'PinStreamerV2(Output.Pose,true); // SUB01_STREAMER_VISUAL_V2_FACE: desk  pin', 1))
    before = {p.name: sha(p) for p in pod_nopin.iterdir()}
    code, report = install_seatfix(pod_nopin)
    assert code == 2 and 'anchor missing in Sub01HomeHands.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_nopin.iterdir()} == before


def test_seatfix_text(seatfix_patched):
    cpp, header = lf(seatfix_patched / 'Sub01HomeLab.cpp'), lf(seatfix_patched / 'Sub01HomeLab.h')
    hands_h, proxy = lf(seatfix_patched / 'Sub01HomeHands.h'), lf(seatfix_patched / 'Sub01HomeHands.cpp')
    for name in PATCHED:
        text = lf(seatfix_patched / name)
        assert text.count(SEATFIX_MARKER + ' BEGIN') == text.count(SEATFIX_MARKER + ' END') == 1, name
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
        # the seat fix sits inside the v2 .. face range, so the fields/methods extraction of build_units(end=FACE_END) sees it
        assert text.index(SEATFIX_MARKER + ' BEGIN') < text.index(FACE_MARKER + ' BEGIN') < text.index(FACE_END)
    # root yaw decoupled from the camera look; authored relative transform remembered; offset applied to the mesh component only
    start = cpp[cpp.index('void ASub01HomeCharacter::StartStreamerVisualV2('):cpp.index('bool ASub01HomeCharacter::ParseStreamerVisualV2(')]
    assert 'StreamerVisualControllerYawWas=bUseControllerRotationYaw;bUseControllerRotationYaw=false;' in start
    assert 'StreamerVisualBodyRelative=FirstPersonBody?FirstPersonBody->GetRelativeTransform():FTransform::Identity;' in start
    assert 'SUB01_STREAMER_VISUAL_SEAT_FIX_READY' in start and 'SUB01_STREAMER_VISUAL_FACE_RIG' in start and 'BodyMesh->GetMorphTargets()' in start
    assert f'FirstPersonBody->BoundsScale={seatfix.BOUNDS_SCALE:g}.f;FirstPersonBody->UpdateBounds();' in start
    apply = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualV2('):cpp.index('// SUB01_STREAMER_VISUAL_V2 END')]
    assert f'if(!Seat.Equals(StreamerVisualSeatApplied,{seatfix.SEAT_EPSILON:g})){{StreamerVisualSeatApplied=Seat;FirstPersonBody->SetRelativeTransform(Seat*StreamerVisualBodyRelative,false,nullptr,ETeleportType::TeleportPhysics);}}' in apply
    assert 'const bool SeatValid=StreamerVisualSchemaVersion==2&&Anim&&Anim->StreamerVisualSeatOffsetValid;' in apply
    assert apply.index('StreamerVisualSeatHas=SeatValid;') < apply.index('// Camera: "spectator" = the authored v1 view')
    assert 'SetWorldTransform' not in apply and 'SetActorLocationAndRotation' not in apply
    # face camera from the measured head towards the monitor; tuning file with the event's ownership rules; old formula gone
    camera = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){'):cpp.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot(')]
    for text in ('Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);', 'const FVector Side=FVector::CrossProduct(FVector::UpVector,-Towards);',
                 'StreamerVisualFaceLocation=Monitor+Towards*double(StreamerVisualFaceForwardCm)+Side*double(StreamerVisualFaceSideCm)+FVector(0,0,StreamerVisualFaceUpCm);',
                 'StreamerVisualFaceAim=Mean-FVector(0,0,StreamerVisualFaceAimDropCm);', 'FMath::Lerp(65.f,StreamerVisualFaceFov,Ease)',
                 'const FVector Mean=StreamerVisualFaceHeadSum*(1./StreamerVisualFaceHeadCount);', f'Now-StreamerVisualFaceSampleAt>={seatfix.FACE_SAMPLE_SECONDS:g}',
                 'if(Face&&!StreamerVisualFaceAimed)return;', 'Now-StreamerVisualFaceSelectedAt>=2', 'if(ReadStreamerVisualFaceTuning()){StreamerVisualFaceAimed=false;StreamerVisualFaceHeadCount=0;}',
                 f'const FVector Monitor({seatfix.MONITOR[0]},{seatfix.MONITOR[1]},{seatfix.MONITOR[2]});', 'SUB01_STREAMER_VISUAL_FACE_CAMERA location=%s aim=%s headMean=%s samples=%d'):
        assert text in camera, text
    assert 'Monitor+FVector(0,0,28)' not in camera and '42.f' not in camera and 'StreamerVisualFaceDistanceCm' not in cpp
    assert camera.index('const bool Settled=') < camera.index('if(Face&&!StreamerVisualFaceAimed&&(Settled||')
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    assert f'"{seatfix.TUNING_PATH}"' in tuning and f'Schema!=TEXT("{seatfix.TUNING_SCHEMA}")' in tuning and 'Sequence<=StreamerVisualFaceTuningSequence' in tuning
    for key, (lo, hi) in seatfix.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key}"),' in tuning and f',{lo},{hi});' in tuning, key
    assert 'S.st_uid==getuid()&&!(S.st_mode&0077)&&S.st_size>0&&S.st_size<=2048' in cpp[cpp.index('static bool Sub01StreamerVisualPrivateJson('):]
    # receipt fields (the existing ones kept)
    for text in ('TEXT("seat_offset")', 'TEXT("seat_offset_cm")', 'TEXT("seat_offset_yaw_deg")', 'TEXT("seat_offset_applied")', 'TEXT("seat_offset_settled")',
                 'TEXT("pelvis_world")', 'TEXT("head_world")', 'TEXT("face_camera_location")', 'TEXT("face_camera_aim")', 'TEXT("face_camera_tuning_sequence")',
                 'TEXT("camera_world")', 'TEXT("body_bounds")', 'TEXT("clip_audit_done")', 'TEXT("desk_offset_before_pin_cm")', 'TEXT("face_camera_blend")', 'TEXT("camera_fov")'):
        assert text in cpp, text
    assert f'StreamerVisualFaceUpCm={seatfix.FACE_UP_CM:g}.f' in header and f'StreamerVisualFaceFov={seatfix.FACE_FOV:g}.f' in header and f'StreamerVisualFaceForwardCm={seatfix.FACE_FORWARD_CM:g}.f' in header
    # proxy: per-clip D (yaw twist + exact translation), crossfade blend, published after evaluation; the no-pin guard still only measures
    assert 'UPROPERTY(Transient) FTransform StreamerVisualSeatOffset;' in hands_h and 'UPROPERTY(Transient) int32 StreamerVisualPelvisBone=-1;' in hands_h
    for text in ('static FQuat StreamerV2YawTwist(const FQuat& Q){const FQuat T(0,0,Q.Z,Q.W);', 'const FQuat Twist=StreamerV2YawTwist(R9.GetRotation()*Clip.GetRotation().Inverse());',
                 'return FTransform(Twist,R9.GetTranslation()-Twist.RotateVector(Clip.GetTranslation()));',
                 'StreamerV2Seat=To->Seat;if(From&&From->SeatValid)StreamerV2Seat.Blend(From->Seat,To->Seat,Progress);', 'StreamerV2SeatSettled=Progress>=1;',
                 'if(PelvisValid){Entry.Seat=StreamerV2SeatFor(StreamerV2PinPelvis,Pelvis);Entry.SeatValid=true;', 'SUB01_STREAMER_VISUAL_SEAT_OFFSET clip=%s',
                 'FTransform Seat=FTransform::Identity;bool SeatValid=false;};FStreamerV2ClipRef StreamerV2ClipRefs[6];',
                 ' static constexpr bool StreamerV2PinEnabled=false;', 'if(!StreamerV2PinEnabled)return;',
                 ' StreamerVisualSeatOffset=Proxy.StreamerV2Seat;StreamerVisualSeatOffsetValid=Proxy.StreamerV2SeatValid;StreamerVisualSeatSettled=Proxy.StreamerV2SeatSettled;'):
        assert text in proxy, text
    eval_body = proxy[proxy.index('void EvaluateStreamerV2(FPoseContext& Output){'):]
    assert eval_body.index('PublishStreamerV2Seat();') < eval_body.index('PinStreamerV2(Output.Pose,true);') < eval_body.index('StreamerV2HandsValid=')
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    assert evaluate.index('PrepareStreamerV2Pin(Output)') < evaluate.index('Blend.Evaluate_AnyThread(Output);') < evaluate.index('EvaluateStreamerV2(Output);')


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_seatfix_cpp_compiles_syntax_only_against_stub(seatfix_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(seatfix_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


def _seatfix_face_expectations() -> dict:
    """The face camera the driver expects for Head (214,-300,135) from the installer's constants (same formula, Python)."""
    import math
    head = (214.0, -300.0, 135.0)
    dx, dy = head[0] - seatfix.MONITOR[0], head[1] - seatfix.MONITOR[1]  # from the monitor towards him
    n = math.hypot(dx, dy)
    tx, ty = dx / n, dy / n
    sx, sy = ty, -tx  # Up x (-Towards) (left-handed): his right
    loc = (seatfix.MONITOR[0] + tx * seatfix.FACE_FORWARD_CM + sx * seatfix.FACE_SIDE_CM, seatfix.MONITOR[1] + ty * seatfix.FACE_FORWARD_CM + sy * seatfix.FACE_SIDE_CM,
           seatfix.MONITOR[2] + seatfix.FACE_UP_CM)
    aim = (head[0], head[1], head[2] - seatfix.FACE_AIM_DROP_CM)
    d = (aim[0] - loc[0], aim[1] - loc[1], aim[2] - loc[2])
    return {'loc': loc, 'yaw': math.degrees(math.atan2(d[1], d[0])), 'pitch': math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))),
            'fov': seatfix.FACE_FOV, 'mid_fov': (65 + seatfix.FACE_FOV) / 2}


SEATFIX_DRIVER = r'''
#include <cstdlib>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N) { for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += .1; C.ApplyStreamerVisualV2(0, .1f); } }  // 10 fps stub clock
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 const FTransform Rel0(FQuat::Identity, FVector(0, 0, -91), FVector(1, 1, 1));
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Body.StubRelative = Rel0; Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65; C.bUseControllerRotationYaw = true;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle");
 // the root no longer follows the camera look; the authored relative transform is remembered; the body bounds are scaled for the offset pose
 CHECK(!C.bUseControllerRotationYaw && C.StreamerVisualControllerYawWas && C.StreamerVisualBodyRelativeValid && C.StreamerVisualBodyRelative.Equals(Rel0, 1e-9), 1);
 CHECK(Near(Body.BoundsScale, @@BOUNDS@@, 1e-6) && Body.StubBoundsUpdates == 1, 9);
 Ticks(C, 2); CHECK(!C.StreamerVisualSeatHas && Body.StubRelative.Equals(Rel0, 1e-9), 2);  // no offset published yet: the mesh is untouched
 // the proxy publishes the field offset (Desk7 loops: ~99 cm along +Y, 15.5 cm up, -25.6 deg yaw): mesh relative = D * authored relative
 const FQuat Yaw = FRotator(0, -25.6, 0).Quaternion(); const FTransform D(Yaw, FVector(1, 99, 15.5), FVector(1, 1, 1));
 Anim.StreamerVisualSeatOffset = D; Anim.StreamerVisualSeatOffsetValid = true; Anim.StreamerVisualSeatSettled = true;
 Ticks(C, 1); const FTransform Expected = D * Rel0;
 CHECK(C.StreamerVisualSeatHas && Body.StubRelative.Equals(Expected, 1e-6) && Near(Body.StubRelative.GetTranslation().Y, 99, 1e-9) && Near(Body.StubRelative.GetTranslation().Z, -75.5, 1e-9) && Near(Body.StubRelative.Rotator().Yaw, -25.6, 1e-6), 3);
 // below the epsilon nothing is re-applied; above it is; a v1 event restores the authored relative transform once, then nothing touches the mesh
 Body.StubRelative = FTransform(); Anim.StreamerVisualSeatOffset = FTransform(Yaw, FVector(1, 99.005, 15.5), FVector(1, 1, 1)); Ticks(C, 1); CHECK(Body.StubRelative.Equals(FTransform(), 1e-9), 4);
 Anim.StreamerVisualSeatOffset = FTransform(Yaw, FVector(1, 99.5, 15.5), FVector(1, 1, 1)); Ticks(C, 1); CHECK(Near(Body.StubRelative.GetTranslation().Y, 99.5, 1e-9), 5);
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 1); CHECK(!C.StreamerVisualSeatHas && Body.StubRelative.Equals(Rel0, 1e-9), 6);
 Body.StubRelative = FTransform(); Ticks(C, 2); CHECK(Body.StubRelative.Equals(FTransform(), 1e-9), 7);
 C.StreamerVisualSchemaVersion = 2; Anim.StreamerVisualSeatOffset = D; Ticks(C, 1); CHECK(C.StreamerVisualSeatHas && Body.StubRelative.Equals(Expected, 1e-6), 8);
 // face camera: waits (camera untouched) until the seat offset is settled and applied, then samples the Head bone for @@SAMPLE@@ s and is placed on the monitor
 Body.StubHeadIndex = 7; Body.StubHead = FVector(214, -300, 135); Anim.StreamerVisualSeatSettled = false;
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 5);
 CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334 && C.StreamerVisualFaceHeadCount == 0, 10);
 Anim.StreamerVisualSeatSettled = true; Ticks(C, 5);  // 0.5 s of samples: still waiting, the camera untouched
 CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceHeadCount == 5 && C.StreamerVisualFaceAlpha == 0 && Camera.StubWorld.Translation.X == 334, 11);
 for (int K = 0; K < 8; ++K) { Body.StubHead = FVector(K % 2 ? 204 : 224, -300, 135); Ticks(C, 1); }  // sway +-10 around 214 over > 1 s: the mean is aimed at, not the last sample
 CHECK(C.StreamerVisualFaceAimed && C.StreamerVisualFaceAimSource == TEXT("head") && Near(C.StreamerVisualFaceAim.X, 214, 1.5) && Near(C.StreamerVisualFaceAim.Y, -300, 1e-6) && Near(C.StreamerVisualFaceAim.Z, 135 - @@DROP@@, 1e-6), 12);
 CHECK(Near(C.StreamerVisualFaceLocation.X, @@LX@@, .05) && Near(C.StreamerVisualFaceLocation.Y, @@LY@@, .05) && Near(C.StreamerVisualFaceLocation.Z, @@LZ@@, 1e-6) && Near(C.StreamerVisualFaceLook.Yaw, @@YAW@@, 2.5) && Near(C.StreamerVisualFaceLook.Pitch, @@PITCH@@, .5), 13);
 Ticks(C, 4); CHECK(C.StreamerVisualFaceAlpha >= .5 - 1e-5 && C.StreamerVisualFaceAlpha <= .7 + 1e-5 && Camera.FieldOfView > 65 && Camera.FieldOfView < @@FOV@@, 14);  // the 1 s blend began with the aim
 Ticks(C, 7);
 CHECK(C.StreamerVisualFaceAlpha == 1 && Near(Camera.FieldOfView, @@FOV@@, 1e-6) && Near(Camera.StubWorld.Translation.X, @@LX@@, .05) && Near(Camera.StubWorld.Translation.Y, @@LY@@, .05) && Near(Camera.StubWorld.Translation.Z, @@LZ@@, 1e-6), 15);
 // the 2 s fallback: an unsettled offset still gets a camera after 2 s of waiting (plus the sampling second)
 C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 11); CHECK(C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334 && C.StreamerVisualFaceSelectedAt < 0, 16);
 Anim.StreamerVisualSeatSettled = false; FPlatformTime::StubNow = 100; C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 3); CHECK(!C.StreamerVisualFaceAimed && Near(C.StreamerVisualFaceSelectedAt, 100.1, 1e-9) && C.StreamerVisualFaceHeadCount == 0, 17);
 FPlatformTime::StubNow = 101.9; Ticks(C, 1); CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceHeadCount == 0, 18);
 FPlatformTime::StubNow = 102.1; Ticks(C, 1); CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceHeadCount == 1, 19);  // sampling started
 Ticks(C, 11); CHECK(C.StreamerVisualFaceAimed, 20);
 // an implausible Head location falls back to body + 120 at once; a v1 event fades the face layer out
 C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 11); Body.StubHead = FVector(0, 0, 0); Anim.StreamerVisualSeatSettled = true;
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 1); CHECK(C.StreamerVisualFaceAimed && C.StreamerVisualFaceAimSource == TEXT("body+120") && Near(C.StreamerVisualFaceAim.Z, 6.191812330665947 + 120 - @@DROP@@, 1e-6), 21);
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 11); CHECK(C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334, 22);
 // desk slot unchanged from the pin fix: mouse plays the sitting loop, typing its own
 UAnimSequence Sit, Type, Reach; C.StreamerVisualV2Clips.Reset(); C.StreamerVisualV2Clips.Add(&Sit); C.StreamerVisualV2Clips.Add(&Type); C.StreamerVisualV2Clips.Add(&Reach);
 CHECK(C.StreamerVisualDeskSlot(&Anim, 0) == 0 && C.StreamerVisualDeskSlot(&Anim, 1) == 1 && C.StreamerVisualDeskSlot(&Anim, 2) == 0, 23);
 std::printf("ok\n");
 return 0;
}
'''

SEAT_MATH_DRIVER = r'''
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
int main() {
 // the field numbers: R9's pelvis at 0.7 s and a Desk7 loop's at 0 s (component space), the loop also turned 25.6 deg and tilted 5 deg
 const FTransform R9(FQuat::Identity, FVector(0.908, 6.407, 88.529), FVector(1, 1, 1));
 const FTransform Clip(FRotator(5, 25.6, 0).Quaternion(), FVector(-0.058, -92.651, 73.049), FVector(1, 1, 1));
 const FTransform D = FSub01HandsProxy::StreamerV2SeatFor(R9, Clip), Seated = Clip * D;
 CHECK(Near(Seated.GetTranslation().X, 0.908, 1e-9) && Near(Seated.GetTranslation().Y, 6.407, 1e-9) && Near(Seated.GetTranslation().Z, 88.529, 1e-9), 1);  // pelvis exactly on R9's
 CHECK(Near(Seated.Rotator().Yaw, 0, 1e-6) && Near(Seated.Rotator().Pitch, 5, 1e-6) && Near(Seated.Rotator().Roll, 0, 1e-6), 2);  // yaw matched, the clip's own tilt kept
 CHECK(Near(D.Rotator().Yaw, -25.6, 1e-6) && Near(D.Rotator().Pitch, 0, 1e-9) && Near(D.Rotator().Roll, 0, 1e-9) && Near(D.GetTranslation().Z, 88.529 - 73.049, 1e-9), 3);
 CHECK(D.GetTranslation().Size() > 95 && D.GetTranslation().Size() < 105, 4);  // about 1 m: the station offset
 CHECK(FSub01HandsProxy::StreamerV2SeatFor(R9, R9).Equals(FTransform::Identity, 1e-9), 5);  // the frozen R9 itself: identity
 CHECK(Near(FSub01HandsProxy::StreamerV2YawTwist(FRotator(30, 40, 0).Quaternion()).Rotator().Yaw, 40, 1e-6) && Near(FSub01HandsProxy::StreamerV2YawTwist(FRotator(30, 40, 0).Quaternion()).Rotator().Pitch, 0, 1e-9), 6);
 CHECK(FSub01HandsProxy::StreamerV2YawTwist(FQuat(0, 0, 0, 0)).Equals(FQuat::Identity, 1e-12), 7);
 // a crossfade blend of two offsets lands in between (what PublishStreamerV2Seat does with Progress)
 FTransform Mid = FTransform::Identity; Mid.Blend(FTransform::Identity, D, .5f);
 CHECK(Near(Mid.GetTranslation().Z, (88.529 - 73.049) / 2, 1e-6) && Near(Mid.Rotator().Yaw, -12.8, 1e-6), 8);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_seatfix_logic_runs(seatfix_patched, tmp_path):
    e = _seatfix_face_expectations()
    driver = (SEATFIX_DRIVER.replace('@@LX@@', repr(e['loc'][0])).replace('@@LY@@', repr(e['loc'][1])).replace('@@LZ@@', repr(e['loc'][2]))
              .replace('@@YAW@@', repr(e['yaw'])).replace('@@PITCH@@', repr(e['pitch'])).replace('@@MIDFOV@@', repr(e['mid_fov']))
              .replace('@@FOV@@', repr(e['fov'])).replace('@@DROP@@', repr(seatfix.FACE_AIM_DROP_CM)).replace('@@SAMPLE@@', repr(seatfix.FACE_SAMPLE_SECONDS))
              .replace('@@BOUNDS@@', repr(seatfix.BOUNDS_SCALE)))
    units = build_units(seatfix_patched, tmp_path, end=FACE_END, driver=driver, hands_driver=SEAT_MATH_DRIVER)
    run = _run_driver(units, tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(units, tmp_path, unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v2_behaviour_unchanged_under_seatfix(seatfix_patched, tmp_path):
    """The whole v2 driver (debounce, bounds, monitor framing, spectator/monitor blend) passes on the seat-fixed code."""
    run = _run_driver(build_units(seatfix_patched, tmp_path, end=FACE_END), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
