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
 FQuat() = default;
 FQuat(double InX, double InY, double InZ, double InW) : X(InX), Y(InY), Z(InZ), W(InW) {}
 FQuat operator*(const FQuat& Q) const { return Q; }
 FQuat GetNormalized() const { return *this; }
 FVector RotateVector(const FVector& V) const { const FVector Q(X, Y, Z); const FVector T = FVector::CrossProduct(Q, V) * 2.; return V + T * W + FVector::CrossProduct(Q, T); }  // UE formula
 FRotator Rotator() const;
 double AngularDistance(const FQuat& Q) const { return 2 * std::acos(std::fmin(1.0, std::fabs(X * Q.X + Y * Q.Y + Z * Q.Z + W * Q.W))); }
 static FQuat Slerp(const FQuat& A, const FQuat&, double) { return A; }
};
struct FRotator {
 double Pitch = 0, Yaw = 0, Roll = 0;
 static const FRotator ZeroRotator;
 FRotator() = default;
 FRotator(double InPitch, double InYaw, double InRoll) : Pitch(InPitch), Yaw(InYaw), Roll(InRoll) {}
 FRotator& operator+=(const FRotator& R) { Pitch += R.Pitch; Yaw += R.Yaw; Roll += R.Roll; return *this; }
 FQuat Quaternion() const { return FQuat(); }
 FString ToString() const { return FString(); }
};
inline const FRotator FRotator::ZeroRotator{0, 0, 0};
inline FRotator FVector::Rotation() const { const double D = 180 / 3.14159265358979323846; return FRotator(std::atan2(Z, std::sqrt(X * X + Y * Y)) * D, std::atan2(Y, X) * D, 0); }
inline FRotator FQuat::Rotator() const { return FRotator(); }
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
 FRotator Rotator() const { return FRotator(); }
 FVector GetUnitAxis(EAxis::Type Axis) const { return Rotation.RotateVector(Axis == EAxis::X ? FVector(1, 0, 0) : Axis == EAxis::Y ? FVector(0, 1, 0) : FVector(0, 0, 1)); }
 bool ContainsNaN() const { return Translation.ContainsNaN(); }
 void NormalizeRotation() {}
 void Blend(const FTransform& A, const FTransform&, float) { *this = A; }
 FTransform operator*(const FTransform& Other) const { return Other; }
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
struct FPlatformTime { static double Seconds() { return 0; } };
struct FPlatformProcess { static uint32 GetCurrentProcessId() { return 0; } };
struct FDateTime { static FDateTime UtcNow() { return {}; } int64 ToUnixTimestamp() const { return 0; } int32 GetMillisecond() const { return 0; } };
struct FFileHelper { static bool LoadFileToString(FString&, const TCHAR*) { return false; } static bool SaveStringToFile(const FString&, const TCHAR*) { return false; } };
#define UTF8_TO_TCHAR(x) ((void)(x), u"")
#define TCHAR_TO_UTF8(x) ((void)(x), "")
class UObject { public: virtual ~UObject() = default; FString GetPathName() const { return FString(); } };
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
template<class T> T* Cast(UObject*) { return nullptr; }
template<class T> T* LoadObject(UObject*, const TCHAR*) { return nullptr; }
class USkeleton : public UObject {};
class USkeletalMesh : public UObject { public: USkeleton* GetSkeleton() const { return nullptr; } };
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
class USceneComponent : public UActorComponent {
public:
 FTransform StubWorld; FRotator StubRotation;
 const FTransform& GetComponentTransform() const { return StubWorld; }
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
 int32 StubHeadIndex = INDEX_NONE; FVector StubHead;
 USkeletalMesh* GetSkeletalMeshAsset() const { return nullptr; }
 int32 GetBoneIndex(FName) const { return StubHeadIndex; }
 FVector GetBoneLocation(FName) const { return StubHead; }
 UAnimInstance* GetAnimInstance() const { return nullptr; }
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
class APawn : public AActor { public: TObjectPtr<AController> Controller; };
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


def build_units(src: Path, work: Path, end: str = MARKER + ' END', driver: str = None) -> dict:
    """Translation units from the patched files; #line keeps diagnostics on the patched sources. `end` closes the
    streamer fields (Sub01HomeLab.h) and the appended methods (Sub01HomeLab.cpp): the v2 END, or the face END on top."""
    stub, hands_inc, char_inc = work / 'stub', work / 'hands_inc', work / 'char_inc'
    for d in (stub / 'Animation', hands_inc, char_inc):
        d.mkdir(parents=True, exist_ok=True)
    (stub / 'ue_stub.h').write_text(STUB)
    (stub / 'UObject').mkdir(exist_ok=True)
    for name in ('CoreMinimal.h', 'Animation/AnimInstance.h', 'UObject/UnrealType.h'):
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
    (work / 'hands.cpp').write_text('#include "Sub01HomeHands.h"\n#include "Sub01HomeLab.h"\n#include "Sub01CapturedLayerClock.h"\n'
                                    f'#line {at} "{src / "Sub01HomeHands.cpp"}"\n{proxy}\n')
    fields, _ = _block(header, ' bool TickPrivateStreamerVisual(float Dt);', end)
    methods, m_at = _block(cpp, MARKER + ' BEGIN', end)
    tick, t_at = _function(cpp, 'bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){')
    unit = CHARACTER.replace('@@FIELDS@@', fields).replace(
        '@@METHODS@@', f'#line {m_at} "{src / "Sub01HomeLab.cpp"}"\n{methods}').replace(
        '@@TICK@@', f'#line {t_at} "{src / "Sub01HomeLab.cpp"}"\n{tick}')
    (work / 'character.cpp').write_text(unit)
    (work / 'driver.cpp').write_text(unit + (DRIVER if driver is None else driver))
    return {'hands': (work / 'hands.cpp', hands_inc), 'character': (work / 'character.cpp', char_inc),
            'driver': (work / 'driver.cpp', char_inc), 'stub': stub}


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


def _run_driver(units: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    name, path, _ = COMPILERS[0]
    source, include = units['driver']
    binary = tmp_path / 'driver-bin'
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
