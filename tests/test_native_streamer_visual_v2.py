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
#include <map>
#include <memory>
#include <string>
#include <type_traits>
#include <initializer_list>
#include <utility>
#include <vector>
#include <functional>
#include <atomic>
#include <cerrno>
#include <cstring>
#include <ctime>
#include <fcntl.h>
#include <signal.h>
#include <pthread.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
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
struct FColor { uint8 B = 0, G = 0, R = 0, A = 0; };  // BGRA in memory, like UE's
template<class T> class TArray {
 // contiguous for pixels/bytes (GetData), a deque otherwise (TArray<bool> must hand out bool&)
 std::conditional_t<std::is_same_v<T, FColor> || std::is_same_v<T, uint8>, std::vector<T>, std::deque<T>> Data;
public:
 TArray() = default;
 TArray(std::initializer_list<T> Items) : Data(Items) {}
 int32 Num() const { return int32(Data.size()); }
 bool IsValidIndex(int32 I) const { return I >= 0 && I < Num(); }
 int32 Add(const T& Item) { Data.push_back(Item); return Num() - 1; }
 void Reset() { Data.clear(); }
 void Empty() { Data.clear(); }
 T* GetData() { return Data.data(); }
 const T* GetData() const { return Data.data(); }
 void SetNumUninitialized(int32 N) { Data.resize(std::size_t(N)); }
 void SetNum(int32 N) { Data.resize(std::size_t(N)); }
 void Init(const T& Value, int32 N) { Data.assign(std::size_t(N), Value); }
 T& operator[](int32 I) { return Data[std::size_t(I)]; }
 const T& operator[](int32 I) const { return Data[std::size_t(I)]; }
 T& Last() { return Data.back(); }
 const T& Last() const { return Data.back(); }
 auto begin() { return Data.begin(); } auto end() { return Data.end(); }
 auto begin() const { return Data.begin(); } auto end() const { return Data.end(); }
};
template<class T> class TArray64 {  // UE: 64-bit sizes (JPEG bytes)
 std::vector<T> Data;
public:
 int64 Num() const { return int64(Data.size()); }
 T* GetData() { return Data.data(); }
 const T* GetData() const { return Data.data(); }
 void Reset() { Data.clear(); }
 void Append(const T* Items, int64 Count) { Data.insert(Data.end(), Items, Items + Count); }
 void SetNum(int64 N) { Data.resize(std::size_t(N)); }
 void SetNumZeroed(int64 N) { Data.assign(std::size_t(N), T()); }  // v22
 T& operator[](int64 I) { return Data[std::size_t(I)]; }
 const T& operator[](int64 I) const { return Data[std::size_t(I)]; }
};
template<class F> using TFunction = std::function<F>;  // v22: UpdateTextureRegions' cleanup
template<class T> T&& MoveTemp(T& Value) { return static_cast<T&&>(Value); }
template<class T> using TUniquePtr = std::unique_ptr<T>;
template<class T, class... A> std::unique_ptr<T> MakeUnique(A&&... Args) { return std::make_unique<T>(std::forward<A>(Args)...); }
struct FMemory { static void* Memcpy(void* D, const void* S, std::size_t N) { return std::memcpy(D, S, N); } };
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
 T& operator*() const { return *Ptr; }
 T* Get() const { return Ptr.get(); }
 void Reset() { Ptr.reset(); }
};
template<class T, class... A> TSharedRef<T> MakeShared(A&&... Args) { TSharedRef<T> Ref; Ref.Ptr = std::make_shared<T>(std::forward<A>(Args)...); return Ref; }
namespace ESearchCase { enum Type { CaseSensitive, IgnoreCase }; }
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
 bool StartsWith(const TCHAR* Prefix) const { std::u16string P(Prefix); return Data.compare(0, P.size(), P) == 0; }
 bool StartsWith(const TCHAR* Prefix, ESearchCase::Type) const { return StartsWith(Prefix); }  // v21: case-sensitive callers only
 bool Split(const TCHAR* At, FString* Left, FString* Right) const { const std::size_t P = Data.find(At); if (P == std::u16string::npos) return false; if (Left) Left->Data = Data.substr(0, P); if (Right) Right->Data = Data.substr(P + std::u16string(At).size()); return true; }
 auto begin() const { return Data.begin(); } auto end() const { return Data.end(); }
 const TCHAR& operator[](int32 I) const { return Data[std::size_t(I)]; }
 friend FString operator+(const FString& A, const FString& B) { FString R = A; R.Data += B.Data; return R; }
 friend FString operator+(const FString& A, const TCHAR* B) { FString R = A; R.Data += B; return R; }
 static FString FromInt(int32) { return FString(); }
 template<class... A> static FString Printf(const TCHAR*, A...) { return FString(); }
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
class UClass { public: FString GetName() const { return FString(); } };
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
 FVector operator*(const FVector& V) const { return {X * V.X, Y * V.Y, Z * V.Z}; }  // UE: component-wise
 double GetMin() const { return std::fmin(X, std::fmin(Y, Z)); }
 double Size() const { return std::sqrt(X * X + Y * Y + Z * Z); }
 FVector GetSafeNormal() const { const double S = std::sqrt(X * X + Y * Y + Z * Z); return S > 0 ? FVector(X / S, Y / S, Z / S) : FVector(); }
 bool ContainsNaN() const { return !(std::isfinite(X) && std::isfinite(Y) && std::isfinite(Z)); }
 bool IsNearlyZero(double Tolerance = 1e-4) const { return std::fabs(X) <= Tolerance && std::fabs(Y) <= Tolerance && std::fabs(Z) <= Tolerance; }
 bool Equals(const FVector& V, double Tolerance = 1e-4) const { return std::fabs(X - V.X) <= Tolerance && std::fabs(Y - V.Y) <= Tolerance && std::fabs(Z - V.Z) <= Tolerance; }
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
 FQuat(const FVector& Axis, double Angle) { const double S = std::sin(Angle / 2); X = Axis.X * S; Y = Axis.Y * S; Z = Axis.Z * S; W = std::cos(Angle / 2); }  // UE: unit axis, radians
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
 static FQuat FindBetweenNormals(const FVector& A, const FVector& B) {  // UE: the rotation taking unit A to unit B
  const double D = FVector::DotProduct(A, B); if (D < -1 + 1e-9) { FVector Axis = FVector::CrossProduct(A, FVector(1, 0, 0)); if (Axis.Size() < 1e-6) Axis = FVector::CrossProduct(A, FVector(0, 1, 0)); Axis = Axis.GetSafeNormal(); return FQuat(Axis.X, Axis.Y, Axis.Z, 0); }
  const FVector C = FVector::CrossProduct(A, B); return FQuat(C.X, C.Y, C.Z, 1 + D).GetNormalized();
 }
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
 bool Equals(const FRotator& R, double Tolerance = 1e-4) const { return std::fabs(Pitch - R.Pitch) <= Tolerance && std::fabs(Yaw - R.Yaw) <= Tolerance && std::fabs(Roll - R.Roll) <= Tolerance; }
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
 void SetScale3D(const FVector& S) { Scale3D = S; }  // v23: neck girth
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
 FVector TransformPosition(const FVector& V) const { return Rotation.RotateVector(FVector(V.X * Scale3D.X, V.Y * Scale3D.Y, V.Z * Scale3D.Z)) + Translation; }
 FVector InverseTransformPosition(const FVector& V) const { const FVector D = V - Translation; const FVector R = Rotation.Inverse().RotateVector(D); return FVector(R.X / Scale3D.X, R.Y / Scale3D.Y, R.Z / Scale3D.Z); }
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
 static double Cos(double X) { return std::cos(X); }  // v23
 static double Sqrt(double X) { return std::sqrt(X); }
 static double Acos(double X) { return std::acos(X); }
 static double Atan2(double Y, double X) { return std::atan2(Y, X); }
 static double Exp(double X) { return std::exp(X); }
 template<class T> static constexpr T DegreesToRadians(T D) { return D * T(3.14159265358979323846 / 180); }
 template<class T> static constexpr T RadiansToDegrees(T R) { return R * T(180 / 3.14159265358979323846); }
 static FRotator RInterpTo(const FRotator& Current, const FRotator&, float, float) { return Current; }
};
class FJsonValue { public: FString StubString; bool StubIsString = false; bool TryGetString(FString& Out) const { if (!StubIsString) return false; Out = StubString; return true; } };
class FJsonObject {
public:  // v22: a driver may fill the Stub maps (the PC bridge's state reads); empty, every lookup misses as before
 std::map<std::u16string, FString> StubStrings; std::map<std::u16string, bool> StubBools; std::map<std::u16string, TSharedPtr<FJsonObject>> StubObjects;
 bool TryGetArrayField(const FString&, const TArray<TSharedPtr<FJsonValue>>*&) const { return false; }
 bool TryGetStringField(const FString& Key, FString& Out) const { auto It = StubStrings.find(*Key); if (It == StubStrings.end()) return false; Out = It->second; return true; }
 bool TryGetBoolField(const FString& Key, bool& Out) const { auto It = StubBools.find(*Key); if (It == StubBools.end()) return false; Out = It->second; return true; }
 bool TryGetObjectField(const FString& Key, const TSharedPtr<FJsonObject>*& Out) const { auto It = StubObjects.find(*Key); if (It == StubObjects.end()) return false; Out = &It->second; return true; }
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
struct FPlatformTime { static inline double StubNow = 0; static double Seconds() { return StubNow; } static double ToMilliseconds(uint64 Cycles) { return double(Cycles) * 1e-3; } };
inline uint32 StubGpuCycles = 0;
inline uint32 GGameThreadTime = 0, GRenderThreadTime = 0, GRHIThreadTime = 0, GSwapBufferTime = 0, GRenderThreadWaitTime = 0, GGameThreadWaitTime = 0;  // v21: RenderTimer.h
inline uint32 RHIGetGPUFrameCycles(uint32 = 0) { return StubGpuCycles; }
struct FPlatformProcess { static uint32 GetCurrentProcessId() { return 0; } };
struct FDateTime { static FDateTime UtcNow() { return {}; } int64 ToUnixTimestamp() const { return 0; } int32 GetMillisecond() const { return 0; } };
struct FFileHelper { static bool LoadFileToString(FString&, const TCHAR*) { return false; } static bool SaveStringToFile(const FString&, const TCHAR*) { return false; } };
#define UTF8_TO_TCHAR(x) ((void)(x), u"")
inline std::string StubUtf8(const TCHAR* S) { std::string R; for (; S && *S; ++S) R += char(*S); return R; }  // ASCII paths only
#define TCHAR_TO_UTF8(x) (::StubUtf8(x).c_str())
class UObject { public: virtual ~UObject() = default; FString GetPathName() const { return FString(); } FString GetName() const { return FString(); } UClass* GetClass() const { static UClass None; return &None; } };
template<class T> class TWeakObjectPtr {
 T* Ptr = nullptr;
public:
 TWeakObjectPtr() = default;
 TWeakObjectPtr(T* P) : Ptr(P) {}
 bool IsValid() const { return Ptr != nullptr; }
 T* Get() const { return Ptr; }
};
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
 friend bool operator==(const TObjectPtr& A, std::nullptr_t) { return A.Ptr == nullptr; }  // UE compares with nullptr too
};
inline UObject* StubCastTarget = nullptr;  // a driver names the one object Cast<> may return (no RTTI/typeinfo needed from the unit)
inline std::vector<UObject*> StubCastAlso;  // v23: more objects Cast<> may return (the mouse scan's static-mesh components)
template<class T> T* Cast(UObject* Object) { if (!Object) return nullptr; if (Object == StubCastTarget) return static_cast<T*>(Object);
 for (UObject* Also : StubCastAlso) if (Also == Object) return static_cast<T*>(Object); return nullptr; }
template<class T> T* NewObject(UObject*, FName = FName()) { return new T(); }
enum class ELightUnits : uint8 { Unitless, Candelas, Lumens };
namespace EComponentMobility { enum Type { Static, Stationary, Movable }; }
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
struct FHitResult { FVector ImpactPoint; };
struct FCollisionQueryParams { FCollisionQueryParams(FName, bool = false) {} };
struct FAttachmentTransformRules { static const FAttachmentTransformRules KeepWorldTransform; };
inline const FAttachmentTransformRules FAttachmentTransformRules::KeepWorldTransform{};
class UWorld : public UObject { public: float GetDeltaSeconds() const { return 0; } };
inline bool StubWorldEnabled = false; inline UWorld StubTheWorld;  // v23: an opt-in world (AActor::GetWorld, TActorIterator) for the mouse component scan
class UActorComponent : public UObject { public: bool StubRegistered = true; void RegisterComponent() { StubRegistered = true; } bool IsRegistered() const { return StubRegistered; } };
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
 bool StubVisible = true;
 void SetVisibility(bool V) { StubVisible = V; }
 bool IsVisible() const { return StubVisible; }  // v23
 EComponentMobility::Type StubMobility = EComponentMobility::Static;  // v21: the props are made Movable before they move
 void SetMobility(EComponentMobility::Type M) { StubMobility = M; }
 EComponentMobility::Type GetMobility() const { return StubMobility; }
 USceneComponent* StubParent = nullptr;  // v21: attachment chain
 bool IsAttachedTo(const USceneComponent* C) const { for (const USceneComponent* P = StubParent; P; P = P->StubParent) if (P == C) return true; return false; }
 int32 StubChildren = 0; int32 GetNumChildrenComponents() const { return StubChildren; }  // v23: the mouse must be a leaf
};
class UPrimitiveComponent : public USceneComponent {
public:  // the stub trace hits at *StubTraceAnchor + StubTraceOffset when StubTraceHit (the anchor follows its actor)
 uint8 bOnlyOwnerSee : 1 = 0; bool StubChannels[3] = {true, false, false};  // v21
 void SetOnlyOwnerSee(bool B) { bOnlyOwnerSee = B ? 1 : 0; }
 void SetLightingChannels(bool A, bool B, bool C) { StubChannels[0] = A; StubChannels[1] = B; StubChannels[2] = C; }
 bool StubSimulating = false; bool IsSimulatingPhysics(FName = FName()) const { return StubSimulating; }  // v23
 bool StubTraceHit = false; const FVector* StubTraceAnchor = nullptr; FVector StubTraceOffset;
 bool LineTraceComponent(FHitResult& Hit, const FVector, const FVector, const FCollisionQueryParams&) { if (!StubTraceHit || !StubTraceAnchor) return false; Hit.ImpactPoint = *StubTraceAnchor + StubTraceOffset; return true; }
};
class ULightComponent : public USceneComponent { public: float Intensity = 0, Temperature = 6500; bool bUseTemperature = false; bool StubChannels[3] = {true, false, false}; void SetIntensity(float I) { Intensity = I; } void SetTemperature(float T) { Temperature = T; } void SetCastShadows(bool) {}
 void SetLightingChannels(bool A, bool B, bool C) { StubChannels[0] = A; StubChannels[1] = B; StubChannels[2] = C; }
 float StubSpecular = 1; void SetSpecularScale(float S) { StubSpecular = S; } };  // v23
class ULocalLightComponent : public ULightComponent { public: float StubRadius = 0; void SetIntensityUnits(ELightUnits) {} void SetAttenuationRadius(float R) { StubRadius = R; } };
class USpotLightComponent : public ULocalLightComponent { public: float StubInner = 0, StubOuter = 0, StubSource = 0, StubSoft = 0; void SetInnerConeAngle(float A) { StubInner = A; } void SetOuterConeAngle(float A) { StubOuter = A; }
 void SetSourceRadius(float R) { StubSource = R; } void SetSoftSourceRadius(float R) { StubSoft = R; } };
class USkeletalMeshComponent : public UPrimitiveComponent {
public:
 int32 StubHeadIndex = INDEX_NONE; FVector StubHead; UAnimInstance* StubAnim = nullptr; int32 StubForcedLod = 0;
 int32 GetNumLODs() const { return 1; }
 TArray<FName> GetMaterialSlotNames() const { return {}; }
 void SetForcedLOD(int32 L) { StubForcedLod = L; }
 USkeletalMesh* GetSkeletalMeshAsset() const { return nullptr; }
 int32 GetBoneIndex(FName) const { return StubHeadIndex; }
 FVector GetBoneLocation(FName) const { return StubHead; }
 FTransform GetBoneTransform(int32) const { return FTransform(FQuat::Identity, StubHead, FVector(1, 1, 1)); }
 UAnimInstance* GetAnimInstance() const { return StubAnim; }
 void UnHideBoneByName(FName) {}
 void ShowMaterialSection(int32, int32, bool, int32) {}
 void SetAnimInstanceClass(UClass*) {}
};
enum EAutoExposureMethod : int { AEM_Histogram, AEM_Basic, AEM_Manual, AEM_MAX };  // v22: UE Scene.h
struct FPostProcessSettings { float StubExposure = 0;
 uint8 bOverride_AutoExposureMethod : 1 = 0, bOverride_AutoExposureBias : 1 = 0, bOverride_AutoExposureMinBrightness : 1 = 0, bOverride_AutoExposureMaxBrightness : 1 = 0,
  bOverride_AutoExposureApplyPhysicalCameraExposure : 1 = 0;  // v22: cam2 exposure (UE: uint8 bitfields)
 TEnumAsByte<EAutoExposureMethod> AutoExposureMethod = AEM_Histogram; float AutoExposureBias = 1, AutoExposureMinBrightness = -10, AutoExposureMaxBrightness = 20; uint32 AutoExposureApplyPhysicalCameraExposure : 1 = 1; };
class UCameraComponent : public USceneComponent { public: float FieldOfView = 90; FPostProcessSettings PostProcessSettings; float PostProcessBlendWeight = 1; void SetFieldOfView(float F) { FieldOfView = F; } };
// cam2: render target, scene capture, render thread, GPU readback, image wrapper, async task (all synchronous in the stub)
enum EPixelFormat { PF_Unknown, PF_B8G8R8A8 };
enum ESceneCaptureSource { SCS_SceneColorHDR, SCS_FinalColorLDR };
class FRHITexture { public: int32 StubPitch = 1280; uint8 StubShade = 7; uint32 StubSerial = 0; };
template<class T> class TRefCountPtr { T* Ptr = nullptr; public: TRefCountPtr() = default; TRefCountPtr(T* P) : Ptr(P) {} T* GetReference() const { return Ptr; } };
using FTextureRHIRef = TRefCountPtr<FRHITexture>;
class FRHICommandList {};
class FRHICommandListImmediate : public FRHICommandList {};
namespace StubRender {  // Deferred: commands wait for Flush() (the render thread), else they run at once
 inline FRHICommandListImmediate Immediate; inline int32 Commands = 0; inline bool Deferred = false; inline std::vector<std::function<void()>> Queue;
 struct FDispatch { template<class L> void operator()(L&& Lambda) const { ++Commands; if (!Deferred) { Lambda(Immediate); return; } Queue.push_back([Command = std::forward<L>(Lambda)]() mutable { Command(Immediate); }); } };
 inline void Flush() { std::vector<std::function<void()>> Now; Now.swap(Queue); for (auto& Command : Now) Command(); } }
#define ENQUEUE_RENDER_COMMAND(Type) ::StubRender::FDispatch{}
class FTextureRenderTargetResource { public: FTextureRHIRef Texture; const FTextureRHIRef& GetRenderTargetTexture() const { return Texture; } };
class UTextureRenderTarget2D : public UObject {
public:
 int32 SizeX = 0, SizeY = 0; EPixelFormat Format = PF_Unknown; FRHITexture StubTexture; FTextureRenderTargetResource StubResource;
 void InitCustomFormat(uint32 X, uint32 Y, EPixelFormat F, bool) { SizeX = int32(X); SizeY = int32(Y); Format = F; }
 void UpdateResourceImmediate(bool = true) { StubResource.Texture = FTextureRHIRef(&StubTexture); }
 FTextureRenderTargetResource* GameThread_GetRenderTargetResource() { return &StubResource; }
};
struct FEngineShowFlags { bool MotionBlur = true, DepthOfField = true; void SetMotionBlur(bool V) { MotionBlur = V; } void SetDepthOfField(bool V) { DepthOfField = V; }
 bool AmbientOcclusion = true, ScreenSpaceReflections = true, ContactShadows = true, VolumetricFog = true, LensFlares = true, Particles = true;  // v21: the lite capture
 void SetAmbientOcclusion(bool V) { AmbientOcclusion = V; } void SetScreenSpaceReflections(bool V) { ScreenSpaceReflections = V; } void SetContactShadows(bool V) { ContactShadows = V; }
 void SetVolumetricFog(bool V) { VolumetricFog = V; } void SetLensFlares(bool V) { LensFlares = V; } void SetParticles(bool V) { Particles = V; } };
class USceneCaptureComponent2D : public USceneComponent {
public:
 TObjectPtr<UTextureRenderTarget2D> TextureTarget; ESceneCaptureSource CaptureSource = SCS_SceneColorHDR; bool bCaptureEveryFrame = true, bCaptureOnMovement = true, bAlwaysPersistRenderingState = false;
 FPostProcessSettings PostProcessSettings; float PostProcessBlendWeight = 0; FEngineShowFlags ShowFlags; float FOVAngle = 90; int32 StubCaptures = 0, StubDeferred = 0;
 float MaxViewDistanceOverride = -1, LODDistanceFactor = 1;  // v21
 void CaptureScene() { ++StubCaptures; if (TextureTarget) { ++TextureTarget->StubTexture.StubShade; ++TextureTarget->StubTexture.StubSerial; } }
 void CaptureSceneDeferred() { ++StubDeferred; CaptureScene(); }  // the stub renders at once; the engine renders it with the frame's main view
};
struct FRHIGPUTextureReadbackStub { static inline int32 ReadyAfterPolls = 1; static inline int32 Locks = 0; static inline int32 BadLocks = 0; };
class FRHIGPUTextureReadback {  // staging pixel (x,y) = (B shade, G x, R y, A 0xA5); padding 0xEE; pixel (0,719) = the capture serial
 int32 Polls = 0; bool Copied = false, Ready = false, Locked = false; std::vector<uint8> Staging; int32 Pitch = 0;
public:
 explicit FRHIGPUTextureReadback(FName) {}
 bool IsReady() { Ready = Copied && ++Polls > FRHIGPUTextureReadbackStub::ReadyAfterPolls; return Ready; }
 void EnqueueCopy(FRHICommandList&, FRHITexture* Source) {
  if (Locked) ++FRHIGPUTextureReadbackStub::BadLocks;
  Pitch = Source->StubPitch; Staging.assign(std::size_t(Pitch) * 720 * 4, 0xEE);
  for (int32 Y = 0; Y < 720; ++Y) for (int32 X = 0; X < 1280; ++X) { uint8* P = &Staging[(std::size_t(Y) * Pitch + X) * 4]; P[0] = Source->StubShade; P[1] = uint8(X); P[2] = uint8(Y); P[3] = 0xA5; }
  std::memcpy(&Staging[std::size_t(719) * Pitch * 4], &Source->StubSerial, 4); Copied = true; Ready = false; Polls = 0; }
 void* Lock(int32& OutRowPitchInPixels, int32* OutBufferHeight = nullptr) { ++FRHIGPUTextureReadbackStub::Locks; if (!Ready || Locked) ++FRHIGPUTextureReadbackStub::BadLocks; Locked = true; OutRowPitchInPixels = Pitch; if (OutBufferHeight) *OutBufferHeight = 720; return Staging.data(); }
 void Unlock() { if (!Locked) ++FRHIGPUTextureReadbackStub::BadLocks; Locked = false; Copied = Ready = false; }
};
enum class EImageFormat : int8 { Invalid = -1, PNG = 0, JPEG };
enum class EGammaSpace : uint8 { Linear, Pow22, sRGB };
struct FImageView { const FColor* Colors = nullptr; int32 SizeX = 0, SizeY = 0; FImageView(const FColor* C, int32 X, int32 Y, EGammaSpace = EGammaSpace::sRGB) : Colors(C), SizeX(X), SizeY(Y) {} };
class IImageWrapperModule {  // the stub "JPEG": FF D8, the shade, an encode counter (4), the capture serial (4), filler, FF D9 (StubBytes long)
public:  // every pixel is checked against the staging pattern: a wrong row pitch, size or order shows up in StubPixelErrors
 static inline int64 StubBytes = 2000; static inline uint32 StubCounter = 0; static inline int64 StubPixelErrors = 0;
 bool CompressImage(TArray64<uint8>& Out, EImageFormat Format, const FImageView& Image, int32 Quality) {
  if (Format != EImageFormat::JPEG || !Image.Colors || Quality <= 0) return false;
  if (Image.SizeX != 1280 || Image.SizeY != 720) ++StubPixelErrors;
  for (int32 Y = 0; Y < Image.SizeY; ++Y) for (int32 X = 0; X < Image.SizeX; ++X) { if (X == 0 && Y == 719) continue; const FColor& C = Image.Colors[std::size_t(Y) * Image.SizeX + X];
   if (C.B != Image.Colors[0].B || C.G != uint8(X) || C.R != uint8(Y) || C.A != 0xA5) ++StubPixelErrors; }
  std::vector<uint8> Bytes(std::size_t(StubBytes), 0x55); Bytes[0] = 0xFF; Bytes[1] = 0xD8; const uint32 N = ++StubCounter;
  Bytes[2] = Image.Colors[0].B; std::memcpy(&Bytes[3], &N, 4); std::memcpy(&Bytes[7], &Image.Colors[std::size_t(719) * Image.SizeX], 4); Bytes[Bytes.size() - 2] = 0xFF; Bytes[Bytes.size() - 1] = 0xD9;
  Out.Reset(); Out.Append(Bytes.data(), int64(Bytes.size())); return true; }
 TSharedPtr<class IImageWrapper> CreateImageWrapper(EImageFormat Format);  // v22: the monitor feed's decoder (defined below)
};
struct FModuleManager { template<class T> static T& LoadModuleChecked(FName) { static T Module; return Module; } };
namespace ENamedThreads { enum Type { AnyBackgroundThreadNormalTask }; }
namespace StubAsync { inline bool Deferred = false; inline int64 Launched = 0; inline std::vector<std::function<void()>> Queue; inline void Flush() { std::vector<std::function<void()>> Now; Now.swap(Queue); for (auto& Task : Now) Task(); } }
template<class F> void AsyncTask(ENamedThreads::Type, F&& Function) { ++StubAsync::Launched; if (!StubAsync::Deferred) { Function(); return; } StubAsync::Queue.push_back(std::function<void()>(std::forward<F>(Function))); }
// v22: persistent textures (CreateTransient's mip starts as 0xCD garbage; UpdateTextureRegions copies on the "render thread" = StubRender,
// then runs the cleanup) and the JPEG decoder (a stub "JPEG": SOI, APP0 "JFIF\0" + the serial (4), SOF0 with the size, SOS, entropy, EOI)
enum TextureFilter { TF_Nearest, TF_Bilinear, TF_Trilinear, TF_Default };
enum TextureAddress { TA_Wrap, TA_Clamp, TA_Mirror };
struct FUpdateTextureRegion2D { uint32 DestX = 0, DestY = 0; int32 SrcX = 0, SrcY = 0; uint32 Width = 0, Height = 0; FUpdateTextureRegion2D() = default;
 FUpdateTextureRegion2D(uint32 DX, uint32 DY, int32 SX, int32 SY, uint32 W, uint32 H) : DestX(DX), DestY(DY), SrcX(SX), SrcY(SY), Width(W), Height(H) {} };
class FTextureResource {};
class UTexture : public UObject { public: bool SRGB = false, NeverStream = false; TextureFilter Filter = TF_Default; TextureAddress AddressX = TA_Wrap, AddressY = TA_Wrap; };
class UTexture2D : public UTexture {
public:
 static inline int64 StubCreated = 0, StubUpdates = 0, StubCleanups = 0;
 int32 StubX = 0, StubY = 0; EPixelFormat StubFormat = PF_Unknown; bool StubHasResource = false; FTextureResource StubResource; std::vector<uint8> StubPixels;
 static UTexture2D* CreateTransient(int32 X, int32 Y, EPixelFormat Format = PF_B8G8R8A8, const FName& = FName()) {
  auto* T = new UTexture2D(); T->StubX = X; T->StubY = Y; T->StubFormat = Format; T->StubPixels.assign(std::size_t(X) * std::size_t(Y) * 4, 0xCD); ++StubCreated; return T; }
 int32 GetSizeX() const { return StubX; } int32 GetSizeY() const { return StubY; } EPixelFormat GetPixelFormat() const { return StubFormat; }
 void UpdateResource() { StubHasResource = true; }
 FTextureResource* GetResource() const { return StubHasResource ? const_cast<FTextureResource*>(&StubResource) : nullptr; }
 void UpdateTextureRegions(int32 Mip, uint32 NumRegions, const FUpdateTextureRegion2D* Regions, uint32 SrcPitch, uint32 SrcBpp, uint8* SrcData, TFunction<void(uint8*, const FUpdateTextureRegion2D*)> Cleanup) {
  ++StubUpdates;
  ::StubRender::FDispatch{}([this, Mip, NumRegions, Regions, SrcPitch, SrcBpp, SrcData, Cleanup](FRHICommandListImmediate&) {
   for (uint32 R = 0; R < NumRegions && Mip == 0; ++R) { const FUpdateTextureRegion2D& G = Regions[R];
    for (uint32 Y = 0; Y < G.Height; ++Y) std::memcpy(&StubPixels[(std::size_t(G.DestY + Y) * std::size_t(StubX) + G.DestX) * 4], SrcData + std::size_t(G.SrcY + int32(Y)) * SrcPitch + std::size_t(G.SrcX) * SrcBpp, std::size_t(G.Width) * SrcBpp); }
   ++StubCleanups; Cleanup(SrcData, Regions); }); }
 const uint8* StubPixel(int32 X, int32 Y) const { return &StubPixels[(std::size_t(Y) * std::size_t(StubX) + std::size_t(X)) * 4]; }
};
enum class ERGBFormat : int8 { Invalid = -1, RGBA = 0, BGRA = 1, Gray = 2 };
class IImageWrapper {  // decoded pixel (x,y) = (B serial & 255, G x, R y, A 255)
public:
 static inline int64 StubDecodes = 0, StubRefused = 0;
 int64 W = 0, H = 0; uint32 Serial = 0; bool Valid = false;
 bool SetCompressed(const void* In, int64 Size) {
  const uint8* B = static_cast<const uint8*>(In); Valid = false;
  if (Size < 4 || B[0] != 0xFF || B[1] != 0xD8 || B[Size - 2] != 0xFF || B[Size - 1] != 0xD9) { ++StubRefused; return false; }
  for (int64 P = 2; P + 3 < Size;) { if (B[P] != 0xFF) { ++StubRefused; return false; } while (P + 1 < Size && B[P + 1] == 0xFF) ++P;
   const uint8 M = B[P + 1]; const int64 L = (int64(B[P + 2]) << 8) | B[P + 3];
   if (M == 0xC0) { H = (int64(B[P + 5]) << 8) | B[P + 6]; W = (int64(B[P + 7]) << 8) | B[P + 8]; }
   if (M == 0xE0) std::memcpy(&Serial, B + P + 9, 4);
   if (M == 0xDA) break; P += 2 + L; }
  Valid = W > 0 && H > 0; if (!Valid) ++StubRefused; return Valid; }
 int64 GetWidth() const { return W; } int64 GetHeight() const { return H; }
 bool GetRaw(ERGBFormat Format, int32 Bits, TArray64<uint8>& Out) {
  if (!Valid || Format != ERGBFormat::BGRA || Bits != 8) return false; ++StubDecodes; Out.SetNumZeroed(W * H * 4);
  for (int64 Y = 0; Y < H; ++Y) for (int64 X = 0; X < W; ++X) { uint8* P = &Out[(Y * W + X) * 4]; P[0] = uint8(Serial); P[1] = uint8(X); P[2] = uint8(Y); P[3] = 255; }
  return true; }
};
inline TSharedPtr<IImageWrapper> IImageWrapperModule::CreateImageWrapper(EImageFormat Format) { if (Format != EImageFormat::JPEG) return nullptr; return MakeShared<IImageWrapper>(); }
class UCharacterMovementComponent : public UActorComponent { public: void StopMovementImmediately() {} void DisableMovement() {} };
class AController : public UObject { public: void SetControlRotation(const FRotator&) {} };
class AActor : public UObject {
public:
 FVector StubLocation, StubExtent; FQuat StubQuat;
 FVector StubScale{1, 1, 1}; FVector GetActorScale3D() const { return StubScale; } void SetActorScale3D(const FVector& S) { StubScale = S; }  // v23: chair_scale
 FQuat GetActorQuat() const { return StubQuat; }
 bool SetActorLocationAndRotation(const FVector& L, const FQuat& Q, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { StubLocation = L; StubQuat = Q; return true; }
 UWorld* GetWorld() const { return StubWorldEnabled ? &StubTheWorld : nullptr; }  // v23: null unless a driver opts in
 USceneComponent* GetRootComponent() const { return nullptr; }
 FVector GetActorLocation() const { return StubLocation; }
 bool SetActorLocation(const FVector& L, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { StubLocation = L; return true; }
 bool SetActorLocationAndRotation(FVector, FRotator, bool = false, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { return true; }
 void GetActorBounds(bool, FVector& Origin, FVector& Extent, bool = false) const { Origin = StubLocation; Extent = StubExtent; }
 UPrimitiveComponent* StubPrimitive = nullptr;
 template<class T> T* FindComponentByClass() const { if constexpr (std::is_same_v<T, UPrimitiveComponent>) return StubPrimitive; else return nullptr; }
 std::vector<UPrimitiveComponent*> StubComponents;  // v21: GetComponents
 template<class T> void GetComponents(TArray<T*>& Out, bool = false) const { Out.Reset(); for (UPrimitiveComponent* P : StubComponents) Out.Add(static_cast<T*>(P)); }
};
class UEngine { public: std::vector<std::u16string> StubExec; bool Exec(UWorld*, const TCHAR* Command) { StubExec.push_back(Command); return true; } };  // v21: the live console
inline UEngine* GEngine = nullptr;
class IConsoleVariable { public: FString StubValue; FString GetString() const { return StubValue; } };
class IConsoleManager { public: static IConsoleManager& Get() { static IConsoleManager Manager; return Manager; } IConsoleVariable* FindConsoleVariable(const TCHAR*) { return nullptr; } };
class UStaticMesh : public UObject {};
class UStaticMeshComponent : public UPrimitiveComponent { public: UStaticMesh* StubMesh = nullptr; UStaticMesh* GetStaticMesh() const { return StubMesh; } };  // v23: StubMesh
class UInstancedStaticMeshComponent : public UStaticMeshComponent {};
class AStaticMeshActor : public AActor { public: UStaticMeshComponent* GetStaticMeshComponent() const { return nullptr; } };
inline std::vector<AActor*> StubWorldActors;  // v23: what TActorIterator walks in the opt-in world (nothing otherwise)
template<class T> struct TActorIterator { std::size_t I = 0; bool On = false; explicit TActorIterator(UWorld* World) : On(World && StubWorldEnabled) {}
 explicit operator bool() const { return On && I < StubWorldActors.size(); } void operator++() { ++I; } T* operator*() const { return static_cast<T*>(StubWorldActors[I]); } };
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
struct FReferenceSkeleton {  // empty by default (every lookup misses); a driver fills names/parents to run the proxy on a chain
 std::vector<FName> StubNames; std::vector<int32> StubParents;
 int32 GetNum() const { return int32(StubNames.size()); }
 int32 GetParentIndex(int32 I) const { return I >= 0 && I < GetNum() ? StubParents[std::size_t(I)] : INDEX_NONE; }
 int32 FindBoneIndex(const FName& Name) const { for (int32 I = 0; I < GetNum(); ++I) if (StubNames[std::size_t(I)] == Name) return I; return INDEX_NONE; }
 FName GetBoneName(int32 I) const { return I >= 0 && I < GetNum() ? StubNames[std::size_t(I)] : FName(); }
};
inline const FReferenceSkeleton& USkeletalMesh::GetRefSkeleton() const { static FReferenceSkeleton None; return None; }
struct FBoneContainer {  // compact index = mesh index (every bone required)
 const FReferenceSkeleton* StubRef = nullptr;
 const FReferenceSkeleton& GetReferenceSkeleton() const { static FReferenceSkeleton None; return StubRef ? *StubRef : None; }
 FCompactPoseBoneIndex MakeCompactPoseIndex(const FMeshPoseBoneIndex& I) const { FCompactPoseBoneIndex C; C.Index = I.Index >= 0 && I.Index < GetReferenceSkeleton().GetNum() ? I.Index : INDEX_NONE; return C; }
 FMeshPoseBoneIndex MakeMeshPoseIndex(const FCompactPoseBoneIndex& C) const { return FMeshPoseBoneIndex(C.Index); }
};
struct FCompactPose {
 FBoneContainer StubContainer; std::vector<FTransform> StubBones;  // local transforms
 const FBoneContainer& GetBoneContainer() const { return StubContainer; }
 FTransform& operator[](FCompactPoseBoneIndex C) { static FTransform None; return C.Index >= 0 && C.Index < int32(StubBones.size()) ? StubBones[std::size_t(C.Index)] : None; }
 const FTransform& operator[](FCompactPoseBoneIndex C) const { static FTransform None; return C.Index >= 0 && C.Index < int32(StubBones.size()) ? StubBones[std::size_t(C.Index)] : None; }
 int32 GetNumBones() const { return int32(StubBones.size()); }
 TArray<FCompactPoseBoneIndex> ForEachBoneIndex() const { TArray<FCompactPoseBoneIndex> All; for (int32 I = 0; I < GetNumBones(); ++I) { FCompactPoseBoneIndex C; C.Index = I; All.Add(C); } return All; }
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
class USub01PCBridge : public UActorComponent { public: void SetOperatorFocus(bool) {} bool HasOperatorFocus() const { return false; }
 // v22: the monitor feed API; the gate is the driver's (the real one is tested on the patched bridge itself)
 bool StubFeedAllowed = false; uint64 StubGeneration = 0; double StubAspect = 1280. / 720., StubConfirmedAt = -1; UTexture* StubFeed = nullptr; int64 StubFeedSets = 0;
 bool IsMonitorFeedAllowed(double) const { return StubFeedAllowed; } uint64 GetMonitorPrivacyGeneration() const { return StubGeneration; }
 double GetMonitorConfirmedAt() const { return StubConfirmedAt; } FString MonitorFeedGateReason(double) const { return StubFeedAllowed ? FString(u"open") : FString(u"stub closed"); }
 double GetMonitorScreenAspect() const { return StubAspect; } int32 GetMonitorTexturesCreated() const { return 0; }
 bool SetMonitorFeedFrame(UTexture* Frame) { if (Frame && !StubFeedAllowed) Frame = nullptr; if (Frame != StubFeed) ++StubFeedSets; StubFeed = Frame; return Frame != nullptr; } };
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
    (stub / 'Engine').mkdir(exist_ok=True)
    (stub / 'Components').mkdir(exist_ok=True)
    for name in ('CoreMinimal.h', 'Animation/AnimInstance.h', 'UObject/UnrealType.h', 'Animation/MorphTarget.h', 'Engine/StaticMeshActor.h',
                 'Components/SpotLightComponent.h', 'Components/InstancedStaticMeshComponent.h', 'RHI.h'):
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
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == 15 and all(e['count'] == 1 for e in planned['edits'])
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
                 'if(Face&&!StreamerVisualFaceAimed)return;', 'Now-StreamerVisualFaceSelectedAt>=2', 'if(StreamerVisualTuningChanged){StreamerVisualTuningChanged=false;if(Face){StreamerVisualFaceAimed=false;StreamerVisualFaceHeadCount=0;}}',
                 f'const FVector Monitor({seatfix.MONITOR[0]},{seatfix.MONITOR[1]},{seatfix.MONITOR[2]});', 'SUB01_STREAMER_VISUAL_FACE_CAMERA location=%s aim=%s headMean=%s samples=%d'):
        assert text in camera, text
    assert 'Monitor+FVector(0,0,28)' not in camera and '42.f' not in camera and 'StreamerVisualFaceDistanceCm' not in cpp
    assert camera.index('const bool Settled=') < camera.index('if(Face&&!StreamerVisualFaceAimed&&(Settled||')
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    assert f'"{seatfix.TUNING_PATH}"' in tuning and f'Schema!=TEXT("{seatfix.TUNING_SCHEMA}")' in tuning and 'Sequence<=StreamerVisualFaceTuningSequence' in tuning
    for key, (lo, hi) in seatfix.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key}"),' in tuning and f',{lo},{hi});' in tuning, key
    assert 'seat_back_cm' in seatfix.TUNING_LIMITS and seatfix.TUNING_LIMITS['seat_back_cm'] == (0, 40) and seatfix.SEAT_BACK_CM == 0
    assert 'ApplyStreamerVisualDeskProps(SeatValid&&StreamerVisualDeskPropsEnabled>0?' in apply
    # pull-back: composed with the clip offset on the mesh component, polled from the tuning file in the seat block, desk props follow by the world delta
    for text in ('const FVector PullLocal=StreamerVisualFacingLocal*double(-StreamerVisualSeatBackCm)+StreamerVisualRightLocal*double(StreamerVisualSeatSideCm);',
                 'Seat=Anim->StreamerVisualSeatOffset*FTransform(FQuat::Identity,PullLocal);', 'SUB01_STREAMER_VISUAL_SEAT_BACK cm=%.1f sideCm=%.1f',
                 'ApplyStreamerVisualDeskProps(SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(PullLocal):FVector::ZeroVector);',
                 'if(ReadStreamerVisualFaceTuning())StreamerVisualTuningChanged=true;'):
        assert text in apply, text
    props = cpp[cpp.index('void ASub01HomeCharacter::ScanStreamerVisualDeskProps(){'):cpp.index(SEATFIX_MARKER + ' END')]
    for text in ('TActorIterator<AActor> It(GetWorld())', 'A->FindComponentByClass<UStaticMeshComponent>()', f'Mesh.StartsWith(TEXT("{seatfix.DESK_PROP_MESH_PREFIX}"))',
                 f'!Mesh.StartsWith(TEXT("{seatfix.DESK_MESH_PREFIX}"))', 'SUB01_STREAMER_VISUAL_%s_CANDIDATE', 'chairParts=%d',
                 f'Extent.X<={seatfix.CHAIR_MAX_EXTENT[0]}&&Extent.Y<={seatfix.CHAIR_MAX_EXTENT[1]}&&Extent.Z<={seatfix.CHAIR_MAX_EXTENT[2]}',
                 'Name.Contains(TEXT("mouse"))||Name.Contains(TEXT("keyboard"))', 'SUB01_STREAMER_VISUAL_DESK_PROPS found=%d',
                 'SUB01_STREAMER_VISUAL_DESK_PROPS moved=%d delta=%s', 'A->SetActorLocation(StreamerVisualDeskPropOrigins[I]+WorldDelta,false,nullptr,ETeleportType::TeleportPhysics);',
                 f'Extent.X<={seatfix.DESK_PROP_MAX_EXTENT[0]}&&Extent.Y<={seatfix.DESK_PROP_MAX_EXTENT[1]}&&Extent.Z<={seatfix.DESK_PROP_MAX_EXTENT[2]}'):
        assert text in props, text
    assert 'StreamerVisualFacingLocal=FVector(Chosen==0?1:Chosen==1?-1:0,Chosen==2?1:Chosen==3?-1:0,0);' in start
    for text in ('TEXT("seat_back_cm")', 'TEXT("seat_side_cm")', 'TEXT("desk_props_moved")', 'TEXT("desk_props_delta")', 'TEXT("chair_parts")',
                 'TEXT("posture_lean_deg")', 'TEXT("posture_head_deg")'):
        assert text in cpp, text
    # posture layer: eased, split over Spine1/Spine2 on the breathing axis, head on the gaze axis; the v2 breathing terms kept
    assert 'Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W)+StreamerVisualPostureLeanApplied*.5,0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1)+StreamerVisualPostureLeanApplied*.5,0,0);Anim->StreamerVisualHeadOffset.Pitch+=StreamerVisualPostureHeadApplied;' in apply
    assert 'SUB01_STREAMER_VISUAL_POSTURE leanDeg=%.1f' in apply and f'-{seatfix.POSTURE_RATE_DEG_PER_S:g}.f*Dt,{seatfix.POSTURE_RATE_DEG_PER_S:g}.f*Dt' in apply
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
 // pull-back knob: a constant translation away from the monitor (-facing, here -Y of the component) and to his right (-X), composed after the clip offset
 CHECK(C.StreamerVisualFacingLocal.Equals(FVector(0, 1, 0), 1e-9) && C.StreamerVisualRightLocal.Equals(FVector(-1, 0, 0), 1e-9) && C.StreamerVisualSeatBackApplied == 0, 30);
 C.StreamerVisualSeatBackCm = 22; C.StreamerVisualSeatSideCm = 5; Ticks(C, 1);
 const FTransform Pulled = D * FTransform(FQuat::Identity, FVector(-5, -22, 0), FVector(1, 1, 1)) * Rel0;
 CHECK(C.StreamerVisualSeatBackApplied == 22 && C.StreamerVisualSeatSideApplied == 5 && Body.StubRelative.Equals(Pulled, 1e-6) && Near(Body.StubRelative.GetTranslation().Y, 99 - 22, 1e-6) && Near(Body.StubRelative.GetTranslation().X, 1 - 5, 1e-6), 31);
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 1); CHECK(!C.StreamerVisualSeatHas && Body.StubRelative.Equals(Rel0, 1e-9), 32);  // v1: authored again, knob or not
 C.StreamerVisualSchemaVersion = 2; C.StreamerVisualSeatBackCm = 0; C.StreamerVisualSeatSideCm = 0; Ticks(C, 1); CHECK(Body.StubRelative.Equals(Expected, 1e-6) && C.StreamerVisualSeatBackApplied == 0, 33);
 // posture layer: eased at the rate (deg/s), half the lean on each spine bone, the head pitch added to the gaze offset
 CHECK(Near(Anim.StreamerVisualSpine1Offset.Pitch, .6 * std::sin(2 * PI * .22 * 0), 1e-9) && C.StreamerVisualPostureLeanApplied == 0, 34);
 C.StreamerVisualPostureLeanDeg = -10; C.StreamerVisualPostureHeadDeg = 8; Ticks(C, 1);
 CHECK(Near(C.StreamerVisualPostureLeanApplied, -@@RATE@@ * .1, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, @@RATE@@ * .1, 1e-4) && Near(Anim.StreamerVisualSpine1Offset.Pitch, -@@RATE@@ * .05, 1e-4) && Near(Anim.StreamerVisualSpine2Offset.Pitch - .6 * std::sin(-1.1), -@@RATE@@ * .05, 1e-4), 35);  // W = 0 in the stub (Now = StartedAt = 0): breathing only on Spine2's lag
 Ticks(C, 20); CHECK(Near(C.StreamerVisualPostureLeanApplied, -10, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, 8, 1e-4) && Near(Anim.StreamerVisualSpine1Offset.Pitch, -5, 1e-4) && Near(Anim.StreamerVisualSpine2Offset.Pitch - .6 * std::sin(-1.1), -5, 1e-4), 36);
 Anim.StreamerVisualHeadOffset = FRotator(-4, 0, 0); C.ApplyStreamerVisualV2(0, .1f); CHECK(Near(Anim.StreamerVisualHeadOffset.Pitch, -4 + 8, 1e-4), 37);
 C.StreamerVisualPostureLeanDeg = 0; C.StreamerVisualPostureHeadDeg = 0; Ticks(C, 20); CHECK(Near(C.StreamerVisualPostureLeanApplied, 0, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, 0, 1e-4), 38);
 // face camera: waits (camera untouched) until the seat offset is settled and applied, then samples the Head bone for @@SAMPLE@@ s and is placed on the monitor
 Body.StubHeadIndex = 7; Body.StubHead = FVector(214, -300, 135); Anim.StreamerVisualSeatSettled = false;
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 5);
 CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceAlpha == 0 && Camera.FieldOfView == 65 && Camera.StubWorld.Translation.X == 334 && C.StreamerVisualFaceHeadCount == 0, 10);
 Anim.StreamerVisualSeatSettled = true; Ticks(C, 5);  // 0.5 s of samples: still waiting, the camera untouched
 CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceHeadCount == 5 && C.StreamerVisualFaceAlpha == 0 && Camera.StubWorld.Translation.X == 334, 11);
 for (int K = 0; K < 8; ++K) { Body.StubHead = FVector(K % 2 ? 204 : 224, -300, 135); Ticks(C, 1); }  // sway +-10 around 214 over > 1 s: the mean is aimed at, not the last sample
 CHECK(C.StreamerVisualFaceAimed && C.StreamerVisualFaceAimSource == TEXT("head") && Near(C.StreamerVisualFaceAim.X, 214, 1.5) && Near(C.StreamerVisualFaceAim.Y, -300, 1e-6) && Near(C.StreamerVisualFaceAim.Z, 135 - @@DROP@@, 1e-6), 12);
 CHECK(Near(C.StreamerVisualFaceLocation.X, @@LX@@, .4) && Near(C.StreamerVisualFaceLocation.Y, @@LY@@, .4) && Near(C.StreamerVisualFaceLocation.Z, @@LZ@@, 1e-6) && Near(C.StreamerVisualFaceLook.Yaw, @@YAW@@, 2.5) && Near(C.StreamerVisualFaceLook.Pitch, @@PITCH@@, 1), 13);  // the mean head sits within +-1 cm of 214: the webcam point moves with the monitor->head direction
 Ticks(C, 4); CHECK(C.StreamerVisualFaceAlpha >= .5 - 1e-5 && C.StreamerVisualFaceAlpha <= .7 + 1e-5 && (Camera.FieldOfView - 65) * (Camera.FieldOfView - @@FOV@@) <= 0, 14);  // the 1 s blend began with the aim: FOV between 65 and the face FOV
 Ticks(C, 7);
 CHECK(C.StreamerVisualFaceAlpha == 1 && Near(Camera.FieldOfView, @@FOV@@, 1e-6) && Near(Camera.StubWorld.Translation.X, @@LX@@, .4) && Near(Camera.StubWorld.Translation.Y, @@LY@@, .4) && Near(Camera.StubWorld.Translation.Z, @@LZ@@, 1e-6), 15);
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
              .replace('@@BOUNDS@@', repr(seatfix.BOUNDS_SCALE)).replace('@@RATE@@', repr(seatfix.POSTURE_RATE_DEG_PER_S)))
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


