"""Minimal Unreal Engine stub shim for tools/check_native_adapters_compile_closure.py (source-only; no engine).

The shim declares only the engine types, functions and macros that the installed native adapters (and the root
code that hosts their inserted lines: the class declarations, FSub01HandsProxy, the PC/device bridge headers)
actually reference. Signatures mirror UE 5 (LWC doubles, TCHAR = char16_t as on Linux, TObjectPtr, JSON field
lookups through TryGet*Field). It is NOT the engine: it proves C++ closure of the project code (every project symbol
declared, no shadowing, no duplicate definitions, types consistent with these stub signatures) and that every
UE_LOG / FString::Printf format matches its arguments, but an engine API whose real signature differs from its stub
is only caught by the real build.

Format checking: UE 5 validates printf formats at compile time. The shim does the same with a consteval format
object: %d/%i/%u/%x/%c need an integer (or bool / unscoped enum), %f/%e/%g a floating value, %s a TCHAR pointer
(never an FString or an ANSI char pointer), %p a pointer; '*' widths take an integer.
"""
from __future__ import annotations

from pathlib import Path

SHIM_NAME = 'Sub01UEShim.h'

SHIM = r'''#pragma once
// Sub01 compile-closure stub shim: NOT Unreal Engine. See tools/native_adapters_ue_shim.py.
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <initializer_list>
#include <memory>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
#include <algorithm>

#ifndef WITH_EDITOR
#define WITH_EDITOR 0
#endif

typedef std::int8_t int8; typedef std::uint8_t uint8; typedef std::int16_t int16; typedef std::uint16_t uint16;
typedef std::int32_t int32; typedef std::uint32_t uint32; typedef long long int64; typedef unsigned long long uint64;
typedef char16_t TCHAR; typedef char ANSICHAR; typedef uint16 FBoneIndexType;
#define TEXT(x) u##x
#define UCLASS(...)
#define USTRUCT(...)
#define UPROPERTY(...)
#define UFUNCTION(...)
#define GENERATED_BODY()
#define SUB01HOMELAB_API
#define UE_ARRAY_COUNT(a) (sizeof(a)/sizeof((a)[0]))
#define INDEX_NONE (-1)
#define BIG_NUMBER (3.4e+38f)
#define PI (3.1415926535897932f)
#define MAX_TOTAL_INFLUENCES 12
enum EForceInit { ForceInit };
template<class T> std::remove_reference_t<T>&& MoveTemp(T&& V) { return static_cast<std::remove_reference_t<T>&&>(V); }
namespace ESearchCase { enum Type { CaseSensitive, IgnoreCase }; }

// ------------------------------------------------------------------ printf formats (UE 5 checks them at compile time)
namespace Sub01Shim {
enum class EArg { Int, Float, TStr, AStr, Ptr, Other };
template<class T> consteval EArg KindOf() {
 using U = std::remove_cvref_t<T>;
 if constexpr (std::is_same_v<U, bool> || std::is_integral_v<U>) return EArg::Int;
 else if constexpr (std::is_enum_v<U>) return std::is_convertible_v<U, int> ? EArg::Int : EArg::Other;
 else if constexpr (std::is_floating_point_v<U>) return EArg::Float;
 else if constexpr (std::is_array_v<U>) return std::is_same_v<std::remove_cv_t<std::remove_extent_t<U>>, TCHAR> ? EArg::TStr : (std::is_same_v<std::remove_cv_t<std::remove_extent_t<U>>, char> ? EArg::AStr : EArg::Ptr);
 else if constexpr (std::is_pointer_v<U>) return std::is_same_v<std::remove_cv_t<std::remove_pointer_t<U>>, TCHAR> ? EArg::TStr : (std::is_same_v<std::remove_cv_t<std::remove_pointer_t<U>>, char> ? EArg::AStr : EArg::Ptr);
 else if constexpr (std::is_null_pointer_v<U>) return EArg::Ptr;
 else return EArg::Other;
}
void FormatArgumentMismatch();  // not constexpr: reaching it makes the consteval format check fail to compile
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
   if (*P == u'*') { if (Arg >= Count || Kinds[Arg] != EArg::Int) FormatArgumentMismatch(); ++Arg; ++P; }
   while (*P >= u'0' && *P <= u'9') ++P;
   if (*P == u'.') { ++P; if (*P == u'*') { if (Arg >= Count || Kinds[Arg] != EArg::Int) FormatArgumentMismatch(); ++Arg; ++P; } while (*P >= u'0' && *P <= u'9') ++P; }
   while (*P == u'h' || *P == u'l' || *P == u'L' || *P == u'z' || *P == u'j' || *P == u't' || *P == u'q') ++P;
   if (*P == u'I' && P[1] == u'6' && P[2] == u'4') P += 3;
   if (Arg >= Count) FormatArgumentCount();
   const EArg Have = Kinds[Arg++];
   switch (*P) {
    case u'd': case u'i': case u'u': case u'x': case u'X': case u'o': case u'c': if (Have != EArg::Int) FormatArgumentMismatch(); break;
    case u'f': case u'F': case u'e': case u'E': case u'g': case u'G': case u'a': case u'A': if (Have != EArg::Float) FormatArgumentMismatch(); break;
    case u's': if (Have != EArg::TStr) FormatArgumentMismatch(); break;
    case u'p': if (Have != EArg::Ptr && Have != EArg::TStr && Have != EArg::AStr) FormatArgumentMismatch(); break;
    default: FormatArgumentMismatch();
   }
  }
  if (Arg != Count) FormatArgumentCount();
 }
};
template<class... T> void Log(TFormat<std::type_identity_t<T>...>, T&&...) {}
enum class ELogVerbosity { Fatal, Error, Warning, Display, Log, Verbose, VeryVerbose };
struct FLogCategory {};
}
inline Sub01Shim::FLogCategory LogTemp;
#define UE_LOG(Category, Verbosity, Format, ...) do { (void)&Category; (void)::Sub01Shim::ELogVerbosity::Verbosity; ::Sub01Shim::Log(Format __VA_OPT__(,) __VA_ARGS__); } while (0)

// ------------------------------------------------------------------ containers
template<class T> class TArray {
 std::vector<T> Data;
public:
 TArray() = default;
 TArray(std::initializer_list<T> Items) : Data(Items) {}
 int32 Num() const { return int32(Data.size()); }
 bool IsEmpty() const { return Data.empty(); }
 bool IsValidIndex(int32 I) const { return I >= 0 && I < Num(); }
 int32 Add(const T& Item) { Data.push_back(Item); return Num() - 1; }
 int32 Add(T&& Item) { Data.push_back(std::move(Item)); return Num() - 1; }
 template<class... A> int32 Emplace(A&&... Args) { Data.emplace_back(std::forward<A>(Args)...); return Num() - 1; }
 void Reserve(int32 N) { Data.reserve(std::size_t(N)); }
 void Empty() { Data.clear(); }
 void Reset() { Data.clear(); }
 bool Contains(const T& Item) const { return std::find(Data.begin(), Data.end(), Item) != Data.end(); }
 T& operator[](int32 I) { return Data[std::size_t(I)]; }
 const T& operator[](int32 I) const { return Data[std::size_t(I)]; }
 T& Last() { return Data.back(); }
 const T& Last() const { return Data.back(); }
 template<class P> void Sort(P Less) { std::sort(Data.begin(), Data.end(), Less); }
 T* begin() { return Data.data(); } T* end() { return Data.data() + Data.size(); }
 const T* begin() const { return Data.data(); } const T* end() const { return Data.data() + Data.size(); }
};
template<class K, class V> struct TPair { K Key; V Value; };
template<class K, class V> class TMap {
 std::vector<TPair<K, V>> Pairs;
public:
 V& Add(const K& Key, const V& Value) { if (V* Found = Find(Key)) { *Found = Value; return *Found; } Pairs.push_back({Key, Value}); return Pairs.back().Value; }
 V& Add(const K& Key) { if (V* Found = Find(Key)) return *Found; Pairs.push_back({Key, V()}); return Pairs.back().Value; }
 V* Find(const K& Key) { for (auto& P : Pairs) if (P.Key == Key) return &P.Value; return nullptr; }
 const V* Find(const K& Key) const { for (auto& P : Pairs) if (P.Key == Key) return &P.Value; return nullptr; }
 V FindRef(const K& Key) const { const V* Found = Find(Key); return Found ? *Found : V(); }
 V& FindChecked(const K& Key) { return *Find(Key); }
 const V& FindChecked(const K& Key) const { return *Find(Key); }
 V& operator[](const K& Key) { return *Find(Key); }
 const V& operator[](const K& Key) const { return *Find(Key); }
 bool Contains(const K& Key) const { return Find(Key) != nullptr; }
 int32 Num() const { return int32(Pairs.size()); }
 void Empty() { Pairs.clear(); }
 auto begin() { return Pairs.begin(); } auto end() { return Pairs.end(); }
 auto begin() const { return Pairs.begin(); } auto end() const { return Pairs.end(); }
};
template<class T> class TSet { std::vector<T> Items; public: void Add(const T& V) { Items.push_back(V); } bool Contains(const T& V) const { return std::find(Items.begin(), Items.end(), V) != Items.end(); } };
template<class S> using TFunction = std::function<S>;
template<class T> class TSharedRef;
template<class T> class TSharedPtr {
 std::shared_ptr<T> Ptr;
public:
 TSharedPtr() = default;
 TSharedPtr(std::nullptr_t) {}
 TSharedPtr(const TSharedRef<T>& Ref);
 bool IsValid() const { return bool(Ptr); }
 explicit operator bool() const { return bool(Ptr); }
 T* Get() const { return Ptr.get(); }
 T* operator->() const { return Ptr.get(); }
 T& operator*() const { return *Ptr; }
};
template<class T> class TSharedRef { public: std::shared_ptr<T> Ptr; T* operator->() const { return Ptr.get(); } T& Get() const { return *Ptr; } };
template<class T> TSharedPtr<T>::TSharedPtr(const TSharedRef<T>& Ref) : Ptr(Ref.Ptr) {}
template<class E> class TEnumAsByte { uint8 Value = 0; public: TEnumAsByte() = default; TEnumAsByte(E V) : Value(uint8(V)) {} operator E() const { return E(Value); } };

// ------------------------------------------------------------------ strings
class FString {
 std::u16string Data;
public:
 FString() = default;
 FString(const TCHAR* Text) : Data(Text ? Text : u"") {}
 const TCHAR* operator*() const { return Data.c_str(); }
 bool IsEmpty() const { return Data.empty(); }
 int32 Len() const { return int32(Data.size()); }
 void Empty() { Data.clear(); }
 void Reset() { Data.clear(); }
 bool Contains(const TCHAR* Sub, ESearchCase::Type = ESearchCase::IgnoreCase) const { return Data.find(Sub) != std::u16string::npos; }
 bool Contains(const FString& Sub, ESearchCase::Type = ESearchCase::IgnoreCase) const { return Data.find(Sub.Data) != std::u16string::npos; }
 bool EndsWith(const TCHAR* Suffix, ESearchCase::Type = ESearchCase::IgnoreCase) const { std::u16string S(Suffix); return Data.size() >= S.size() && Data.compare(Data.size() - S.size(), S.size(), S) == 0; }
 bool EndsWith(const FString& Suffix, ESearchCase::Type Case = ESearchCase::IgnoreCase) const { return EndsWith(*Suffix, Case); }
 FString Left(int32 Count) const { FString Out; Out.Data = Data.substr(0, std::size_t(Count < 0 ? 0 : Count)); return Out; }
 FString& operator+=(const FString& Other) { Data += Other.Data; return *this; }
 FString& operator+=(const TCHAR* Other) { Data += Other; return *this; }
 friend FString operator+(FString A, const FString& B) { A += B; return A; }
 friend FString operator+(FString A, const TCHAR* B) { A += B; return A; }
 friend bool operator==(const FString& A, const FString& B) { return A.Data == B.Data; }
 friend bool operator==(const FString& A, const TCHAR* B) { return A.Data == B; }
 friend bool operator!=(const FString& A, const FString& B) { return A.Data != B.Data; }
 friend bool operator!=(const FString& A, const TCHAR* B) { return A.Data != B; }
 template<class... T> static FString Printf(Sub01Shim::TFormat<std::type_identity_t<T>...> Format, T&&...) { return FString(Format.Text); }
 auto begin() const { return Data.begin(); } auto end() const { return Data.end(); }
};
#define ANSI_TO_TCHAR(Text) ((const TCHAR*)(Text ? u"" : u""))
class FName {
 FString Text;
public:
 FName() = default;
 FName(const TCHAR* Name) : Text(Name) {}
 explicit FName(const FString& Name) : Text(Name) {}
 bool IsNone() const { return Text.IsEmpty(); }
 FString ToString() const { return Text; }
 bool LexicalLess(const FName& Other) const { return std::u16string(*Text) < std::u16string(*Other.Text); }
 friend bool operator==(const FName& A, const FName& B) { return A.Text == B.Text; }
 friend bool operator!=(const FName& A, const FName& B) { return !(A == B); }
};
inline const FName NAME_None;
struct FCString { static uint64 Strtoui64(const TCHAR*, TCHAR**, int32) { return 0; } };
struct FCommandLine { static const TCHAR* Get() { return u""; } };
struct FParse { static bool Value(const TCHAR*, const TCHAR*, FString&, bool = true) { return false; } static bool Value(const TCHAR*, const TCHAR*, float&) { return false; } };
struct FPaths {
 static FString ProjectDir() { return FString(); }
 template<class... P> static FString Combine(P&&...) { static_assert(sizeof...(P) >= 2); return FString(); }
};
struct FFileHelper { static bool LoadFileToString(FString&, const TCHAR*, uint32 = 0) { return false; } };
struct FPlatformTime { static double Seconds() { return 0; } };

// ------------------------------------------------------------------ math (LWC: double)
struct FVector3f { float X = 0, Y = 0, Z = 0; FVector3f() = default; FVector3f(float InX, float InY, float InZ) : X(InX), Y(InY), Z(InZ) {} };
struct FVector4f { float X = 0, Y = 0, Z = 0, W = 0; };
struct FVector {
 double X = 0, Y = 0, Z = 0;
 static const FVector ZeroVector;
 FVector() = default;
 FVector(double InX, double InY, double InZ) : X(InX), Y(InY), Z(InZ) {}
 explicit FVector(const FVector3f& V) : X(V.X), Y(V.Y), Z(V.Z) {}
 explicit FVector(const FVector4f& V) : X(V.X), Y(V.Y), Z(V.Z) {}
 FVector operator+(const FVector& V) const { return {X + V.X, Y + V.Y, Z + V.Z}; }
 FVector operator-(const FVector& V) const { return {X - V.X, Y - V.Y, Z - V.Z}; }
 FVector operator-() const { return {-X, -Y, -Z}; }
 FVector operator*(double S) const { return {X * S, Y * S, Z * S}; }
 FVector operator/(double S) const { return {X / S, Y / S, Z / S}; }
 FVector& operator+=(const FVector& V) { X += V.X; Y += V.Y; Z += V.Z; return *this; }
 double Size() const { return std::sqrt(X * X + Y * Y + Z * Z); }
 double SizeSquared() const { return X * X + Y * Y + Z * Z; }
 double Size2D() const { return std::sqrt(X * X + Y * Y); }
 double GetMin() const { return std::min(X, std::min(Y, Z)); }
 bool ContainsNaN() const { return !(std::isfinite(X) && std::isfinite(Y) && std::isfinite(Z)); }
 bool IsNearlyZero(double = 1.e-4) const { return Size() < 1.e-4; }
 FVector GetSafeNormal(double = 1.e-8) const { const double S = Size(); return S > 0 ? *this / S : FVector(); }
 FString ToString() const { return FString(); }
 static FVector CrossProduct(const FVector& A, const FVector& B) { return {A.Y * B.Z - A.Z * B.Y, A.Z * B.X - A.X * B.Z, A.X * B.Y - A.Y * B.X}; }
 static double DotProduct(const FVector& A, const FVector& B) { return A.X * B.X + A.Y * B.Y + A.Z * B.Z; }
 static double Dist(const FVector& A, const FVector& B) { return (A - B).Size(); }
};
inline const FVector FVector::ZeroVector;
inline FVector operator*(double S, const FVector& V) { return V * S; }
struct FVector_NetQuantize : FVector { using FVector::FVector; };
struct FVector_NetQuantizeNormal : FVector { using FVector::FVector; };
struct FVector2D {
 double X = 0, Y = 0;
 static const FVector2D ZeroVector;
 FVector2D() = default;
 FVector2D(double InX, double InY) : X(InX), Y(InY) {}
 FVector2D operator+(const FVector2D& V) const { return {X + V.X, Y + V.Y}; }
 FVector2D operator-(const FVector2D& V) const { return {X - V.X, Y - V.Y}; }
 FVector2D operator*(double S) const { return {X * S, Y * S}; }
 double Size() const { return std::sqrt(X * X + Y * Y); }
 FString ToString() const { return FString(); }
 static double Distance(const FVector2D& A, const FVector2D& B) { return (A - B).Size(); }
};
inline const FVector2D FVector2D::ZeroVector;
struct FRotator {
 double Pitch = 0, Yaw = 0, Roll = 0;
 static const FRotator ZeroRotator;
 FRotator() = default;
 FRotator(double InPitch, double InYaw, double InRoll) : Pitch(InPitch), Yaw(InYaw), Roll(InRoll) {}
 FRotator operator+(const FRotator& R) const { return {Pitch + R.Pitch, Yaw + R.Yaw, Roll + R.Roll}; }
 FVector RotateVector(const FVector& V) const { return V; }
 FVector UnrotateVector(const FVector& V) const { return V; }
};
inline const FRotator FRotator::ZeroRotator;
struct FQuat {
 double X = 0, Y = 0, Z = 0, W = 1;
 static const FQuat Identity;
 FQuat() = default;
 FQuat(double InX, double InY, double InZ, double InW) : X(InX), Y(InY), Z(InZ), W(InW) {}
 FQuat operator*(const FQuat& Q) const { return Q; }
 FQuat GetNormalized(double = 1.e-8) const { return *this; }
 FVector RotateVector(const FVector& V) const { return V; }
 bool ContainsNaN() const { return !(std::isfinite(X) && std::isfinite(Y) && std::isfinite(Z) && std::isfinite(W)); }
 double SizeSquared() const { return X * X + Y * Y + Z * Z + W * W; }
};
inline const FQuat FQuat::Identity;
struct FTransform {
 FQuat Rotation; FVector Translation, Scale3D{1, 1, 1};
 FTransform() = default;
 FTransform(const FQuat& R, const FVector& T, const FVector& S = FVector(1, 1, 1)) : Rotation(R), Translation(T), Scale3D(S) {}
 FVector GetLocation() const { return Translation; }
 FQuat GetRotation() const { return Rotation; }
 FVector GetScale3D() const { return Scale3D; }
 FRotator Rotator() const { return FRotator(); }
 FVector TransformPosition(const FVector& V) const { return V; }
 FTransform operator*(const FTransform& Other) const { return Other; }
 void Blend(const FTransform& A, const FTransform&, float) { *this = A; }
};
struct FMatrix44f {
 FVector4f TransformPosition(const FVector3f& V) const { return {V.X, V.Y, V.Z, 1}; }
 FMatrix44f Inverse() const { return *this; }
 FVector3f GetOrigin() const { return FVector3f(); }
};
struct FLinearColor { float R = 0, G = 0, B = 0, A = 1; };
struct FBox {
 FVector Min, Max; uint8 IsValid = 0;
 FBox() = default;
 explicit FBox(EForceInit) {}
 FBox& operator+=(const FVector& P) { Min = P; Max = P; IsValid = 1; return *this; }
 FVector GetCenter() const { return (Min + Max) * .5; }
 FBox ExpandBy(double) const { return *this; }
 bool IsInside(const FVector&) const { return IsValid != 0; }
 FString ToString() const { return FString(); }
};
namespace Sub01Shim {
template<class A, class B> using TMixed = std::conditional_t<std::is_same_v<A, B>, A,
 std::conditional_t<(std::is_floating_point_v<A> || std::is_floating_point_v<B>) && std::is_arithmetic_v<A> && std::is_arithmetic_v<B>, double, void>>;
}
struct FMath {
 // UE: same-type templates plus float/double (and integer/floating) mixes resolved to double; two different
 // integer types are ambiguous (a compile error), as in the engine.
 template<class A, class B, class R = Sub01Shim::TMixed<A, B>> static constexpr R Min(A X, B Y) { static_assert(!std::is_void_v<R>, "FMath::Min of two different integer types"); return X < Y ? R(X) : R(Y); }
 template<class A, class B, class R = Sub01Shim::TMixed<A, B>> static constexpr R Max(A X, B Y) { static_assert(!std::is_void_v<R>, "FMath::Max of two different integer types"); return X < Y ? R(Y) : R(X); }
 template<class T> static constexpr T Min3(T A, T B, T C) { return Min(Min(A, B), C); }
 template<class A, class B, class C, class R = Sub01Shim::TMixed<Sub01Shim::TMixed<A, B>, C>> static constexpr R Clamp(A X, B Lo, C Hi) { static_assert(!std::is_void_v<R>, "FMath::Clamp of mixed integer types"); return X < Lo ? R(Lo) : (Hi < X ? R(Hi) : R(X)); }
 template<class T> static constexpr T Abs(T X) { return X < 0 ? -X : X; }
 template<class T, class U> static T Lerp(const T& A, const T& B, const U& Alpha) { return A + (B - A) * Alpha; }
 static bool IsFinite(double X) { return std::isfinite(X); }
 static double FindDeltaAngleDegrees(double A, double B) { return std::remainder(B - A, 360.); }
 static float Fmod(float X, float Y) { return std::fmod(X, Y); }
 static int32 FloorToInt(float X) { return int32(std::floor(X)); }
 static double Atan2(double Y, double X) { return std::atan2(Y, X); }
 static FVector ClosestPointOnTriangleToPoint(const FVector& Point, const FVector&, const FVector&, const FVector&) { return Point; }
};

// ------------------------------------------------------------------ JSON
class FJsonObject;
class FJsonValue {
public:
 virtual ~FJsonValue() = default;
 double AsNumber() const { return 0; }
 const TSharedPtr<FJsonObject>& AsObject() const;
 const TArray<TSharedPtr<FJsonValue>>& AsArray() const;
 bool TryGetObject(const TSharedPtr<FJsonObject>*& Out) const { Out = nullptr; return false; }
};
class FJsonObject {
public:
 TMap<FString, TSharedPtr<FJsonValue>> Values;
 bool HasField(const FString&) const { return false; }
 bool TryGetStringField(const FString&, FString&) const { return false; }
 bool TryGetBoolField(const FString&, bool&) const { return false; }
 bool TryGetNumberField(const FString&, double&) const { return false; }
 bool TryGetNumberField(const FString&, float&) const { return false; }
 bool TryGetNumberField(const FString&, int32&) const { return false; }
 bool TryGetNumberField(const FString&, uint32&) const { return false; }
 bool TryGetNumberField(const FString&, int64&) const { return false; }
 bool TryGetArrayField(const FString&, const TArray<TSharedPtr<FJsonValue>>*&) const { return false; }
 bool TryGetObjectField(const FString&, const TSharedPtr<FJsonObject>*&) const { return false; }
};
inline const TSharedPtr<FJsonObject>& FJsonValue::AsObject() const { static TSharedPtr<FJsonObject> None; return None; }
inline const TArray<TSharedPtr<FJsonValue>>& FJsonValue::AsArray() const { static TArray<TSharedPtr<FJsonValue>> None; return None; }
template<class C = TCHAR> class TJsonReader {};
template<class C = TCHAR> struct TJsonReaderFactory { static TSharedRef<TJsonReader<C>> Create(const FString&) { return {}; } };
struct FJsonSerializer { template<class C> static bool Deserialize(const TSharedRef<TJsonReader<C>>&, TSharedPtr<FJsonObject>&) { return false; } };

// ------------------------------------------------------------------ objects, components, actors
class UObject {
public:
 virtual ~UObject() = default;
 FString GetPathName() const { return FString(); }
 FString GetName() const { return FString(); }
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
};
template<class T> T* Cast(const UObject*) { return nullptr; }
template<class T> T* LoadObject(UObject*, const TCHAR*) { return nullptr; }
template<class T> T* NewObject(UObject*, FName = FName()) { return nullptr; }
class USkeleton : public UObject {};
struct FMeshBoneInfo { FName Name; int32 ParentIndex = INDEX_NONE; };
class FReferenceSkeleton {
public:
 int32 GetNum() const { return 0; }
 FName GetBoneName(int32) const { return FName(); }
 int32 FindBoneIndex(const FName&) const { return INDEX_NONE; }
 const TArray<FMeshBoneInfo>& GetRefBoneInfo() const { static TArray<FMeshBoneInfo> None; return None; }
};
struct FSoftSkinVertex { FVector3f Position; FVector3f TangentX, TangentY; FVector4f TangentZ; FBoneIndexType InfluenceBones[MAX_TOTAL_INFLUENCES] = {}; uint16 InfluenceWeights[MAX_TOTAL_INFLUENCES] = {}; };
struct FSkelMeshSection { TArray<FSoftSkinVertex> SoftVertices; TArray<FBoneIndexType> BoneMap; };
struct FSkeletalMeshLODModel { TArray<FSkelMeshSection> Sections; };
class FSkeletalMeshModel { public: TArray<FSkeletalMeshLODModel> LODModels; };
class USkeletalMesh : public UObject {
public:
 USkeleton* GetSkeleton() const { return nullptr; }
 const FReferenceSkeleton& GetRefSkeleton() const { static FReferenceSkeleton None; return None; }
 const TArray<FMatrix44f>& GetRefBasesInvMatrix() const { static TArray<FMatrix44f> None; return None; }
#if WITH_EDITOR
 FSkeletalMeshModel* GetImportedModel() const { return nullptr; }
#endif
};
class UStaticMesh : public UObject {};
class UAnimSequenceBase : public UObject { public: virtual float GetPlayLength() const { return 0; } USkeleton* GetSkeleton() const { return nullptr; } };
class UAnimSequence : public UAnimSequenceBase {};
class UWorld;
class AActor;
enum ERelativeTransformSpace { RTS_World, RTS_Actor, RTS_Component, RTS_ParentBoneSpace };
enum ECollisionChannel { ECC_WorldStatic, ECC_WorldDynamic, ECC_Pawn, ECC_Visibility, ECC_Camera };
namespace ECollisionEnabled { enum Type { NoCollision, QueryOnly, PhysicsOnly, QueryAndPhysics }; }
namespace EComponentMobility { enum Type { Static, Stationary, Movable }; }
namespace EEndPlayReason { enum Type { Destroyed, LevelTransition, EndPlayInEditor, RemovedFromWorld, Quit }; }
enum class ETeleportType : uint8 { None, TeleportPhysics, ResetPhysics };
enum EMovementMode { MOVE_None, MOVE_Walking, MOVE_NavWalking, MOVE_Falling, MOVE_Swimming, MOVE_Flying, MOVE_Custom };
struct FAttachmentTransformRules { static const FAttachmentTransformRules KeepWorldTransform; static const FAttachmentTransformRules SnapToTargetNotIncludingScale; };
inline const FAttachmentTransformRules FAttachmentTransformRules::KeepWorldTransform;
inline const FAttachmentTransformRules FAttachmentTransformRules::SnapToTargetNotIncludingScale;
class UActorComponent : public UObject {
public:
 void RegisterComponent() {}
protected:
 virtual void EndPlay(const EEndPlayReason::Type) {}
};
class USceneComponent : public UActorComponent {
public:
 const FTransform& GetComponentTransform() const { static FTransform None; return None; }
 FVector GetComponentLocation() const { return FVector(); }
 USceneComponent* GetAttachParent() const { return nullptr; }
 FTransform GetSocketTransform(FName, ERelativeTransformSpace = RTS_World) const { return FTransform(); }
 bool AttachToComponent(USceneComponent*, const FAttachmentTransformRules&, FName = NAME_None) { return true; }
 void SetupAttachment(USceneComponent*, FName = NAME_None) {}
 void SetUsingAbsoluteLocation(bool) {}
 void SetUsingAbsoluteRotation(bool) {}
 void SetWorldLocation(const FVector&, bool = false, struct FHitResult* = nullptr, ETeleportType = ETeleportType::None) {}
 void SetWorldLocationAndRotation(FVector, const FQuat&, bool = false, struct FHitResult* = nullptr, ETeleportType = ETeleportType::None) {}
 void SetRelativeLocation(FVector, bool = false, struct FHitResult* = nullptr, ETeleportType = ETeleportType::None) {}
 void SetRelativeRotation(FRotator, bool = false, struct FHitResult* = nullptr, ETeleportType = ETeleportType::None) {}
 void SetVisibility(bool, bool = false) {}
 void SetMobility(EComponentMobility::Type) {}
};
class UPrimitiveComponent : public USceneComponent { public: void SetCollisionEnabled(ECollisionEnabled::Type) {} };
class UMeshComponent : public UPrimitiveComponent {};
class UStaticMeshComponent : public UMeshComponent { public: bool SetStaticMesh(UStaticMesh*) { return true; } };
class UAnimInstance;
class USkinnedMeshComponent : public UMeshComponent {
public:
 USkeletalMesh* GetSkeletalMeshAsset() const { return nullptr; }
 const TArray<FTransform>& GetComponentSpaceTransforms() const { static TArray<FTransform> None; return None; }
 FVector GetBoneLocation(FName, ERelativeTransformSpace = RTS_World) const { return FVector(); }
};
class USkeletalMeshComponent : public USkinnedMeshComponent { public: UAnimInstance* GetAnimInstance() const { return nullptr; } };
class UCameraComponent : public USceneComponent {};
class USceneCaptureComponent2D : public USceneComponent {};
class UTextureRenderTarget2D : public UObject {};
class UMaterialInstanceDynamic : public UObject {};
class UInputComponent : public UActorComponent {};
struct FHitResult {
 uint8 bBlockingHit : 1 = 0; uint8 bStartPenetrating : 1 = 0;
 FVector_NetQuantize ImpactPoint; FVector_NetQuantizeNormal ImpactNormal;
 UPrimitiveComponent* GetComponent() const { return nullptr; }
};
struct FCollisionQueryParams { FCollisionQueryParams(FName, bool = false, const AActor* = nullptr) {} };
class UWorld : public UObject {
public:
 bool LineTraceSingleByChannel(FHitResult&, const FVector&, const FVector&, ECollisionChannel, const FCollisionQueryParams&) const { return false; }
};
class UCharacterMovementComponent : public UActorComponent {
public:
 TEnumAsByte<EMovementMode> MovementMode;
 bool IsMovingOnGround() const { return true; }
 void StopMovementImmediately() {}
 void DisableMovement() {}
 void SetMovementMode(EMovementMode, uint8 = 0) {}
 bool MoveUpdatedComponent(const FVector&, const FQuat&, bool, FHitResult* = nullptr, ETeleportType = ETeleportType::None) { return true; }
};
class AController : public UObject { public: FRotator GetControlRotation() const { return FRotator(); } void SetControlRotation(const FRotator&) {} };
class AActor : public UObject {
public:
 FVector GetActorLocation() const { return FVector(); }
 FRotator GetActorRotation() const { return FRotator(); }
 FQuat GetActorQuat() const { return FQuat(); }
 USceneComponent* GetRootComponent() const { return nullptr; }
 UWorld* GetWorld() const { return nullptr; }
 FVector GetVelocity() const { return FVector(); }
 void AddInstanceComponent(UActorComponent*) {}
 virtual void BeginPlay() {}
 virtual void Tick(float) {}
};
class APawn : public AActor {
public:
 uint32 bUseControllerRotationYaw : 1 = 1;
 TObjectPtr<AController> Controller;
 virtual void AddMovementInput(FVector, float = 1.f, bool = false) {}
 virtual void SetupPlayerInputComponent(UInputComponent*) {}
};
class ACharacter : public APawn { public: UCharacterMovementComponent* GetCharacterMovement() const { return nullptr; } };
class AGameModeBase : public AActor {};
struct FTimerHandle {};

// ------------------------------------------------------------------ animation
class FAnimInstanceProxy;
class UAnimInstance : public UObject {
protected:
 virtual FAnimInstanceProxy* CreateAnimInstanceProxy() { return nullptr; }
 virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy*) {}
};
struct FAnimationInitializeContext { explicit FAnimationInitializeContext(FAnimInstanceProxy*) {} };
struct FAnimationCacheBonesContext { explicit FAnimationCacheBonesContext(FAnimInstanceProxy*) {} };
struct FAnimationUpdateContext {};
struct FMeshPoseBoneIndex { explicit FMeshPoseBoneIndex(int32 I) : Index(I) {} int32 Index; };
struct FCompactPoseBoneIndex { int32 Index = INDEX_NONE; int32 GetInt() const { return Index; } };
struct FBoneContainer {
 const FReferenceSkeleton& GetReferenceSkeleton() const { static FReferenceSkeleton None; return None; }
 FCompactPoseBoneIndex MakeCompactPoseIndex(const FMeshPoseBoneIndex&) const { return {}; }
};
struct FCompactPose {
 const FBoneContainer& GetBoneContainer() const { static FBoneContainer None; return None; }
 FTransform& operator[](FCompactPoseBoneIndex) { static FTransform None; return None; }
};
struct FPoseContext { FCompactPose Pose; };
struct FAnimNode_Base { virtual ~FAnimNode_Base() = default; };
struct FPoseLink { void SetLinkNode(FAnimNode_Base*) {} };
struct FAnimNode_SequencePlayer_Standalone : FAnimNode_Base {
 UAnimSequenceBase* GetSequence() const { return nullptr; }
 bool SetSequence(UAnimSequenceBase*) { return true; }
 bool SetAccumulatedTime(float) { return true; }
 float GetAccumulatedTime() const { return 0; }
 bool SetPlayRate(float) { return true; }
 bool SetLoopAnimation(bool) { return true; }
 bool IsLooping() const { return true; }
};
struct FAnimNode_TwoWayBlend : FAnimNode_Base {
 FPoseLink A, B; float Alpha = 0;
 void Initialize_AnyThread(const FAnimationInitializeContext&) {}
 void CacheBones_AnyThread(const FAnimationCacheBonesContext&) {}
 void Update_AnyThread(const FAnimationUpdateContext&) {}
 void Evaluate_AnyThread(FPoseContext&) {}
};
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

# UE header names the shim must answer: each becomes a file that includes the shim. The allowlist itself is derived
# by the checker from the freshly staged (pre-install) module; this is only what the shim provides behind them.


def write(directory: Path, ue_headers, generated_headers=()) -> Path:
    """Write the shim and one forwarding file per allowed UE header (and empty *.generated.h) under directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SHIM_NAME).write_text(SHIM)
    for name in sorted(set(ue_headers)):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#pragma once\n#include "{SHIM_NAME}"\n')
    for name in sorted(set(generated_headers)):
        (directory / name).write_text('#pragma once\n')
    return directory