# ================================================================================================ stream pass (hands IK, typing posture, body look, key light, perf)
STREAMPASS_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_stream_pass.py'
STREAMPASS_MARKER = '// SUB01_STREAMER_VISUAL_V2_STREAMPASS'
_STREAMPASS_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_streampass', STREAMPASS_INSTALL)
streampass = importlib.util.module_from_spec(_STREAMPASS_SPEC)
_STREAMPASS_SPEC.loader.exec_module(streampass)


def install_streampass(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(STREAMPASS_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture
def pod_seatfix(tmp_path) -> Path:
    target = tmp_path / 'seatfix-src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0 and install_nopin(target)[0] == 0 and install_seatfix(target)[0] == 0
    return target


@pytest.fixture(scope='module')
def streampass_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('streampass') / 'src'
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0 and install_nopin(target)[0] == 0 and install_seatfix(target)[0] == 0
    code, report = install_streampass(target)
    assert code == 0, report
    return target


def test_streampass_plans_applies_refuses_twice_and_needs_seatfix(pod_seatfix, pod_nopin):
    before = {p.name: sha(p) for p in pod_seatfix.iterdir()}
    code, planned = install_streampass(pod_seatfix, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == 20 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_seatfix.iterdir()} == before
    code, report = install_streampass(pod_seatfix)
    assert code == 0 and report['status'] == 'applied' and report['key_light']['max_cd'] == streampass.KEY_LIGHT_MAX_CD
    changed = {name for name in before if sha(pod_seatfix / name) != before[name]}
    assert changed == set(PATCHED)
    for name in PATCHED:
        assert sha(pod_seatfix / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_seatfix / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_seatfix.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_streampass(pod_seatfix, *extra)
        assert code == 2 and 'already' in again['reason']
    assert install_seatfix(pod_seatfix)[0] == 2 and install_nopin(pod_seatfix)[0] == 2
    assert {p.name: sha(p) for p in pod_seatfix.iterdir()} == after
    nopin_before = {p.name: sha(p) for p in pod_nopin.iterdir()}
    code, refused = install_streampass(pod_nopin)
    assert code == 2 and 'lacks the seat fix' in refused['reason'] and {p.name: sha(p) for p in pod_nopin.iterdir()} == nopin_before
    # the mouth layer still applies after the stream pass (its anchors are v2 lines both layers only append to)
    assert install_mouth(pod_seatfix)[0] == 0


def test_streampass_missing_anchor_refuses_without_writing(pod_seatfix):
    lab = pod_seatfix / 'Sub01HomeLab.cpp'
    lab.write_bytes(lab.read_bytes().replace(b' StreamerVisualChairParts=ChairCount;\n', b' StreamerVisualChairParts=ChairCount; \n', 1)
                    .replace(b' StreamerVisualChairParts=ChairCount;\r\n', b' StreamerVisualChairParts=ChairCount; \r\n', 1))
    before = {p.name: sha(p) for p in pod_seatfix.iterdir()}
    code, report = install_streampass(pod_seatfix)
    assert code == 2 and 'anchor missing in Sub01HomeLab.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_seatfix.iterdir()} == before


def test_streampass_text(streampass_patched):
    cpp, header = lf(streampass_patched / 'Sub01HomeLab.cpp'), lf(streampass_patched / 'Sub01HomeLab.h')
    hands_h, proxy = lf(streampass_patched / 'Sub01HomeHands.h'), lf(streampass_patched / 'Sub01HomeHands.cpp')
    for name in PATCHED:
        text = lf(streampass_patched / name)
        assert text.count(STREAMPASS_MARKER + ' BEGIN') == text.count(STREAMPASS_MARKER + ' END') == 1, name
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
        assert text.index(STREAMPASS_MARKER + ' BEGIN') < text.index(FACE_END)  # inside the range build_units(end=FACE_END) extracts
    # tuning keys with their limits, read in the seat fix's reader
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    for key, (lo, hi) in streampass.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key}"),' in tuning and f',{lo},{hi});' in tuning, key
    # hands: targets from the keyboard body (widest follower) / mouse, component space, eased alpha; the proxy's own two-bone solve
    apply = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualV2('):cpp.index('// SUB01_STREAMER_VISUAL_V2 END')]
    assert 'UpdateStreamerVisualHands(Anim,Dt);ApplyStreamerVisualBodyLook();UpdateStreamerVisualKeyLight(Now);UpdateStreamerVisualPerf(Now,Dt);' in apply
    assert '(StreamerVisualPostureLeanDeg+(StreamerVisualTypingBase?StreamerVisualTypingLeanDeg:0.f))-StreamerVisualPostureLeanApplied' in apply
    assert '(StreamerVisualPostureHeadDeg+(StreamerVisualTypingBase?StreamerVisualTypingHeadDeg:0.f))-StreamerVisualPostureHeadApplied' in apply
    # desk_base: the typing loop for every non-reading state when on; the chair moves by chair_back_cm (-1 = with the seat); followers know their kind
    assert 'StreamerVisualDeskSlot(Anim,StreamerVisualState==TEXT("typing")||(StreamerVisualDeskBase>0&&StreamerVisualState!=TEXT("reading"))?1:StreamerVisualState==TEXT("mouse")?2:0);StreamerVisualTypingBase=Slot==1;' in apply
    assert 'const float ChairBack=StreamerVisualChairBackCm<0?StreamerVisualSeatBackCm:StreamerVisualChairBackCm;' in apply
    assert 'StreamerVisualDeskPropIsChair.Add(ChairPart);' in cpp and '(Chair?StreamerVisualChairDelta:WorldDelta)' in cpp and 'StreamerVisualChairDelta.Equals(StreamerVisualChairDeltaApplied,.01)' in cpp
    hands = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualHands('):cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualKeyLight(')]
    # recipe (docs/streamer/kimi/posture.md 3): wrist height above the desk (the keyboard's bottom), span, towards him, eased glide on an arc, left hand planted
    for text in ('if(!StreamerVisualDeskPropsScanned)ScanStreamerVisualDeskProps();', 'const FVector K=KB->GetActorLocation()+StreamerVisualKeyboardCentreOffset,E=StreamerVisualKeyboardExtent;',
                 'const FVector Base=K+Toward*double(StreamerVisualHandBackCm)+FVector(0,0,-E.Z+StreamerVisualHandHeightCm),Half=Right*(double(StreamerVisualHandSpanCm)*.5);',
                 'Goal[0]=Base-Half;Name[0]=TEXT("keyboard_left");Goal[1]=Base+Half;Name[1]=TEXT("keyboard_right");', 'Name[1]=M?TEXT("mouse_prop"):TEXT("mouse_point");',
                 f'if(FVector::Dist(Goal[S],StreamerVisualHandMoveTo[S])>{streampass.HAND_GLIDE_RESTART_CM:g})', 'StreamerVisualHandMoveP[S]=FMath::Min(1.,StreamerVisualHandMoveP[S]+Dt/MoveS);',
                 'Sent[S].Z+=double(StreamerVisualHandArcCm)*FMath::Sin(PI*FMath::SmoothStep(0.,1.,StreamerVisualHandMoveP[S]));',
                 'W.InverseTransformPosition(Have?Sent[0]:StreamerVisualHandSent[0])', f'-Dt/{streampass._f(streampass.HAND_BLEND_SECONDS)},Dt/{streampass._f(streampass.HAND_BLEND_SECONDS)}',
                 'SUB01_STREAMER_VISUAL_HANDS target=left:%s%s right:%s%s reach=L%.1f/R%.1f alpha=%.2f elbow=L%.0f/R%.0f fingers=L%.0f/%.0f R%.0f/%.0f',
                 'Anim->StreamerVisualHandPoleLeft=ToComponent.RotateVector(', 'Anim->StreamerVisualFingerCurlAxis=int32(StreamerVisualFingerCurlAxis);'):
        assert text in hands, text
    assert (streampass.HAND_HEIGHT_CM, streampass.HAND_SPAN_CM, streampass.HAND_MOVE_SECONDS, streampass.HAND_ARC_CM) == (4.5, 20.0, 0.25, 4.0)  # the recipe's numbers
    assert 18 <= streampass.HAND_SPAN_CM <= 22 and 4 <= streampass.HAND_HEIGHT_CM <= 5 and streampass.DESK_BASE == 1
    assert f'StreamerVisualHandHeightCm={streampass._f(streampass.HAND_HEIGHT_CM)}' in header and f'StreamerVisualHandSpanCm={streampass._f(streampass.HAND_SPAN_CM)}' in header
    assert 'if(DeskProp&&Extent.X>StreamerVisualKeyboardExtent.X){StreamerVisualKeyboardActor=A;StreamerVisualKeyboardExtent=Extent;StreamerVisualKeyboardCentreOffset=Origin-L;}' in cpp
    # the engine headers precede their first use: StartStreamerVisualV2 (the key light) comes before the appended methods (build v20 failed on that)
    assert cpp.index('#include "Components/SpotLightComponent.h"') < cpp.index('NewObject<USpotLightComponent>') and cpp.index('#include "RHI.h"') < cpp.index('RHIGetGPUFrameCycles')
    assert cpp.startswith(streampass.CPP_TOP_INCLUDES)
    assert ' StreamerVisualChairParts=ChairCount;ScanStreamerVisualMouse();' in cpp and 'SUB01_STREAMER_VISUAL_MOUSE_CANDIDATE' in cpp and 'SUB01_STREAMER_VISUAL_MOUSE_PROP found=%d' in cpp
    # key light: created once at v2 start, candelas, movable, no shadows; placed and scaled every tick
    start = cpp[cpp.index('void ASub01HomeCharacter::StartStreamerVisualV2('):cpp.index('bool ASub01HomeCharacter::ParseStreamerVisualV2(')]
    for text in ('NewObject<USpotLightComponent>(this,TEXT("StreamerVisualKeyLight"))', 'SetIntensityUnits(ELightUnits::Candelas)', 'SetMobility(EComponentMobility::Movable)', 'SetCastShadows(false)', 'bUseTemperature=true'):
        assert text in start, text
    light = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualKeyLight('):cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualBodyLook(')]
    assert f'SetIntensity(Level*{streampass._f(streampass.KEY_LIGHT_MAX_CD)})' in light and 'SetVisibility(Level>0)' in light and 'SUB01_STREAMER_VISUAL_KEY_LIGHT level=%.2f cd=%.0f' in light
    look = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualBodyLook('):cpp.index(STREAMPASS_MARKER + ' END')]
    assert 'FirstPersonBody->SetForcedLOD(int32(StreamerVisualForcedLod));' in look and 'ShowMaterialSection(int32(StreamerVisualHideSlot),INDEX_NONE,false,0)' in look and 'GetMaterialSlotNames()' in look
    assert 'SUB01_STREAMER_VISUAL_PERF fps=%.1f ms=%.2f max_ms=%.1f gpu_ms=%.2f' in cpp and 'RHIGetGPUFrameCycles()' in cpp
    for text in ('TEXT("hand_left")', 'TEXT("hand_right")', 'TEXT("hands_alpha")', 'TEXT("mouse_prop")', 'TEXT("key_light")', 'TEXT("hide_slot")', 'TEXT("forced_lod")', 'TEXT("fps")', 'TEXT("frame_ms")', 'TEXT("gpu_ms")',
                 'TEXT("elbow_left_deg")', 'TEXT("elbow_right_deg")', 'TEXT("finger_curl_deg_measured")', 'TEXT("frame_max_ms")'):
        assert text in cpp, text
    assert 'UPROPERTY() TObjectPtr<class USpotLightComponent> StreamerVisualKeyLight;' in header
    assert 'UPROPERTY(Transient) FVector StreamerVisualHandTargetLeft=FVector::ZeroVector;' in hands_h and 'UPROPERTY(Transient) float StreamerVisualHandDistRight=-1;' in hands_h
    # proxy: IK after the breathing/posture evaluation and before the head offset; lengths kept, only two local rotations change
    for text in ('static bool StreamerV2SolveTwoBone(const FVector& A,const FVector& B,const FVector& C,const FVector& T,FVector& OutB,FVector& OutC,const FVector& Pole=FVector::ZeroVector,double PoleWeight=0,FVector* LastBend=nullptr){',
                 'D=FMath::Clamp(D,FMath::Abs(L1-L2)+.1,(L1+L2)*.999);', 'const FQuat LocalU=CsP.GetRotation().Inverse()*NewU,LocalF=NewU.Inverse()*NewF;',
                 'const FQuat D2=FQuat::FindBetweenNormals(D1.RotateVector((C-B).GetSafeNormal()),(NC-NB).GetSafeNormal());', 'NewF=D2*D1*CsF.GetRotation();',
                 'TEXT("LeftHandIndex1"),TEXT("LeftHandIndex2"),TEXT("LeftHandIndex3")', 'TEXT("RightHandPinky1"),TEXT("RightHandPinky2"),TEXT("RightHandPinky3")',
                 f'FMath::DegreesToRadians(Curl*(J?{streampass.FINGER_MIDDLE_FACTOR:g}:1.))', 'StreamerVisualElbowDegLeft=Proxy.StreamerV2ElbowDeg[0];',
                 'Bend=Mixed.Size()>.3?Mixed.GetSafeNormal():PN;', 'if(StreamerV2ArmRef==&Ref&&StreamerV2ArmCount==Ref.GetNum())return;', 'if(!StreamerV2ComponentTransform(Output.Pose,H,Done))continue;',
                 'Output.Pose[CU].SetRotation(FQuat::Slerp(Output.Pose[CU].GetRotation(),LocalU,StreamerV2HandAlpha).GetNormalized());',
                 'if(Ref.GetParentIndex(F)!=U||Ref.GetParentIndex(H)!=F)continue;', 'TEXT("LeftArm"),TEXT("LeftForeArm"),TEXT("LeftHand")'):
        assert text in proxy, text
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    assert evaluate.index('EvaluateStreamerV2(Output);') < evaluate.index('EvaluateStreamerV2Hands(Output);') < evaluate.index('FindBoneIndex(TEXT("Head"))')
    assert 'Output.Pose[CH]' not in proxy  # the hand's own local transform is never touched


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_streampass_cpp_compiles_syntax_only_against_stub(streampass_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(streampass_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


STREAMPASS_DRIVER = r'''
#include <cstdlib>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N) { for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += .1; C.ApplyStreamerVisualV2(FPlatformTime::StubNow, .1f); } }
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Body.StubRelative = FTransform(FQuat::Identity, FVector(0, 0, -91), FVector(1, 1, 1)); Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true; C.StreamerVisualDeskBase = 0;
 // key light created at v2 start (candelas, movable); scaled by key_light on the first tick, hidden at 0
 CHECK(C.StreamerVisualKeyLight.Get() != nullptr && C.StreamerVisualKeyLight->bUseTemperature, 1);
 Ticks(C, 1); CHECK(Near(C.StreamerVisualKeyLight->Intensity, @@LEVEL@@ * @@MAXCD@@, 1e-3) && Near(C.StreamerVisualKeyLight->Temperature, @@TEMPK@@, 1e-3) && C.StreamerVisualKeyLight->StubVisible, 2);
 C.StreamerVisualKeyLightLevel = 0; Ticks(C, 1); CHECK(C.StreamerVisualKeyLight->Intensity == 0 && !C.StreamerVisualKeyLight->StubVisible, 3);
 C.StreamerVisualKeyLightLevel = 1; Ticks(C, 1); CHECK(Near(C.StreamerVisualKeyLight->Intensity, @@MAXCD@@, 1e-3) && C.StreamerVisualKeyLight->StubVisible, 4);
 // body look: LOD0 forced once in streamer mode, a hidden slot applied on change
 CHECK(Body.StubForcedLod == @@LOD@@ && C.StreamerVisualForcedLodApplied == @@LOD@@ && C.StreamerVisualHideSlotApplied == -1, 5);
 // typing posture on top of the base: the eased targets become base + typing while the state is typing
 C.StreamerVisualPostureLeanDeg = -4; C.StreamerVisualPostureHeadDeg = 2; Ticks(C, 20); CHECK(Near(C.StreamerVisualPostureLeanApplied, -4, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, 2, 1e-4), 6);
 C.StreamerVisualState = TEXT("typing"); Ticks(C, 40); CHECK(Near(C.StreamerVisualPostureLeanApplied, -4 + @@TLEAN@@, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, 2 + @@THEAD@@, 1e-4), 7);
 C.StreamerVisualState = TEXT("reading"); Ticks(C, 40); CHECK(Near(C.StreamerVisualPostureLeanApplied, -4, 1e-4) && Near(C.StreamerVisualPostureHeadApplied, 2, 1e-4), 8);
 // desk_base 1: the typing loop (and its sit-up) in idle/talking/mouse, the reading loop only for reading
 C.StreamerVisualDeskBase = 1; C.StreamerVisualState = TEXT("idle"); Ticks(C, 40); CHECK(C.StreamerVisualTypingBase && Near(C.StreamerVisualPostureLeanApplied, -4 + @@TLEAN@@, 1e-4), 9);
 C.StreamerVisualState = TEXT("reading"); Ticks(C, 40); CHECK(!C.StreamerVisualTypingBase && Near(C.StreamerVisualPostureLeanApplied, -4, 1e-4), 90);
 C.StreamerVisualDeskBase = 0; C.StreamerVisualState = TEXT("idle"); Ticks(C, 40);
 // hands: nothing without a keyboard body; with one, wrist targets on the keyboard (recipe numbers) in component space, alpha eased over the blend time
 CHECK(!Anim.StreamerVisualHandIK && C.StreamerVisualHandAlpha == 0, 10);
 AActor KB; KB.StubLocation = FVector(209, -339.433, 79.9); KB.StubExtent = FVector(16.05, 5.8, 0.9); C.StreamerVisualKeyboardActor = &KB; C.StreamerVisualKeyboardExtent = KB.StubExtent;
 C.StreamerVisualKeyboardCentreOffset = FVector(1, -2, .5);  // bounds centre vs actor pivot
 Ticks(C, 1);
 // he faces about -Y (yaw 165.4): "towards him" = +Y, his right = +X on the axis-aligned keyboard; wrists hand_height above the keyboard's bottom
 const FVector Base = KB.StubLocation + FVector(1, -2, .5) + FVector(0, @@BACK@@, -0.9 + @@HEIGHT@@);
 const FVector Left = Base - FVector(@@SPAN@@ / 2, 0, 0), Right = Base + FVector(@@SPAN@@ / 2, 0, 0);
 CHECK(Anim.StreamerVisualHandIK && Near(C.StreamerVisualHandAlpha, .1 / @@BLEND@@, 1e-5) && C.StreamerVisualHandTargetName[0] == TEXT("keyboard_left") && C.StreamerVisualHandTargetName[1] == TEXT("keyboard_right"), 11);
 CHECK(Anim.StreamerVisualHandTargetLeft.Equals(Body.StubWorld.InverseTransformPosition(Left), 1e-6) && Anim.StreamerVisualHandTargetRight.Equals(Body.StubWorld.InverseTransformPosition(Right), 1e-6), 12);
 CHECK(Near(FVector::Dist(Left, Right), @@SPAN@@, 1e-9) && Near(Left.Z - (KB.StubLocation.Z + .5 - .9), @@HEIGHT@@, 1e-9), 120);  // span apart, height above the desk
 // elbow poles in component space (the body is only yawed): down, back (away from the monitor = component -Y), out (left arm +X, right arm -X)
 CHECK(Near(Anim.StreamerVisualHandPoleLeft.Z, @@POLEUP@@, 1e-6) && Near(Anim.StreamerVisualHandPoleLeft.Y, -@@POLEBACK@@, 1e-6) && Near(Anim.StreamerVisualHandPoleLeft.X, @@POLEOUT@@, 1e-6), 121);
 CHECK(Near(Anim.StreamerVisualHandPoleRight.Z, @@POLEUP@@, 1e-6) && Near(Anim.StreamerVisualHandPoleRight.Y, -@@POLEBACK@@, 1e-6) && Near(Anim.StreamerVisualHandPoleRight.X, -@@POLEOUT@@, 1e-6), 122);
 CHECK(Near(Anim.StreamerVisualElbowPole, @@POLE@@, 1e-6) && Anim.StreamerVisualFingerCurlAxis == @@AXIS@@ && Anim.StreamerVisualFingerCurlDeg == @@CURL@@, 123);
 // the proxy's measurements come back for the log and the receipt
 Anim.StreamerVisualElbowDegLeft = 92; Anim.StreamerVisualElbowDegRight = 97; Anim.StreamerVisualFingerMcpRight = 28; C.StreamerVisualFingerCurlDeg = 12; C.StreamerVisualFingerCurlAxis = 1; Ticks(C, 1);
 CHECK(C.StreamerVisualElbowDeg[0] == 92 && C.StreamerVisualElbowDeg[1] == 97 && C.StreamerVisualFingerCurlMeasured[2] == 28 && Anim.StreamerVisualFingerCurlDeg == 12 && Anim.StreamerVisualFingerCurlAxis == 1, 124);
 Ticks(C, 4); CHECK(Near(C.StreamerVisualHandAlpha, 1, 1e-6) && Near(Anim.StreamerVisualHandAlpha, 1, 1e-6), 13);
 // a small drift of the keyboard (props following the pull-back) is tracked at once, no glide, no arc
 KB.StubLocation.X += 1.5; Ticks(C, 1);
 CHECK(C.StreamerVisualHandWorld[0].Equals(Left + FVector(1.5, 0, 0), 1e-9) && C.StreamerVisualHandMoveP[0] == 1 && Anim.StreamerVisualHandTargetLeft.Equals(Body.StubWorld.InverseTransformPosition(Left + FVector(1.5, 0, 0)), 1e-6), 125);
 KB.StubLocation.X -= 1.5; Ticks(C, 1);
 // mouse state: the right wrist glides to the tuning point in hand_move_s (eased) on an arc; the left stays planted
 C.StreamerVisualState = TEXT("mouse"); Ticks(C, 1);
 const FVector Mouse(@@MX@@, @@MY@@, @@MZ@@); const double P1 = std::fmin(1.0, .1 / @@MOVE@@), E1 = P1 * P1 * (3 - 2 * P1);
 CHECK(C.StreamerVisualHandTargetName[1] == TEXT("mouse_point") && C.StreamerVisualHandWorld[1].Equals(Right + (Mouse - Right) * E1, 1e-6) && C.StreamerVisualHandWorld[0].Equals(Left, 1e-9), 14);
 CHECK(Near(Anim.StreamerVisualHandTargetRight.Z - Body.StubWorld.InverseTransformPosition(C.StreamerVisualHandWorld[1]).Z, @@ARC@@ * std::sin(PI * E1), 1e-6) && Anim.StreamerVisualHandTargetLeft.Equals(Body.StubWorld.InverseTransformPosition(Left), 1e-6), 140);
 Ticks(C, int(@@MOVE@@ / .1) + 1); CHECK(C.StreamerVisualHandWorld[1].Equals(Mouse, 1e-6) && C.StreamerVisualHandMoveP[1] == 1 && Anim.StreamerVisualHandTargetRight.Equals(Body.StubWorld.InverseTransformPosition(Mouse), 1e-6), 15);  // landed, no arc
 // a new goal mid-arc restarts from the SHOWN position (arc included): no vertical pop
 C.StreamerVisualState = TEXT("typing"); Ticks(C, 1); const FVector Shown = C.StreamerVisualHandSent[1]; CHECK(Shown.Z > C.StreamerVisualHandWorld[1].Z + .5, 151);
 C.StreamerVisualState = TEXT("mouse"); Ticks(C, 1); CHECK(C.StreamerVisualHandMoveFrom[1].Equals(Shown, 1e-9) && C.StreamerVisualHandMoveP[1] < 1, 152);
 Ticks(C, int(@@MOVE@@ / .1) + 1); CHECK(C.StreamerVisualHandWorld[1].Equals(Mouse, 1e-6), 153);
 C.StreamerVisualState = TEXT("typing"); Ticks(C, int(@@MOVE@@ / .1) + 1); CHECK(C.StreamerVisualHandWorld[1].Equals(Right, 1e-6) && C.StreamerVisualHandTargetName[1] == TEXT("keyboard_right"), 16);
 // a mouse prop wins over the tuning point: the wrist behind its centre (towards him) at the hand height above its bottom
 AActor MouseProp; MouseProp.StubLocation = FVector(240, -330, 80); C.StreamerVisualMouseActor = &MouseProp; C.StreamerVisualMouseExtent = FVector(3, 5, 2); C.StreamerVisualMouseCentreOffset = FVector(0, 0, 1);
 C.StreamerVisualState = TEXT("mouse"); Ticks(C, int(@@MOVE@@ / .1) + 1);
 CHECK(C.StreamerVisualHandTargetName[1] == TEXT("mouse_prop") && C.StreamerVisualHandWorld[1].Equals(FVector(240, -330 + @@MOUSEBACK@@, 80 + 1 - 2 + @@HEIGHT@@), 1e-6), 150);
 C.StreamerVisualMouseActor = nullptr; C.StreamerVisualState = TEXT("typing"); Ticks(C, int(@@MOVE@@ / .1) + 1);
 // hands_ik off in the middle of a glide: the fade-out keeps the last SHOWN target (arc included), no snap
 C.StreamerVisualState = TEXT("mouse"); Ticks(C, 1); const FVector ShownMid = Anim.StreamerVisualHandTargetRight; CHECK(C.StreamerVisualHandMoveP[1] < 1, 170);
 C.StreamerVisualHandsIK = 0; Ticks(C, 1); CHECK(Anim.StreamerVisualHandTargetRight.Equals(ShownMid, 1e-9) && Anim.StreamerVisualHandIK, 171);
 C.StreamerVisualHandsIK = 1; C.StreamerVisualState = TEXT("typing"); Ticks(C, 10);
 // hands_ik off: alpha eases out, the proxy flag drops at 0
 C.StreamerVisualHandsIK = 0; Ticks(C, 1); CHECK(Near(C.StreamerVisualHandAlpha, 1 - .1 / @@BLEND@@, 1e-5) && Anim.StreamerVisualHandIK, 17);
 Ticks(C, 5); CHECK(C.StreamerVisualHandAlpha == 0 && !Anim.StreamerVisualHandIK, 18);
 // perf window: averages published after the window and reset
 // perf: a window of wall-clock ticks (one 250 ms hitch), GPU samples averaged; the next window starts clean
 C.StreamerVisualPerfLastNow = 0; StubGpuCycles = 16000; double T = 5000; C.UpdateStreamerVisualPerf(T, 0);
 int Frames = 0; while (T + .1 < 5000 + @@PERF@@) { T += (Frames == 7 ? .25 : .1); C.UpdateStreamerVisualPerf(T, .01f); ++Frames; }
 CHECK(C.StreamerVisualPerfFrames == Frames, 19); T = std::fmax(T + .1, 5000 + @@PERF@@ + 1e-6); C.UpdateStreamerVisualPerf(T, .01f); ++Frames; const double Span = T - 5000;  // this tick closes the window
 CHECK(Near(C.StreamerVisualPerfFps, Frames / Span, 1e-3) && Near(C.StreamerVisualPerfFrameMs, Span * 1000 / Frames, 1e-3) && Near(C.StreamerVisualPerfMaxFrameMs, 250, 1e-3) && Near(C.StreamerVisualPerfGpuMs, 16, 1e-4), 20);
 CHECK(C.StreamerVisualPerfFrames == 0 && C.StreamerVisualPerfGpuSamples == 0 && Near(C.StreamerVisualPerfWindowStart, T, 1e-9), 21);
 StubGpuCycles = 0; C.StreamerVisualPerfLastNow = 0; T = 9000; C.UpdateStreamerVisualPerf(T, 0); for (int K = 0; K < 400; ++K) C.UpdateStreamerVisualPerf(T += .1, .01f);
 CHECK(C.StreamerVisualPerfGpuMs == -1 && Near(C.StreamerVisualPerfFps, 10, 1e-6), 22);  // no RHI sample: -1, not a fake 0
 std::printf("ok\n");
 return 0;
}
'''

STREAMPASS_MATH_DRIVER = r'''
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
int main() {
 // a bent arm: upper arm A->B, forearm B->C; a reachable target keeps both lengths and puts the wrist on the target
 const FVector A(0, 0, 0), B(10, 0, -28), C(10, 25, -33), T(5, 30, -25); FVector NB, NC;
 const double L1 = (B - A).Size(), L2 = (C - B).Size();
 CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, T, NB, NC), 1);
 CHECK(Near((NB - A).Size(), L1, 1e-9) && Near((NC - NB).Size(), L2, 1e-9) && NC.Equals(T, 1e-9), 2);
 // the elbow stays on the side of the original bend plane
 const FVector Axis = (T - A).GetSafeNormal(); const FVector Bend0 = (B - A) - Axis * FVector::DotProduct(B - A, Axis), Bend1 = (NB - A) - Axis * FVector::DotProduct(NB - A, Axis);
 CHECK(FVector::DotProduct(Bend0.GetSafeNormal(), Bend1.GetSafeNormal()) > .99, 3);
 // out of reach: the arm points at the target, nearly straight, lengths kept
 const FVector Far(0, 120, 0); CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, Far, NB, NC), 4);
 CHECK(Near((NB - A).Size(), L1, 1e-9) && Near((NC - NB).Size(), L2, 1e-9) && Near((NC - A).Size(), (L1 + L2) * .999, 1e-9) && FVector::DotProduct((NC - A).GetSafeNormal(), FVector(0, 1, 0)) > .9999, 5);
 // degenerate chains are refused
 CHECK(!FSub01HandsProxy::StreamerV2SolveTwoBone(A, A, C, T, NB, NC) && !FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, A, NB, NC), 6);
 // FindBetweenNormals as the proxy uses it: rotating the old elbow direction onto the new one
 const FQuat D1 = FQuat::FindBetweenNormals((B - A).GetSafeNormal(), (NB - A).GetSafeNormal());
 CHECK(D1.RotateVector((B - A).GetSafeNormal()).Equals((NB - A).GetSafeNormal(), 1e-9), 7);
 // the forearm carried by the upper arm (D1) and then bent at the elbow (D2) lands on the new forearm direction
 const FQuat D2 = FQuat::FindBetweenNormals(D1.RotateVector((C - B).GetSafeNormal()), (NC - NB).GetSafeNormal());
 CHECK((D2 * D1).RotateVector((C - B).GetSafeNormal()).Equals((NC - NB).GetSafeNormal(), 1e-9), 8);
 // pole bias: weight 1 puts the elbow on the pole's side (down), lengths and wrist unchanged; weight 0 is the clip's plane
 FVector PB, PC; const FVector Down(0, 0, -1), Side(1, 0, 0);
 CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, T, PB, PC, Side, 1), 9);
 const FVector Bend2 = (PB - A) - Axis * FVector::DotProduct(PB - A, Axis);
 CHECK(FVector::DotProduct(Bend2.GetSafeNormal(), (Side - Axis * FVector::DotProduct(Side, Axis)).GetSafeNormal()) > .9999 && PC.Equals(T, 1e-9) && Near((PB - A).Size(), L1, 1e-9), 10);
 FVector TB, TC, QB, QC; CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, T, TB, TC) && FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, T, QB, QC, Down, 0) && QB.Equals(TB, 1e-12), 11);
 FVector HB, HC; CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(A, B, C, T, HB, HC, Axis, 1) && HB.Equals(TB, 1e-9), 12);  // a pole along the axis has no direction: ignored
 // a straight arm on the shoulder-target line: the previous frame's bend is reused (no jump to a fixed axis), then remembered
 { const FVector SA(0, 0, 0), SB(0, 20, 0), SC(0, 45, 0), ST(0, 30, 0); FVector Last(0, 0, -1), OB, OC;
   CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(SA, SB, SC, ST, OB, OC, FVector(), 0, &Last) && OB.Z < -1 && Near(OB.X, 0, 1e-9) && Last.Equals(FVector(0, 0, -1), 1e-9), 14); }
 // the clip's elbow up, the pole down: half and half would cancel, so the pole wins (no flip through zero); a light pole keeps the clip's side
 { const FVector UA(0, 0, 0), UB(0, 15, 10), UC(0, 30, 0), UT(0, 28, 0); FVector OB, OC, Last;
   CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(UA, UB, UC, UT, OB, OC, FVector(0, 0, -1), .5, &Last) && OB.Z < 0 && Last.Z < -.99, 15);
   CHECK(FSub01HandsProxy::StreamerV2SolveTwoBone(UA, UB, UC, UT, OB, OC, FVector(0, 0, -1), .2) && OB.Z > 0, 16); }
 // the measured angles: 90, 180, degenerate -1
 CHECK(Near(FSub01HandsProxy::StreamerV2AngleDeg(FVector(1, 0, 0), FVector(0, 1, 0)), 90, 1e-9) && Near(FSub01HandsProxy::StreamerV2AngleDeg(FVector(1, 0, 0), FVector(-2, 0, 0)), 180, 1e-9) && FSub01HandsProxy::StreamerV2AngleDeg(FVector(), FVector(1, 0, 0)) == -1, 13);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_streampass_logic_runs(streampass_patched, tmp_path):
    sp = streampass
    driver = (STREAMPASS_DRIVER.replace('@@LEVEL@@', repr(sp.KEY_LIGHT_LEVEL)).replace('@@MAXCD@@', repr(sp.KEY_LIGHT_MAX_CD)).replace('@@TEMPK@@', repr(sp.KEY_LIGHT_TEMP_K))
              .replace('@@LOD@@', repr(sp.FORCED_LOD)).replace('@@TLEAN@@', repr(sp.TYPING_LEAN_DEG)).replace('@@THEAD@@', repr(sp.TYPING_HEAD_DEG))
              .replace('@@HEIGHT@@', repr(sp.HAND_HEIGHT_CM))
              .replace('@@BLEND@@', repr(sp.HAND_BLEND_SECONDS)).replace('@@MX@@', repr(sp.MOUSE_POINT[0])).replace('@@MY@@', repr(sp.MOUSE_POINT[1])).replace('@@MZ@@', repr(sp.MOUSE_POINT[2]))
              .replace('@@PERF@@', repr(sp.PERF_LOG_SECONDS)).replace('@@SPAN@@', repr(sp.HAND_SPAN_CM)).replace('@@BACK@@', repr(sp.HAND_BACK_CM))
              .replace('@@MOVE@@', repr(sp.HAND_MOVE_SECONDS)).replace('@@ARC@@', repr(sp.HAND_ARC_CM)).replace('@@POLE@@', repr(sp.ELBOW_POLE)).replace('@@AXIS@@', repr(sp.FINGER_CURL_AXIS))
              .replace('@@CURL@@', repr(sp.FINGER_CURL_DEG)).replace('@@POLEUP@@', repr(sp.ELBOW_POLE_VECTOR[0])).replace('@@POLEBACK@@', repr(sp.ELBOW_POLE_VECTOR[1]))
              .replace('@@POLEOUT@@', repr(sp.ELBOW_POLE_VECTOR[2])).replace('@@MOUSEBACK@@', repr(sp.MOUSE_BACK_CM)))
    units = build_units(streampass_patched, tmp_path, end=FACE_END, driver=driver, hands_driver=STREAMPASS_MATH_DRIVER)
    run = _run_driver(units, tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(units, tmp_path, unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v2_behaviour_unchanged_under_streampass(streampass_patched, tmp_path):
    run = _run_driver(build_units(streampass_patched, tmp_path, end=FACE_END), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ cam 2 (second camera behind him -> MJPEG FIFO)
CAM2_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_cam2.py'
CAM2_MARKER = '// SUB01_STREAMER_VISUAL_V2_CAM2'
CAM2_FILES = ('Sub01HomeLab.cpp', 'Sub01HomeLab.h')
_CAM2_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_cam2', CAM2_INSTALL)
cam2 = importlib.util.module_from_spec(_CAM2_SPEC)
_CAM2_SPEC.loader.exec_module(cam2)


def install_cam2(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(CAM2_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


def _stack_to_streampass(target: Path) -> None:
    shutil.copytree(SOURCE, target)
    assert install(target)[0] == 0 and install_face(target)[0] == 0 and install_pinfix(target)[0] == 0 and install_nopin(target)[0] == 0
    assert install_seatfix(target)[0] == 0 and install_streampass(target)[0] == 0


@pytest.fixture
def pod_streampass(tmp_path) -> Path:
    target = tmp_path / 'streampass-src'
    _stack_to_streampass(target)
    return target


@pytest.fixture(scope='module')
def cam2_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('cam2') / 'src'
    _stack_to_streampass(target)
    code, report = install_cam2(target)
    assert code == 0, report
    return target


def test_cam2_plans_applies_refuses_twice_and_needs_streampass(pod_streampass, pod_seatfix):
    before = {p.name: sha(p) for p in pod_streampass.iterdir()}
    code, planned = install_cam2(pod_streampass, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == len(cam2.EDITS) == 7 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == before
    code, report = install_cam2(pod_streampass)
    assert code == 0 and report['status'] == 'applied' and report['cam2']['fps'] == 60 and report['cam2']['size'] == [1280, 720]
    changed = {name for name in before if sha(pod_streampass / name) != before[name]}
    assert changed == set(CAM2_FILES)  # the hands files are not touched
    for name in CAM2_FILES:
        assert report['files'][name]['before_sha256'] == before[name]
        assert sha(pod_streampass / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_streampass / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_streampass.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_cam2(pod_streampass, *extra)
        assert code == 2 and 'already' in again['reason']
    assert install_streampass(pod_streampass)[0] == 2 and install_seatfix(pod_streampass)[0] == 2
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == after
    seat_before = {p.name: sha(p) for p in pod_seatfix.iterdir()}
    code, refused = install_cam2(pod_seatfix)
    assert code == 2 and 'lacks the stream pass' in refused['reason'] and {p.name: sha(p) for p in pod_seatfix.iterdir()} == seat_before
    assert install_mouth(pod_streampass)[0] == 0  # the mouth layer still applies on top (v20 = stream pass + cam2 + mouth)


def test_cam2_missing_anchor_refuses_without_writing(pod_streampass):
    lab = pod_streampass / 'Sub01HomeLab.cpp'
    lab.write_bytes(lab.read_bytes().replace(b'UpdateStreamerVisualPerf(Now,Dt); // SUB01_STREAMER_VISUAL_V2_STREAMPASS', b'UpdateStreamerVisualPerf(Now,Dt);  // SUB01_STREAMER_VISUAL_V2_STREAMPASS', 1))
    before = {p.name: sha(p) for p in pod_streampass.iterdir()}
    code, report = install_cam2(pod_streampass)
    assert code == 2 and 'anchor missing in Sub01HomeLab.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == before


def test_cam2_text(cam2_patched):
    import math
    cpp, header = lf(cam2_patched / 'Sub01HomeLab.cpp'), lf(cam2_patched / 'Sub01HomeLab.h')
    for name in PATCHED:
        text = lf(cam2_patched / name)
        assert text.count(CAM2_MARKER + ' BEGIN') == text.count(CAM2_MARKER + ' END') == (1 if name in CAM2_FILES else 0), name
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
    for text in (cpp, header):
        assert text.index(CAM2_MARKER + ' BEGIN') < text.index(FACE_END)  # inside the range build_units(end=FACE_END) extracts
    # engine headers ahead of their first use (the build v20 lesson)
    for include, use in (('"Components/SceneCaptureComponent2D.h"', 'NewObject<USceneCaptureComponent2D>'), ('"RHIGPUReadback.h"', 'TUniquePtr<FRHIGPUTextureReadback>'),
                         ('"IImageWrapperModule.h"', 'IImageWrapperModule* Images'), ('"Engine/TextureRenderTarget2D.h"', 'NewObject<UTextureRenderTarget2D>(this,TEXT("StreamerVisualCam2Target"))'),
                         ('<sys/ioctl.h>', 'FIONREAD'), ('<signal.h>', 'pthread_sigmask'), ('"Async/Async.h"', 'AsyncTask(')):
        assert cpp.index('#include ' + include) < cpp.index(use), include
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    for key, (lo, hi) in cam2.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key}"),{cam2.TUNING_FIELDS[key]},{lo},{hi});' in tuning, key
    start = cpp[cpp.index('void ASub01HomeCharacter::StartStreamerVisualV2('):cpp.index('bool ASub01HomeCharacter::ParseStreamerVisualV2(')]
    apply = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualV2('):cpp.index('// SUB01_STREAMER_VISUAL_V2 END')]
    assert 'StartStreamerVisualCam2();' in start and 'UpdateStreamerVisualCam2(Now,Dt);' in apply
    body = cpp[cpp.index(CAM2_MARKER + ' BEGIN'):cpp.index(CAM2_MARKER + ' END')]
    # never block: manual captures, polled fences, no ReadPixels/flush/wait, non-blocking FIFO, whole frames only, SIGPIPE contained
    for text in ('bCaptureEveryFrame=false', 'bCaptureOnMovement=false', 'bAlwaysPersistRenderingState=true', 'ESceneCaptureSource::SCS_FinalColorLDR', 'ShowFlags.SetMotionBlur(false)',
                 'InitCustomFormat(1280,720,PF_B8G8R8A8,false)', 'if(!Deferred)StreamerVisualCam2->CaptureScene();', 'ENQUEUE_RENDER_COMMAND(Sub01StreamerCam2Readback)',
                 'const bool Copy=!Deferred||StreamerVisualCam2HasPrevious;StreamerVisualCam2HasPrevious=Deferred;', 'if(Deferred)StreamerVisualCam2->CaptureSceneDeferred();',
                 'ShowFlags.SetDepthOfField(false)', 'while(N<0&&errno==EINTR)', 'if(sigpending(&Waiting)==0&&sigismember(&Waiting,SIGPIPE))', 'Size<=PipeBytes?int64(PipeBytes)-Queued>=Size:Queued==0',
                 'Readback[S]->IsReady()', 'Readback[Best]->Lock(Pitch,&Rows)', 'Readback[Best]->Unlock();', 'Readback[Free]->EnqueueCopy(RHICmdList,Texture);',
                 'if(EncodeBusy.exchange(1)!=0)++DroppedBusy;', 'AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask,', 'Images->CompressImage(Jpeg,EImageFormat::JPEG,FImageView(Pixels.GetData(),Width,Height),Quality.load())',
                 'O_WRONLY|O_NONBLOCK|O_CLOEXEC', f'::fcntl(Fd,F_SETPIPE_SZ,{cam2.PIPE_BYTES});', '::ioctl(Fd,FIONREAD,&Queued)', 'Rest.Append(Data+N,Size-N);',
                 'pthread_sigmask(SIG_BLOCK,&Block,&Old);', 'sigtimedwait(&Block,nullptr,&Zero);', 'pthread_sigmask(SIG_SETMASK,&Old,nullptr);',
                 '::mkfifo(TCHAR_TO_UTF8(*Pipe.FifoPath),0600)', '!S_ISFIFO(S.st_mode)||S.st_uid!=getuid()', 'Now+.5*Dt>=StreamerVisualCam2NextAt',
                 'SUB01_STREAMER_VISUAL_CAM2 started=%d fifo=%s', 'SUB01_STREAMER_VISUAL_CAM2 fps=%.1f capture_fps=%.1f target_fps=%.0f frames=%d reader=%d game_ms_per_capture=%.2f game_ms_per_frame=%.3f',
                 f'TEXT("{cam2.STATUS_SCHEMA}")', 'TEXT("last_frame_utc")', 'TEXT("fps")', 'TEXT("frames")', 'std::rename(TCHAR_TO_UTF8(*Tmp),TCHAR_TO_UTF8(*Final));'):
        assert text in body, text
    for text in ('ReadPixels', 'FlushRenderingCommands', '->Wait(', 'ReadSurfaceData', 'O_RDWR', 'usleep', 'FPlatformProcess::Sleep'):
        assert text not in body, text
    for text in ('TEXT("cam2_on")', 'TEXT("cam2_fps")', 'TEXT("cam2_capture_fps")', 'TEXT("cam2_frames")', 'TEXT("cam2_reader")', 'TEXT("cam2_reason")', 'TEXT("fps")', 'TEXT("gpu_ms")'):
        assert text in cpp, text
    assert 'UPROPERTY() TObjectPtr<class USceneCaptureComponent2D> StreamerVisualCam2;' in header and f'StreamerVisualCam2Fps={streampass._f(cam2.CAM2_FPS)}' in header
    assert cam2.CAM2_FPS == 60 and f'StreamerVisualCam2Dir=TEXT("{cam2.STREAM_DIR}")' in header  # owner: 60 fps on everything
    # the copy of a deferred capture is enqueued BEFORE the next request (it reads the previous one); a frame counts once its last byte is written
    assert body.index('ENQUEUE_RENDER_COMMAND(Sub01StreamerCam2Readback)') < body.index('if(Deferred)StreamerVisualCam2->CaptureSceneDeferred();') and cam2.CAM2_DEFERRED == 1
    write = body[body.index(' void WriteFrame('):]
    assert '++Written' not in write and write.count('Finished();') == 2 and 'void Finished(){++Written;' in body
    # the default view: from behind him and to his right at ~1.6 m, the chair (pulled back up to 30 cm) and the monitor inside the horizontal FOV
    loc, yaw, pitch, fov = cam2.CAM2_LOCATION, cam2.CAM2_YAW, cam2.CAM2_PITCH, cam2.CAM2_FOV
    assert 150 <= loc[2] <= 170 and -40 < pitch < 0
    for point in ((208, -311), (215, -282), seatfix.MONITOR[:2]):  # pelvis on the authored chair, pulled back 30 cm, the monitor
        bearing = math.degrees(math.atan2(point[1] - loc[1], point[0] - loc[0]))
        assert abs((bearing - yaw + 180) % 360 - 180) < fov / 2 - 3, point  # FOVAngle is horizontal: inside the frame with a margin


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_cam2_cpp_compiles_syntax_only_against_stub(cam2_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(cam2_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


CAM2_DRIVER = r'''
#include <cstdlib>
#include <vector>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N, double Dt) {  // a game tick, then the render thread's commands, then the worker's tasks
 for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += Dt; C.ApplyStreamerVisualV2(FPlatformTime::StubNow, float(Dt)); StubRender::Flush(); StubAsync::Flush(); } }
static std::vector<uint8> Drain(int Fd) { std::vector<uint8> Out; uint8 Buf[65536]; for (;;) { const ssize_t N = read(Fd, Buf, sizeof Buf); if (N <= 0) break; Out.insert(Out.end(), Buf, Buf + N); } return Out; }
static int WholeFrames(const std::vector<uint8>& B, std::size_t Size, int& Shade, uint32* FirstSerial = nullptr) {  // -1 = split, foreign or out of order
 if (Size == 0 || B.size() % Size) return -1; int64 LastEncode = -1; int64 LastSerial = -1;
 for (std::size_t K = 0; K < B.size() / Size; ++K) { const uint8* F = &B[K * Size]; if (F[0] != 0xFF || F[1] != 0xD8 || F[Size - 2] != 0xFF || F[Size - 1] != 0xD9) return -1;
  uint32 Encode = 0, Serial = 0; std::memcpy(&Encode, F + 3, 4); std::memcpy(&Serial, F + 7, 4);
  if (int64(Encode) <= LastEncode || int64(Serial) <= LastSerial) return -1;  // strictly newer encodes of strictly newer captures
  LastEncode = Encode; LastSerial = Serial; if (K == 0 && FirstSerial) *FirstSerial = Serial; Shade = F[2]; }
 return int(B.size() / Size);
}
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Camera.PostProcessSettings.StubExposure = 1.25f; Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65;
 C.StreamerVisualCam2Dir = u"@@DIR@@"; FPlatformTime::StubNow = 1000; StubRender::Deferred = StubAsync::Deferred = true;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true;
 // created once at v2 start: the FIFO (0600), a 1280x720 BGRA8 target, a manual LDR capture with the view camera's post process
 struct stat S; CHECK(C.StreamerVisualCam2.Get() && C.StreamerVisualCam2Target.Get() && C.StreamerVisualCam2Reason.IsEmpty() && lstat("@@DIR@@/cam2.mjpeg", &S) == 0 && S_ISFIFO(S.st_mode) && (S.st_mode & 0777) == 0600, 1);
 USceneCaptureComponent2D* Cap = C.StreamerVisualCam2.Get(); UTextureRenderTarget2D* Target = C.StreamerVisualCam2Target.Get();
 CHECK(!Cap->bCaptureEveryFrame && !Cap->bCaptureOnMovement && Cap->bAlwaysPersistRenderingState && Cap->CaptureSource == SCS_FinalColorLDR && !Cap->ShowFlags.MotionBlur && Cap->PostProcessSettings.StubExposure == 1.25f, 2);
 CHECK(Cap->TextureTarget.Get() == Target && Target->SizeX == 1280 && Target->SizeY == 720 && Target->Format == PF_B8G8R8A8, 3);
 C.StartStreamerVisualCam2(); CHECK(C.StreamerVisualCam2.Get() == Cap, 4);  // once per process
 // placed at the defaults on the first tick; one capture per tick at 60 fps in a 60 fps game
 Target->StubTexture.StubPitch = 1344;  // staging rows wider than the image: copied row by row
 Ticks(C, 1, 1 / 60.);
 CHECK(Cap->StubWorld.Translation.Equals(FVector(@@X@@, @@Y@@, @@Z@@), 1e-4) && Near(Cap->StubRotation.Yaw, @@YAW@@, 1e-3) && Near(Cap->StubRotation.Pitch, @@PITCH@@, 1e-3) && Near(Cap->FOVAngle, @@FOV@@, 1e-4), 5);
 Ticks(C, 59, 1 / 60.); CHECK(Cap->StubCaptures == 60 && Cap->StubDeferred == 60 && !Cap->ShowFlags.DepthOfField, 6);  // deferred by default
 // nobody reads the FIFO: frames are encoded and dropped, nothing blocks
 auto& Pipe = *C.StreamerVisualCam2Pipe; CHECK(Pipe.Written.load() == 0 && Pipe.DroppedNoReader.load() >= 50 && Pipe.Encoded.load() >= 50 && !Pipe.Reader.load() && FRHIGPUTextureReadbackStub::Locks >= 50, 7);
 // cam2_fps 30 in a 60 fps game: every other tick; a 24 fps game caps it at one per tick
 C.StreamerVisualCam2Fps = 30; int Before = Cap->StubCaptures; Ticks(C, 60, 1 / 60.); CHECK(Cap->StubCaptures - Before >= 29 && Cap->StubCaptures - Before <= 31, 8);
 C.StreamerVisualCam2Fps = 60; Before = Cap->StubCaptures; Ticks(C, 24, 1 / 24.); CHECK(Cap->StubCaptures - Before == 24, 9);
 // a reader: the writer opens within a second and every frame arrives whole and in order
 const int R = open("@@DIR@@/cam2.mjpeg", O_RDONLY | O_NONBLOCK); CHECK(R >= 0, 10);
 Ticks(C, 90, 1 / 60.); CHECK(Pipe.Reader.load() && Pipe.Written.load() >= 30 && Pipe.PipeBytes == @@PIPE@@, 11);
 int Shade = -1; std::vector<uint8> Got = Drain(R); const int64 Written1 = Pipe.Written.load();
 CHECK(WholeFrames(Got, std::size_t(IImageWrapperModule::StubBytes), Shade) == int(Written1) && Shade >= 0, 12);
 // a slow reader: the pipe holds what fits, the rest is dropped as WHOLE frames (never a split JPEG)
 IImageWrapperModule::StubBytes = 300000; const int64 Full0 = Pipe.DroppedFull.load(), Written2 = Pipe.Written.load();
 Ticks(C, 12, 1 / 60.); const int Fit = int(@@PIPE@@ / 300000);
 CHECK(Pipe.Written.load() - Written2 == Fit && Pipe.DroppedFull.load() - Full0 >= 12 - Fit - 3, 13);
 Got = Drain(R); CHECK(WholeFrames(Got, 300000, Shade) == Fit, 14);
 IImageWrapperModule::StubBytes = 2000; Ticks(C, 6, 1 / 60.); Got = Drain(R); CHECK(WholeFrames(Got, 2000, Shade) >= 3, 15);  // flows again
 // a frame larger than the pipe starts only on an empty pipe and streams through the rest; it counts when its last byte is in
 IImageWrapperModule::StubBytes = @@PIPE@@ + @@PIPE@@ / 2; const int64 Written3 = Pipe.Written.load(); Ticks(C, 1, 1 / 60.);
 CHECK(Pipe.Written.load() == Written3 && Pipe.Rest.Num() == @@PIPE@@ / 2, 150);
 Got = Drain(R); Ticks(C, 1, 1 / 60.); CHECK(Pipe.Written.load() == Written3 + 1 && Pipe.Rest.Num() == 0, 151);  // the rest went out; the newer big frame waits for an empty pipe
 { std::vector<uint8> More = Drain(R); Got.insert(Got.end(), More.begin(), More.end()); } CHECK(WholeFrames(Got, std::size_t(@@PIPE@@ + @@PIPE@@ / 2), Shade) == 1, 152);
 IImageWrapperModule::StubBytes = 2000; Ticks(C, 4, 1 / 60.); Drain(R);
 // cam2_deferred 0: CaptureScene() and the copy of that same capture
 C.StreamerVisualCam2Deferred = 0; const int Deferred0 = Cap->StubDeferred; Before = Cap->StubCaptures; Ticks(C, 6, 1 / 60.);
 CHECK(Cap->StubCaptures - Before == 6 && Cap->StubDeferred == Deferred0, 153); Got = Drain(R); CHECK(WholeFrames(Got, 2000, Shade) >= 3, 154);
 C.StreamerVisualCam2Deferred = 1;
 // the reader leaves: EPIPE (SIGPIPE blocked and consumed: this process survives), the writer closes and waits for the next reader
 close(R); Ticks(C, 6, 1 / 60.); CHECK(!Pipe.Reader.load() && Pipe.Fd < 0, 16);
 // the GPU falls behind: the ring of 3 fills and captures are dropped, nothing waits
 FRHIGPUTextureReadbackStub::ReadyAfterPolls = 50; const int64 Slots0 = Pipe.DroppedSlots.load(); Ticks(C, 10, 1 / 60.); CHECK(Pipe.DroppedSlots.load() - Slots0 >= 6, 17);
 FRHIGPUTextureReadbackStub::ReadyAfterPolls = 1;
 // a reader that leaves mid-frame: its unfinished frame is dropped, the next reader starts on a frame boundary
 const int R2 = open("@@DIR@@/cam2.mjpeg", O_RDONLY | O_NONBLOCK); FPlatformTime::StubNow += 1.5; IImageWrapperModule::StubBytes = 2000; Ticks(C, 3, 1 / 60.); Drain(R2);
 IImageWrapperModule::StubBytes = @@PIPE@@ + @@PIPE@@ / 2; Ticks(C, 1, 1 / 60.); CHECK(Pipe.Reader.load() && Pipe.Rest.Num() == @@PIPE@@ / 2, 160);
 close(R2); IImageWrapperModule::StubBytes = 2000; Ticks(C, 2, 1 / 60.); CHECK(!Pipe.Reader.load() && Pipe.Rest.Num() == 0 && Pipe.Fd < 0, 161);
 const int R3 = open("@@DIR@@/cam2.mjpeg", O_RDONLY | O_NONBLOCK); FPlatformTime::StubNow += 1.5; Ticks(C, 6, 1 / 60.); Got = Drain(R3);
 CHECK(Got.size() >= 2 && Got[0] == 0xFF && Got[1] == 0xD8 && WholeFrames(Got, 2000, Shade) >= 3, 162);
 // a pause: copies still in flight when cam2 turns off are never shown after it
 FRHIGPUTextureReadbackStub::ReadyAfterPolls = 3; Ticks(C, 2, 1 / 60.); const uint32 PauseSerial = Target->StubTexture.StubSerial;
 C.StreamerVisualCam2On = 0; Ticks(C, 5, 1 / 60.); FRHIGPUTextureReadbackStub::ReadyAfterPolls = 1; Drain(R3); const int64 Stale0 = Pipe.DroppedStale.load();
 C.StreamerVisualCam2On = 1; Ticks(C, 8, 1 / 60.); uint32 FirstAfter = 0; Got = Drain(R3);
 CHECK(Pipe.DroppedStale.load() > Stale0 && WholeFrames(Got, 2000, Shade, &FirstAfter) >= 2 && FirstAfter > PauseSerial, 170);
 close(R3); Ticks(C, 3, 1 / 60.);
 // tuning: placement and FOV applied on change; cam2 0 stops the captures
 C.StreamerVisualCam2X = 300; C.StreamerVisualCam2Yaw = -120; C.StreamerVisualCam2Fov = 80; Ticks(C, 1, 1 / 60.);
 CHECK(Near(Cap->StubWorld.Translation.X, 300, 1e-9) && Near(Cap->StubRotation.Yaw, -120, 1e-9) && Near(Cap->FOVAngle, 80, 1e-9), 18);
 C.StreamerVisualCam2On = 0; Before = Cap->StubCaptures; Ticks(C, 30, 1 / 60.); CHECK(Cap->StubCaptures == Before, 19);
 // the log window and the status run without a reader or a file system (stub); the receipt's numbers are filled
 FPlatformTime::StubNow += 31; C.StreamerVisualCam2On = 1; Ticks(C, 2, 1 / 60.); CHECK(C.StreamerVisualCam2FpsAchieved >= 0 && C.StreamerVisualCam2LogFrames <= 2, 20);
 // an existing path that is not a FIFO is never replaced: cam2 stays off with a reason
 ASub01HomeCharacter D; D.FirstPersonBody = &Body; D.ViewCamera = &Camera; D.StreamerVisualCam2Dir = u"@@DIR2@@";
 D.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); D.StreamerVisualSchemaVersion = 2;
 CHECK(!D.StreamerVisualCam2Reason.IsEmpty() && lstat("@@DIR2@@/cam2.mjpeg", &S) == 0 && S_ISREG(S.st_mode), 21);
 Before = D.StreamerVisualCam2->StubCaptures; Ticks(D, 10, 1 / 60.); CHECK(D.StreamerVisualCam2->StubCaptures == Before, 22);
 CHECK(FRHIGPUTextureReadbackStub::BadLocks == 0 && IImageWrapperModule::StubPixelErrors == 0, 23);  // locked only when ready, paired; every pixel row copied right
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_cam2_logic_runs(cam2_patched, tmp_path):
    fifo_dir, foreign_dir = tmp_path / 'stream', tmp_path / 'foreign'
    fifo_dir.mkdir()
    foreign_dir.mkdir()
    (foreign_dir / 'cam2.mjpeg').write_bytes(b'not a fifo')
    driver = (CAM2_DRIVER.replace('@@DIR@@', str(fifo_dir)).replace('@@DIR2@@', str(foreign_dir)).replace('@@X@@', repr(cam2.CAM2_LOCATION[0]))
              .replace('@@Y@@', repr(cam2.CAM2_LOCATION[1])).replace('@@Z@@', repr(cam2.CAM2_LOCATION[2])).replace('@@YAW@@', repr(cam2.CAM2_YAW))
              .replace('@@PITCH@@', repr(cam2.CAM2_PITCH)).replace('@@FOV@@', repr(cam2.CAM2_FOV)).replace('@@PIPE@@', str(cam2.PIPE_BYTES)))
    units = build_units(cam2_patched, tmp_path / 'u', end=FACE_END, driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    assert (foreign_dir / 'cam2.mjpeg').read_bytes() == b'not a fifo'


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_earlier_layers_unchanged_under_cam2(cam2_patched, tmp_path):
    """The v2 driver and the stream pass driver still pass with cam2 on top (cam2 only adds a capture per tick)."""
    run = _run_driver(build_units(cam2_patched, tmp_path / 'v2', end=FACE_END), tmp_path / 'v2')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


# ================================================================================================ pose fix (visual QA of v19: axes, loop seam, aim once, seat yaw, chair fit)
POSEFIX_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_pose_fix.py'
POSEFIX_MARKER = '// SUB01_STREAMER_VISUAL_V2_POSEFIX'
_POSEFIX_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_posefix', POSEFIX_INSTALL)
posefix = importlib.util.module_from_spec(_POSEFIX_SPEC)
_POSEFIX_SPEC.loader.exec_module(posefix)


def install_posefix(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(POSEFIX_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


@pytest.fixture(scope='module')
def v20_patched(tmp_path_factory) -> Path:
    """The full v20 stack in the pod order: ... seat fix, stream pass, cam2, mouth, pose fix."""
    target = tmp_path_factory.mktemp('v20') / 'src'
    _stack_to_streampass(target)
    assert install_cam2(target)[0] == 0 and install_mouth(target)[0] == 0
    code, report = install_posefix(target)
    assert code == 0, report
    return target


def test_posefix_plans_applies_refuses_twice_and_needs_streampass_and_mouth(pod_streampass, pod_seatfix):
    code, refused = install_posefix(pod_streampass)
    assert code == 2 and 'lacks the mouth layer' in refused['reason']  # the mouth emphasis moves into the head channel
    assert install_mouth(pod_streampass)[0] == 0
    before = {p.name: sha(p) for p in pod_streampass.iterdir()}
    code, planned = install_posefix(pod_streampass, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == len(posefix.EDITS) == 25 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == before
    code, report = install_posefix(pod_streampass)
    assert code == 0 and report['status'] == 'applied' and report['loop_fade_s'] == posefix.LOOP_FADE_SECONDS
    assert {name for name in before if sha(pod_streampass / name) != before[name]} == set(PATCHED)
    for name in PATCHED:
        assert sha(pod_streampass / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (pod_streampass / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    after = {p.name: sha(p) for p in pod_streampass.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_posefix(pod_streampass, *extra)
        assert code == 2 and 'already' in again['reason']
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == after
    assert install_cam2(pod_streampass)[0] == 0  # cam2 also goes on after the pose fix
    seat_before = {p.name: sha(p) for p in pod_seatfix.iterdir()}
    code, refused = install_posefix(pod_seatfix)
    assert code == 2 and 'lacks the stream pass' in refused['reason'] and {p.name: sha(p) for p in pod_seatfix.iterdir()} == seat_before


def test_posefix_missing_anchor_refuses_without_writing(pod_streampass):
    assert install_mouth(pod_streampass)[0] == 0
    hands = pod_streampass / 'Sub01HomeHands.cpp'
    hands.write_bytes(hands.read_bytes().replace(b'Progress+FMath::Min(DeltaSeconds,.1f)/.24f);', b'Progress+FMath::Min(DeltaSeconds,.1f)/ .24f);', 1))
    before = {p.name: sha(p) for p in pod_streampass.iterdir()}
    code, report = install_posefix(pod_streampass)
    assert code == 2 and 'anchor missing in Sub01HomeHands.cpp' in report['reason']
    assert {p.name: sha(p) for p in pod_streampass.iterdir()} == before


def test_posefix_text(v20_patched):
    cpp, header = lf(v20_patched / 'Sub01HomeLab.cpp'), lf(v20_patched / 'Sub01HomeLab.h')
    hands_h, proxy = lf(v20_patched / 'Sub01HomeHands.h'), lf(v20_patched / 'Sub01HomeHands.cpp')
    for name in PATCHED:
        text = lf(v20_patched / name)
        assert text.count(POSEFIX_MARKER + ' BEGIN') == text.count(POSEFIX_MARKER + ' END') == 1, name
        assert closure.brace_walk(closure.strip(text)) == closure.brace_walk(closure.strip(lf(SOURCE / name))), name
        assert text.index(POSEFIX_MARKER + ' BEGIN') < text.index(FACE_END), name
    # no Euler-channel offset is left on the spine or the head: every one goes through the body-frame turn
    assert 'StreamerV2Spine[K].Quaternion()' not in proxy and 'StreamerVisualHeadOffset.Quaternion()' not in proxy
    assert 'FRotator(Deg*FMath::Clamp(StreamerV2Mouth,0.f,1.f),0,0)' in proxy  # only for a real jaw bone (none on this skeleton)
    for text in ("const FQuat Q=P.GetRotation();Pose[C].SetRotation((Q.Inverse()*Delta*Q*Pose[C].GetRotation()).GetNormalized());",
                 'FTransform L,R;if(StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[6],L)&&StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[7],R))',
                 'const FVector Right=StreamerV2Right(Pose),Forward=FVector::CrossProduct(Right,FVector::UpVector);',
                 'StreamerV2Turn(Pose,StreamerV2PoseBones[1+K],FQuat(Right,FMath::DegreesToRadians(Deg)));',
                 'FQuat(FVector::UpVector,FMath::DegreesToRadians(Yaw*W))*FQuat(Right,FMath::DegreesToRadians(-Pitch*W))',
                 f'static const double Weights[3]={{{posefix.LEAN_WEIGHTS[0]:g},{posefix.LEAN_WEIGHTS[1]:g},{posefix.LEAN_WEIGHTS[2]:g}}};',
                 'TEXT("Hips"),TEXT("Spine"),TEXT("Spine1"),TEXT("Spine2"),TEXT("Neck"),TEXT("Head"),TEXT("LeftUpLeg"),TEXT("RightUpLeg")',
                 'if(StreamerV2JawBone==INDEX_NONE){StreamerV2MouthPitch=-2.f*FMath::Clamp(StreamerV2Mouth,0.f,1.f);return;}',
                 'Current.SetAccumulatedTime(0);Progress=0;StreamerV2SeamFading=true;', 'if(StreamerVisualActive&&StreamerV2)StreamerV2LoopSeam(DeltaSeconds);',
                 'if(Current.GetSequence()!=Hands->TargetSequence&&!(StreamerV2SeamFading&&Progress<1)) {', 'StreamerV2RightInHips=H.GetRotation().Inverse().RotateVector(D.GetSafeNormal());',
                 'FVector Right=H.GetRotation().RotateVector(StreamerV2RightInHips);Right.Z=0;if(Right.Size()>.5)StreamerV2LastRight=Right.GetSafeNormal();',
                 f'FMath::Abs(Achieved)>={posefix._d(posefix.LEAN_ACHIEVED_MIN_DEG)}',
                 '/(StreamerV2SeamFading&&Current.GetSequence()==StreamerV2SeamSequence?FMath::Max(.05f,StreamerV2SeamFade):.24f));',
                 'StreamerVisualSeatPivot=Proxy.StreamerV2PinPelvis.GetTranslation();', 'StreamerV2LeanCmd=Hands->StreamerVisualLeanDeg;'):
        assert text in proxy, text
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    assert evaluate.index('EvaluateStreamerV2(Output);') < evaluate.index('EvaluateStreamerV2Mouth(Output);') < evaluate.index('EvaluateStreamerV2Hands(Output);') < evaluate.index('ApplyStreamerV2Head(Output);')
    body = proxy[proxy.index('void EvaluateStreamerV2(FPoseContext& Output){'):]
    assert body.index('PinStreamerV2(Output.Pose,true);') < body.index('ApplyStreamerV2Body(Output);')
    assert 'UPROPERTY(Transient) float StreamerVisualLeanDeg=0;' in hands_h and 'UPROPERTY(Transient) FVector StreamerVisualSeatPivot=FVector::ZeroVector;' in hands_h
    # character: the lean on its own channel, head yaw knob, seat yaw about the pelvis, chair fit and turn, the face aim kept
    apply = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualV2('):cpp.index('// SUB01_STREAMER_VISUAL_V2 END')]
    for text in ('Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W),0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1),0,0);Anim->StreamerVisualLeanDeg=StreamerVisualPostureLeanApplied;',
                 'Anim->StreamerVisualHeadOffset.Yaw+=StreamerVisualHeadYawApplied;', 'Seat=Anim->StreamerVisualSeatOffset*FTransform(SeatTurn,Pivot-SeatTurn.RotateVector(Pivot))*FTransform(FQuat::Identity,PullLocal);',
                 '+StreamerVisualChairFitShown:FVector::ZeroVector;', 'FitStreamerVisualChair(Now,Dt,Anim);LogStreamerVisualPose(Now,Anim);',
                 'if(ReadStreamerVisualFaceTuning()){StreamerVisualTuningChanged=true;StreamerVisualChairFitPasses=0;}'):
        assert text in apply, text
    assert 'StreamerVisualPostureLeanApplied*.5' not in apply
    camera = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){'):cpp.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot(')]
    assert 'if(!Face)StreamerVisualFaceSelectedAt=-10; // the aim itself is kept' in camera and 'StreamerVisualFaceAimed=false;StreamerVisualFaceSelectedAt=-10' not in camera
    assert f'K=1.-FMath::Exp(-double(Dt)/{posefix.FACE_MEAN_SECONDS:g});' in camera and f'StreamerVisualFaceMeanSeconds>={posefix.FACE_MIN_SECONDS:g}' in camera
    assert 'if(Face)StreamerVisualFaceSelectedAt=Now;' in camera and f'FromMean=StreamerVisualFaceHeadCount>0&&StreamerVisualFaceMeanSeconds>={posefix.FACE_MIN_SECONDS:g};' in camera
    fit = cpp[cpp.index('void ASub01HomeCharacter::FitStreamerVisualChair('):cpp.index('void ASub01HomeCharacter::LogStreamerVisualPose(')]
    for text in ('Sacrum=Pelvis-Facing*double(StreamerVisualSacrumBackCm)', 'Gap=FVector::DotProduct(Sacrum,Facing)-Front,Move=Gap-double(StreamerVisualBackrestGapCm);',
                 f'-{posefix._d(posefix.CHAIR_FIT_MAX_CM)},{posefix._d(posefix.CHAIR_FIT_MAX_CM)}', 'SUB01_STREAMER_VISUAL_CHAIR_FIT pass=%d method=%s backrest=%s',
                 f'Prim->LineTraceComponent(Hit,Probe+Facing*{posefix.TRACE_FRONT_CM:g},Probe-Facing*{posefix.TRACE_BACK_CM:g},Params)', f'const double Max={posefix.CHAIR_FIT_SPEED_CM_S:g}*double(Dt);',
                 'if(!StreamerVisualChairFitShown.Equals(StreamerVisualChairFitWorld,.01))return;'):
        assert text in fit, text
    assert 'A->SetActorLocationAndRotation(StreamerVisualChairPivotWorld+Yaw.RotateVector(StreamerVisualDeskPropOrigins[I]-StreamerVisualChairPivotWorld)+StreamerVisualChairDelta,Yaw*StreamerVisualDeskPropRotations[I]' in cpp
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    for key, (lo, hi) in posefix.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key}"),{posefix.TUNING_FIELDS[key]},{lo},{hi});' in tuning, key
    for text in ('TEXT("lean_measured_deg")', 'TEXT("lean_gain")', 'TEXT("head_yaw_deg")', 'TEXT("seat_yaw_deg")', 'TEXT("loop_seams")', 'TEXT("backrest_gap_cm")', 'TEXT("chair_fit_cm")', 'TEXT("cam2_fps")'):
        assert text in cpp, text


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_v20_cpp_compiles_syntax_only_against_stub(v20_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(v20_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


POSEFIX_DRIVER = r'''
#include <cstdlib>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N) { for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += .1; C.ApplyStreamerVisualV2(FPlatformTime::StubNow, .1f); } }
static double Gap(const FVector& Pelvis, const FVector& F, const AActor& Back, double Sacrum) {
 const double Front = FVector::DotProduct(Back.StubLocation, F) + std::fabs(Back.StubExtent.X * F.X) + std::fabs(Back.StubExtent.Y * F.Y);
 return FVector::DotProduct(Pelvis - F * Sacrum, F) - Front;
}
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 const FTransform Rel0(FQuat::Identity, FVector(0, 0, -91), FVector(1, 1, 1));
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Body.StubRelative = Rel0; Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65; C.StreamerVisualCam2Dir = u"@@DIR@@";
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true; C.StreamerVisualDeskBase = 0;
 // 1. the lean has its own channel (forward degrees, eased), the spine offsets carry breathing only; head yaw is eased into the head offset's yaw
 C.StreamerVisualPostureLeanDeg = -10; C.StreamerVisualHeadYawDeg = 14; Ticks(C, 20);
 CHECK(Near(Anim.StreamerVisualLeanDeg, -10, 1e-4) && std::fabs(Anim.StreamerVisualSpine1Offset.Pitch) <= .6 + 1e-9 && std::fabs(Anim.StreamerVisualSpine2Offset.Pitch) <= .6 + 1e-9 && Near(C.StreamerVisualHeadYawApplied, 14, 1e-4), 1);
 Anim.StreamerVisualHeadOffset = FRotator(-4, 2, 0); Ticks(C, 1); CHECK(Near(Anim.StreamerVisualHeadOffset.Pitch, -4, 1e-9) && Near(Anim.StreamerVisualHeadOffset.Yaw, 2 + 14, 1e-4) && Near(Anim.StreamerVisualLoopFadeSeconds, @@FADE@@, 1e-6), 2);
 // 2. seat yaw about the proxy's seated pelvis, between the clip offset and the pull-back (the pivot stays put)
 const FTransform D(FRotator(0, -25.6, 0).Quaternion(), FVector(1, 99, 15.5), FVector(1, 1, 1)); const FVector Pivot(0.075, 22.727, 64.214);
 Anim.StreamerVisualSeatOffset = D; Anim.StreamerVisualSeatOffsetValid = true; Anim.StreamerVisualSeatSettled = true; Anim.StreamerVisualSeatPivot = Pivot; Anim.StreamerVisualPelvisBone = 0;
 C.StreamerVisualChairFit = 0; C.StreamerVisualSeatYawDeg = 20; C.StreamerVisualSeatBackCm = 10;
 // chair parts: a backrest behind and above the pelvis, the seat pan below it, an armrest to the side; the authored pelvis on the chair
 const FVector Pelvis = Body.StubWorld.TransformPosition(Pivot); Body.StubHead = Pelvis;  // GetBoneTransform(pelvis) in the stub
 const FVector F0 = (Body.StubWorld.GetRotation().RotateVector(FVector(0, 1, 0)) * FVector(1, 1, 0)).GetSafeNormal(), Side0 = FVector::CrossProduct(FVector::UpVector, F0);
 AActor Back, Pan, Arm; Back.StubLocation = Pelvis - F0 * 8. + FVector(0, 0, 30); Back.StubExtent = FVector(20, 4, 25); Pan.StubLocation = Pelvis + FVector(0, 0, -8); Pan.StubExtent = FVector(25, 25, 4);
 Arm.StubLocation = Pelvis + Side0 * 25. + FVector(0, 0, 10); Arm.StubExtent = FVector(4, 20, 5);
 for (AActor* A : {&Back, &Pan, &Arm}) { C.StreamerVisualDeskProps.Add(A); C.StreamerVisualDeskPropOrigins.Add(A->StubLocation); C.StreamerVisualDeskPropIsChair.Add(true); C.StreamerVisualDeskPropRotations.Add(FQuat::Identity); }
 const FVector BackOrigin = Back.StubLocation;
 Ticks(C, 1);
 const FQuat Yaw(FVector(0, 0, 1), 20 * 3.14159265358979323846 / 180); const FTransform AboutPivot(Yaw, Pivot - Yaw.RotateVector(Pivot), FVector(1, 1, 1));
 CHECK(AboutPivot.TransformPosition(Pivot).Equals(Pivot, 1e-9) && Body.StubRelative.Equals(D * AboutPivot * FTransform(FQuat::Identity, FVector(0, -10, 0), FVector(1, 1, 1)) * Rel0, 1e-6), 3);
 const FVector Pull = Body.StubWorld.GetRotation().RotateVector(FVector(0, -10, 0));
 CHECK(Back.StubLocation.Equals(Pelvis + Yaw.RotateVector(BackOrigin - Pelvis) + Pull, 1e-6) && Back.StubQuat.Equals(Yaw, 1e-9) && Near(C.StreamerVisualChairYaw, 20, 1e-6), 4);  // the chair turns with him about the seat
 // 3. chair fit: the backrest that cut through him (gap < 0) ends backrest_gap_cm behind the sacrum; the pan and the armrest are not the backrest
 C.StreamerVisualSeatYawDeg = 0; C.StreamerVisualSeatBackCm = 0; Ticks(C, 2);
 const double Before = Gap(Pelvis, F0, Back, @@SACRUM@@); CHECK(Back.StubLocation.Equals(BackOrigin, 1e-6) && Before < -5, 5);
 C.StreamerVisualChairFit = 1; C.StreamerVisualChairFitPasses = 0;
 Ticks(C, 60);
 const double After = Gap(Pelvis, F0, Back, @@SACRUM@@);
 CHECK(Near(After, @@TARGET@@, @@DEADBAND@@ + 1e-6) && Near(C.StreamerVisualBackrestGapMeasured, After, @@DEADBAND@@ + 1e-6) && C.StreamerVisualChairFitPasses == @@PASSES@@, 6);
 CHECK(Near(C.StreamerVisualChairFitCm, Before - After, 1e-6) && C.StreamerVisualChairFitCm < 0 && Pan.StubLocation.Equals(Pelvis + FVector(0, 0, -8) + F0 * double(C.StreamerVisualChairFitCm), 1e-6), 7);  // the whole chair moved back
 C.StreamerVisualChairFit = 0; Ticks(C, 1); CHECK(!Back.StubLocation.Equals(BackOrigin, 1e-3) && C.StreamerVisualChairFitCm == 0, 80);  // gliding back, no jump
 Ticks(C, 5); CHECK(Back.StubLocation.Equals(BackOrigin, 1e-6), 8);  // chair_fit 0: back to the plain pull-back
 // the traced surface at sacrum height wins over the bounds: the real backrest face is 2 cm in front of its centre (the box front is 8.9)
 UPrimitiveComponent BackPrim; BackPrim.StubTraceHit = true; BackPrim.StubTraceAnchor = &Back.StubLocation; BackPrim.StubTraceOffset = F0 * 2.; Back.StubPrimitive = &BackPrim;
 C.StreamerVisualChairFit = 1; C.StreamerVisualChairFitPasses = 0; Ticks(C, 60);
 { const double Traced = FVector::DotProduct(Pelvis - F0 * @@SACRUM@@, F0) - FVector::DotProduct(Back.StubLocation + F0 * 2., F0);
   CHECK(Near(Traced, @@TARGET@@, @@DEADBAND@@ + 1e-6) && Near(C.StreamerVisualBackrestGapMeasured, Traced, @@DEADBAND@@ + 1e-6) && C.StreamerVisualChairFitCm < 0, 81); }
 Back.StubPrimitive = nullptr; C.StreamerVisualChairFit = 0; Ticks(C, 10);
 // 4. the face camera aims once from the background head mean and keeps the aim across switches; a tuning change re-aims
 Body.StubHeadIndex = 7; Body.StubHead = FVector(214, -300, 135); C.StreamerVisualCameraTarget = TEXT("spectator"); Ticks(C, 25);
 CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceMeanSeconds >= 2, 9);
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 1);
 CHECK(C.StreamerVisualFaceAimed && C.StreamerVisualFaceAimSource == TEXT("head_mean") && C.StreamerVisualFaceAlpha > 0 && Near(C.StreamerVisualFaceAim.X, 214, 1e-6), 10);  // at once, no 1 s sampling
 const FVector Placed = C.StreamerVisualFaceLocation; const FRotator Look = C.StreamerVisualFaceLook;
 C.StreamerVisualCameraTarget = TEXT("spectator"); Body.StubHead = FVector(224, -300, 135); Ticks(C, 12);
 C.StreamerVisualCameraTarget = TEXT("face"); Ticks(C, 1);
 CHECK(C.StreamerVisualFaceAimed && C.StreamerVisualFaceLocation.Equals(Placed, 1e-9) && Near(C.StreamerVisualFaceLook.Yaw, Look.Yaw, 1e-9) && C.StreamerVisualFaceAlpha > 0, 11);  // kept
 C.StreamerVisualTuningChanged = true; Ticks(C, 1); CHECK(!C.StreamerVisualFaceAimed && C.StreamerVisualFaceMeanSeconds < .2, 12);
 Ticks(C, 21); CHECK(C.StreamerVisualFaceAimed && Near(C.StreamerVisualFaceAim.X, 224, 1e-6) && !C.StreamerVisualFaceLocation.Equals(Placed, 1e-3), 13);
 std::printf("ok\n");
 return 0;
}
'''

POSEFIX_MATH_DRIVER = r'''
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
int main() {
 const double R = 3.14159265358979323846 / 180;
 // his frame: Right from the thighs, Forward = Right x Up; a turn about Right by +a tips the trunk forward (lean), -a raises the nose
 const FVector Right(-1, 0, 0), Up(0, 0, 1), Forward = FVector::CrossProduct(Right, Up);
 CHECK(Forward.Equals(FVector(0, 1, 0), 1e-12), 1);
 const FVector Tipped = FQuat(Right, 10 * R).RotateVector(Up); CHECK(Tipped.Y > 0 && Near(std::atan2(Tipped.Y, Tipped.Z) / R, 10, 1e-9), 2);
 const FVector Nose = FQuat(Right, -5 * R).RotateVector(Forward); CHECK(Near(std::atan2(Nose.Z, Nose.Y) / R, 5, 1e-9), 3);  // nose up 5
 const FVector Turned = FQuat(Up, 20 * R).RotateVector(Forward); CHECK(Turned.X < 0, 4);  // yaw +20 turns towards his right (-X here)
 // local' = parent^-1 * Delta * parent * local: the bone's component rotation becomes Delta * (parent * local), whatever the parent/local
 const FQuat P = FRotator(12, -70, 33).Quaternion(), L = FRotator(-40, 15, 80).Quaternion(), Delta = FQuat(Right, 10 * R);
 const FQuat Local2 = P.Inverse() * Delta * P * L; CHECK((P * Local2).Equals(Delta * (P * L), 1e-12), 5);
 // the measured inclination of the pelvis-to-head line about his facing
 CHECK(Near(FSub01HandsProxy::StreamerV2Incline(FVector(0, 10, 10), Forward), 45, 1e-9) && Near(FSub01HandsProxy::StreamerV2Incline(FVector(0, -10, 10), Forward), -45, 1e-9), 6);
 std::printf("ok\n");
 return 0;
}
'''



POSE_CHAIN_DRIVER = r"""
#include <cstdlib>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static const double Deg = 3.14159265358979323846 / 180;
static FTransform Inv(const FTransform& T) { const FQuat Q = T.GetRotation().Inverse(); return FTransform(Q, Q.RotateVector(T.GetTranslation()) * -1., FVector(1, 1, 1)); }
static FQuat AlongY(const FVector& Dir, double Twist) {  // a Mixamo-like bone: local +Y along the bone, twisted about it
 const FQuat ToDir = FQuat::FindBetweenNormals(FVector(0, 1, 0), Dir.GetSafeNormal()); return ToDir * FQuat(FVector(0, 1, 0), Twist * Deg); }
struct FChain {  // a seated Mixamo-like skeleton in component space (he faces +Y, his right is -X), stored as locals
 FReferenceSkeleton Ref; std::vector<FTransform> Cs; FPoseContext Context{nullptr};
 FChain() {
  const TCHAR* Names[] = {u"Hips", u"Spine", u"Spine1", u"Spine2", u"Neck", u"Head", u"LeftUpLeg", u"RightUpLeg", u"LeftArm", u"LeftForeArm", u"LeftHand", u"RightArm", u"RightForeArm", u"RightHand", u"LeftHandIndex1", u"LeftHandIndex2", u"LeftHandIndex3"};
  const int32 Parents[] = {-1, 0, 1, 2, 3, 4, 0, 0, 3, 8, 9, 3, 11, 12, 10, 14, 15};
  for (int K = 0; K < 17; ++K) { Ref.StubNames.push_back(FName(Names[K])); Ref.StubParents.push_back(Parents[K]); }
  const FVector Lean(0, std::sin(25 * Deg), std::cos(25 * Deg));  // the clips' 25 deg forward hunch
  FVector P[17]; P[0] = FVector(0, 20, 65); P[1] = P[0] + Lean * 10.; P[2] = P[1] + Lean * 12.; P[3] = P[2] + Lean * 12.; P[4] = P[3] + Lean * 14.; P[5] = P[4] + Lean * 10.;
  P[6] = P[0] + FVector(10, 0, -5); P[7] = P[0] + FVector(-10, 0, -5);
  P[8] = P[3] + FVector(17, -2, 6); P[9] = P[8] + FVector(4, 3, -27); P[10] = P[9] + FVector(0, 25, -3);
  P[11] = P[3] + FVector(-17, -2, 6); P[12] = P[11] + FVector(-4, 3, -27); P[13] = P[12] + FVector(0, 25, -3);
  P[14] = P[10] + FVector(0, 9, -1); P[15] = P[14] + FVector(0, 4, -1); P[16] = P[15] + FVector(0, 3, -1);
  const double Twists[17] = {0, 37, -21, 53, 11, -44, 0, 0, 30, -15, 20, -30, 15, -20, 5, 5, 5};
  for (int K = 0; K < 17; ++K) { const int32 C = K == 5 || K == 10 || K == 13 || K == 16 ? -1 : -2;  // ends point like their parent
   FVector Dir = K == 0 ? Lean : K == 6 || K == 7 ? FVector(0, 1, -.2) : C == -1 ? P[K] - P[Parents[K]] : FVector();
   if (C == -2 && Dir.IsNearlyZero()) { for (int J = 0; J < 17; ++J) if (Parents[J] == K && J != 6 && J != 7 && J != 11) { Dir = P[J] - P[K]; break; } }
   Cs.push_back(FTransform(AlongY(Dir, Twists[K]), P[K], FVector(1, 1, 1))); }
  Context.Pose.StubContainer.StubRef = &Ref;
  for (int K = 0; K < 17; ++K) Context.Pose.StubBones.push_back(Parents[K] < 0 ? Cs[std::size_t(K)] : Cs[std::size_t(K)] * Inv(Cs[std::size_t(Parents[K])]));
 }
 FTransform Component(int32 Bone) const { FTransform Out; FSub01HandsProxy::StreamerV2ComponentTransform(Context.Pose, Bone, Out); return Out; }
};
static double Incline(const FChain& C) { const FVector D = C.Component(5).GetTranslation() - C.Component(0).GetTranslation(); return std::atan2(D.Y, D.Z) / Deg; }  // Hips->Head, forward +Y
int main() {
 FSub01HandsProxy Proxy(nullptr);
 // the stub chain itself: locals rebuild the component transforms
 { FChain C; CHECK(C.Component(5).GetTranslation().Equals(C.Cs[5].GetTranslation(), 1e-6) && C.Component(10).GetTranslation().Equals(C.Cs[10].GetTranslation(), 1e-6), 1); }
 // lean +10 (forward): the measured gain converges so the Hips->Head line turns by 10 +- 1 deg; the pelvis does not move; no sideways drift
 { FChain Base; const double Before = Incline(Base); const FVector Head0 = Base.Component(5).GetTranslation();
   Proxy.StreamerV2LeanCmd = 10; Proxy.StreamerV2Dt = 1.f / 60; Proxy.StreamerV2Spine[0] = Proxy.StreamerV2Spine[1] = FRotator::ZeroRotator;
   double Last = 0; FVector Head1;
   for (int Frame = 0; Frame < 120; ++Frame) { FChain C; Proxy.ApplyStreamerV2Body(C.Context); Last = Incline(C) - Before; Head1 = C.Component(5).GetTranslation();
     CHECK(C.Component(0).GetTranslation().Equals(Base.Component(0).GetTranslation(), 1e-9), 2); }
   CHECK(Near(Last, 10, 1) && Near(Proxy.StreamerV2LeanMeasured, Last, 1e-3) && Proxy.StreamerV2LeanGain > 1, 3);
   CHECK(std::fabs(Head1.X - Head0.X) < .5, 4);  // lateral (his right is -X) head drift < 5 mm
   CHECK(Proxy.StreamerV2BodyRight.Equals(FVector(-1, 0, 0), 1e-6), 5); }
 // lean -16 (sit up) moves the head back
 { FChain Base; const double Before = Incline(Base); Proxy.StreamerV2LeanCmd = -16; double Last = 0;
   for (int Frame = 0; Frame < 120; ++Frame) { FChain C; Proxy.ApplyStreamerV2Body(C.Context); Last = Incline(C) - Before; }
   CHECK(Near(Last, -16, 1.6), 6); Proxy.StreamerV2LeanCmd = 0; }
 // head channel: nose DOWN 5 deg = pitch -5 -> the face turns 5 +- 0.5 down, yaw and twist < 1 deg; yaw +20 turns it to his right
 { FChain Base; const FQuat H0 = Base.Component(5).GetRotation(); const FVector Face0 = FVector(0, 1, 0), Ear0 = FVector(-1, 0, 0);
   const FVector FaceLocal = H0.Inverse().RotateVector(Face0), EarLocal = H0.Inverse().RotateVector(Ear0);
   FChain C; Proxy.StreamerVisualHeadOffset = FRotator(-5, 0, 0); Proxy.ApplyStreamerV2Head(C.Context);
   const FQuat H1 = C.Component(5).GetRotation(); const FVector Face = H1.RotateVector(FaceLocal), Ear = H1.RotateVector(EarLocal);
   CHECK(Near(std::atan2(Face.Z, std::hypot(Face.X, Face.Y)) / Deg, -5, .5) && std::fabs(std::atan2(-Face.X, Face.Y) / Deg) < 1 && std::acos(std::fmin(1., FVector::DotProduct(Ear, Ear0))) / Deg < 1, 7);
   FChain D; Proxy.StreamerVisualHeadOffset = FRotator(0, 20, 0); Proxy.ApplyStreamerV2Head(D.Context);
   const FVector Turned = D.Component(5).GetRotation().RotateVector(FaceLocal);
   CHECK(Near(std::atan2(-Turned.X, Turned.Y) / Deg, 20, 1) && std::fabs(std::atan2(Turned.Z, std::hypot(Turned.X, Turned.Y)) / Deg) < 1, 8);  // towards his right (-X)
   // the mouth emphasis (head-only rig): 2 deg nose down, consumed once
   FChain M; Proxy.StreamerVisualHeadOffset = FRotator::ZeroRotator; Proxy.StreamerV2MouthPitch = -2; Proxy.ApplyStreamerV2Head(M.Context);
   const FVector Spoken = M.Component(5).GetRotation().RotateVector(FaceLocal); CHECK(Near(std::atan2(Spoken.Z, std::hypot(Spoken.X, Spoken.Y)) / Deg, -2, .2) && Proxy.StreamerV2MouthPitch == 0, 9); }
 // hands IK through the pose: alpha 0 leaves it, alpha 1 puts the wrist on the target with both lengths kept and the hand's local untouched
 { FChain C0; const FTransform Hand0 = C0.Context.Pose.StubBones[10]; const FVector Target(14, 52, 85);
   Proxy.StreamerV2HandIK = true; Proxy.StreamerV2HandAlpha = 0; Proxy.StreamerV2HandTarget[0] = Proxy.StreamerV2HandTarget[1] = Target; Proxy.EvaluateStreamerV2Hands(C0.Context);
   CHECK(C0.Component(10).GetTranslation().Equals(C0.Cs[10].GetTranslation(), 1e-9), 10);
   FChain C; Proxy.StreamerV2HandAlpha = 1; Proxy.StreamerV2ElbowPole = .5f; Proxy.StreamerV2HandPole[0] = FVector(.3, -.5, -1); Proxy.StreamerV2HandPole[1] = FVector(-.3, -.5, -1);
   Proxy.EvaluateStreamerV2Hands(C.Context);
   const FVector S = C.Component(8).GetTranslation(), E = C.Component(9).GetTranslation(), W = C.Component(10).GetTranslation();
   CHECK(W.Equals(Target, 1e-4) && Near((E - S).Size(), (C.Cs[9].GetTranslation() - C.Cs[8].GetTranslation()).Size(), 1e-6) && Near((W - E).Size(), (C.Cs[10].GetTranslation() - C.Cs[9].GetTranslation()).Size(), 1e-6), 11);
   CHECK(C.Context.Pose.StubBones[10].GetRotation().Equals(Hand0.GetRotation(), 1e-12) && Proxy.StreamerV2HandDist[0] < 1e-3 && Proxy.StreamerV2ElbowDeg[0] > 0 && Proxy.StreamerV2ElbowDeg[0] < 180, 12);
   CHECK(E.Z < (S.Z + W.Z) / 2, 13);  // the elbow hangs below the shoulder-wrist line (pole down)
   // finger curl: +10 deg about the local Z of the proximal phalanx, x1.2 on the middle one
   FChain F; Proxy.StreamerV2FingerCurlDeg = 10; Proxy.StreamerV2FingerCurlAxis = 2; const FQuat I1 = F.Context.Pose.StubBones[14].GetRotation(), I2 = F.Context.Pose.StubBones[15].GetRotation();
   Proxy.EvaluateStreamerV2Hands(F.Context);
   CHECK(F.Context.Pose.StubBones[14].GetRotation().Equals(I1 * FQuat(FVector(0, 0, 1), 10 * Deg), 1e-9) && F.Context.Pose.StubBones[15].GetRotation().Equals(I2 * FQuat(FVector(0, 0, 1), 12 * Deg), 1e-9), 14);
   CHECK(Proxy.StreamerV2FingerFlex[0][0] >= 0 && Proxy.StreamerV2FingerFlex[0][1] >= 0, 15); }
 std::printf("ok\n");
 return 0;
}
"""


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v20_proxy_runs_on_a_bone_chain(v20_patched, tmp_path):
    """The real proxy code (lean with the adaptive gain, head pitch/yaw, mouth emphasis, hand IK, finger curl) on a Mixamo-like
    chain whose bones point along local +Y with arbitrary twists: Kimi's acceptance numbers, offline."""
    units = build_units(v20_patched, tmp_path, end=FACE_END, hands_driver=POSE_CHAIN_DRIVER)
    run = _run_driver(units, tmp_path, unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_posefix_logic_runs(v20_patched, tmp_path):
    (tmp_path / 'cam2').mkdir()
    driver = (POSEFIX_DRIVER.replace('@@DIR@@', str(tmp_path / 'cam2')).replace('@@FADE@@', repr(posefix.LOOP_FADE_SECONDS)).replace('@@SACRUM@@', repr(posefix.SACRUM_BACK_CM))
              .replace('@@TARGET@@', repr(posefix.BACKREST_GAP_CM)).replace('@@DEADBAND@@', repr(posefix.CHAIR_FIT_DEADBAND_CM)).replace('@@PASSES@@', str(posefix.CHAIR_FIT_PASSES)))
    units = build_units(v20_patched, tmp_path / 'u', end=FACE_END, driver=driver, hands_driver=POSEFIX_MATH_DRIVER)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    run = _run_driver(units, tmp_path / 'u', unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v2_behaviour_unchanged_under_v20(v20_patched, tmp_path):
    """The v2 driver (debounce, sway bounds, monitor framing, spectator/monitor blend) still passes on the full v20 stack."""
    run = _run_driver(build_units(v20_patched, tmp_path, end=FACE_END), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


def _header_members(header: str) -> set:
    """Data-member names of the real character header (heuristic: ';'-separated declarations without parentheses)."""
    import re
    names = set()
    for line in closure.strip(header).splitlines():
        line = re.sub(r'\{[^{}]*\}', '', line)
        for segment in line.split(';'):
            if '(' in segment or not segment.strip():
                continue
            for part in segment.split(','):
                match = re.search(r'([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:=.*)?$', part.strip())
                if match and part.strip() != match.group(1):
                    names.add(match.group(1))
    return names


def _added_locals(before: str, after: str) -> set:
    import difflib
    import re
    added = '\n'.join(line[1:] for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm='', n=0)
                      if line.startswith('+') and not line.startswith('+++'))
    added = closure.strip(added)
    types = r'(?:FQuat|FVector|FRotator|FTransform|FString|FColor|double|float|bool|int32|int64|int|uint8|uint64|auto|ssize_t|sigset_t|timespec)'
    names = set(re.findall(r'\b' + types + r'\s*[&*]?\s+([A-Z][A-Za-z0-9_]*)\s*(?=[=({;,\[])', added))
    for declaration in re.findall(r'\b' + types + r'\s*[&*]?\s+[A-Z][^;()]*;', added):  # A=1,B=2 lists
        names.update(re.findall(r',\s*([A-Z][A-Za-z0-9_]*)\s*(?=[=;\[])', declaration))
    return names


def test_v20_new_locals_do_not_shadow_character_fields(v20_patched, seatfix_patched):
    """The engine build compiles with -Wshadow -Werror against the WHOLE character class (the stub has only the streamer fields):
    build v20 failed once on a local `SeatYaw` shadowing ASub01HomeCharacter::SeatYaw."""
    members = _header_members(lf(v20_patched / 'Sub01HomeLab.h'))
    assert {'SeatYaw', 'StreamerVisualCam2Fps', 'StreamerVisualHandSpanCm'} <= members
    added = _added_locals(lf(seatfix_patched / 'Sub01HomeLab.cpp'), lf(v20_patched / 'Sub01HomeLab.cpp'))
    assert {'SeatTurn', 'Facing', 'Pelvis'} <= added
    assert not (added & members), sorted(added & members)
    # and every member the stream pass / cam2 / pose fix declare is new to the class (a duplicate is an error only the engine build would see)
    before = _header_members(lf(seatfix_patched / 'Sub01HomeLab.h'))
    for marker in (STREAMPASS_MARKER, CAM2_MARKER, POSEFIX_MARKER):
        header = lf(v20_patched / 'Sub01HomeLab.h')
        block = header[header.index(marker + ' BEGIN'):header.index(marker + ' END')]
        declared = _header_members(block)
        assert declared and not (declared & before), (marker, sorted(declared & before))


# ================================================================================================ v21 fixes (60 fps tools + visual fixes)
V21_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_v21_fixes.py'
V21_MARKER = '// SUB01_STREAMER_VISUAL_V2_V21'
_V21_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_v21', V21_INSTALL)
v21 = importlib.util.module_from_spec(_V21_SPEC)
_V21_SPEC.loader.exec_module(v21)


def install_v21(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(V21_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


def _stack_to_v20(target: Path) -> None:
    _stack_to_streampass(target)
    assert install_cam2(target)[0] == 0 and install_mouth(target)[0] == 0 and install_posefix(target)[0] == 0


@pytest.fixture(scope='module')
def v21_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('v21') / 'src'
    _stack_to_v20(target)
    code, report = install_v21(target)
    assert code == 0, report
    return target


def test_v21_plans_applies_refuses_twice_and_needs_v20(tmp_path):
    target = tmp_path / 'src'
    _stack_to_streampass(target)
    assert install_cam2(target)[0] == 0 and install_mouth(target)[0] == 0
    before = {p.name: sha(p) for p in target.iterdir()}
    code, refused = install_v21(target)
    assert code == 2 and 'lacks the pose fix' in refused['reason'] and {p.name: sha(p) for p in target.iterdir()} == before
    assert install_posefix(target)[0] == 0
    before = {p.name: sha(p) for p in target.iterdir()}
    code, planned = install_v21(target, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == len(v21.EDITS) + 1 and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in target.iterdir()} == before
    code, report = install_v21(target)
    assert code == 0 and report['status'] == 'applied' and report['key_light']['cd'] == v21.KEY_CD
    assert {name for name in before if sha(target / name) != before[name]} == {'Sub01HomeLab.cpp', 'Sub01HomeLab.h'}
    for name in ('Sub01HomeLab.cpp', 'Sub01HomeLab.h'):
        assert sha(target / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
    after = {p.name: sha(p) for p in target.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_v21(target, *extra)
        assert code == 2 and 'already' in again['reason']
    assert {p.name: sha(p) for p in target.iterdir()} == after


def test_v21_missing_anchor_refuses_without_writing(tmp_path):
    target = tmp_path / 'src'
    _stack_to_v20(target)
    cpp = target / 'Sub01HomeLab.cpp'
    cpp.write_bytes(cpp.read_bytes().replace(b'const bool On=StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty();', b'const bool On=StreamerVisualCam2On>0 && StreamerVisualCam2Reason.IsEmpty();', 1))
    before = {p.name: sha(p) for p in target.iterdir()}
    code, report = install_v21(target)
    assert code == 2 and 'anchor missing in Sub01HomeLab.cpp' in report['reason']
    assert {p.name: sha(p) for p in target.iterdir()} == before


def test_v21_text(v21_patched):
    cpp, header = lf(v21_patched / 'Sub01HomeLab.cpp'), lf(v21_patched / 'Sub01HomeLab.h')
    for text in (cpp, header):
        assert text.count(V21_MARKER + ' BEGIN') == text.count(V21_MARKER + ' END') == 1
        assert text.index(V21_MARKER + ' BEGIN') < text.index(FACE_END)
    assert closure.brace_walk(closure.strip(cpp)) is not None
    assert '#include "RenderTimer.h"' in cpp and '#include "Engine/Engine.h"' in cpp and '#include "HAL/IConsoleManager.h"' in cpp
    perf = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualPerf('):cpp.index('void ASub01HomeCharacter::ScanStreamerVisualMouse(')]
    for name in v21.PERF_GLOBALS:
        assert name in perf
    assert ' '.join(f'{k}=%.2f' for k in v21.PERF_THREADS) in perf and perf.count('Now+StreamerVisualPerfWindowSeconds') == 2 and 'Now+30' not in perf
    camera2 = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualCam2('):cpp.index('void ASub01HomeCharacter::WriteStreamerVisualCam2Status(')]
    assert 'StreamerVisualCam2Reason.IsEmpty()&&ProbeStreamerVisualCam2Reader(Now);' in camera2 and 'ApplyStreamerVisualCam2Lite();' in camera2
    assert 'const int Handed=HandoffFd.exchange(-1);' in cpp and 'std::atomic<int> HandoffFd{-1};' in cpp and 'MakeStreamerVisualBodySeenByCaptures();ApplyStreamerVisualCam2Lite();' in cpp
    key = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualKeyLight('):cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualBodyLook(')]
    assert 'Level*2500' not in key and 'StreamerVisualKeyLight->SetIntensity(Cd);' in key and 'SetLightingChannels(!BodyOnly,BodyOnly,false);' in key
    assert 'Prim->SetLightingChannels(true,BodyOnly,false);' in key and 'SetSoftSourceRadius(StreamerVisualKeyLightSoftCm);' in key
    fit = cpp[cpp.index('void ASub01HomeCharacter::FitStreamerVisualChair('):cpp.index('void ASub01HomeCharacter::LogStreamerVisualPose(')]
    assert 'FVector::DotProduct(Rel,Facing)>-3' not in fit and 'HalfDepth>FMath::Max(' in fit and 'LogStreamerVisualChairParts(Pelvis,Facing,Side);' in fit
    assert f'FMath::Abs(AlongFacing)>{posefix._d(v21.BACKREST_MAX_ALONG_CM)}' in fit and f'Move,-{posefix._d(v21.CHAIR_FIT_MAX_CM)},{posefix._d(v21.CHAIR_FIT_MAX_CM)});' in fit
    writer = cpp[cpp.index(' void WriteFrame(const uint8* Data,int64 Size){'):cpp.index(' sigset_t Block,Old;')]
    assert '::open(' not in writer and 'Reader.store(true);HandoffFd.store(-1);Fd=Offered;' in writer  # the probe is the only opener
    assert 'StreamerVisualDeskPropIsChair.Add(ChairPart);StreamerVisualDeskPropRotations.Add(A->GetActorQuat());' in cpp  # a statement, not a comment
    assert 'if(PropRoot->GetMobility()!=EComponentMobility::Movable){PropRoot->SetMobility(EComponentMobility::Movable);++StreamerVisualDeskPropsMadeMovable;}' in cpp  # Static props never moved
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    for key_name, (lo, hi) in v21.TUNING_LIMITS.items():
        assert f'Field(TEXT("{key_name}"),{v21.TUNING_FIELDS[key_name]},{lo},{hi});' in tuning, key_name
    assert 'if(Now>=StreamerVisualConsoleAt){StreamerVisualConsoleAt=Now+.5;ReadStreamerVisualConsole();}' in cpp
    assert f'"{v21.CONSOLE_PATH}"' in cpp and f'TEXT("{v21.CONSOLE_SCHEMA}")' in cpp
    for field in ('key_light_cd', 'perf_swap_ms', 'perf_rhi_ms', 'console_applied', 'cam2_idle_no_reader', 'body_seen_cleared'):
        assert f'TEXT("{field}")' in cpp, field
    assert f'StreamerVisualKeyLightCd={streampass._f(v21.KEY_CD)}' in header and 'static bool StreamerVisualConsoleAllowed(const FString& Command);' in header


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_v21_cpp_compiles_syntax_only_against_stub(v21_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units(v21_patched, tmp_path, end=FACE_END)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


V21_DRIVER = CAM2_DRIVER[:CAM2_DRIVER.index('int main() {')] + r'''
static bool Allowed(const TCHAR* Command) { return ASub01HomeCharacter::StreamerVisualConsoleAllowed(FString(Command)); }
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65;
 // his primitives: the owner-only body and a follower attached to it; an unrelated primitive of the actor stays as it is
 USkeletalMeshComponent Follower; Follower.StubParent = &Body; Follower.bOnlyOwnerSee = 1; Body.bOnlyOwnerSee = 1; UPrimitiveComponent Other;
 C.StubComponents = {&Body, &Follower, &Other};
 C.StreamerVisualCam2Dir = u"@@DIR@@"; FPlatformTime::StubNow = 1000; StubRender::Deferred = StubAsync::Deferred = true;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true;
 // 1. a scene capture has no view owner: his owner-only primitives become visible to every view at cam2 start
 CHECK(!Body.bOnlyOwnerSee && !Follower.bOnlyOwnerSee && C.StreamerVisualBodySeenCount == 2, 1);
 // 2. cam2 renders only for a reader: nothing is captured, read back or encoded without one
 USceneCaptureComponent2D* Cap = C.StreamerVisualCam2.Get(); auto& Pipe = *C.StreamerVisualCam2Pipe; Ticks(C, 120, 1 / 60.);
 CHECK(Cap->StubCaptures == 0 && C.StreamerVisualCam2Idle >= 100 && Pipe.Encoded.load() == 0 && FRHIGPUTextureReadbackStub::Locks == 0, 2);
 const int R = open("@@DIR@@/cam2.mjpeg", O_RDONLY | O_NONBLOCK); CHECK(R >= 0, 3);
 Ticks(C, 90, 1 / 60.);  // the probe opens within a second and hands the descriptor to the writer
 CHECK(Pipe.Reader.load() && Pipe.HandoffFd.load() < 0 && Cap->StubCaptures >= 60 && Pipe.Written.load() >= 30, 4);
 int Shade = -1; std::vector<uint8> Got = Drain(R); CHECK(WholeFrames(Got, std::size_t(IImageWrapperModule::StubBytes), Shade) == int(Pipe.Written.load()), 5);
 close(R); Ticks(C, 10, 1 / 60.); CHECK(!Pipe.Reader.load() && Pipe.Fd < 0, 6);  // the writer saw EPIPE
 int Before = Cap->StubCaptures; Ticks(C, 120, 1 / 60.); CHECK(Cap->StubCaptures - Before <= 3, 7);  // paused again
 // 3. the lite capture, on change
 CHECK(Cap->ShowFlags.AmbientOcclusion && Cap->MaxViewDistanceOverride < 0 && Near(Cap->LODDistanceFactor, 1, 1e-9), 8);
 C.StreamerVisualCam2Lite = 1; Ticks(C, 1, 1 / 60.);
 CHECK(!Cap->ShowFlags.AmbientOcclusion && !Cap->ShowFlags.ScreenSpaceReflections && !Cap->ShowFlags.ContactShadows && !Cap->ShowFlags.VolumetricFog && !Cap->ShowFlags.LensFlares && !Cap->ShowFlags.Particles
       && Near(Cap->MaxViewDistanceOverride, @@VIEW@@, 1e-3) && Near(Cap->LODDistanceFactor, @@LOD@@, 1e-6) && Cap->ShowFlags.MotionBlur == false, 9);
 C.StreamerVisualCam2Lite = 0; Ticks(C, 1, 1 / 60.); CHECK(Cap->ShowFlags.AmbientOcclusion && Cap->ShowFlags.Particles && Cap->MaxViewDistanceOverride < 0 && Near(Cap->LODDistanceFactor, 1, 1e-9), 10);
 // 4. the key light: candelas, soft, short, on his lighting channel only
 USpotLightComponent* Key = C.StreamerVisualKeyLight.Get(); Ticks(C, 1, 1 / 60.);
 CHECK(Near(Key->Intensity, @@CD@@, 1e-6) && Key->StubVisible && !Key->StubChannels[0] && Key->StubChannels[1] && Body.StubChannels[0] && Body.StubChannels[1] && Follower.StubChannels[1] && !Other.StubChannels[1], 11);
 CHECK(C.StreamerVisualKeyLightBodyPrims == 2 && Near(Key->StubRadius, @@RADIUS@@, 1e-6) && Near(Key->StubSoft, @@SOFT@@, 1e-6) && Near(Key->StubSource, @@SOFT@@ / 2, 1e-6) && Near(Key->StubOuter, @@OUTER@@, 1e-6), 12);
 C.StreamerVisualKeyLightBodyOnly = 0; Ticks(C, 1, 1 / 60.); CHECK(Key->StubChannels[0] && !Key->StubChannels[1] && Body.StubChannels[0] && !Body.StubChannels[1], 13);
 C.StreamerVisualKeyLightCd = 0; Ticks(C, 1, 1 / 60.); CHECK(!Key->StubVisible && Key->Intensity == 0, 14);
 C.StreamerVisualKeyLightCd = .3f; C.StreamerVisualSchemaVersion = 1; Ticks(C, 1, 1 / 60.); CHECK(!Key->StubVisible, 15);  // only for v2 events
 C.StreamerVisualSchemaVersion = 2; Ticks(C, 1, 1 / 60.); CHECK(Key->StubVisible && Near(Key->Intensity, .3, 1e-6), 16);
 // 5. the engine's per-frame thread times, averaged over perf_window_s
 GGameThreadTime = 4000; GRenderThreadTime = 9000; GRHIThreadTime = 12000; GSwapBufferTime = 3000; GRenderThreadWaitTime = 2000; GGameThreadWaitTime = 1000;  // stub: cycles * 1e-3 ms
 C.StreamerVisualPerfWindowSeconds = 5; Ticks(C, 1200, 1 / 60.);
 CHECK(Near(C.StreamerVisualPerfThreadMs[0], 4, 1e-9) && Near(C.StreamerVisualPerfThreadMs[1], 9, 1e-9) && Near(C.StreamerVisualPerfThreadMs[2], 12, 1e-9) && Near(C.StreamerVisualPerfThreadMs[3], 3, 1e-9)
       && Near(C.StreamerVisualPerfThreadMs[4], 2, 1e-9) && Near(C.StreamerVisualPerfThreadMs[5], 1, 1e-9) && Near(C.StreamerVisualPerfFps, 60, 1.5), 17);
 // 6. the console whitelist
 CHECK(Allowed(u"r.ScreenPercentage 70") && Allowed(u"t.MaxFPS 60") && Allowed(u"csvprofile start") && Allowed(u"csvprofile stop") && Allowed(u"csvprofile frames=300") && Allowed(u"sg.ShadowQuality 2")
       && Allowed(u"r.Lumen.Reflections.Allow 0") && Allowed(u"r.Shadow.RadiusThreshold 0.05") && Allowed(u"r.Foo -1") && Allowed(u"r.ShadowQuality") && Allowed(u"t.MaxFPS"), 18);
 CHECK(!Allowed(u"stat unit") && !Allowed(u"quit") && !Allowed(u"r.Foo 1;quit") && !Allowed(u"r.Foo 1 | exit") && !Allowed(u"t.MaxFPSX 3") && !Allowed(u"r.Foo /tmp/x") && !Allowed(u"") && !Allowed(u"R.foo 1")
       && !Allowed(u"a.ParallelAnimEvaluation=1") && !Allowed(u"r.Foo abc") && !Allowed(u"r.Foo 1 2") && !Allowed(u"csvprofile frames=x") && !Allowed(u"csvprofile startx") && !Allowed(u"r. 1") && !Allowed(u"r.Foo 1.2.3"), 19);
 { std::u16string Long(u"r."); Long.append(std::size_t(@@MAXCHARS@@), u'a'); CHECK(!Allowed(Long.c_str()), 20); }
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v21_logic_runs(v21_patched, tmp_path):
    fifo_dir = tmp_path / 'stream'
    fifo_dir.mkdir()
    driver = (V21_DRIVER.replace('@@DIR@@', str(fifo_dir)).replace('@@VIEW@@', repr(v21.CAM2_VIEW_CM)).replace('@@LOD@@', repr(v21.CAM2_LOD_FACTOR))
              .replace('@@CD@@', repr(v21.KEY_CD)).replace('@@RADIUS@@', repr(v21.KEY_RADIUS_CM)).replace('@@SOFT@@', repr(v21.KEY_SOFT_CM))
              .replace('@@OUTER@@', repr(v21.KEY_CONES[1])).replace('@@MAXCHARS@@', str(v21.CONSOLE_MAX_CHARS)))
    units = build_units(v21_patched, tmp_path / 'u', end=FACE_END, driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v21_chair_fit_ignores_a_fat_shell_and_keeps_the_pose_fix_behaviour(v21_patched, tmp_path):
    """The pose fix's driver on v21 with one more chair part: a fat shell behind him (its bounds front lies IN FRONT of the pelvis, so v20
    would have pulled the chair 25 cm through him). v21 takes only the thin, tall, central part behind him: the same fitted gap as before."""
    shell = ('AActor Back, Pan, Arm, Shell; Shell.StubLocation = Pelvis - F0 * 10. + FVector(0, 0, 20); Shell.StubExtent = FVector(34, 31, 47); ',
             'for (AActor* A : {&Back, &Pan, &Arm, &Shell}) {')
    driver = POSEFIX_DRIVER.replace('AActor Back, Pan, Arm; ', shell[0], 1).replace('for (AActor* A : {&Back, &Pan, &Arm}) {', shell[1], 1)
    assert driver != POSEFIX_DRIVER and driver.count('&Shell') == 1
    (tmp_path / 'cam2').mkdir()
    driver = (driver.replace('@@DIR@@', str(tmp_path / 'cam2')).replace('@@FADE@@', repr(posefix.LOOP_FADE_SECONDS)).replace('@@SACRUM@@', repr(posefix.SACRUM_BACK_CM))
              .replace('@@TARGET@@', repr(posefix.BACKREST_GAP_CM)).replace('@@DEADBAND@@', repr(posefix.CHAIR_FIT_DEADBAND_CM)).replace('@@PASSES@@', str(posefix.CHAIR_FIT_PASSES)))
    units = build_units(v21_patched, tmp_path / 'u', end=FACE_END, driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v2_behaviour_unchanged_under_v21(v21_patched, tmp_path):
    run = _run_driver(build_units(v21_patched, tmp_path, end=FACE_END), tmp_path)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


def test_v21_new_locals_do_not_shadow_character_fields(v21_patched, tmp_path):
    v20 = tmp_path / 'v20'
    _stack_to_v20(v20)
    members = _header_members(lf(v21_patched / 'Sub01HomeLab.h'))
    added = _added_locals(lf(v20 / 'Sub01HomeLab.cpp'), lf(v21_patched / 'Sub01HomeLab.cpp'))
    assert {'Handed', 'Probed', 'Offered', 'AlongFacing'} <= added
    assert not (added & members), sorted(added & members)
    header = lf(v21_patched / 'Sub01HomeLab.h')
    declared = _header_members(header[header.index(V21_MARKER + ' BEGIN'):header.index(V21_MARKER + ' END')])
    assert declared and not (declared & _header_members(lf(v20 / 'Sub01HomeLab.h'))), sorted(declared & _header_members(lf(v20 / 'Sub01HomeLab.h')))


# ================================================================================================ v22 (monitor feed, persistent textures, cam2 exposure)
V22_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_v22.py'
V22_MARKER = '// SUB01_STREAMER_VISUAL_V2_V22'
_V22_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_v22', V22_INSTALL)
v22 = importlib.util.module_from_spec(_V22_SPEC)
_V22_SPEC.loader.exec_module(v22)
V22_FILES = tuple(v22.FILES.values())
LAYOUT_SOURCE = ROOT / 'tools/native_pc_bridge/Sub01GuestFrameLayout.h'  # byte-identical to the pod copy the PC bridge includes


def install_v22(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(V22_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


def _stack_to_v21(target: Path) -> None:
    _stack_to_v20(target)
    assert install_v21(target)[0] == 0


@pytest.fixture(scope='module')
def v22_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('v22') / 'src'
    _stack_to_v21(target)
    code, report = install_v22(target)
    assert code == 0, report
    return target


@pytest.fixture(scope='module')
def v21_stack(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('v21-stack') / 'src'
    _stack_to_v21(target)
    return target


def test_v22_plans_applies_refuses_twice_and_needs_v21(v21_stack, tmp_path):
    target = tmp_path / 'src'
    shutil.copytree(v21_stack, target)
    before = {p.name: sha(p) for p in target.iterdir()}
    code, planned = install_v22(target, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == len(v22.EDITS) + 2 and all(e['count'] == 1 for e in planned['edits'] if e['anchor'] != v22.PC_BIND)
    assert [e['count'] for e in planned['edits'] if e['anchor'] == v22.PC_BIND] == [v22.PC_BIND_SITES]
    assert {p.name: sha(p) for p in target.iterdir()} == before and not (target / v22.NEW_HEADER).exists()
    code, report = install_v22(target)
    assert code == 0 and report['status'] == 'applied' and report['monitor_feed']['fps'] == 60 and report['cinematic_pc_inc'] == 'absent'
    assert {name for name in before if sha(target / name) != before[name]} == set(V22_FILES)  # the hands files are not touched
    for name in V22_FILES:
        assert sha(target / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
        raw = (target / name).read_bytes()
        assert raw.count(b'\r\n') == (raw.count(b'\n') if report['files'][name]['line_ending'] == 'CRLF' else 0)
    new = target / v22.NEW_HEADER
    assert sha(new) == report['files'][v22.NEW_HEADER]['after_sha256'] and (new.stat().st_mode & 0o777) == ((target / 'Sub01PCBridge.h').stat().st_mode & 0o777)
    assert not [p for p in target.iterdir() if p.name.endswith('.v2tmp')]
    after = {p.name: sha(p) for p in target.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_v22(target, *extra)
        assert code == 2 and 'already' in again['reason']
    assert install_v21(target)[0] == 2 and {p.name: sha(p) for p in target.iterdir()} == after
    v20 = tmp_path / 'v20'
    _stack_to_v20(v20)
    v20_before = {p.name: sha(p) for p in v20.iterdir()}
    code, refused = install_v22(v20)
    assert code == 2 and 'lacks v21' in refused['reason'] and {p.name: sha(p) for p in v20.iterdir()} == v20_before


def test_v22_missing_anchor_or_extra_binding_refuses_without_writing(v21_stack, tmp_path):
    cases = {'bridge_texture': ('Sub01PCBridge.cpp', b'UTexture2D* Texture=FImageUtils::CreateTexture2DFromImage(Padded);', b'UTexture2D* Texture=FImageUtils::CreateTexture2DFromImage( Padded);'),
             'device_texture': ('Sub01HomeDeviceBridge.cpp', b'FImageUtils::ImportBufferAsTexture2D(Pixels);', b'FImageUtils::ImportBufferAsTexture2D(Pixels );'),
             'seventh_binding': ('Sub01PCBridge.cpp', b'void USub01PCBridge::SendFlag(', b'static void Sub01Extra(UMaterialInstanceDynamic* MonitorMaterial,UTexture* T){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),T);}\r\nvoid USub01PCBridge::SendFlag(')}  # the pod copies are CRLF
    for case, (name, old, new) in cases.items():
        target = tmp_path / case
        shutil.copytree(v21_stack, target)
        path = target / name
        assert path.read_bytes().count(old) == 1, case
        path.write_bytes(path.read_bytes().replace(old, new, 1))
        before = {p.name: sha(p) for p in target.iterdir()}
        code, report = install_v22(target)
        assert code == 2 and ('anchor missing in ' + name in report['reason'] or '"PCFrame" bindings' in report['reason']), (case, report)
        assert {p.name: sha(p) for p in target.iterdir()} == before and not (target / v22.NEW_HEADER).exists(), case


def test_v22_refuses_a_cinematic_include_that_binds_the_monitor(v21_stack, tmp_path):
    target = tmp_path / 'src'
    shutil.copytree(v21_stack, target)
    (target / v22.CINEMATIC_PC_INC).write_text('void USub01PCBridge::X(){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),nullptr);}\n')
    before = {p.name: sha(p) for p in target.iterdir()}
    code, report = install_v22(target)
    assert code == 2 and v22.CINEMATIC_PC_INC in report['reason'] and {p.name: sha(p) for p in target.iterdir()} == before
    (target / v22.CINEMATIC_PC_INC).write_text('bool USub01PCBridge::BeginCinematicWebsite(FString&,FString&){return false;}\n')
    code, report = install_v22(target, '--dry-run')
    assert code == 0 and report['cinematic_pc_inc'] == 'present, no PCFrame binding'
    # the pod copy only reads PCFrame back (observation check): allowed
    (target / v22.CINEMATIC_PC_INC).write_text('void USub01PCBridge::ObserveCinematicWebsite(){\r\n UTexture* Actual=nullptr;'
                                               'if(!MonitorMaterial->GetTextureParameterValue(FName(TEXT("PCFrame")),Actual)||Actual!=GraphicalFrame.Get())return;\r\n}\r\n')
    code, report = install_v22(target, '--dry-run')
    assert code == 0 and report['cinematic_pc_inc'] == 'present, reads PCFrame only'
    # fail closed: a setter that names PCFrame through a variable in another statement is still refused
    (target / v22.CINEMATIC_PC_INC).write_text('void USub01PCBridge::X(UTexture* Feed){\n const FName P(TEXT("PCFrame"));\n'
                                               ' MonitorMaterial->SetTextureParameterValue(P,Feed);\n}\n')
    code, report = install_v22(target, '--dry-run')
    assert code == 2 and v22.CINEMATIC_PC_INC in report['reason']
    (target / v22.CINEMATIC_PC_INC).write_text('bool USub01PCBridge::BeginCinematicWebsite(FString&,FString&){return false;}\n')
    (target / v22.NEW_HEADER).write_text('// someone else\'s header\n')
    code, report = install_v22(target)
    assert code == 2 and 'already exists' in report['reason'] and (target / v22.NEW_HEADER).read_text() == '// someone else\'s header\n'


def test_v22_text(v22_patched):
    cpp, header = lf(v22_patched / 'Sub01HomeLab.cpp'), lf(v22_patched / 'Sub01HomeLab.h')
    pc_cpp, pc_h = lf(v22_patched / 'Sub01PCBridge.cpp'), lf(v22_patched / 'Sub01PCBridge.h')
    dev_cpp, dev_h = lf(v22_patched / 'Sub01HomeDeviceBridge.cpp'), lf(v22_patched / 'Sub01HomeDeviceBridge.h')
    for text in (cpp, header, pc_cpp):
        assert text.count(V22_MARKER + ' BEGIN') == text.count(V22_MARKER + ' END') == 1
    assert pc_h.count(V22_MARKER + ' BEGIN') == pc_h.count(V22_MARKER + ' END') == 2  # the public API and the private members
    for text in (cpp, header):
        assert text.index(V21_MARKER + ' END') < text.index(V22_MARKER + ' BEGIN') < text.index(V22_MARKER + ' END') < text.index(FACE_END)  # inside build_units' range
    for name in (*V22_FILES, *PATCHED):
        assert closure.brace_walk(closure.strip(lf(v22_patched / name))) is not None, name
    # 2. no per-frame UTexture2D left; every "PCFrame" binding of the PC bridge goes through ShowFrame -> SelectMonitorFrame (the only direct bind)
    assert 'CreateTexture2DFromImage' not in pc_cpp and 'ImportBufferAsTexture2D' not in dev_cpp
    block = pc_cpp[pc_cpp.index(V22_MARKER + ' BEGIN'):pc_cpp.index(V22_MARKER + ' END')]
    assert pc_cpp.count(v22.PC_BIND) == block.count(v22.PC_BIND) == 1 and pc_cpp.count('ShowFrame(') == v22.PC_BIND_SITES + 1
    select = block[block.index('void USub01PCBridge::SelectMonitorFrame(){'):block.index('bool USub01PCBridge::IsMonitorFeedAllowed(')]
    assert select.index('if(BoundFrame&&BoundFrame.Get()==Wanted)return;') < select.index(v22.PC_BIND)  # the MID only on a change
    assert pc_cpp.index('void USub01PCBridge::Poll(){\n SelectMonitorFrame();') >= 0  # the poll timer re-selects before it may return early
    endplay = pc_cpp[pc_cpp.index('void USub01PCBridge::EndPlay('):pc_cpp.index('void USub01PCBridge::ReadState(')]
    assert endplay.index('ReleaseMonitorFeed();') < endplay.index('ClearTimer(PollTimer)')  # Kimi's review: the MID leaves the feed at EndPlay
    assert 'Sub01PersistentTexture::Ensure(PersistentFrame,Layout.Width,Layout.Height,&FramesCreated);' in pc_cpp and 'Sub01PersistentTexture::Update(Texture,0,0,Layout.Width,Layout.Height,MoveTemp(Padded.RawData))' in pc_cpp
    assert 'Sub01PersistentTexture::Ensure(PersistentImages.FindOrAdd(Device),BGRA.SizeX,BGRA.SizeY,&PersistentImagesCreated)' in dev_cpp and 'FImageUtils::DecompressImage(Pixels.GetData(),Pixels.Num(),Decoded)' in dev_cpp
    assert 'UPROPERTY()TMap<FName,TObjectPtr<UTexture2D>> PersistentImages;' in dev_h and 'UPROPERTY() TObjectPtr<UTexture2D> PersistentFrame;' in pc_h
    for text in (pc_cpp, dev_cpp):  # engine headers ahead of their first use (the build v20 lesson)
        assert text.index('#include "Sub01PersistentTexture.h"') < text.index('Sub01PersistentTexture::Ensure(')
    assert dev_cpp.index('#include "ImageCore.h"') < dev_cpp.index('FImage Decoded,BGRA;')
    # the privacy gate: dropped first thing in ClearPrivateState; the poll's second read (its start time) confirms the connected Vagon desktop
    clear = pc_cpp[pc_cpp.index('void USub01PCBridge::ClearPrivateState('):pc_cpp.index('void USub01PCBridge::ApplyTerminal(')]
    assert clear.index('FeedFrame=nullptr;PublicConfirmedAt=-1;FeedSourceConnected=false;') < clear.index('ShowFrame(TerminalCanvas)')
    poll = pc_cpp[pc_cpp.index('void USub01PCBridge::Poll(){'):pc_cpp.index('void USub01PCBridge::SendGraphicalInput(')]
    assert poll.index('const double AskedAt=FPlatformTime::Seconds();') < poll.index('ReadState([this,Epoch,AskedAt](TSharedPtr<FJsonObject> After){') < poll.index('if(!IsPublicState(After))') \
        < poll.index('NoteMonitorFeedSource(After,AskedAt);') < poll.index('ApplyTerminal(After);')
    for text in ('TEXT("pc_mode"),Mode)&&Mode==TEXT("vagon")', 'TEXT("connected"),Connected)&&Connected', 'TEXT("available"),Available)&&Available',
                 'TEXT("kind"),Kind)&&Kind==TEXT("graphical")', 'TEXT("phase"),Phase)&&Phase==TEXT("connected")', 'PublicConfirmedAt=FeedSourceConnected?AskedAt:-1.;SelectMonitorFrame();',
                 f'Now-PublicConfirmedAt<={v22._num(v22.CONFIRM_SECONDS)}', f'Now-FeedFrameAt<={v22._num(v22.RENEW_SECONDS)}', '!Private&&!LocalPrivacy&&!PrivacyDesired&&FeedSourceConnected'):
        assert text in block, text
    # the character: tuning keys on their own V22 line, start/tick/receipt hooks, the reader never blocks, never decodes on the game thread
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    line = [row for row in tuning.split('\n') if V22_MARKER in row]
    assert len(line) == 1 and all(f'Field(TEXT("{k}"),{v22.TUNING_FIELDS[k]},{lo},{hi});' in line[0] for k, (lo, hi) in v22.TUNING_LIMITS.items())
    assert {'monitor_feed', 'monitor_fps', 'monitor_delay_s', 'monitor_stale_s', 'cam2_exposure', 'cam2_ev_bias', 'cam2_ev_min', 'cam2_ev_max'} == set(v22.TUNING_LIMITS)
    assert v22.STALE_SECONDS >= 1.5 and v22.PLAYOUT_SECONDS == 0.75 and v22.TUNING_LIMITS['monitor_delay_s'][0] >= 0.5  # above the sidecar's 0.5 s neutral repeat; Kimi
    start = cpp[cpp.index('void ASub01HomeCharacter::StartStreamerVisualV2('):cpp.index('bool ASub01HomeCharacter::ParseStreamerVisualV2(')]
    apply = cpp[cpp.index('void ASub01HomeCharacter::ApplyStreamerVisualV2('):cpp.index('// SUB01_STREAMER_VISUAL_V2 END')]
    camera2 = cpp[cpp.index('void ASub01HomeCharacter::UpdateStreamerVisualCam2('):cpp.index('void ASub01HomeCharacter::WriteStreamerVisualCam2Status(')]
    assert 'StartStreamerVisualMonitorFeed();' in start and 'UpdateStreamerVisualMonitorFeed(Now,Dt);' in apply and 'ApplyStreamerVisualCam2Exposure();' in camera2
    body = cpp[cpp.index(V22_MARKER + ' BEGIN'):cpp.index(V22_MARKER + ' END')]
    for text in ('O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW', '!S_ISFIFO(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)', 'AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask,',
                 'if(At<=Now-Delay&&At<ConfirmedAt)Pick=I;', 'Taken->ReadAt>=ConfirmedAt', f'Sub01PersistentTexture::PendingUploads().load()>={v22.MAX_PENDING_UPLOADS}',
                 'Sub01PersistentTexture::Clear(StreamerVisualMonitorTexture)', 'SUB01_STREAMER_VISUAL_MONITOR_FEED_GATE open=%d',
                 'Feed.Busy.load()==0', 'Ready.exchange(Frame)', 'Feed.Ready.exchange(nullptr)', 'Images->CreateImageWrapper(EImageFormat::JPEG)', 'GetRaw(ERGBFormat::BGRA,8,Out.Pixels)',
                 f'W>{v22.MAX_W}||H>{v22.MAX_H}', 'PCBridge->SetMonitorFeedFrame(Fresh?StreamerVisualMonitorTexture.Get():nullptr)', 'PCBridge->IsMonitorFeedAllowed(Now)',
                 'Sub01GuestFrameLayout(Width,Height,PCBridge->GetMonitorScreenAspect(),Layout)', 'SUB01_STREAMER_VISUAL_MONITOR_FEED fps=%.1f decoded=%d dropped=%d stale=%d',
                 'SUB01_STREAMER_VISUAL_CAM2_EXPOSURE mode=%d', 'Settings.AutoExposureMethod=AEM_Manual;'):
        assert text in body, text
    for text in ('O_RDWR', 'O_WRONLY', 'mkfifo', 'unlink', 'FlushRenderingCommands', 'usleep', 'FPlatformProcess::Sleep', 'CreateTexture2DFromImage', 'ImportBufferAsTexture2D', 'ViewCamera->PostProcessSettings'):
        assert text not in body, text  # a reader only; never creates or replaces the sidecar's FIFO; never waits; the main camera untouched
    game_thread = body[body.index('void ASub01HomeCharacter::UpdateStreamerVisualMonitorFeed('):body.index('void ASub01HomeCharacter::LogStreamerVisualMonitorFeed(')]
    assert '::read(' not in game_thread and 'Decode(' not in game_thread and 'Sub01ScanJpegs(' not in game_thread
    for field in ('monitor_feed_on', 'monitor_feed_bound', 'monitor_feed_allowed', 'monitor_feed_fps', 'monitor_feed_decoded', 'monitor_feed_dropped', 'monitor_feed_stale',
                  'monitor_feed_age_ms', 'monitor_feed_textures', 'monitor_feed_reason', 'pc_bridge_textures', 'cam2_exposure', 'cam2_ev_bias',
                  'monitor_feed_delay_s', 'monitor_feed_stale_s', 'monitor_feed_epoch', 'monitor_feed_gate_reason', 'monitor_feed_upload_busy', 'monitor_feed_in_fps'):
        assert f'TEXT("{field}")' in cpp, field
    assert f'StreamerVisualMonitorFps={streampass._f(v22.MONITOR_FPS)}' in header and v22.MONITOR_FPS == 60 and v22.MONITOR_FEED == 1
    assert 'UPROPERTY() TObjectPtr<class UTexture2D> StreamerVisualMonitorTexture;' in header
    assert '#include "Sub01PersistentTexture.h"' in cpp and '#include "Sub01GuestFrameLayout.h"' in cpp and '#include "IImageWrapper.h"' in cpp
    new = lf(v22_patched / v22.NEW_HEADER)
    assert new == v22.PERSISTENT_HEADER and ('UpdateTextureRegions(0,1,Region,uint32(Width)*4,4,Owned->GetData(),[Owned](uint8*,const FUpdateTextureRegion2D* Done)'
                                             '{delete Owned;delete Done;--PendingUploads();});') in new
    assert 'NeverStream=true' in new and 'SRGB=true' in new and 'PF_B8G8R8A8' in new and '!Texture->GetResource()' in new


V22_INCLUDES = '#include "ue_stub.h"\n#include "Sub01PersistentTexture.h"\n#include "Sub01GuestFrameLayout.h"\n'


def build_units_v22(src: Path, work: Path, driver: str = None) -> dict:
    """build_units on the v22 stack: the character unit also sees the new persistent-texture header and the bridge's layout header."""
    units = build_units(src, work, end=FACE_END, driver=driver)
    include = units['character'][1]
    shutil.copy(src / v22.NEW_HEADER, include / v22.NEW_HEADER)
    shutil.copy(LAYOUT_SOURCE, include / 'Sub01GuestFrameLayout.h')
    (units['stub'] / 'Engine').mkdir(exist_ok=True)
    (units['stub'] / 'Engine' / 'Texture2D.h').write_text('#pragma once\n#include "ue_stub.h"\n')
    for key in ('character', 'driver'):
        path = units[key][0]
        text = path.read_text()
        assert text.startswith('#include "ue_stub.h"\n')
        path.write_text(text.replace('#include "ue_stub.h"\n', V22_INCLUDES, 1))
    return units


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_v22_cpp_compiles_syntax_only_against_stub(v22_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units_v22(v22_patched, tmp_path)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


PERSISTENT_DRIVER = r'''#include "ue_stub.h"
#include "Sub01PersistentTexture.h"
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static TArray64<uint8> Frame(int32 W, int32 H, uint8 Shade) { TArray64<uint8> P; P.SetNumZeroed(int64(W) * H * 4); for (int64 I = 0; I < P.Num(); I += 4) { P[I] = Shade; P[I + 1] = uint8(I / 4); P[I + 2] = 7; P[I + 3] = 255; } return P; }
static bool Black(const UTexture2D* T, int32 X, int32 Y) { const uint8* P = T->StubPixel(X, Y); return P[0] == 0 && P[1] == 0 && P[2] == 0 && P[3] == 255; }
int main() {
 StubRender::Deferred = true; TObjectPtr<UTexture2D> Slot; int32 Created = 0;
 // created once: B8G8R8A8, sRGB, never streamed, clamped, bilinear, with a resource; its uninitialised mip is overwritten with opaque black first
 UTexture2D* A = Sub01PersistentTexture::Ensure(Slot, 8, 4, &Created);
 CHECK(A && Slot.Get() == A && Created == 1 && UTexture2D::StubCreated == 1 && A->GetPixelFormat() == PF_B8G8R8A8 && A->SRGB && A->NeverStream && A->Filter == TF_Bilinear && A->AddressX == TA_Clamp && A->AddressY == TA_Clamp && A->GetResource(), 1);
 CHECK(UTexture2D::StubUpdates == 1 && UTexture2D::StubCleanups == 0 && Sub01PersistentTexture::PendingUploads().load() == 1, 2);
 StubRender::Flush(); CHECK(UTexture2D::StubCleanups == 1 && Sub01PersistentTexture::PendingUploads().load() == 0, 3);
 for (int32 Y = 0; Y < 4; ++Y) for (int32 X = 0; X < 8; ++X) CHECK(Black(A, X, Y), 4);
 // a region update: the buffer is moved in (the caller's copy is gone) and freed by the cleanup after the RHI copy, outside the region untouched
 TArray64<uint8> P = Frame(3, 2, 42); CHECK(Sub01PersistentTexture::Update(A, 4, 1, 3, 2, MoveTemp(P)) && P.Num() == 0, 5);
 CHECK(A->StubPixel(4, 1)[0] == 0, 6);  // not before the render thread ran
 StubRender::Flush(); CHECK(UTexture2D::StubCleanups == 2 && A->StubPixel(4, 1)[0] == 42 && A->StubPixel(6, 2)[0] == 42 && A->StubPixel(6, 2)[1] == 5 && Black(A, 3, 1) && Black(A, 7, 1) && Black(A, 4, 0) && Black(A, 4, 3), 7);
 // the same size again and again: the same texture, nothing created, every heap copy freed exactly once
 for (int K = 0; K < 100; ++K) { UTexture2D* B = Sub01PersistentTexture::Ensure(Slot, 8, 4, &Created); CHECK(B == A, 8); CHECK(Sub01PersistentTexture::Update(B, 0, 0, 8, 4, Frame(8, 4, uint8(K))), 9); }
 CHECK(Sub01PersistentTexture::PendingUploads().load() == 100, 101);  // what a stalled render thread would accumulate (callers check it)
 StubRender::Flush(); CHECK(Created == 1 && UTexture2D::StubCreated == 1 && UTexture2D::StubUpdates == 102 && UTexture2D::StubCleanups == 102 && A->StubPixel(7, 3)[0] == 99
                            && Sub01PersistentTexture::PendingUploads().load() == 0, 10);
 // Clear: the whole texture opaque black again (a new source rect, a dead feed)
 CHECK(Sub01PersistentTexture::Clear(A) && !Sub01PersistentTexture::Clear(nullptr), 102); StubRender::Flush();
 for (int32 Y = 0; Y < 4; ++Y) for (int32 X = 0; X < 8; ++X) CHECK(Black(A, X, Y), 103);
 CHECK(UTexture2D::StubUpdates == 103 && UTexture2D::StubCleanups == 103, 104);
 // refused without enqueuing anything: a wrong buffer size, a region outside the texture, no texture, no resource
 CHECK(!Sub01PersistentTexture::Update(A, 0, 0, 8, 4, Frame(8, 3, 1)) && !Sub01PersistentTexture::Update(A, 6, 0, 3, 1, Frame(3, 1, 1)) && !Sub01PersistentTexture::Update(A, -1, 0, 1, 1, Frame(1, 1, 1))
       && !Sub01PersistentTexture::Update(nullptr, 0, 0, 1, 1, Frame(1, 1, 1)) && UTexture2D::StubUpdates == 103 && Sub01PersistentTexture::PendingUploads().load() == 0, 11);
 UTexture2D NoResource; NoResource.StubX = NoResource.StubY = 2; CHECK(!Sub01PersistentTexture::Update(&NoResource, 0, 0, 1, 1, Frame(1, 1, 1)) && UTexture2D::StubUpdates == 103, 12);
 CHECK(!Sub01PersistentTexture::Ensure(Slot, 0, 4, &Created) && !Sub01PersistentTexture::Ensure(Slot, 5000, 4, &Created) && Slot.Get() == A && Created == 1, 13);
 // a new size: a new texture (the old one is left to the garbage collector), black again
 UTexture2D* C = Sub01PersistentTexture::Ensure(Slot, 6, 6, &Created); StubRender::Flush();
 CHECK(C && C != A && Slot.Get() == C && Created == 2 && UTexture2D::StubCreated == 2 && Black(C, 5, 5) && UTexture2D::StubUpdates == UTexture2D::StubCleanups, 14);
 delete A; delete C;
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v22_persistent_texture_runs(v22_patched, tmp_path):
    """One texture per size, updated in place; each heap copy freed once by the cleanup (AddressSanitizer when available)."""
    stub = tmp_path / 'stub'
    (stub / 'Engine').mkdir(parents=True)
    (stub / 'ue_stub.h').write_text(STUB)
    for name in ('CoreMinimal.h', 'RHI.h', 'Engine/Texture2D.h'):
        (stub / name).write_text('#pragma once\n#include "ue_stub.h"\n')
    shutil.copy(v22_patched / v22.NEW_HEADER, tmp_path / v22.NEW_HEADER)
    (tmp_path / 'driver.cpp').write_text(PERSISTENT_DRIVER)
    name, path, _ = COMPILERS[0]
    for sanitize in (['-fsanitize=address,undefined', '-fno-omit-frame-pointer'], []):
        build = subprocess.run([path, '-std=c++20', '-O1', *sanitize, f'-I{tmp_path}', '-isystem', str(stub), str(tmp_path / 'driver.cpp'), '-o', str(tmp_path / 'driver')],
                               capture_output=True, text=True)
        if build.returncode == 0:
            break
    assert build.returncode == 0, build.stderr[-6000:]
    run = subprocess.run([str(tmp_path / 'driver')], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


BRIDGE_UNIT = r'''#include "ue_stub.h"
#include "Sub01PersistentTexture.h"
class UCanvasRenderTarget2D : public UTexture {};
class UMaterialInstanceDynamic : public UObject { public: UTexture* StubBound = nullptr; int64 StubSets = 0; void SetTextureParameterValue(const FName&, UTexture* T) { StubBound = T; ++StubSets; } };
class USub01PCBridge : public UActorComponent {
public:  // stand-ins for the members of Sub01PCBridge.h the v22 code reads (same names and types), then the patched v22 declarations
 bool Private = true, LocalPrivacy = false, PrivacyDesired = false, ReadOnlyBrowser = false; uint64 Generation = 0; double ScreenAspect = 1.7;
 TObjectPtr<UMaterialInstanceDynamic> MonitorMaterial; TObjectPtr<UCanvasRenderTarget2D> TerminalCanvas;
 bool IsPublicState(const TSharedPtr<FJsonObject>& State) const;
@@PUBLIC@@
@@PRIVATE@@
};
@@ISPUBLIC@@
@@METHODS@@
'''
BRIDGE_DRIVER = r'''
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static TSharedPtr<FJsonObject> State(bool Privacy, const TCHAR* Mode, bool Connected, bool Available, const TCHAR* Kind = u"graphical", const TCHAR* Phase = u"connected") {  // a runner /pc/state
 TSharedPtr<FJsonObject> S = MakeShared<FJsonObject>(); S->StubBools[u"privacy"] = Privacy; if (Mode) S->StubStrings[u"pc_mode"] = FString(Mode);
 TSharedPtr<FJsonObject> V = MakeShared<FJsonObject>(); V->StubBools[u"connected"] = Connected; if (Phase) V->StubStrings[u"phase"] = FString(Phase); S->StubObjects[u"vagon"] = V;
 TSharedPtr<FJsonObject> D = MakeShared<FJsonObject>(); D->StubBools[u"available"] = Available; if (Kind) D->StubStrings[u"kind"] = FString(Kind); S->StubObjects[u"display"] = D; return S; }
int main() {
 UMaterialInstanceDynamic Mid; UCanvasRenderTarget2D Canvas; UTexture2D Graphical, Feed; USub01PCBridge B; B.MonitorMaterial = &Mid; B.TerminalCanvas = &Canvas;
 double& Now = FPlatformTime::StubNow; Now = 100;
 // closed until a public poll confirmed the connected Vagon desktop: the bridge's own picture
 B.ShowFrame(&Canvas); CHECK(Mid.StubBound == &Canvas && Mid.StubSets == 1, 1);
 B.ShowFrame(&Canvas); CHECK(Mid.StubSets == 1, 101);  // the same picture again: the MID is not touched (textures update in place)
 CHECK(!B.IsMonitorFeedAllowed(Now) && !B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Canvas && B.GetMonitorConfirmedAt() < 0, 2);
 CHECK(B.MonitorFeedGateReason(Now) == FString(u"PC private or backend unavailable"), 102);
 B.Private = false; B.NoteMonitorFeedSource(State(false, u"vagon", true, true), Now);  // the poll's second read (Private false as after ApplyTerminal)
 CHECK(B.IsMonitorFeedAllowed(Now + .2) && B.GetMonitorConfirmedAt() == 100 && B.MonitorFeedGateReason(Now) == FString(u"open"), 3);
 CHECK(B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Feed, 4);
 const int64 Sets = Mid.StubSets; CHECK(B.SetMonitorFeedFrame(&Feed) && Mid.StubSets == Sets, 5);  // renewing every tick touches nothing
 B.ShowFrame(&Graphical); CHECK(Mid.StubBound == &Feed && Mid.StubSets == Sets, 6);  // the bridge's own poll never takes the monitor back (no flicker)
 CHECK(!B.SetMonitorFeedFrame(nullptr) && Mid.StubBound == &Graphical, 7);  // no progress: the bridge's latest own picture
 auto Reopen = [&]() { B.Private = B.LocalPrivacy = B.PrivacyDesired = B.ReadOnlyBrowser = false; B.NoteMonitorFeedSource(State(false, u"vagon", true, true), Now); return B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Feed; };
 // every privacy flag closes it at once and the bridge's own picture comes back on the next renewal
 CHECK(Reopen(), 8); B.LocalPrivacy = true; CHECK(!B.IsMonitorFeedAllowed(Now) && !B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Graphical && B.MonitorFeedGateReason(Now) == FString(u"local privacy"), 9);
 CHECK(Reopen(), 10); B.PrivacyDesired = true; CHECK(!B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Graphical, 11);
 CHECK(Reopen(), 12); B.Private = true; CHECK(!B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Graphical, 13);
 CHECK(Reopen(), 14); B.ReadOnlyBrowser = true; CHECK(!B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Graphical && B.MonitorFeedGateReason(Now) == FString(u"read-only cinematic browser"), 15);
 CHECK(Reopen(), 16); B.ShowFrame(&Graphical); B.LocalPrivacy = true; B.ShowFrame(&Graphical); CHECK(Mid.StubBound == &Graphical, 17);  // the poll itself drops it too
 // a confirming read that is not the public, connected Vagon desktop with an available GRAPHICAL display closes it AT ONCE (no renewal needed)
 struct { bool Privacy; const TCHAR* Mode; bool Connected, Available; const TCHAR* Kind; } Closed[] = {{true, u"vagon", true, true, u"graphical"},
  {false, u"chromium", true, true, u"graphical"}, {false, nullptr, true, true, u"graphical"}, {false, u"vagon", false, true, u"graphical"}, {false, u"vagon", true, false, u"graphical"},
  {false, u"vagon", true, true, u"terminal"}, {false, u"vagon", true, true, nullptr}};
 int32 Case = 20; for (auto& C : Closed) { CHECK(Reopen(), Case); B.NoteMonitorFeedSource(State(C.Privacy, C.Mode, C.Connected, C.Available, C.Kind), Now);
  CHECK(Mid.StubBound == &Graphical && !B.IsMonitorFeedAllowed(Now) && B.GetMonitorConfirmedAt() < 0 && !B.SetMonitorFeedFrame(&Feed), Case + 1); Case += 2; }
 // the Vagon host page's login/dashboard can come with connected still true: the phase must be "connected" too (the sidecar's rule)
 for (const TCHAR* Phase : {u"connecting", u"login_required", u"dashboard"}) { CHECK(Reopen(), 37); B.NoteMonitorFeedSource(State(false, u"vagon", true, true, u"graphical", Phase), Now); CHECK(Mid.StubBound == &Graphical && !B.IsMonitorFeedAllowed(Now), 38); }
 CHECK(Reopen(), 39); B.NoteMonitorFeedSource(State(false, u"vagon", true, true, u"graphical", nullptr), Now); CHECK(Mid.StubBound == &Graphical && !B.IsMonitorFeedAllowed(Now), 35);
 CHECK(B.MonitorFeedGateReason(Now) == FString(u"source mismatch (not the public, connected Vagon desktop)"), 36);
 CHECK(Reopen(), 40); B.NoteMonitorFeedSource(nullptr, Now); CHECK(!B.IsMonitorFeedAllowed(Now) && Mid.StubBound == &Graphical, 41);  // backend unavailable
 CHECK(Reopen(), 42); B.LocalPrivacy = true; B.NoteMonitorFeedSource(State(false, u"vagon", true, true), Now); B.LocalPrivacy = false; CHECK(!B.IsMonitorFeedAllowed(Now), 43);  // not public: not confirmed
 // the confirming read must have STARTED less than @@CONFIRM@@ s ago; the poll timer's SelectMonitorFrame drops the feed even without a renewal
 Now = 200; CHECK(Reopen(), 44); const double T0 = Now;
 CHECK(B.IsMonitorFeedAllowed(T0 + @@CONFIRM@@ - .01) && !B.IsMonitorFeedAllowed(T0 + @@CONFIRM@@ + .01) && !B.IsMonitorFeedAllowed(T0 - .01), 45);
 Now = T0 + @@CONFIRM@@ + .01; CHECK(B.MonitorFeedGateReason(Now) == FString(u"no recent public confirmation"), 46);
 B.SelectMonitorFrame(); CHECK(Mid.StubBound == &Graphical, 47);  // a hung backend: the 0.5 s poll timer re-selects before it returns early
 // a feed the character stops renewing is dropped by the next selection even while the gate stays open
 Now = 300; CHECK(Reopen(), 48); Now += @@RENEW@@ + .05; B.NoteMonitorFeedSource(State(false, u"vagon", true, true), Now); CHECK(Mid.StubBound == &Graphical, 49);
 CHECK(B.SetMonitorFeedFrame(&Feed) && Mid.StubBound == &Feed, 50);  // renewed again: back
 CHECK(B.GetMonitorPrivacyGeneration() == 0 && B.GetMonitorScreenAspect() == 1.7 && B.GetMonitorTexturesCreated() == 0, 51);
 // EndPlay while the feed is bound: the MID itself leaves the feed's texture (the terminal canvas, or nothing without one) and nothing is held
 CHECK(Mid.StubBound == &Feed, 52); B.ReleaseMonitorFeed(); CHECK(Mid.StubBound == &Canvas && !B.FeedFrame && !B.BoundFrame && !B.OwnFrame && !B.IsMonitorFeedAllowed(Now), 53);
 CHECK(Reopen(), 54); B.TerminalCanvas = nullptr; B.ReleaseMonitorFeed(); CHECK(Mid.StubBound == nullptr && !B.FeedFrame && !B.BoundFrame, 55);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v22_pc_bridge_gate_runs(v22_patched, tmp_path):
    """The patched bridge's own v22 methods and IsPublicState, run against stand-ins for its other members: fail closed on every condition."""
    pc_h, pc_cpp = lf(v22_patched / 'Sub01PCBridge.h'), lf(v22_patched / 'Sub01PCBridge.cpp')
    for member in ('Private=true', 'LocalPrivacy=false', 'bool PrivacyDesired=false', 'ReadOnlyBrowser=false', 'uint64 Generation=0;', 'double ScreenAspect=1.7;',
                   'TObjectPtr<UMaterialInstanceDynamic> MonitorMaterial;', 'TObjectPtr<UCanvasRenderTarget2D> TerminalCanvas;'):
        assert member in pc_h, member  # the stand-ins mirror the real declarations
    public, at = _block(pc_h, ' // SUB01_STREAMER_VISUAL_V2_V22 BEGIN (tools', ' // SUB01_STREAMER_VISUAL_V2_V22 END\n')
    private, p_at = _block(pc_h, ' // SUB01_STREAMER_VISUAL_V2_V22 BEGIN (private)', '// SUB01_STREAMER_VISUAL_V2_V22 END (private)\n')
    ispublic, i_at = _function(pc_cpp, 'bool USub01PCBridge::IsPublicState(')
    methods, m_at = _block(pc_cpp, V22_MARKER + ' BEGIN', V22_MARKER + ' END')
    unit = BRIDGE_UNIT.replace('@@PUBLIC@@', f'#line {at} "{v22_patched / "Sub01PCBridge.h"}"\n{public}').replace(
        '@@PRIVATE@@', f'#line {p_at} "{v22_patched / "Sub01PCBridge.h"}"\n{private}').replace(
        '@@ISPUBLIC@@', f'#line {i_at} "{v22_patched / "Sub01PCBridge.cpp"}"\n{ispublic}').replace(
        '@@METHODS@@', f'#line {m_at} "{v22_patched / "Sub01PCBridge.cpp"}"\n{methods}')
    stub = tmp_path / 'stub'
    (stub / 'Engine').mkdir(parents=True)
    (stub / 'ue_stub.h').write_text(STUB)
    for name in ('CoreMinimal.h', 'RHI.h', 'Engine/Texture2D.h'):
        (stub / name).write_text('#pragma once\n#include "ue_stub.h"\n')
    shutil.copy(v22_patched / v22.NEW_HEADER, tmp_path / v22.NEW_HEADER)
    name, path, flags = COMPILERS[0]
    (tmp_path / 'bridge.cpp').write_text(unit)
    syntax = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{tmp_path}', '-isystem', str(stub), str(tmp_path / 'bridge.cpp')], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr[-6000:]
    driver = BRIDGE_DRIVER.replace('@@CONFIRM@@', repr(v22.CONFIRM_SECONDS)).replace('@@RENEW@@', repr(v22.RENEW_SECONDS))
    (tmp_path / 'driver.cpp').write_text(unit + driver)
    build = subprocess.run([path, '-std=c++20', '-O1', f'-I{tmp_path}', '-isystem', str(stub), str(tmp_path / 'driver.cpp'), '-o', str(tmp_path / 'driver')], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr[-6000:]
    run = subprocess.run([str(tmp_path / 'driver')], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


V22_PREFIX = CAM2_DRIVER[:CAM2_DRIVER.index('int main() {')] + r'''
#include <algorithm>
static std::vector<uint8> MakeJpeg(uint32 Serial, int32 W = 64, int32 H = 36, int32 Entropy = 300) {  // the stub decoder's format, a structurally real JPEG
 std::vector<uint8> J = {0xFF, 0xD8};
 auto Segment = [&J](uint8 Marker, std::vector<uint8> Body) { J.push_back(0xFF); J.push_back(Marker); const int32 L = int32(Body.size()) + 2; J.push_back(uint8(L >> 8)); J.push_back(uint8(L)); J.insert(J.end(), Body.begin(), Body.end()); };
 Segment(0xE0, {'J', 'F', 'I', 'F', 0, uint8(Serial), uint8(Serial >> 8), uint8(Serial >> 16), uint8(Serial >> 24), 0xFF, 0xD9, 0xFF, 0xD8, 0xFF});  // EOI and SOI bytes inside a segment
 J.push_back(0xFF);  // a fill byte before the next marker
 Segment(0xC0, {8, uint8(H >> 8), uint8(H), uint8(W >> 8), uint8(W), 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1});
 Segment(0xDA, {3, 1, 0, 2, 0x11, 3, 0x11, 0, 63, 0});
 for (int32 K = 0; K < Entropy; ++K) { J.push_back(uint8(K * 7 + int32(Serial))); if (J.back() == 0xFF) J.push_back(0x00); if (K == Entropy / 2) { J.push_back(0xFF); J.push_back(0xD3); } }  // stuffing, a restart marker
 J.push_back(0xFF); J.push_back(0xFF); J.push_back(0xD9);  // fill before EOI
 return J;
}
'''
SCAN_DRIVER = V22_PREFIX + r'''
static std::vector<uint8> Cat(std::initializer_list<std::vector<uint8>> Parts) { std::vector<uint8> Out; for (const auto& P : Parts) Out.insert(Out.end(), P.begin(), P.end()); return Out; }
static FSub01JpegScan Scan(const std::vector<uint8>& B, int64 Max = 1 << 22) { return Sub01ScanJpegs(B.data(), int64(B.size()), Max); }
int main() {
 const std::vector<uint8> A = MakeJpeg(1), B = MakeJpeg(2), C = MakeJpeg(3); const int64 a = int64(A.size()), b = int64(B.size());
 // one whole frame, its EOI found by walking (the FF D9 inside APP0 does not end it), the stuffing, the RST and the fill bytes skipped
 FSub01JpegScan S = Scan(A); CHECK(S.Frames == 1 && S.Start == 0 && S.End == a && S.Consumed == a && S.Resyncs == 0, 1);
 // two whole frames and half of a third: the newest whole one, the half kept
 const std::vector<uint8> Half(C.begin(), C.begin() + int64(C.size()) / 2);
 S = Scan(Cat({A, B, Half})); CHECK(S.Frames == 2 && S.Start == a && S.End == a + b && S.Consumed == a + b && S.Resyncs == 0, 2);
 // the half is finished by the next read: found then
 S = Scan(Cat({Half, std::vector<uint8>(C.begin() + int64(C.size()) / 2, C.end())})); CHECK(S.Frames == 1 && S.End == int64(C.size()), 3);
 // garbage first (with an FF D8 not followed by FF, and a stray FF D8 FF + a reserved marker): resynced on the real SOI
 std::vector<uint8> Junk(300, 0x5A); Junk[10] = 0xFF; Junk[11] = 0xD8; Junk[100] = 0xFF; Junk[101] = 0xD8; Junk[102] = 0xFF; Junk[103] = 0x5A;
 S = Scan(Cat({Junk, A})); CHECK(S.Frames == 1 && S.Start == 300 && S.End == 300 + a && S.Resyncs >= 1 && S.Skipped == 300, 4);
 // a frame cut in its entropy data, followed by a whole one: the SOI inside the cut frame resyncs, only the whole one is returned
 const std::vector<uint8> Cut(B.begin(), B.begin() + b - 60);
 S = Scan(Cat({Cut, C})); CHECK(S.Frames == 1 && S.Start == b - 60 && S.End == b - 60 + int64(C.size()) && S.Resyncs >= 1, 5);
 // a possibly split SOI at the end is kept; plain garbage is consumed
 S = Scan(Cat({A, {0x11, 0xFF}})); CHECK(S.Frames == 1 && S.Consumed == a + 1, 6);
 S = Scan(Cat({A, {0x11, 0xFF, 0xD8}})); CHECK(S.Frames == 1 && S.Consumed == a + 1, 7);
 S = Scan(std::vector<uint8>(100, 0x22)); CHECK(S.Frames == 0 && S.Consumed == 100 && S.Resyncs == 1, 8);
 S = Scan(std::vector<uint8>()); CHECK(S.Frames == 0 && S.Consumed == 0 && S.Start < 0, 9);
 // a frame over the size limit is garbage (resync), the next one is found; an unfinished frame within the limit waits
 S = Scan(Cat({MakeJpeg(4, 64, 36, 2000), A}), 1000); CHECK(S.Frames == 1 && S.End == int64(MakeJpeg(4, 64, 36, 2000).size()) + a && S.Resyncs >= 1, 10);
 S = Scan(Half, 1000); CHECK(S.Frames == 0 && S.Consumed == 0, 11);
 // an unfinished frame longer than the limit is dropped instead of waiting forever
 { const std::vector<uint8> Long = MakeJpeg(5, 64, 36, 3000); S = Scan(std::vector<uint8>(Long.begin(), Long.begin() + 2500), 1000); CHECK(S.Frames == 0 && S.Consumed >= 2000, 12); }
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v22_jpeg_scan_resyncs_and_keeps_the_newest_frame(v22_patched, tmp_path):
    units = build_units_v22(v22_patched, tmp_path / 'u', driver=SCAN_DRIVER)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


FEED_DRIVER = V22_PREFIX + r'''
static int Writer = -1; static int64 TickNo = 0; static bool Confirming = true;
static bool Put(const std::vector<uint8>& B, std::size_t From = 0, std::size_t To = std::size_t(-1)) {
 To = std::min(To, B.size()); for (std::size_t Done = From; Done < To;) { const ssize_t N = write(Writer, B.data() + Done, To - Done); if (N <= 0) return false; Done += std::size_t(N); } return true; }
static int32 ShownSerial(ASub01HomeCharacter& C) {  // the serial (low byte) in the texture at source pixel (5,7) through the bridge's layout; -2 = blank/other
 UTexture2D* T = C.StreamerVisualMonitorTexture.Get(); if (!T) return -1;
 const uint8* P = T->StubPixel((T->GetSizeX() - 64) / 2 + 5, (T->GetSizeY() - 36) / 2 + 7); return P[1] == 5 && P[2] == 7 && P[3] == 255 ? P[0] : -2; }
// game ticks at 60 Hz; the PC bridge's poll confirms the connected desktop every 0.5 s (its second read's start time); then the render thread and the tasks
static void Run(ASub01HomeCharacter& C, USub01PCBridge& B, int N, bool Render = true, bool Tasks = true) {
 for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += 1 / 60.; if (++TickNo % 30 == 0 && Confirming) B.StubConfirmedAt = FPlatformTime::StubNow;
  C.ApplyStreamerVisualV2(FPlatformTime::StubNow, 1 / 60.f); if (Render) StubRender::Flush(); if (Tasks) StubAsync::Flush(); } }
static double RunUntil(ASub01HomeCharacter& C, USub01PCBridge& B, uint32 Serial, int Max = 240) {  // -> seconds until shown, or -1
 const double T0 = FPlatformTime::StubNow; for (int K = 0; K < Max; ++K) { Run(C, B, 1); if (ShownSerial(C) == int32(uint8(Serial))) return FPlatformTime::StubNow - T0; } return -1; }
int main() {
 signal(SIGPIPE, SIG_IGN);
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; USub01PCBridge Bridge; ASub01HomeCharacter C;
 C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim; C.PCBridge = &Bridge; Bridge.StubAspect = 2.0;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65;
 C.StreamerVisualCam2Dir = u"@@DIR@@"; FPlatformTime::StubNow = 1000; StubRender::Deferred = StubAsync::Deferred = true;
 CHECK(mkfifo("@@DIR@@/monitor.mjpeg", 0600) == 0, 1);
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true; C.StreamerVisualCam2On = 0;
 FSub01MonitorFeed& Feed = *C.StreamerVisualMonitorFeed; CHECK(Feed.FifoPath == FString(u"@@DIR@@/monitor.mjpeg") && Feed.Images, 2);
 CHECK(Near(C.StreamerVisualMonitorDelaySeconds, @@DELAY@@, 1e-6) && Near(C.StreamerVisualMonitorStaleSeconds, @@STALE@@, 1e-6), 200);
 // 1. the reader opens the sidecar's FIFO (no writer yet), so the sidecar can connect; nothing is bound while the gate is closed
 Run(C, Bridge, 3); CHECK(Feed.Open.load() && Feed.Fd >= 0 && !C.StreamerVisualMonitorFeedBound && Bridge.StubFeed == nullptr, 3);
 Writer = open("@@DIR@@/monitor.mjpeg", O_WRONLY | O_NONBLOCK); CHECK(Writer >= 0, 4);
 // 2. gate closed: the bytes are read and discarded, nothing queued or decoded, no texture
 CHECK(Put(MakeJpeg(1)) && Put(MakeJpeg(2)), 5); Run(C, Bridge, 3);
 CHECK(Feed.Discarded.load() > 0 && Feed.Queued.load() == 0 && Feed.Decoded.load() == 0 && IImageWrapper::StubDecodes == 0 && Bridge.StubFeed == nullptr && UTexture2D::StubCreated == 0, 6);
 CHECK(C.StreamerVisualMonitorFeedGateReason == FString(u"not started") || C.StreamerVisualMonitorFeedGateReason == FString(u"stub closed"), 201);
 // 3. the gate opens: what arrives during the @@GUARD@@ s quarantine is discarded too (frames the pipe and ffmpeg held from before)
 Bridge.StubFeedAllowed = true; Run(C, Bridge, 1); CHECK(C.StreamerVisualMonitorFeedGateReason == FString(u"open"), 202);
 CHECK(Put(MakeJpeg(3)), 7); Run(C, Bridge, 6); CHECK(Feed.Queued.load() == 0 && Feed.Decoded.load() == 0 && Bridge.StubFeed == nullptr, 8);
 Run(C, Bridge, 12);
 // 4. three frames in one read: only the newest is queued; it plays out no sooner than the delay and once a later confirmation completed, into ONE
 //    texture laid out like the bridge's (aspect 2: 72x36, 4 px black sides)
 const int64 Older0 = Feed.DroppedOlder.load(); CHECK(Put(MakeJpeg(10)) && Put(MakeJpeg(11)) && Put(MakeJpeg(12)), 9); Run(C, Bridge, 1);
 CHECK(Feed.Queued.load() == 1 && Feed.DroppedOlder.load() - Older0 == 2, 10);
 Run(C, Bridge, 30); CHECK(Feed.Decoded.load() == 0 && ShownSerial(C) == -1, 11);  // 0.5 s: still waiting for its playout
 const double Shown12 = RunUntil(C, Bridge, 12); UTexture2D* Tex = C.StreamerVisualMonitorTexture.Get();
 CHECK(Shown12 > 0 && Shown12 + 31 / 60. >= @@DELAY@@ && Shown12 + 31 / 60. < @@DELAY@@ + .6 && Feed.Decoded.load() == 1 && IImageWrapper::StubDecodes == 1 && Bridge.StubFeed == Tex && C.StreamerVisualMonitorFeedBound, 12);
 CHECK(Tex && UTexture2D::StubCreated == 1 && Tex->GetSizeX() == 72 && Tex->GetSizeY() == 36 && Tex->SRGB && Tex->NeverStream && Tex->StubPixel(0, 0)[3] == 255 && Tex->StubPixel(0, 0)[0] == 0 && Tex->StubPixel(71, 35)[0] == 0, 13);
 // 5. one frame per tick for a second: played out one per tick after the delay, still ONE texture, every upload's heap copy freed
 const int64 Shown0 = C.StreamerVisualMonitorFeedShown;
 for (uint32 K = 0; K < 60; ++K) { CHECK(Put(MakeJpeg(100 + K)), 14); Run(C, Bridge, 1); }
 CHECK(RunUntil(C, Bridge, 159) > 0 && C.StreamerVisualMonitorFeedShown - Shown0 >= 50, 15);
 CHECK(UTexture2D::StubCreated == 1 && C.StreamerVisualMonitorTexture.Get() == Tex && C.StreamerVisualMonitorTexturesCreated == 1 && UTexture2D::StubUpdates == UTexture2D::StubCleanups
       && Sub01PersistentTexture::PendingUploads().load() == 0, 16);
 // 6. at most one pump (read + one decode) in flight: while it has not run, the game thread launches no second one
 for (int K = 0; K < 6; ++K) Run(C, Bridge, 1, true, false);
 CHECK(StubAsync::Queue.size() == 1 && Feed.Busy.load() == 1, 17); StubAsync::Flush(); CHECK(Feed.Busy.load() == 0, 18);
 // 7. resync: garbage, a frame cut short (its tail never comes), then a whole one: the whole one is shown, nothing failed to decode
 { std::vector<uint8> Junk(500, 0x5A); Junk[100] = 0xFF; Junk[101] = 0xD8; Junk[200] = 0xFF; Junk[201] = 0xD8; Junk[202] = 0xFF; const std::vector<uint8> Cut = MakeJpeg(200); const int64 R0 = Feed.Resyncs.load();
   CHECK(Put(Junk) && Put(Cut, 0, Cut.size() - 80) && Put(MakeJpeg(201)), 19); CHECK(RunUntil(C, Bridge, 201) > 0 && Feed.Resyncs.load() > R0 && Feed.DecodeFailed.load() == 0, 20); }
 // 8. a frame split across reads: shown once whole
 { const std::vector<uint8> J = MakeJpeg(202); CHECK(Put(J, 0, 50), 21); Run(C, Bridge, 60); CHECK(ShownSerial(C) == 201 && Feed.Queued.load() == 0, 22); CHECK(Put(J, 50), 23); CHECK(RunUntil(C, Bridge, 202) > 0, 24); }
 // 9. the bridge's privacy generation changes while a decoded frame waits: a new epoch, that frame is never uploaded, the bridge's picture meanwhile
 { CHECK(Put(MakeJpeg(203)), 25); for (int K = 0; K < 240 && !Feed.Ready.load(); ++K) { Run(C, Bridge, 1, true, false); StubAsync::Flush(); }
   CHECK(Feed.Ready.load() != nullptr, 26); ++Bridge.StubGeneration; const int64 Rejected0 = C.StreamerVisualMonitorFeedRejected; Run(C, Bridge, 1);
   CHECK(C.StreamerVisualMonitorFeedRejected == Rejected0 + 1 && Bridge.StubFeed == nullptr && ShownSerial(C) == -2, 27); }  // and the texture blanked
 // 10. the gate closes: unbound at once, blanked; what was written while closed is never shown, not even after it reopens
 Run(C, Bridge, 20); CHECK(Put(MakeJpeg(204)), 28); CHECK(RunUntil(C, Bridge, 204) > 0 && Bridge.StubFeed == Tex, 29);
 Bridge.StubFeedAllowed = false; Run(C, Bridge, 1); CHECK(Bridge.StubFeed == nullptr && !C.StreamerVisualMonitorFeedBound && ShownSerial(C) == -2, 30);
 CHECK(Put(MakeJpeg(205)), 31); Run(C, Bridge, 3); Bridge.StubFeedAllowed = true; Run(C, Bridge, 90);
 CHECK(ShownSerial(C) == -2 && Bridge.StubFeed == nullptr && Feed.Decoded.load() > 0, 32);
 CHECK(Put(MakeJpeg(206)), 33); CHECK(RunUntil(C, Bridge, 206) > 0 && Bridge.StubFeed == Tex, 34);
 // 11. a dead feed: no new upload for monitor_stale_s -> the bridge's own picture (counted once) and a blank texture; back with the next frame
 const int64 Stale0 = C.StreamerVisualMonitorFeedStale; Run(C, Bridge, int(@@STALE@@ * 60) - 6); CHECK(Bridge.StubFeed == Tex && ShownSerial(C) == 206, 35);
 Run(C, Bridge, 12); CHECK(Bridge.StubFeed == nullptr && C.StreamerVisualMonitorFeedStale == Stale0 + 1 && !C.StreamerVisualMonitorFeedBound && ShownSerial(C) == -2, 36);
 CHECK(Put(MakeJpeg(207)), 37); CHECK(RunUntil(C, Bridge, 207) > 0 && Bridge.StubFeed == Tex, 38);
 // 12. confirm-after: without a confirmation that started after a frame was read, the frame never plays out (a locked runner the game has not noticed)
 Confirming = false; CHECK(Put(MakeJpeg(220)), 39); Run(C, Bridge, 150); CHECK(ShownSerial(C) != 220 && Feed.Queued.load() == 1, 40);
 Confirming = true; CHECK(RunUntil(C, Bridge, 220) > 0, 41);
 // 13. the playout ring is bounded: without confirmations frames pile up to @@RING@@, the oldest dropped; the newest plays out afterwards
 Confirming = false; const int64 Overflow0 = Feed.DroppedOverflow.load(); for (uint32 K = 0; K < 70; ++K) { CHECK(Put(MakeJpeg(K)), 42); Run(C, Bridge, 1); }
 CHECK(Feed.Queued.load() == @@RING@@ && Feed.DroppedOverflow.load() - Overflow0 == 70 - @@RING@@, 43);
 Confirming = true; CHECK(RunUntil(C, Bridge, 69) > 0 && Feed.Queued.load() == 0, 44);
 // 14. a stalled render thread: at most @@PENDING@@ uploads wait for the RHI, newer frames are dropped (counted), nothing piles up
 { const int64 Busy0 = C.StreamerVisualMonitorFeedUploadBusy; for (uint32 K = 0; K < 90; ++K) { CHECK(Put(MakeJpeg(150 + K)), 45); Run(C, Bridge, 1, false, true); }
   CHECK(Sub01PersistentTexture::PendingUploads().load() <= @@PENDING@@ && C.StreamerVisualMonitorFeedUploadBusy - Busy0 >= 20, 46);
   StubRender::Flush(); CHECK(Sub01PersistentTexture::PendingUploads().load() == 0 && UTexture2D::StubUpdates == UTexture2D::StubCleanups, 47); CHECK(RunUntil(C, Bridge, 239) > 0, 48); }
 // 15. monitor_fps 30: a pump every other tick; 60: every tick
 int64 L0 = StubAsync::Launched; C.StreamerVisualMonitorFps = 30; Run(C, Bridge, 60); CHECK(StubAsync::Launched - L0 >= 29 && StubAsync::Launched - L0 <= 31, 49);
 L0 = StubAsync::Launched; C.StreamerVisualMonitorFps = 60; Run(C, Bridge, 60); CHECK(StubAsync::Launched - L0 >= 59, 50);
 // 16. monitor_feed 0: unbound and the FIFO closed (no reader: the sidecar stops ffmpeg), no pumps; 1 reopens it
 C.StreamerVisualMonitorFeedOn = 0; Run(C, Bridge, 3); CHECK(!Feed.Open.load() && Feed.Fd < 0 && Bridge.StubFeed == nullptr, 51);
 close(Writer); errno = 0; CHECK(open("@@DIR@@/monitor.mjpeg", O_WRONLY | O_NONBLOCK) < 0 && errno == ENXIO, 52);
 L0 = StubAsync::Launched; Run(C, Bridge, 30); CHECK(StubAsync::Launched == L0, 53);
 C.StreamerVisualMonitorFeedOn = 1; FPlatformTime::StubNow += 1.1; Run(C, Bridge, 3); CHECK(Feed.Open.load(), 54);
 Writer = open("@@DIR@@/monitor.mjpeg", O_WRONLY | O_NONBLOCK); CHECK(Writer >= 0, 55); Run(C, Bridge, 20);
 CHECK(Put(MakeJpeg(250)), 56); CHECK(RunUntil(C, Bridge, 250) > 0 && Bridge.StubFeed == Tex, 57);
 // 17. a writer that leaves mid-frame (the sidecar crashed) and a new one: the cut frame never shows, the next whole one does
 { const std::vector<uint8> J = MakeJpeg(251); CHECK(Put(J, 0, J.size() - 100), 58); close(Writer); Run(C, Bridge, 2); Writer = open("@@DIR@@/monitor.mjpeg", O_WRONLY | O_NONBLOCK);
   CHECK(Writer >= 0 && Put(MakeJpeg(252)), 59); CHECK(RunUntil(C, Bridge, 252) > 0 && Feed.DecodeFailed.load() == 0 && IImageWrapper::StubRefused == 0, 60); }
 // 18. the log window ran (many seconds of ticks) and the texture is still the one created at the first frame
 CHECK(C.StreamerVisualMonitorFeedWindowAt > 1005 && C.StreamerVisualMonitorFeedFpsShown >= 0 && UTexture2D::StubCreated == 1, 61);
 // 19. a path that is not this user's private FIFO is never opened: a regular file, a group-readable FIFO
 for (const TCHAR* Dir : {u"@@DIR2@@", u"@@DIR3@@"}) { ASub01HomeCharacter D; D.FirstPersonBody = &Body; D.ViewCamera = &Camera; D.PCBridge = &Bridge; D.StreamerVisualCam2Dir = Dir;
  D.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); D.StreamerVisualSchemaVersion = 2; D.StreamerVisualDeskPropsScanned = true; D.StreamerVisualCam2On = 0; Run(D, Bridge, 3);
  CHECK(!D.StreamerVisualMonitorFeed->Open.load() && D.StreamerVisualMonitorFeed->Fd < 0 && D.StreamerVisualMonitorFeed->Refused.load() == 1, 62); }
 close(Writer);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v22_monitor_feed_logic_runs(v22_patched, tmp_path):
    """Runs the patched reader against a real FIFO: privacy gate and quarantine, newest frame only, the playout delay and confirm-after rule, one pump
    in flight, one texture, resync, the bounded ring, the pending-upload cap, the no-progress fallback (blanked), monitor_fps and monitor_feed,
    a foreign path never opened."""
    dirs = {name: tmp_path / name for name in ('stream', 'foreign', 'shared')}
    for path in dirs.values():
        path.mkdir()
    (dirs['foreign'] / 'monitor.mjpeg').write_bytes(b'not a fifo')
    os.mkfifo(dirs['shared'] / 'monitor.mjpeg')
    os.chmod(dirs['shared'] / 'monitor.mjpeg', 0o640)
    driver = (FEED_DRIVER.replace('@@DIR@@', str(dirs['stream'])).replace('@@DIR2@@', str(dirs['foreign'])).replace('@@DIR3@@', str(dirs['shared']))
              .replace('@@STALE@@', repr(v22.STALE_SECONDS)).replace('@@DELAY@@', repr(v22.PLAYOUT_SECONDS)).replace('@@GUARD@@', repr(v22.GUARD_SECONDS))
              .replace('@@RING@@', str(v22.RING_FRAMES)).replace('@@PENDING@@', str(v22.MAX_PENDING_UPLOADS)))
    units = build_units_v22(v22_patched, tmp_path / 'u', driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    assert (dirs['foreign'] / 'monitor.mjpeg').read_bytes() == b'not a fifo'


EXPOSURE_DRIVER = V22_PREFIX + r'''
int main() {
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
 Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
 Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65; Camera.PostProcessBlendWeight = .6f;
 FPostProcessSettings& Web = Camera.PostProcessSettings; Web.bOverride_AutoExposureBias = 1; Web.AutoExposureBias = .5f; Web.bOverride_AutoExposureMinBrightness = 1; Web.AutoExposureMinBrightness = -3;
 Web.bOverride_AutoExposureMethod = 1; Web.AutoExposureMethod = AEM_Manual;  // a copied manual method: mode 1 must still be automatic
 C.StreamerVisualCam2Dir = u"@@DIR@@"; FPlatformTime::StubNow = 1000; StubRender::Deferred = StubAsync::Deferred = true;
 C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true;
 USceneCaptureComponent2D* Cap = C.StreamerVisualCam2.Get(); FPostProcessSettings& P = Cap->PostProcessSettings;
 CHECK(P.bOverride_AutoExposureBias && P.AutoExposureBias == .5f && Near(Cap->PostProcessBlendWeight, .6, 1e-6), 1);  // v21 copied the webcam's settings at start
 // the default (mode @@MODE@@): histogram auto exposure (forced) with the bias @@BIAS@@ at full weight; the house volume's EV100 range is not overridden (min > max)
 Ticks(C, 1, 1 / 60.);
 CHECK(P.bOverride_AutoExposureBias && Near(P.AutoExposureBias, @@BIAS@@, 1e-6) && Near(Cap->PostProcessBlendWeight, 1, 1e-9) && P.bOverride_AutoExposureMethod && P.AutoExposureMethod.GetValue() == AEM_Histogram && !P.bOverride_AutoExposureMaxBrightness
       && P.bOverride_AutoExposureMinBrightness && P.AutoExposureMinBrightness == -3 && !P.bOverride_AutoExposureApplyPhysicalCameraExposure, 2);
 CHECK(Web.AutoExposureBias == .5f && Web.bOverride_AutoExposureBias && Near(Camera.PostProcessBlendWeight, .6, 1e-6) && Web.AutoExposureMethod.GetValue() == AEM_Manual, 3);  // the main camera untouched
 // an EV100 range (mode 1, min <= max)
 C.StreamerVisualCam2EvMin = -1; C.StreamerVisualCam2EvMax = 2; Ticks(C, 1, 1 / 60.);
 CHECK(P.bOverride_AutoExposureMinBrightness && P.bOverride_AutoExposureMaxBrightness && Near(P.AutoExposureMinBrightness, -1, 1e-6) && Near(P.AutoExposureMaxBrightness, 2, 1e-6), 4);
 // manual: AEM_Manual, physical camera exposure off, fixed at the bias; no range
 C.StreamerVisualCam2Exposure = 2; C.StreamerVisualCam2EvBias = 2.5f; Ticks(C, 1, 1 / 60.);
 CHECK(P.bOverride_AutoExposureMethod && P.AutoExposureMethod.GetValue() == AEM_Manual && P.bOverride_AutoExposureApplyPhysicalCameraExposure && !P.AutoExposureApplyPhysicalCameraExposure
       && Near(P.AutoExposureBias, 2.5, 1e-6) && Near(P.AutoExposureMinBrightness, -3, 1e-6) && !P.bOverride_AutoExposureMaxBrightness && Near(Cap->PostProcessBlendWeight, 1, 1e-9), 5);
 // 0: exactly what cam2 copied from the webcam
 C.StreamerVisualCam2Exposure = 0; Ticks(C, 1, 1 / 60.);
 CHECK(P.bOverride_AutoExposureBias && P.AutoExposureBias == .5f && P.bOverride_AutoExposureMethod && P.AutoExposureMethod.GetValue() == AEM_Manual && !P.bOverride_AutoExposureApplyPhysicalCameraExposure
       && P.AutoExposureApplyPhysicalCameraExposure && P.bOverride_AutoExposureMinBrightness && P.AutoExposureMinBrightness == -3 && !P.bOverride_AutoExposureMaxBrightness && Near(Cap->PostProcessBlendWeight, .6, 1e-6), 6);
 // applied on change only (a later tuning change re-applies everything)
 P.AutoExposureBias = 9; Ticks(C, 5, 1 / 60.); CHECK(P.AutoExposureBias == 9, 7);
 C.StreamerVisualCam2Exposure = 1; Ticks(C, 1, 1 / 60.); CHECK(Near(P.AutoExposureBias, 2.5, 1e-6) && Near(P.AutoExposureMinBrightness, -1, 1e-6), 8);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v22_cam2_exposure_runs(v22_patched, tmp_path):
    (tmp_path / 'cam2').mkdir()
    driver = (EXPOSURE_DRIVER.replace('@@DIR@@', str(tmp_path / 'cam2')).replace('@@BIAS@@', repr(v22.CAM2_EV_BIAS)).replace('@@MODE@@', str(v22.CAM2_EXPOSURE)))
    assert v22.CAM2_EXPOSURE == 1 and v22.CAM2_EV_MIN > v22.CAM2_EV_MAX  # the default: auto + bias, the volume's range kept
    units = build_units_v22(v22_patched, tmp_path / 'u', driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_earlier_behaviour_unchanged_under_v22(v22_patched, tmp_path):
    """The v2 driver and the v21 driver (cam2 reader gate, lite capture, key light, perf, console) still pass on the v22 stack."""
    run = _run_driver(build_units_v22(v22_patched, tmp_path / 'v2'), tmp_path / 'v2')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    (tmp_path / 'stream').mkdir()
    driver = (V21_DRIVER.replace('@@DIR@@', str(tmp_path / 'stream')).replace('@@VIEW@@', repr(v21.CAM2_VIEW_CM)).replace('@@LOD@@', repr(v21.CAM2_LOD_FACTOR))
              .replace('@@CD@@', repr(v21.KEY_CD)).replace('@@RADIUS@@', repr(v21.KEY_RADIUS_CM)).replace('@@SOFT@@', repr(v21.KEY_SOFT_CM))
              .replace('@@OUTER@@', repr(v21.KEY_CONES[1])).replace('@@MAXCHARS@@', str(v21.CONSOLE_MAX_CHARS)))
    run = _run_driver(build_units_v22(v22_patched, tmp_path / 'v21', driver=driver), tmp_path / 'v21')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


def test_v22_new_locals_do_not_shadow_members(v22_patched, v21_stack):
    members = _header_members(lf(v22_patched / 'Sub01HomeLab.h'))
    added = _added_locals(lf(v21_stack / 'Sub01HomeLab.cpp'), lf(v22_patched / 'Sub01HomeLab.cpp'))
    assert {'Gate', 'Accept', 'Fresh', 'Bound', 'Mode', 'Range'} <= added
    assert not (added & members), sorted(added & members)
    header = lf(v22_patched / 'Sub01HomeLab.h')
    declared = _header_members(header[header.index(V22_MARKER + ' BEGIN'):header.index(V22_MARKER + ' END')])
    assert declared and not (declared & _header_members(lf(v21_stack / 'Sub01HomeLab.h')))
    bridge_members = _header_members(lf(v22_patched / 'Sub01PCBridge.h'))
    bridge_added = _added_locals(lf(v21_stack / 'Sub01PCBridge.cpp'), lf(v22_patched / 'Sub01PCBridge.cpp'))
    assert {'Connected', 'Available', 'AskedAt'} <= bridge_added and not (bridge_added & bridge_members), sorted(bridge_added & bridge_members)
    assert not ({'Mode', 'Vagon', 'Screen', 'Own', 'Now'} & bridge_members)  # FString/pointer locals the type heuristic does not see
    pc_h = lf(v22_patched / 'Sub01PCBridge.h')
    v22_declared = _header_members(pc_h[pc_h.index(V22_MARKER + ' BEGIN (private)'):pc_h.index(V22_MARKER + ' END (private)')])
    assert v22_declared and not (v22_declared & _header_members(lf(v21_stack / 'Sub01PCBridge.h')))
    dev_members = _header_members(lf(v22_patched / 'Sub01HomeDeviceBridge.h'))
    dev_added = _added_locals(lf(v21_stack / 'Sub01HomeDeviceBridge.cpp'), lf(v22_patched / 'Sub01HomeDeviceBridge.cpp'))
    assert not (dev_added & dev_members) and not ({'Decoded', 'BGRA', 'Texture'} & dev_members), sorted(dev_added & dev_members)
    assert 'PersistentImages' not in lf(v21_stack / 'Sub01HomeDeviceBridge.h') and 'PersistentImagesCreated' in dev_members


# ================================================================================================ v23 (live look corrections)
V23_INSTALL = ROOT / 'tools/native_streamer_visual_v2/install_v23.py'
V23_MARKER = '// SUB01_STREAMER_VISUAL_V2_V23'
_V23_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_v23', V23_INSTALL)
v23 = importlib.util.module_from_spec(_V23_SPEC)
_V23_SPEC.loader.exec_module(v23)
V23_EDITED = ('Sub01HomeLab.cpp', 'Sub01HomeLab.h', 'Sub01HomeHands.cpp', 'Sub01HomeHands.h')


def install_v23(source: Path, *extra) -> tuple:
    run = subprocess.run([sys.executable, '-I', str(V23_INSTALL), '--source', str(source), *extra], capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout)


def _stack_to_v22(target: Path) -> None:
    _stack_to_v21(target)
    assert install_v22(target)[0] == 0


@pytest.fixture(scope='module')
def v23_patched(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp('v23') / 'src'
    _stack_to_v22(target)
    code, report = install_v23(target)
    assert code == 0, report
    return target


def test_v23_plans_applies_refuses_twice_and_needs_v22(tmp_path):
    target = tmp_path / 'src'
    _stack_to_v21(target)
    before = {p.name: sha(p) for p in target.iterdir()}
    code, refused = install_v23(target)
    assert code == 2 and 'lacks v22' in refused['reason'] and {p.name: sha(p) for p in target.iterdir()} == before
    assert install_v22(target)[0] == 0
    before = {p.name: sha(p) for p in target.iterdir()}
    code, planned = install_v23(target, '--dry-run')
    assert code == 0 and planned['status'] == 'planned' and len(planned['edits']) == len(v23.EDITS) and all(e['count'] == 1 for e in planned['edits'])
    assert {p.name: sha(p) for p in target.iterdir()} == before
    code, report = install_v23(target)
    assert code == 0 and report['status'] == 'applied'
    # only the character and the anim proxy files: never v22's bridges (PC bridge, device bridge), Build.cs or the ini
    assert {name for name in before if sha(target / name) != before[name]} == set(V23_EDITED)
    assert set(report['untouched']) == {'Sub01PCBridge.h', 'Sub01PCBridge.cpp', 'Sub01HomeDeviceBridge.h', 'Sub01HomeDeviceBridge.cpp', 'Sub01PersistentTexture.h'}
    for name in V23_EDITED:
        assert sha(target / name) == report['files'][name]['after_sha256'] == planned['files'][name]['after_sha256']
    after = {p.name: sha(p) for p in target.iterdir()}
    for extra in ((), ('--dry-run',)):
        code, again = install_v23(target, *extra)
        assert code == 2 and 'already' in again['reason']
    assert {p.name: sha(p) for p in target.iterdir()} == after


def test_v23_missing_anchor_refuses_without_writing(tmp_path):
    target = tmp_path / 'src'
    _stack_to_v22(target)
    hands = target / 'Sub01HomeHands.cpp'
    hands.write_bytes(hands.read_bytes().replace(b'static const double Weights[2]={0.4,0.6};', b'static const double Weights[2]={0.45,0.55};', 1))
    before = {p.name: sha(p) for p in target.iterdir()}
    code, report = install_v23(target)
    assert code == 2 and 'anchor missing in Sub01HomeHands.cpp' in report['reason']
    assert {p.name: sha(p) for p in target.iterdir()} == before  # Sub01HomeLab.* had valid anchors and are untouched too


def test_v23_keys_defaults_and_ranges():
    """The key table: unique keys and fields, every default inside its range, the defaults that switch a step off."""
    keys = [key for key, *_ in v23.TUNING]
    assert len(keys) == len(set(keys)) == len(v23.TUNING_FIELDS) and len(set(v23.TUNING_FIELDS.values())) == len(keys)
    off = {'pelvis_pitch_deg': 0, 'shoulder_drop_deg': 0, 'shoulder_back_deg': 0, 'neck_back_deg': 0, 'neck_share': 0.4, 'neck_girth': 1, 'elbow_min_deg': 0,
           'elbow_pole_back': 0.5, 'elbow_pole_out': 0.3, 'hand_orient': 0, 'finger_bend_deg': 0, 'mouse_scan': 0, 'hand_on_mouse': 0, 'key_side_cm': 0,
           'key_up_extra_cm': 0, 'key_specular': 1, 'fill_cd': 0, 'rim_cd': 0, 'chair_scale': 1, 'chair_back_extra_cm': 0, 'chair_side_cm': 0}
    for key, value in off.items():
        assert v23.DEFAULTS[key] == value, key  # today's look: the step is skipped
    assert (v23.DEFAULTS['elbow_pole_back'], v23.DEFAULTS['elbow_pole_out']) == streampass.ELBOW_POLE_VECTOR[1:] and v23.DEFAULTS['neck_share'] == posefix.HEAD_WEIGHTS[0]
    existing = (set(getattr(seatfix, 'TUNING_LIMITS', ())) | set(getattr(cam2, 'TUNING_LIMITS', ())) | set(streampass.TUNING_LIMITS) | set(posefix.TUNING_LIMITS)
                | set(v21.TUNING_LIMITS) | {'up_cm', 'forward_cm', 'side_cm', 'aim_drop_cm', 'fov_deg', 'seat_back_cm', 'seat_side_cm', 'desk_props', 'posture_lean_deg', 'posture_head_deg'})
    assert not existing & set(keys), sorted(existing & set(keys))
    for key, (lo, hi) in v23.TUNING_LIMITS.items():
        assert lo < hi and lo <= v23.DEFAULTS[key] <= hi, key
    # the live session: ordered steps; every value inside its key's clamp (v23's own keys or an earlier layer's)
    limits = {**streampass.TUNING_LIMITS, **posefix.TUNING_LIMITS, **v21.TUNING_LIMITS, **v23.TUNING_LIMITS}
    assert v23.RECOMMENDED[0] == ('baseline', {}) and len(v23.RECOMMENDED) >= 8
    for step, values in v23.RECOMMENDED:
        for key, value in values.items():
            lo, hi = limits[key]
            assert lo <= value <= hi, (step, key)


def test_v23_text(v23_patched, v22_patched):
    texts = {name: lf(v23_patched / name) for name in V23_EDITED}
    for name, text in texts.items():
        assert text.count(V23_MARKER + ' BEGIN') == text.count(V23_MARKER + ' END') == 1, name
        assert closure.brace_walk(closure.strip(text)) is not None, name
    cpp, header, proxy, hands_h = (texts[n] for n in V23_EDITED)
    v21_cpp, v21_hands = lf(v22_patched / 'Sub01HomeLab.cpp'), lf(v22_patched / 'Sub01HomeHands.cpp')  # the base: v21 + v22
    for text in (cpp, header):  # inside the region the stub harness compiles
        assert text.index(V23_MARKER + ' BEGIN') < text.index(FACE_END)
    # keys parsed: ONE delimited block right after the Field lambda, each key once with its clamp; every older tuning line kept verbatim
    tuning = cpp[cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):cpp.index(SEATFIX_MARKER + ' END')]
    old_tuning = v21_cpp[v21_cpp.index('bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){'):v21_cpp.index(SEATFIX_MARKER + ' END')]
    block = tuning[tuning.index(V23_MARKER + ' TUNING ('):tuning.index(V23_MARKER + ' TUNING END')]
    assert tuning.index(v23.TUNING_LAMBDA.strip()) < tuning.index(V23_MARKER + ' TUNING (')
    for key, field, lo, hi, default in v23.TUNING:
        assert f'Field(TEXT("{key}"),{field},{lo},{hi});' in block and tuning.count(f'TEXT("{key}")') == 1, key
        assert f'{field}={streampass._f(default)}' in header, key  # compiled default = today's look
        assert f'TEXT("v23_{key}")' in cpp, key  # receipt
    reader, old_reader = (_function(text, 'bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){')[0] for text in (cpp, v21_cpp))
    added = [line for line in reader.split('\n') if line not in old_reader.split('\n')]
    assert all('Field(TEXT("' in line and 'StreamerVisualV23' in line or V23_MARKER in line for line in added), added
    assert set(old_reader.split('\n')) <= set(reader.split('\n')) and len(reader.split('\n')) == len(old_reader.split('\n')) + len(added)
    # v22's territory: the cam2 code, v22's own block and the key light function are byte-identical to the v22 base; the bridges are not edited (installer test)
    assert cpp[cpp.index(V22_MARKER + ' BEGIN'):cpp.index(V22_MARKER + ' END')] == v21_cpp[v21_cpp.index(V22_MARKER + ' BEGIN'):v21_cpp.index(V22_MARKER + ' END')]
    for head in ('void ASub01HomeCharacter::StartStreamerVisualCam2(', 'void ASub01HomeCharacter::UpdateStreamerVisualCam2(',
                 'void ASub01HomeCharacter::WriteStreamerVisualCam2Status(', 'void ASub01HomeCharacter::UpdateStreamerVisualKeyLight(',
                 'void ASub01HomeCharacter::UpdateStreamerVisualPerf('):
        assert _function(cpp, head)[0] == _function(v21_cpp, head)[0], head
    assert cpp[cpp.index('// SUB01_STREAMER_VISUAL_V2_CAM2 BEGIN'):cpp.index('// SUB01_STREAMER_VISUAL_V2_CAM2 END')] == \
        v21_cpp[v21_cpp.index('// SUB01_STREAMER_VISUAL_V2_CAM2 BEGIN'):v21_cpp.index('// SUB01_STREAMER_VISUAL_V2_CAM2 END')]
    # wiring: the tick, the chair delta and the fit, the hands' mouse goal, the proxy steps in order
    assert '  UpdateStreamerVisualV23(Now,Dt,Anim);' in cpp and '+StreamerVisualChairFitShown+StreamerVisualV23ChairShown:' in cpp
    assert '-Front+FVector::DotProduct(StreamerVisualV23ChairShown,Facing),Move=' in cpp and ':StreamerVisualV23MouseGoal(Toward);' in cpp
    order = [proxy.index(s) for s in ('ApplyStreamerV23Pelvis(Output); //', 'ApplyStreamerV2Body(Output); //', 'ApplyStreamerV23Shoulders(Output); //')]
    assert order == sorted(order)
    evaluate = proxy[proxy.index('virtual bool Evaluate(FPoseContext& Output) override {'):]
    order = [evaluate.index(s) for s in ('EvaluateStreamerV2Hands(Output);', 'ApplyStreamerV2Head(Output);', 'if(StreamerV2)ApplyStreamerV23Head(Output);')]
    assert order == sorted(order)
    hands = proxy[proxy.index('void EvaluateStreamerV2Hands(FPoseContext& Output){'):]
    assert hands.index('const FVector Reached=StreamerV23Target(S,A,B,C);') < hands.index('ApplyStreamerV23Hand(Output.Pose,S,H);') < hands.index('// finger curl (optional') \
        < hands.index('MeasureStreamerV23Hand(Output.Pose,S,U,F,H);')
    assert 'StreamerVisualV23ChairWiden(StreamerVisualDeskPropOrigins[I]-StreamerVisualChairPivotWorld)' in cpp and 'StreamerVisualV23ScaleChairPart(A);}' in cpp
    assert '&&StreamerVisualV23ChairScaleShown==StreamerVisualV23ChairScaleApplied)return;' in cpp
    assert '(StreamerVisualState==TEXT("reading")||StreamerVisualState==TEXT("idle"))' in cpp  # hand_on_mouse whitelist
    assert 'static const double Weights[2]={0.4,0.6};' not in proxy and 'Shared?1.-double(StreamerV23NeckShare):0.6' in proxy
    assert 'UPROPERTY(Transient) float StreamerVisualV23NeckShare=0.4f;' in hands_h and 'StreamerVisualV23OrientErrRightDeg=Proxy.StreamerV23OrientErr[1];' in proxy
    # nothing outside the v23 blocks changed but the documented one-line wirings
    import difflib
    for name, old in (('Sub01HomeLab.cpp', v21_cpp), ('Sub01HomeHands.cpp', v21_hands)):
        new = texts[name]
        removed = [line[1:] for line in difflib.unified_diff(old.split('\n'), new.split('\n'), lineterm='', n=0) if line.startswith('-') and not line.startswith('---')]
        assert len(removed) == {'Sub01HomeLab.cpp': 7, 'Sub01HomeHands.cpp': 2}[name], (name, removed)  # chair delta, fit gap, chair move/gate, 3 hand lines; neck weights, IK solve


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++ for the syntax-only compile')
@pytest.mark.parametrize('compiler', COMPILERS, ids=[c[0] for c in COMPILERS])
@pytest.mark.parametrize('unit', ['hands', 'character'])
def test_v23_cpp_compiles_syntax_only_against_stub(v23_patched, tmp_path, compiler, unit):
    name, path, flags = compiler
    units = build_units_v22(v23_patched, tmp_path)
    source, include = units[unit]
    run = subprocess.run([path, '-std=c++20', '-fsyntax-only', *flags, f'-I{include}', '-isystem', str(units['stub']), str(source)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-6000:]


V23_BODY = r"""
#include <cstdlib>
#include <string>
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static const double Deg = 3.14159265358979323846 / 180;
static FTransform Inv(const FTransform& T) { const FQuat Q = T.GetRotation().Inverse(); return FTransform(Q, Q.RotateVector(T.GetTranslation()) * -1., FVector(1, 1, 1)); }
static FQuat AlongY(const FVector& Dir, double Twist) {  // a Mixamo-like bone: local +Y along the bone, twisted about it
 const FQuat ToDir = FQuat::FindBetweenNormals(FVector(0, 1, 0), Dir.GetSafeNormal()); return ToDir * FQuat(FVector(0, 1, 0), Twist * Deg); }
struct FBody {  // a seated Mixamo-like skeleton in component space (he faces +Y, his right is -X): spine, neck, head, thighs, clavicles, arms, hands, 4 fingers x 3
 FReferenceSkeleton Ref; std::vector<FTransform> Cs; std::vector<FVector> P; std::vector<int32> Parents; FPoseContext Context{nullptr};
 int32 Add(const std::u16string& Name, int32 Parent, const FVector& At) { Ref.StubNames.push_back(FName(Name.c_str())); Ref.StubParents.push_back(Parent); Parents.push_back(Parent); P.push_back(At); return int32(P.size()) - 1; }
 explicit FBody(const FQuat& HandTurn = FQuat::Identity) {
  const FVector Lean(0, std::sin(25 * Deg), std::cos(25 * Deg));  // the clips' 25 deg forward hunch
  const int32 Hips = Add(u"Hips", -1, FVector(0, 20, 65)); const int32 Spine = Add(u"Spine", Hips, P[Hips] + Lean * 10.);
  const int32 Spine1 = Add(u"Spine1", Spine, P[Spine] + Lean * 12.); const int32 Spine2 = Add(u"Spine2", Spine1, P[Spine1] + Lean * 12.);
  const int32 Neck = Add(u"Neck", Spine2, P[Spine2] + Lean * 14.); Add(u"Head", Neck, P[Neck] + Lean * 10.);
  Add(u"LeftUpLeg", Hips, P[Hips] + FVector(10, 0, -5)); Add(u"RightUpLeg", Hips, P[Hips] + FVector(-10, 0, -5));
  static const char16_t* const Side[2] = {u"Left", u"Right"}; static const char16_t* const Finger[4] = {u"Index", u"Middle", u"Ring", u"Pinky"};
  const double Lateral[4] = {-3, -1, 1, 3}, Ahead[4] = {9, 9.5, 9, 8};  // index inside, pinky outside
  for (int S = 0; S < 2; ++S) { const double Out = S ? -1 : 1; const std::u16string N(Side[S]);
   const int32 Clav = Add(N + u"Shoulder", Spine2, P[Spine2] + FVector(3 * Out, -1, 6)); const int32 Arm = Add(N + u"Arm", Clav, P[Clav] + FVector(14 * Out, -1, 0));
   const int32 Fore = Add(N + u"ForeArm", Arm, P[Arm] + FVector(4 * Out, 3, -27)); const int32 Hand = Add(N + u"Hand", Fore, P[Fore] + FVector(0, 25, -3));
   for (int G = 0; G < 4; ++G) { int32 Parent = Hand; FVector At = P[Hand] + HandTurn.RotateVector(FVector(Lateral[G] * Out, Ahead[G], -1));
    for (int K = 1; K <= 3; ++K) { Parent = Add(N + u"Hand" + Finger[G] + char16_t(u'0' + K), Parent, At); At = At + HandTurn.RotateVector(K == 1 ? FVector(0, 4, -.5) : FVector(0, 2.5, -.5)); } } }
  const int32 Count = int32(P.size());
  for (int32 K = 0; K < Count; ++K) { FVector Dir; for (int32 J = 0; J < Count; ++J) if (Parents[std::size_t(J)] == K) { Dir = P[std::size_t(J)] - P[std::size_t(K)]; break; }
   if (Dir.IsNearlyZero()) Dir = Parents[std::size_t(K)] >= 0 ? P[std::size_t(K)] - P[std::size_t(Parents[std::size_t(K)])] : FVector(0, 0, 1);
   Cs.push_back(FTransform(AlongY(Dir, double((K * 37) % 90 - 45)), P[std::size_t(K)], FVector(1, 1, 1))); }
  Context.Pose.StubContainer.StubRef = &Ref;
  for (int32 K = 0; K < Count; ++K) Context.Pose.StubBones.push_back(Parents[std::size_t(K)] < 0 ? Cs[std::size_t(K)] : Cs[std::size_t(K)] * Inv(Cs[std::size_t(Parents[std::size_t(K)])]));
 }
 FBody(const FBody&) = delete;
 int32 Index(const char16_t* Name) const { return Ref.FindBoneIndex(FName(Name)); }
 FTransform Component(int32 Bone) const { FTransform Out; FSub01HandsProxy::StreamerV2ComponentTransform(Context.Pose, Bone, Out); return Out; }
 FVector At(const char16_t* Name) const { return Component(Index(Name)).GetTranslation(); }
};
static void Setup(FSub01HandsProxy& Proxy) {  // the desk pose: v2 active, lean, IK on the keys, finger curl, mouth, gaze/head offset
 Proxy.StreamerVisualActive = true; Proxy.StreamerV2 = true; Proxy.StreamerV2Dt = 1.f / 60; Proxy.StreamerV2LeanCmd = -8; Proxy.StreamerV2HandIK = true; Proxy.StreamerV2HandAlpha = 1;
 Proxy.StreamerV2ElbowPole = .5f; Proxy.StreamerV2HandTarget[0] = FVector(10, 52, 78); Proxy.StreamerV2HandTarget[1] = FVector(-10, 52, 78);
 Proxy.StreamerV2HandPole[0] = FVector(.3, -.5, -1); Proxy.StreamerV2HandPole[1] = FVector(-.3, -.5, -1); Proxy.StreamerV2FingerCurlDeg = 6; Proxy.StreamerV2Mouth = .5f;
}
"""

V23_DUMP_DRIVER = V23_BODY + r"""
static void Dump(const FBody& B) { for (const FTransform& T : B.Context.Pose.StubBones) std::printf("%a %a %a %a %a %a %a %a %a %a\n", T.Rotation.X, T.Rotation.Y, T.Rotation.Z, T.Rotation.W,
  T.Translation.X, T.Translation.Y, T.Translation.Z, T.Scale3D.X, T.Scale3D.Y, T.Scale3D.Z); }
int main() {  // the WHOLE proxy Evaluate (clip pose, lean + breathing, mouth, hands IK + finger curl, head channel) on 40 frames: printed bit for bit
 FSub01HandsProxy Proxy(nullptr); Setup(Proxy);
 for (int Frame = 0; Frame < 40; ++Frame) { Proxy.StreamerVisualHeadOffset = FRotator(-5 + Frame * .1, 7, 0); Proxy.StreamerV2Spine[0] = FRotator(.6 * std::sin(Frame * .1), 0, 0);
  FBody B(FQuat(FVector(0, 0, 1), .3)); Proxy.Evaluate(B.Context); if (Frame % 13 == 0 || Frame == 39) Dump(B); }
 std::printf("measured %a %a %a %a %a %a %a\n", Proxy.StreamerV2LeanMeasured, Proxy.StreamerV2LeanGain, Proxy.StreamerV2HandDist[0], Proxy.StreamerV2ElbowDeg[1], Proxy.StreamerV2FingerFlex[0][0],
  Proxy.StreamerV2FingerFlex[1][1], Proxy.StreamerV2BodyRight.X);
 return 0;
}
"""


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v23_defaults_leave_the_proxy_pose_bit_identical(v23_patched, v22_patched, tmp_path):
    """The real proxy Evaluate on a 40-bone Mixamo-like body, built once from the v21 sources and once from the v23 sources with every
    v23 value at its default: every bone's local transform and every published measurement is the same, bit for bit (printf %a).
    (v22 does not edit the anim proxy: the base is v21's proxy as v22 ships it.)"""
    outputs = []
    for label, src in (('v22', v22_patched), ('v23', v23_patched)):
        units = build_units(src, tmp_path / label, end=FACE_END, hands_driver=V23_DUMP_DRIVER)
        run = _run_driver(units, tmp_path / label, unit='hands_driver')
        assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-4000:]
        outputs.append(run.stdout)
    assert outputs[0].count('\n') > 160 and 'measured' in outputs[0]
    assert outputs[0] == outputs[1]


V23_CHAIN_DRIVER = V23_BODY + r"""
static double Incline(const FBody& B) { const FVector D = B.At(u"Head") - B.At(u"Hips"); return std::atan2(D.Y, D.Z) / Deg; }  // Hips->Head, forward +Y
static FVector Palm(const FBody& B, int S, FVector* Fingers = nullptr, FVector* Across = nullptr) {  // palm side from the bone positions (right hand: -(F x A))
 const char16_t* const Hand[2] = {u"LeftHand", u"RightHand"}; const char16_t* const I1[2] = {u"LeftHandIndex1", u"RightHandIndex1"};
 const char16_t* const M1[2] = {u"LeftHandMiddle1", u"RightHandMiddle1"}; const char16_t* const P1[2] = {u"LeftHandPinky1", u"RightHandPinky1"};
 const FVector F = (B.At(M1[S]) - B.At(Hand[S])).GetSafeNormal(); FVector A = B.At(P1[S]) - B.At(I1[S]); A = (A - F * FVector::DotProduct(A, F)).GetSafeNormal();
 if (Fingers) *Fingers = F; if (Across) *Across = A; const FVector N = FVector::CrossProduct(F, A); return (S ? N * -1. : N).GetSafeNormal(); }
int main() {
 const FVector Up(0, 0, 1), Forward(0, 1, 0), Right(-1, 0, 0);
 // 1. pelvis_pitch_deg -10 (sit up): the Hips->Head line turns back by 10 deg about the pelvis, the pelvis stays, the thighs keep their orientation
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); FBody Base; FBody B; const double Before = Incline(B); const FTransform Hips0 = B.Component(0);
   Proxy.StreamerV23Pelvis = -10; Proxy.ApplyStreamerV23Pelvis(B.Context);
   CHECK(Near(Incline(B) - Before, -10, 1e-6) && B.Component(0).GetTranslation().Equals(Hips0.GetTranslation(), 1e-12), 1);
   CHECK(B.Component(B.Index(u"LeftUpLeg")).GetRotation().Equals(Base.Component(Base.Index(u"LeftUpLeg")).GetRotation(), 1e-9) && B.Component(B.Index(u"RightUpLeg")).GetRotation().Equals(Base.Component(Base.Index(u"RightUpLeg")).GetRotation(), 1e-9), 2);
   FBody D; Proxy.StreamerV23Pelvis = 0; Proxy.ApplyStreamerV23Pelvis(D.Context); for (std::size_t K = 0; K < D.Cs.size(); ++K) CHECK(D.Context.Pose.StubBones[K].Equals(Base.Context.Pose.StubBones[K], 0), 3); }
 // 2. shoulders: drop lowers both arm roots alike, back moves them back; symmetric
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); FBody Base; FBody B; Proxy.StreamerV23ShoulderDrop = 10; Proxy.ApplyStreamerV23Shoulders(B.Context);
   const FVector L = B.At(u"LeftArm") - Base.At(u"LeftArm"), R = B.At(u"RightArm") - Base.At(u"RightArm");
   CHECK(L.Z < -1 && Near(L.Z, R.Z, 1e-9) && Near(L.X, -R.X, 1e-9) && Near(L.Y, R.Y, 1e-9), 4);
   FBody C; Proxy.StreamerV23ShoulderDrop = 0; Proxy.StreamerV23ShoulderBack = 10; Proxy.ApplyStreamerV23Shoulders(C.Context);
   const FVector LB = C.At(u"LeftArm") - Base.At(u"LeftArm"), RB = C.At(u"RightArm") - Base.At(u"RightArm"); CHECK(LB.Y < -1 && Near(LB.Y, RB.Y, 1e-9) && std::fabs(LB.Z) < 1e-9, 5); }
 // 3. chin tuck: the head moves back, its orientation is kept; 4. neck girth: the Head is untouched, the Neck swells across its long axis
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); FBody Base; FBody B; Proxy.StreamerV2BodyRight = Right; Proxy.StreamerV23NeckBack = 10; Proxy.ApplyStreamerV23Head(B.Context);
   const int32 H = B.Index(u"Head"), N = B.Index(u"Neck");
   CHECK(B.Component(H).GetRotation().Equals(Base.Component(H).GetRotation(), 1e-9) && B.At(u"Head").Y < Base.At(u"Head").Y - 1, 6);
   FBody G; Proxy.StreamerV23NeckBack = 0; Proxy.StreamerV23NeckGirth = 1.2f; Proxy.ApplyStreamerV23Head(G.Context); const FTransform Head = G.Component(H), Neck = G.Component(N);
   CHECK(Head.GetRotation().Equals(Base.Component(H).GetRotation(), 1e-9) && Head.GetTranslation().Equals(Base.Component(H).GetTranslation(), 1e-9) && Head.GetScale3D().Equals(FVector(1, 1, 1), 1e-12), 7);
   CHECK(Neck.GetScale3D().Equals(FVector(1.2, 1, 1.2), 1e-6) && Neck.GetTranslation().Equals(Base.Component(N).GetTranslation(), 1e-12), 8);
   CHECK(Near(Proxy.StreamerV23Incline, Incline(G), 1e-6) && Proxy.StreamerV23NeckAlign > .999, 9); }  // the measurements the receipt shows
 // 4b. neck_girth needs the Neck->child offset on one local axis: a diagonal one is skipped (no shear), its alignment published
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); Proxy.StreamerV2BodyRight = Right; FBody G; const std::size_t H = std::size_t(G.Index(u"Head")), N = std::size_t(G.Index(u"Neck"));
   const double Len = G.Context.Pose.StubBones[H].GetTranslation().Size(); G.Context.Pose.StubBones[H].SetTranslation(FVector(0, 1, 1).GetSafeNormal() * Len);
   const FTransform Neck0 = G.Context.Pose.StubBones[N], Head0 = G.Context.Pose.StubBones[H]; Proxy.StreamerV23NeckGirth = 1.2f; Proxy.ApplyStreamerV23Head(G.Context);
   CHECK(Near(Proxy.StreamerV23NeckAlign, std::sqrt(.5), 1e-6) && G.Context.Pose.StubBones[N].Equals(Neck0, 0) && G.Context.Pose.StubBones[H].Equals(Head0, 0), 26); }
 // 5. neck_share 0: the head channel leaves the Neck alone and turns the Head by the whole pitch
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); FBody Base; const int32 N = Base.Index(u"Neck"), H = Base.Index(u"Head");
   FBody Shared; Proxy.StreamerVisualHeadOffset = FRotator(-6, 0, 0); Proxy.ApplyStreamerV2Head(Shared.Context); CHECK(!Shared.Context.Pose.StubBones[std::size_t(N)].GetRotation().Equals(Base.Context.Pose.StubBones[std::size_t(N)].GetRotation(), 1e-6), 10);
   FBody Alone; Proxy.StreamerV23NeckShare = 0; Proxy.ApplyStreamerV2Head(Alone.Context);
   CHECK(Alone.Context.Pose.StubBones[std::size_t(N)].Equals(Base.Context.Pose.StubBones[std::size_t(N)], 0), 11);
   const FVector Face0 = Base.Component(H).GetRotation().Inverse().RotateVector(Forward), Face = Alone.Component(H).GetRotation().RotateVector(Face0);
   CHECK(Near(std::atan2(Face.Z, std::hypot(Face.X, Face.Y)) / Deg, -6, .5), 12); }
 // 6. elbow_min_deg: a target that closes the elbow to ~74 deg slides forward at the same height until the elbow opens to 95; 0 = untouched
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); Proxy.StreamerV2LeanCmd = 0; Proxy.StreamerV2FingerCurlDeg = 0;
   FBody A; Proxy.ApplyStreamerV2Body(A.Context); Proxy.EvaluateStreamerV2Hands(A.Context);
   CHECK(Proxy.StreamerV2ElbowDeg[0] < 80 && Proxy.StreamerV2HandDist[0] < 1e-3 && Proxy.StreamerV23Slide[0] == 0, 13);
   FBody B; Proxy.StreamerV23ElbowMin = 95; Proxy.ApplyStreamerV2Body(B.Context); Proxy.EvaluateStreamerV2Hands(B.Context); const FVector W = B.At(u"LeftHand"), T = Proxy.StreamerV2HandTarget[0];
   CHECK(Near(Proxy.StreamerV2ElbowDeg[0], 95, .5) && Near(Proxy.StreamerV2ElbowDeg[1], 95, .5) && Proxy.StreamerV23Slide[0] > 1 && Near(W.Z, T.Z, 1e-6) && Near(W.X, T.X, 1e-6) && W.Y > T.Y + 1, 14);
   CHECK(Near(Proxy.StreamerV2HandDist[0], Proxy.StreamerV23Slide[0], 1e-4), 15);  // the receipt's reach error = the slide
   const FVector Sh = B.At(u"LeftArm"), El = B.At(u"LeftForeArm");  // the wrist sits on the SLID target; the elbow's place along his facing is published
   CHECK(Proxy.StreamerV23Residual[0] < 1e-3 && Near(Proxy.StreamerV23ElbowBack[0], -(El.Y - Sh.Y), 1e-6), 150);
   FBody C; Proxy.StreamerV23ElbowMin = 60; Proxy.ApplyStreamerV2Body(C.Context); Proxy.EvaluateStreamerV2Hands(C.Context); CHECK(Proxy.StreamerV23Slide[0] == 0 && Proxy.StreamerV2HandDist[0] < 1e-3, 16);
   // the cap: 150 deg would need ~25 cm, the slide stops at the cap (the elbow stays below the minimum)
   FBody D; Proxy.StreamerV23ElbowMin = 150; Proxy.ApplyStreamerV2Body(D.Context); Proxy.EvaluateStreamerV2Hands(D.Context);
   CHECK(Near(Proxy.StreamerV23Slide[0], @@SLIDEMAX@@, 1e-5) && Proxy.StreamerV2ElbowDeg[0] < 149 && Near(Proxy.StreamerV2HandDist[0], @@SLIDEMAX@@, 1e-3), 160);
   // a target BEHIND the shoulder along his facing: the guard declines (-1) instead of jumping forward; the other hand still slides
   FBody E; Proxy.StreamerV23ElbowMin = 95; Proxy.StreamerV2HandTarget[0] = FVector(10, 25, 78); Proxy.ApplyStreamerV2Body(E.Context); Proxy.EvaluateStreamerV2Hands(E.Context);
   CHECK(Proxy.StreamerV23Slide[0] == -1 && Proxy.StreamerV2HandDist[0] < 1e-3 && Proxy.StreamerV23Slide[1] > 1, 161);
   // 1 cm ahead of the shoulder line the (capped) slide is scaled by 1/ramp: continuous through the line, no 15 cm jump
   FBody R; Proxy.ApplyStreamerV2Body(R.Context); const FVector Line = R.At(u"LeftArm"); Proxy.StreamerV2HandTarget[0] = FVector(Line.X - 7, Line.Y + 1, 78); Proxy.EvaluateStreamerV2Hands(R.Context);
   CHECK(Near(Proxy.StreamerV23Slide[0], @@SLIDEMAX@@ / @@SLIDERAMP@@, 1e-4) && Near(Proxy.StreamerV2HandDist[0], Proxy.StreamerV23Slide[0], 1e-3), 162); }
 // the palm-side convention on hands BUILT palm down (right hand: -(F x A), left: +(F x A))
 { FBody U; CHECK(Palm(U, 0).Z < -.9 && Palm(U, 1).Z < -.9, 17); }
 // 7. hand_orient 1 on hands that start yawed and rolled: fingers along the wanted direction, knuckles level, pinky out, palm down
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); Proxy.StreamerV2LeanCmd = 0; Proxy.StreamerV2FingerCurlDeg = 0; Proxy.StreamerV23HandOrient = 1; Proxy.StreamerV23HandYawIn = 12; Proxy.StreamerV23HandPitch = 10;
   FBody B(FQuat(FVector(.3, .2, .93).GetSafeNormal(), 50 * Deg)); Proxy.ApplyStreamerV2Body(B.Context); Proxy.EvaluateStreamerV2Hands(B.Context);
   for (int S = 0; S < 2; ++S) { FVector F, A; const FVector P = Palm(B, S, &F, &A); const FVector Out = S ? Right : Right * -1.;
    const FVector Flat = Forward * std::cos(12 * Deg) - Out * std::sin(12 * Deg), Want = (Flat * std::cos(10 * Deg) - Up * std::sin(10 * Deg)).GetSafeNormal();
    CHECK(std::acos(std::fmin(1., FVector::DotProduct(F, Want))) / Deg < .5 && std::fabs(A.Z) < .01 && FVector::DotProduct(A, Out) > .9 && P.Z < -.9 && Proxy.StreamerV23OrientErr[S] >= 0 && Proxy.StreamerV23OrientErr[S] < .5, 20 + S); }
   // 8. finger_bend_deg 20: the proximal phalanx turns by the bend towards the palm, the fingertips follow, the measured flexion grows
   const double Flex0 = Proxy.StreamerV2FingerFlex[1][0]; const FVector Tip0 = B.At(u"RightHandIndex3") - B.At(u"RightHandIndex1"), Phalanx0 = (B.At(u"RightHandIndex2") - B.At(u"RightHandIndex1")).GetSafeNormal(); const FVector Palm0 = Palm(B, 1);
   FBody C(FQuat(FVector(.3, .2, .93).GetSafeNormal(), 50 * Deg)); Proxy.StreamerV23FingerBend = 20; Proxy.ApplyStreamerV2Body(C.Context); Proxy.EvaluateStreamerV2Hands(C.Context);
   const FVector Tip = C.At(u"RightHandIndex3") - C.At(u"RightHandIndex1"), Phalanx = (C.At(u"RightHandIndex2") - C.At(u"RightHandIndex1")).GetSafeNormal();
   CHECK(FVector::DotProduct(Tip, Palm0) > FVector::DotProduct(Tip0, Palm0) + 1 && Near(std::acos(std::fmin(1., FVector::DotProduct(Phalanx, Phalanx0))) / Deg, 20, 2)
         && FVector::DotProduct(Phalanx - Phalanx0, Palm0) > 0 && Proxy.StreamerV2FingerFlex[1][0] > Flex0 + 8, 22); }
 // 8b. the keyboard frame: with a keyboard axis 20 deg off his facing, the fingers follow the keyboard, not him
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); Proxy.StreamerV2LeanCmd = 0; Proxy.StreamerV2FingerCurlDeg = 0; Proxy.StreamerV23HandOrient = 1; Proxy.StreamerV23HandYawIn = 0; Proxy.StreamerV23HandPitch = 0;
   const FVector Desk(std::sin(20 * Deg), std::cos(20 * Deg), 0); Proxy.StreamerV23DeskForward = Desk;
   FBody B(FQuat(FVector(.3, .2, .93).GetSafeNormal(), 50 * Deg)); Proxy.ApplyStreamerV2Body(B.Context); Proxy.EvaluateStreamerV2Hands(B.Context);
   for (int S = 0; S < 2; ++S) { FVector F, A; Palm(B, S, &F, &A); CHECK(std::acos(std::fmin(1., FVector::DotProduct(F, Desk))) / Deg < .5, 23 + S); }
   // fingertips above the key plane: the *4 end bone, else the last joint + 0.7 x the last phalanx (this body has no *4 bones)
   Proxy.StreamerV23KeyPlaneValid = true; Proxy.StreamerV23KeyPlaneZ = 70; FBody K; Proxy.ApplyStreamerV2Body(K.Context); Proxy.EvaluateStreamerV2Hands(K.Context);
   const char16_t* const Fingers[4] = {u"Index", u"Middle", u"Ring", u"Pinky"}; double Sum = 0, Low = 1e9;
   for (int G = 0; G < 4; ++G) { const std::u16string N = std::u16string(u"RightHand") + Fingers[G]; const FVector T2 = K.At((N + u"2").c_str()), T3 = K.At((N + u"3").c_str());
    const double Above = (T3 + (T3 - T2) * .7).Z - 70; Sum += Above; Low = std::fmin(Low, Above); }
   CHECK(Near(Proxy.StreamerV23TipMean[1], Sum / 4, 1e-4) && Near(Proxy.StreamerV23TipMin[1], Low, 1e-4) && Proxy.StreamerV23TipMean[0] > -90, 25); }
 // 8c. hand_orient from hands turned ~180 deg (fingers pointing back at him): finite, and the same result
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); Proxy.StreamerV2LeanCmd = 0; Proxy.StreamerV2FingerCurlDeg = 0; Proxy.StreamerV23HandOrient = 1; Proxy.StreamerV23HandYawIn = 0; Proxy.StreamerV23HandPitch = 0;
   FBody B(FQuat(FVector(0, 0, 1), 180 * Deg)); Proxy.ApplyStreamerV2Body(B.Context); Proxy.EvaluateStreamerV2Hands(B.Context);
   for (const FTransform& T : B.Context.Pose.StubBones) CHECK(!T.ContainsNaN() && std::isfinite(T.Rotation.X + T.Rotation.Y + T.Rotation.Z + T.Rotation.W), 28);
   for (int S = 0; S < 2; ++S) { FVector F, A; const FVector P = Palm(B, S, &F, &A); const FVector Out = S ? Right : Right * -1.;
    CHECK(std::acos(std::fmin(1., FVector::DotProduct(F, Forward))) / Deg < .5 && std::fabs(A.Z) < .01 && FVector::DotProduct(A, Out) > .9 && P.Z < -.9 && Proxy.StreamerV23OrientErr[S] < .5, 280 + S); } }
 // 9. defaults: no slide, no orientation error reported
 { FSub01HandsProxy Proxy(nullptr); Setup(Proxy); FBody B; Proxy.Evaluate(B.Context);
   CHECK(Proxy.StreamerV23Slide[0] == 0 && Proxy.StreamerV23OrientErr[0] == -1 && Proxy.StreamerV23OrientErr[1] == -1 && Proxy.StreamerV23NeckAlign == -1, 30); }
 // 10. the game-thread hand-over: the instance's v23 fields (what the character writes each tick) -> PreUpdate copies them and clears the
 // last frame's measurements -> Evaluate applies them
 { USub01HomeHandsInstance Anim; StubCastTarget = &Anim; Anim.StreamerVisualActive = true; Anim.StreamerVisualV2 = true; Anim.StreamerVisualHandIK = true; Anim.StreamerVisualHandAlpha = 1;
   Anim.StreamerVisualElbowPole = .5f; Anim.StreamerVisualHandTargetLeft = FVector(10, 52, 78); Anim.StreamerVisualHandTargetRight = FVector(-10, 52, 78); Anim.StreamerVisualLeanDeg = 0;
   Anim.StreamerVisualHandPoleLeft = FVector(.3, -.5, -1); Anim.StreamerVisualHandPoleRight = FVector(-.3, -.5, -1); Anim.StreamerVisualFingerCurlDeg = 0;
   Anim.StreamerVisualV23ElbowMinDeg = 95; Anim.StreamerVisualV23NeckGirth = 1.1f; Anim.StreamerVisualV23PelvisPitchDeg = -10; Anim.StreamerVisualV23HandOrient = .5f;
   FSub01HandsProxy Proxy(nullptr); Proxy.StreamerV23Slide[0] = 7; Proxy.StreamerV23NeckAlign = .3f; Proxy.StreamerV23OrientErr[1] = 9; Proxy.PreUpdate(&Anim, 1.f / 60);
   CHECK(Proxy.StreamerV23ElbowMin == 95 && Proxy.StreamerV23NeckGirth == 1.1f && Proxy.StreamerV23Pelvis == -10 && Proxy.StreamerV23HandOrient == .5f && Proxy.StreamerV2HandIK
         && Proxy.StreamerV23Slide[0] == 0 && Proxy.StreamerV23NeckAlign == -1 && Proxy.StreamerV23OrientErr[1] == -1, 40);
   FBody B; Proxy.Evaluate(B.Context);
   CHECK(Proxy.StreamerV23Slide[0] > 1 && Proxy.StreamerV2ElbowDeg[0] > 94 && Proxy.StreamerV23NeckAlign > .999 && Proxy.StreamerV23OrientErr[0] >= 0, 41);
   StubCastTarget = nullptr; }
 std::printf("ok\n");
 return 0;
}
"""


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v23_proxy_corrections_on_a_bone_chain(v23_patched, tmp_path):
    """Each proxy correction on the Mixamo-like body: hip hinge, clavicles, chin tuck, neck girth, neck share, elbow minimum, hand
    orientation and finger bend, with numeric acceptance (degrees, cm) and the published measurements."""
    units = build_units(v23_patched, tmp_path, end=FACE_END, hands_driver=V23_CHAIN_DRIVER.replace('@@SLIDEMAX@@', repr(v23.SLIDE_MAX_CM))
                        .replace('@@SLIDERAMP@@', repr(v23.SLIDE_RAMP_CM)))
    run = _run_driver(units, tmp_path, unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


V23_CHAR_PRELUDE = r'''
#include <cstdlib>
void USub01HomeHandsInstance::NativePostEvaluateAnimation() {}
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy() { return nullptr; }
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
#define CHECK(c, n) do { if (!(c)) { std::printf("failed %d\n", n); return n; } } while (0)
static bool Near(double A, double B, double E) { return std::fabs(A - B) <= E; }
static void Ticks(ASub01HomeCharacter& C, int N) { for (int K = 0; K < N; ++K) { FPlatformTime::StubNow += .1; C.ApplyStreamerVisualV2(FPlatformTime::StubNow, .1f); } }
struct FScene {  // the character on the authored transform, seated (seat offset valid), a keyboard, a chair (backrest, pan, armrest)
 USkeletalMeshComponent Body; UCameraComponent Camera; USub01HomeHandsInstance Anim; ASub01HomeCharacter C; AActor KB, Back, Pan, Arm; FVector Pelvis, F0, Side0;
 FScene() {
  C.FirstPersonBody = &Body; C.ViewCamera = &Camera; Body.StubAnim = &Anim; StubCastTarget = &Anim;
  Body.StubWorld = FTransform(FQuat(0, 0, .991898180738225, .1270354243831201), FVector(214.00134645387243, -289.2975482520179, 6.191812330665947), FVector(1, 1, 1));
  Body.StubRelative = FTransform(FQuat::Identity, FVector(0, 0, -91), FVector(1, 1, 1)); Camera.StubWorld.Translation = FVector(334, -209, 151); Camera.FieldOfView = 65; C.StreamerVisualCam2Dir = u"@@DIR@@";
  C.StartStreamerVisualV2(FRotator(-13.64, -146.31, 0)); C.StreamerVisualSchemaVersion = 2; C.StreamerVisualState = TEXT("idle"); C.StreamerVisualDeskPropsScanned = true; C.StreamerVisualDeskBase = 0;
  const FVector Pivot(0.075, 22.727, 64.214); Anim.StreamerVisualSeatOffset = FTransform::Identity; Anim.StreamerVisualSeatOffsetValid = true; Anim.StreamerVisualSeatSettled = true; Anim.StreamerVisualSeatPivot = Pivot; Anim.StreamerVisualPelvisBone = 0;
  Pelvis = Body.StubWorld.TransformPosition(Pivot); Body.StubHead = Pelvis;  // GetBoneTransform(pelvis) in the stub
  F0 = (Body.StubWorld.GetRotation().RotateVector(FVector(0, 1, 0)) * FVector(1, 1, 0)).GetSafeNormal(); Side0 = FVector::CrossProduct(FVector::UpVector, F0);
  Back.StubLocation = Pelvis - F0 * 8. + FVector(0, 0, 30); Back.StubExtent = FVector(20, 4, 25); Pan.StubLocation = Pelvis + FVector(0, 0, -8); Pan.StubExtent = FVector(25, 25, 4);
  Arm.StubLocation = Pelvis + Side0 * 25. + FVector(0, 0, 10); Arm.StubExtent = FVector(4, 20, 5);
  for (AActor* A : {&Back, &Pan, &Arm}) { C.StreamerVisualDeskProps.Add(A); C.StreamerVisualDeskPropOrigins.Add(A->StubLocation); C.StreamerVisualDeskPropIsChair.Add(true); C.StreamerVisualDeskPropRotations.Add(FQuat::Identity); }
  KB.StubLocation = FVector(209, -339.433, 79.9); KB.StubExtent = FVector(16.05, 5.8, 0.9); C.StreamerVisualKeyboardActor = &KB; C.StreamerVisualKeyboardExtent = KB.StubExtent; C.StreamerVisualKeyboardCentreOffset = FVector(1, -2, .5);
  C.StreamerVisualDeskProps.Add(&KB); C.StreamerVisualDeskPropOrigins.Add(KB.StubLocation); C.StreamerVisualDeskPropIsChair.Add(false); C.StreamerVisualDeskPropRotations.Add(FQuat::Identity);
 }
};
'''

V23_CHAR_DUMP_DRIVER = V23_CHAR_PRELUDE + r'''
static void P(const FVector& V) { std::printf("%a %a %a\n", V.X, V.Y, V.Z); }
int main() {  // v21 fields only: the character side at the defaults through states, the pull-back and the chair fit, printed bit for bit
 FScene S; ASub01HomeCharacter& C = S.C; C.StreamerVisualSeatBackCm = 20; C.StreamerVisualPostureLeanDeg = -6;
 const TCHAR* States[] = {u"idle", u"typing", u"reading", u"mouse", u"talking", u"typing"};
 for (const TCHAR* State : States) { C.StreamerVisualState = State; for (int K = 0; K < 12; ++K) { Ticks(C, 1);
   P(S.Anim.StreamerVisualHandTargetLeft); P(S.Anim.StreamerVisualHandTargetRight); P(S.Anim.StreamerVisualHandPoleLeft); P(S.Anim.StreamerVisualHandPoleRight);
   std::printf("%a %a %a %a %a\n", S.Anim.StreamerVisualLeanDeg, S.Anim.StreamerVisualHeadOffset.Pitch, S.Anim.StreamerVisualHeadOffset.Yaw, C.StreamerVisualHandAlpha, double(C.StreamerVisualKeyLight->Intensity));
   P(C.StreamerVisualKeyLight->StubWorld.Translation); std::printf("%a %a\n", C.StreamerVisualKeyLight->StubRotation.Pitch, C.StreamerVisualKeyLight->StubRotation.Yaw);
   P(S.Body.StubRelative.Translation); P(C.StreamerVisualChairDelta); P(S.Back.StubLocation); P(S.Pan.StubLocation); P(S.KB.StubLocation);
   std::printf("%a %a %d\n", double(C.StreamerVisualBackrestGapMeasured), double(C.StreamerVisualChairFitCm), C.StreamerVisualChairFitPasses); } }
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v23_defaults_leave_the_character_side_bit_identical(v23_patched, v22_patched, tmp_path):
    """The character side at the v23 defaults (hand targets, poles, posture, key light, seat, chair fit, props) through every state,
    compiled from the v22 and the v23 sources: identical, bit for bit."""
    outputs = []
    for label, src in (('v22', v22_patched), ('v23', v23_patched)):
        (tmp_path / label / 'cam2').mkdir(parents=True)
        driver = V23_CHAR_DUMP_DRIVER.replace('@@DIR@@', str(tmp_path / label / 'cam2'))
        units = build_units_v22(src, tmp_path / label / 'u', driver=driver)
        run = _run_driver(units, tmp_path / label / 'u')
        assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-4000:]
        outputs.append(run.stdout)
    assert outputs[0].count('\n') > 900
    assert outputs[0] == outputs[1]


V23_CHAR_DRIVER = V23_CHAR_PRELUDE + r'''
int main() {
 FScene Scene; ASub01HomeCharacter& C = Scene.C; USub01HomeHandsInstance& Anim = Scene.Anim; USpotLightComponent* Key = C.StreamerVisualKeyLight.Get();
 // 1. the defaults: nothing changes (neutral proxy values, no extra light, no chair extra, the key light where v21 puts it, the stream pass's poles)
 Ticks(C, 10);
 CHECK(!C.StreamerVisualV23Changed() && Anim.StreamerVisualV23PelvisPitchDeg == 0 && Anim.StreamerVisualV23NeckShare == @@SHARE@@f && Anim.StreamerVisualV23NeckGirth == 1 && Anim.StreamerVisualV23ElbowMinDeg == 0
       && Anim.StreamerVisualV23HandOrient == 0 && Anim.StreamerVisualV23FingerBendDeg == 0 && Anim.StreamerVisualV23NeckBackDeg == 0, 1);
 CHECK(!C.StreamerVisualV23Fill && !C.StreamerVisualV23Rim && C.StreamerVisualV23ChairShown.X == 0 && C.StreamerVisualV23ChairShown.Y == 0 && C.StreamerVisualV23ChairShown.Z == 0 && Key->StubSpecular == 1, 2);
 const FVector Monitor(217, -367.67, 114.75), Aim = C.StreamerVisualKeyLightAim; const FVector Towards = FVector(Aim.X - Monitor.X, Aim.Y - Monitor.Y, 0).GetSafeNormal(), Side = FVector::CrossProduct(FVector::UpVector, Towards * -1.);
 CHECK(Key->StubWorld.Translation.Equals(Monitor + Towards * 6. + Side * double(C.StreamerVisualFaceSideCm) + FVector(0, 0, C.StreamerVisualKeyLightUpCm), 1e-9), 3);
 const FVector Facing = C.StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(C.StreamerVisualFacingLocal); const FVector Flat = FVector(Facing.X, Facing.Y, 0).GetSafeNormal(), BodyRight = FVector::CrossProduct(FVector::UpVector, Flat);
 const FQuat ToComponent = Scene.Body.StubWorld.GetRotation().Inverse(); const FVector PoleLeft0 = Anim.StreamerVisualHandPoleLeft, PoleRight0 = Anim.StreamerVisualHandPoleRight;
 CHECK(PoleLeft0.Equals(ToComponent.RotateVector(FVector::UpVector * -1. - Flat * .5 - BodyRight * .3), 1e-12), 4);
 // 2. posture keys eased at 12 deg/s, exact on arrival; v1 events get the neutral values
 C.StreamerVisualV23PelvisPitchDeg = -8; C.StreamerVisualV23NeckBackDeg = 6; C.StreamerVisualV23ShoulderDropDeg = 4; Ticks(C, 3);
 CHECK(Near(Anim.StreamerVisualV23PelvisPitchDeg, -3.6, 1e-4) && Near(Anim.StreamerVisualV23NeckBackDeg, 3.6, 1e-4) && Near(Anim.StreamerVisualV23ShoulderDropDeg, 3.6, 1e-4) && C.StreamerVisualV23Changed(), 5);
 Ticks(C, 5); CHECK(Anim.StreamerVisualV23PelvisPitchDeg == -8 && Anim.StreamerVisualV23NeckBackDeg == 6 && Anim.StreamerVisualV23ShoulderDropDeg == 4, 6);
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 10); CHECK(Anim.StreamerVisualV23PelvisPitchDeg == 0 && Anim.StreamerVisualV23NeckBackDeg == 0, 7); C.StreamerVisualSchemaVersion = 2;
 C.StreamerVisualV23PelvisPitchDeg = 0; C.StreamerVisualV23NeckBackDeg = 0; C.StreamerVisualV23ShoulderDropDeg = 0; Ticks(C, 10);
 // weights eased 1/s: neck share 0.4 -> 0 in 0.4 s
 C.StreamerVisualV23NeckShare = 0; Ticks(C, 2); CHECK(Near(Anim.StreamerVisualV23NeckShare, .2, 1e-6), 8); Ticks(C, 3); CHECK(Anim.StreamerVisualV23NeckShare == 0, 9);
 C.StreamerVisualV23NeckShare = @@SHARE@@f; Ticks(C, 5); CHECK(Anim.StreamerVisualV23NeckShare == @@SHARE@@f && !C.StreamerVisualV23Changed(), 10);
 // hand_orient is a weight too (1/s): 0.5 after 0.5 s, 1 after 1 s
 C.StreamerVisualV23HandOrient = 1; Ticks(C, 5); CHECK(Near(Anim.StreamerVisualV23HandOrient, .5, 1e-6), 100); Ticks(C, 5); CHECK(Anim.StreamerVisualV23HandOrient == 1, 101);
 C.StreamerVisualV23HandOrient = 0; Ticks(C, 10); CHECK(Anim.StreamerVisualV23HandOrient == 0, 102);
 // 3. the elbow pole: back .2 / out .6 recompute the poles; back at the defaults the stream pass's own (bit for bit)
 C.StreamerVisualV23ElbowPoleBack = .2f; C.StreamerVisualV23ElbowPoleOut = .6f; Ticks(C, 5);
 CHECK(Anim.StreamerVisualHandPoleLeft.Equals(ToComponent.RotateVector(FVector::UpVector * -1. - Flat * double(.2f) - BodyRight * double(.6f)), 1e-9)
       && Anim.StreamerVisualHandPoleRight.Equals(ToComponent.RotateVector(FVector::UpVector * -1. - Flat * double(.2f) + BodyRight * double(.6f)), 1e-9), 11);
 C.StreamerVisualV23ElbowPoleBack = .5f; C.StreamerVisualV23ElbowPoleOut = .3f; Ticks(C, 5);
 CHECK(Anim.StreamerVisualHandPoleLeft.Equals(PoleLeft0, 0) && Anim.StreamerVisualHandPoleRight.Equals(PoleRight0, 0), 12);
 // 4. the key off the webcam axis, gliding at @@LIGHTMOVE@@ cm/s; its specular at once
 C.StreamerVisualV23KeySideCm = 30; C.StreamerVisualV23KeyUpCm = 10; Ticks(C, 1); const float KeyStep = float(@@LIGHTMOVE@@ * double(.1f));
 CHECK(Key->StubWorld.Translation.Equals(Monitor + Towards * 6. + Side * double(C.StreamerVisualFaceSideCm + KeyStep) + FVector(0, 0, C.StreamerVisualKeyLightUpCm + KeyStep), 1e-6), 13);
 Ticks(C, 10); CHECK(Key->StubWorld.Translation.Equals(Monitor + Towards * 6. + Side * double(C.StreamerVisualFaceSideCm + 30.f) + FVector(0, 0, C.StreamerVisualKeyLightUpCm + 10.f), 1e-9), 130);
 C.StreamerVisualV23KeySpecular = .4f; Ticks(C, 1); CHECK(Key->StubSpecular == .4f, 14);
 // 5. fill between him and the monitor, rim behind him; on his lighting channel; the specular follows; 0 cd hides; a v1 event turns them off
 C.StreamerVisualV23FillCd = .05f; C.StreamerVisualV23RimCd = .1f; Ticks(C, 1);
 USpotLightComponent* Fill = C.StreamerVisualV23Fill.Get(); USpotLightComponent* Rim = C.StreamerVisualV23Rim.Get(); const double CdStep = double(@@CDRATE@@f * .1f);
 CHECK(Fill && Rim && Fill->StubVisible && Near(Fill->Intensity, CdStep, 1e-7) && Near(Rim->Intensity, CdStep, 1e-7), 150);  // the intensities rise from 0
 Ticks(C, 55);
 CHECK(Fill && Rim && Fill->StubVisible && Rim->StubVisible && Near(Fill->Intensity, .05, 1e-7) && Near(Rim->Intensity, .1, 1e-7) && !Fill->StubChannels[0] && Fill->StubChannels[1] && !Rim->StubChannels[0]
       && Fill->StubSpecular == .4f && Rim->StubSpecular == .4f && Fill->bUseTemperature && Near(Fill->StubRadius, C.StreamerVisualKeyLightRadiusCm, 1e-6), 15);
 const FVector FillRel = Fill->StubWorld.Translation - Aim, RimRel = Rim->StubWorld.Translation - Aim;
 CHECK(Near(FVector::DotProduct(FillRel, Towards), -@@FFRONT@@, 1e-9) && Near(FVector::DotProduct(FillRel, Side), @@FSIDE@@, 1e-9) && Near(FillRel.Z, @@FUP@@, 1e-9) && Near(Fill->Temperature, @@FTEMP@@, 1e-3), 16);
 CHECK(Near(FVector::DotProduct(RimRel, Towards), @@RBACK@@, 1e-9) && Near(FVector::DotProduct(RimRel, Side), @@RSIDE@@, 1e-9) && Near(RimRel.Z, @@RUP@@, 1e-9) && Near(Rim->Temperature, @@RTEMP@@, 1e-3), 17);
 // a placement change glides too (the fill 30 cm further to his right: 3 cm per 0.1 s)
 const FVector FillAt0 = Fill->StubWorld.Translation; C.StreamerVisualV23FillSideCm = @@FSIDE@@f + 30; Ticks(C, 1);
 CHECK(Near((Fill->StubWorld.Translation - FillAt0).Size(), @@LIGHTMOVE@@ * double(.1f), 1e-6) && Near(FVector::DotProduct(Fill->StubWorld.Translation - FillAt0, Side), @@LIGHTMOVE@@ * double(.1f), 1e-6), 151);
 Ticks(C, 10); CHECK(Near(FVector::DotProduct(Fill->StubWorld.Translation - Aim, Side), @@FSIDE@@ + 30, 1e-6), 152); C.StreamerVisualV23FillSideCm = @@FSIDE@@f; Ticks(C, 11);
 C.StreamerVisualV23FillCd = 0; Ticks(C, 1); CHECK(Fill->StubVisible && Near(Fill->Intensity, .05 - CdStep, 1e-6), 180); Ticks(C, 30); CHECK(!Fill->StubVisible && Fill->Intensity == 0 && Rim->StubVisible, 18);
 // a v1 event: the rim fades out, the specular is back at once, the key glides back to exactly where v21 puts it
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 1); CHECK(Rim->StubVisible && Key->StubSpecular == 1, 190);
 CHECK(Key->StubWorld.Translation.Equals(Monitor + Towards * 6. + Side * double(C.StreamerVisualFaceSideCm + (30.f - KeyStep)) + FVector(0, 0, C.StreamerVisualKeyLightUpCm + (10.f - KeyStep)), 1e-6), 191);  // one glide step back
 Ticks(C, 60);
 CHECK(!Rim->StubVisible && Key->StubWorld.Translation.Equals(Monitor + Towards * 6. + Side * double(C.StreamerVisualFaceSideCm) + FVector(0, 0, C.StreamerVisualKeyLightUpCm), 1e-9), 19); C.StreamerVisualSchemaVersion = 2;
 C.StreamerVisualV23RimCd = 0; C.StreamerVisualV23KeySideCm = 0; C.StreamerVisualV23KeyUpCm = 0; C.StreamerVisualV23KeySpecular = 1; Ticks(C, 2);
 // 6. the chair extra: eased 60 cm/s into the chair delta; the fit measures without it, so a re-fit keeps it
 C.StreamerVisualChairFit = 1; C.StreamerVisualChairFitPasses = 0; Ticks(C, 60); const FVector Fitted = Scene.Back.StubLocation; const float Gap1 = C.StreamerVisualBackrestGapMeasured;
 CHECK(C.StreamerVisualChairFitPasses == @@PASSES@@ && Near(Gap1, @@TARGET@@, @@DEADBAND@@ + 1e-6), 20);
 C.StreamerVisualV23ChairBackCm = 10; Ticks(C, 1); CHECK(Near(FVector::DotProduct(C.StreamerVisualV23ChairShown, Scene.F0), -6, 1e-6), 21);  // 60 cm/s x 0.1 s
 Ticks(C, 3); C.StreamerVisualChairFitPasses = 0; Ticks(C, 60);
 CHECK(Scene.Back.StubLocation.Equals(Fitted - Scene.F0 * 10., 1e-6) && Near(C.StreamerVisualBackrestGapMeasured, Gap1, @@DEADBAND@@ + 1e-6), 22);
 C.StreamerVisualV23ChairSideCm = 5; Ticks(C, 5); CHECK(Scene.Back.StubLocation.Equals(Fitted - Scene.F0 * 10. + Scene.Side0 * 5., 1e-6), 23);
 C.StreamerVisualSchemaVersion = 1; Ticks(C, 5); CHECK(C.StreamerVisualV23ChairShown.Size() == 0, 24); C.StreamerVisualSchemaVersion = 2;
 C.StreamerVisualV23ChairBackCm = 0; C.StreamerVisualV23ChairSideCm = 0; Ticks(C, 5);
 // 7. the mouse as a component: plausible = a registered, visible static-mesh LEAF in the zone, small, not simulating, not of the desk packs
 UStaticMesh MouseMesh; UStaticMeshComponent Far, Big, Pack, Parent, Mouse, Hidden, Ghost, Falling, Twin, Own, Prop; const FVector MouseAt(238, -332, 80);
 Far.Bounds.Origin = FVector(300, -332, 81); Far.Bounds.BoxExtent = FVector(3, 6, 2); Big.Bounds.Origin = FVector(238, -332, 81); Big.Bounds.BoxExtent = FVector(20, 6, 2);
 Mouse.Bounds.Origin = FVector(238, -332, 81); Mouse.Bounds.BoxExtent = FVector(3, 6, 2); Mouse.StubWorld.Translation = MouseAt;
 for (UStaticMeshComponent* M : {&Pack, &Parent, &Hidden, &Ghost, &Falling, &Twin, &Own, &Prop}) M->Bounds = Mouse.Bounds;
 for (UStaticMeshComponent* M : {&Far, &Big, &Pack, &Parent, &Mouse, &Hidden, &Ghost, &Falling, &Twin, &Own, &Prop}) { M->StubMesh = &MouseMesh; StubCastAlso.push_back(M); }
 Parent.StubChildren = 1; Hidden.StubVisible = false; Ghost.StubRegistered = false; Falling.StubSimulating = true;
 CHECK(!C.StreamerVisualV23MouseCandidate(&Far, u"none", true) && !C.StreamerVisualV23MouseCandidate(&Big, u"none", true) && !C.StreamerVisualV23MouseCandidate(&Pack, u"R15Part0007", true)
       && !C.StreamerVisualV23MouseCandidate(&Parent, u"none", true) && !C.StreamerVisualV23MouseCandidate(&Hidden, u"none", true) && !C.StreamerVisualV23MouseCandidate(&Ghost, u"none", true)
       && !C.StreamerVisualV23MouseCandidate(&Falling, u"none", true) && !C.StreamerVisualV23MouseCandidate(&Mouse, u"none", false) && C.StreamerVisualV23MouseCandidate(&Mouse, u"none", true)
       && !C.StreamerVisualV23MouseComp.IsValid(), 30);
 // the scan: every component of every actor but his own and the desk props; adopted only when exactly ONE is plausible
 AActor Room; C.StubComponents = {&Own}; Scene.Back.StubComponents = {&Prop}; StubWorldEnabled = true; StubWorldActors = {&C, &Scene.Back, &Room};
 Room.StubComponents = {&Far, &Hidden}; C.ScanStreamerVisualV23Mouse();
 CHECK(C.StreamerVisualV23MouseScanned && !C.StreamerVisualV23MouseComp.IsValid() && C.StreamerVisualV23MouseName == TEXT("none") && C.StreamerVisualV23MouseCandidates == 1, 300);
 Room.StubComponents = {&Far, &Hidden, &Mouse, &Twin}; C.ScanStreamerVisualV23Mouse();
 CHECK(!C.StreamerVisualV23MouseComp.IsValid() && !C.StreamerVisualV23MouseAdopted && C.StreamerVisualV23MouseName == TEXT("no unique candidate") && C.StreamerVisualV23MouseCandidates == 3, 301);
 Mouse.StubMobility = EComponentMobility::Stationary;  // not the field's initial value (Static = 0): the save is really tested
 Room.StubComponents = {&Far, &Hidden, &Mouse}; C.ScanStreamerVisualV23Mouse(); StubWorldEnabled = false; C.StubComponents.clear();
 CHECK(C.StreamerVisualV23MouseComp.Get() == &Mouse && C.StreamerVisualV23MouseAdopted && C.StreamerVisualV23MouseCandidates == 2 && C.StreamerVisualV23MouseCentreOffset.Equals(FVector(0, 0, 1), 1e-12)
       && Mouse.StubMobility == EComponentMobility::Movable && C.StreamerVisualV23MouseMobility == uint8(EComponentMobility::Stationary), 31);
 // it glides (@@MOUSEMOVE@@ cm/s) by the keyboard pull-back
 C.StreamerVisualV23MouseScan = 1; C.StreamerVisualV23MouseScanned = true; C.StreamerVisualSeatBackCm = 20; Ticks(C, 1); const double MouseStep = @@MOUSEMOVE@@ * double(.1f);
 CHECK((Mouse.StubWorld.Translation - MouseAt).Size() <= MouseStep + 1e-9 && (Mouse.StubWorld.Translation - MouseAt).Size() > 0, 32);
 Ticks(C, 60); const FVector Delta = C.StreamerVisualDeskPropDelta;
 CHECK(Delta.Size() > 2 * MouseStep && Mouse.StubWorld.Translation.Equals(MouseAt + Delta, 1e-9), 320);
 // hand_on_mouse: the right hand to the found mouse in idle and reading only; the left hand stays on the keys
 C.StreamerVisualV23HandOnMouse = 1; C.StreamerVisualState = TEXT("reading"); Ticks(C, 5);
 CHECK(C.StreamerVisualHandTargetName[1] == TEXT("mouse_component") && C.StreamerVisualHandTargetName[0] == TEXT("keyboard_left") && C.StreamerVisualHandWorld[1].Equals(C.StreamerVisualV23MouseGoal(FVector(0, 1, 0)), 1e-6), 33);
 C.StreamerVisualState = TEXT("typing"); Ticks(C, 5); CHECK(C.StreamerVisualHandTargetName[1] == TEXT("keyboard_right"), 34);
 C.StreamerVisualState = TEXT("talking"); Ticks(C, 5); CHECK(C.StreamerVisualHandTargetName[1] == TEXT("keyboard_right"), 340);  // not whitelisted
 C.StreamerVisualState = TEXT("idle"); Ticks(C, 5); CHECK(C.StreamerVisualHandTargetName[1] == TEXT("mouse_component"), 341);
 // mouse_scan 0: it glides back, then exactly home with its own mobility, released
 C.StreamerVisualV23MouseScan = 0; Ticks(C, 1);
 CHECK(C.StreamerVisualV23MouseComp.Get() == &Mouse && Near((Mouse.StubWorld.Translation - MouseAt).Size(), Delta.Size() - MouseStep, 1e-6) && Mouse.StubMobility == EComponentMobility::Movable, 35);
 Ticks(C, 20);
 CHECK(Mouse.StubWorld.Translation.Equals(MouseAt, 0) && !C.StreamerVisualV23MouseComp.IsValid() && !C.StreamerVisualV23MouseAdopted && !C.StreamerVisualV23MouseScanned
       && Mouse.StubMobility == EComponentMobility::Stationary && C.StreamerVisualV23MouseName == TEXT("-"), 350);
 C.StreamerVisualState = TEXT("reading"); Ticks(C, 5); CHECK(C.StreamerVisualHandTargetName[1] == TEXT("keyboard_right"), 36);  // no mouse found: hand_on_mouse keeps it on the keys
 C.StreamerVisualV23HandOnMouse = 0;
 // an adopted component that vanishes (its weak pointer goes invalid): released on the next tick, and the tick after scans again (this world is empty: none)
 StubWorldEnabled = true; C.ScanStreamerVisualV23Mouse(); StubWorldEnabled = false; C.StreamerVisualV23MouseScan = 1; CHECK(C.StreamerVisualV23MouseAdopted && C.StreamerVisualV23MouseScanned, 37);
 C.StreamerVisualV23MouseComp = nullptr; Ticks(C, 1); CHECK(!C.StreamerVisualV23MouseAdopted && !C.StreamerVisualV23MouseScanned && C.StreamerVisualV23MouseName == TEXT("-"), 38);
 Ticks(C, 1); CHECK(C.StreamerVisualV23MouseScanned && C.StreamerVisualV23MouseName == TEXT("none"), 39);
 C.StreamerVisualV23MouseScan = 0; Ticks(C, 1); CHECK(!C.StreamerVisualV23MouseScanned, 390); StubCastAlso.clear(); StubWorldActors.clear(); Mouse.StubMobility = EComponentMobility::Static;
 // 8. chair_scale: the chair widened along his side only, about the seated pelvis; the part's local axis closest to his side scaled; back to the authored scale at 1
 const FVector ArmOrigin = C.StreamerVisualDeskPropOrigins[2], BackOrigin = C.StreamerVisualDeskPropOrigins[0];
 C.StreamerVisualV23ChairScale = 1.1f; Ticks(C, 10);
 CHECK(C.StreamerVisualV23ChairScaleShown == 1.1f && Scene.Arm.StubLocation.Equals(ArmOrigin + Scene.Side0 * (25 * double(1.1f - 1.f)) + C.StreamerVisualChairDelta, 1e-6)
       && Scene.Back.StubLocation.Equals(BackOrigin + C.StreamerVisualChairDelta, 1e-6) && Scene.Arm.StubScale.Equals(FVector(1.1f, 1, 1), 1e-6) && Scene.Pan.StubScale.Equals(FVector(1.1f, 1, 1), 1e-6), 40);
 C.StreamerVisualV23ChairScale = 1; Ticks(C, 10);
 CHECK(Scene.Arm.StubLocation.Equals(ArmOrigin + C.StreamerVisualChairDelta, 1e-6) && Scene.Arm.StubScale.Equals(FVector(1, 1, 1), 0) && Scene.KB.StubScale.Equals(FVector(1, 1, 1), 0), 41);
 // 9. the keyboard frame and the key plane for the proxy (component space)
 const FVector TowardHim(0, 1, 0), KeyTop = Scene.KB.StubLocation + C.StreamerVisualKeyboardCentreOffset + FVector(0, 0, C.StreamerVisualKeyboardExtent.Z);
 CHECK(Anim.StreamerVisualV23KeyPlaneValid && Anim.StreamerVisualV23DeskForward.Equals(Scene.Body.StubWorld.GetRotation().Inverse().RotateVector(TowardHim * -1.), 1e-12)
       && Near(Anim.StreamerVisualV23KeyPlaneZ, Scene.Body.StubWorld.InverseTransformPosition(KeyTop).Z, 1e-4), 50);
 // 10. the log: at once on a tuning change (its sequence kept), then every @@LOGS@@ s while a key is off its default; one line when all are back, then quiet
 C.StreamerVisualFaceTuningSequence = 41; C.StreamerVisualV23NeckBackDeg = 3; Ticks(C, 1); const double LogAt1 = C.StreamerVisualV23LogAt;
 CHECK(C.StreamerVisualV23LoggedSequence == 41 && Near(LogAt1, FPlatformTime::StubNow + @@LOGS@@, 1e-6), 60);
 Ticks(C, 50); CHECK(C.StreamerVisualV23LogAt == LogAt1, 61); Ticks(C, 51); CHECK(C.StreamerVisualV23LogAt > LogAt1 && C.StreamerVisualV23LoggedSequence == 41, 62);
 C.StreamerVisualFaceTuningSequence = 42; C.StreamerVisualV23NeckBackDeg = 0; Ticks(C, 1); const double LogAt2 = C.StreamerVisualV23LogAt;
 CHECK(C.StreamerVisualV23LoggedSequence == -1 && Near(LogAt2, FPlatformTime::StubNow + @@LOGS@@, 1e-6), 63);
 Ticks(C, 120); CHECK(C.StreamerVisualV23LogAt == LogAt2 && C.StreamerVisualV23LoggedSequence == -1, 64);
 C.StreamerVisualFaceTuningSequence = 43; C.StreamerVisualV23FillCd = .01f; Ticks(C, 1); CHECK(C.StreamerVisualV23LightsLoggedSequence == 43, 65);  // the lights line
 C.StreamerVisualV23FillCd = 0; Ticks(C, 10);
 std::printf("ok\n");
 return 0;
}
'''


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_v23_character_logic_runs(v23_patched, tmp_path):
    (tmp_path / 'cam2').mkdir()
    d = v23.DEFAULTS
    driver = (V23_CHAR_DRIVER.replace('@@DIR@@', str(tmp_path / 'cam2')).replace('@@SHARE@@', repr(v23.NECK_SHARE_V21[0]))
              .replace('@@FFRONT@@', repr(d['fill_front_cm'])).replace('@@FSIDE@@', repr(d['fill_side_cm'])).replace('@@FUP@@', repr(d['fill_up_cm']))
              .replace('@@FTEMP@@', repr(d['fill_temp_k'])).replace('@@RBACK@@', repr(d['rim_back_cm'])).replace('@@RSIDE@@', repr(d['rim_side_cm']))
              .replace('@@RUP@@', repr(d['rim_up_cm'])).replace('@@RTEMP@@', repr(d['rim_temp_k'])).replace('@@PASSES@@', str(posefix.CHAIR_FIT_PASSES))
              .replace('@@TARGET@@', repr(posefix.BACKREST_GAP_CM)).replace('@@DEADBAND@@', repr(posefix.CHAIR_FIT_DEADBAND_CM))
              .replace('@@LIGHTMOVE@@', repr(v23.LIGHT_MOVE_CM_S)).replace('@@CDRATE@@', repr(v23.LIGHT_CD_RATE)).replace('@@MOUSEMOVE@@', repr(v23.MOUSE_MOVE_CM_S))
              .replace('@@LOGS@@', repr(v23.LOG_SECONDS)))
    assert '@@' not in driver
    units = build_units_v22(v23_patched, tmp_path / 'u', driver=driver)
    run = _run_driver(units, tmp_path / 'u')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr


@pytest.mark.skipif(not COMPILERS, reason='no g++/clang++')
def test_earlier_drivers_pass_under_v23(v23_patched, tmp_path):
    """The v2 driver, the pose fix's character driver and bone chain, the v21 driver and v22's monitor feed and cam2 exposure runs all still pass
    on the v23 sources."""
    run = _run_driver(build_units_v22(v23_patched, tmp_path / 'v2'), tmp_path / 'v2')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    (tmp_path / 'cam2').mkdir()
    pose = (POSEFIX_DRIVER.replace('@@DIR@@', str(tmp_path / 'cam2')).replace('@@FADE@@', repr(posefix.LOOP_FADE_SECONDS)).replace('@@SACRUM@@', repr(posefix.SACRUM_BACK_CM))
            .replace('@@TARGET@@', repr(posefix.BACKREST_GAP_CM)).replace('@@DEADBAND@@', repr(posefix.CHAIR_FIT_DEADBAND_CM)).replace('@@PASSES@@', str(posefix.CHAIR_FIT_PASSES)))
    run = _run_driver(build_units_v22(v23_patched, tmp_path / 'pose', driver=pose), tmp_path / 'pose')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    chain = build_units(v23_patched, tmp_path / 'chain', end=FACE_END, hands_driver=POSE_CHAIN_DRIVER)
    run = _run_driver(chain, tmp_path / 'chain', unit='hands_driver')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    (tmp_path / 'stream').mkdir()
    driver = (V21_DRIVER.replace('@@DIR@@', str(tmp_path / 'stream')).replace('@@VIEW@@', repr(v21.CAM2_VIEW_CM)).replace('@@LOD@@', repr(v21.CAM2_LOD_FACTOR))
              .replace('@@CD@@', repr(v21.KEY_CD)).replace('@@RADIUS@@', repr(v21.KEY_RADIUS_CM)).replace('@@SOFT@@', repr(v21.KEY_SOFT_CM))
              .replace('@@OUTER@@', repr(v21.KEY_CONES[1])).replace('@@MAXCHARS@@', str(v21.CONSOLE_MAX_CHARS)))
    run = _run_driver(build_units_v22(v23_patched, tmp_path / 'v21', driver=driver), tmp_path / 'v21')
    assert run.returncode == 0 and run.stdout.strip() == 'ok', run.stdout + run.stderr
    for name, check in (('feed', test_v22_monitor_feed_logic_runs), ('exposure', test_v22_cam2_exposure_runs)):  # v22's own runtime drivers on the v23 output
        (tmp_path / name).mkdir()
        check(v23_patched, tmp_path / name)


def test_v23_new_locals_do_not_shadow_character_fields(v23_patched, v22_patched):
    members = _header_members(lf(v23_patched / 'Sub01HomeLab.h'))
    added = _added_locals(lf(v22_patched / 'Sub01HomeLab.cpp'), lf(v23_patched / 'Sub01HomeLab.cpp'))
    assert {'ChairFacing', 'ChairGoal', 'LightSide', 'KeyAt'} <= added
    assert not (added & members), sorted(added & members)
    header = lf(v23_patched / 'Sub01HomeLab.h')
    declared = _header_members(header[header.index(V23_MARKER + ' BEGIN'):header.index(V23_MARKER + ' END')])
    assert declared and not (declared & _header_members(lf(v22_patched / 'Sub01HomeLab.h')))
    # the proxy's new locals do not shadow its members either (FAnimInstanceProxy fields such as Skeleton or RequiredBones are not reused)
    proxy_added = _added_locals(lf(v22_patched / 'Sub01HomeHands.cpp'), lf(v23_patched / 'Sub01HomeHands.cpp'))
    proxy_members = {'Previous', 'Current', 'Blend', 'Progress', 'Skeleton', 'RequiredBones', 'SkeletalMeshComponent', 'RootMotionMode', 'Notifies'}
    assert not (proxy_added & proxy_members), sorted(proxy_added & proxy_members)
