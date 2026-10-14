"""Execute the actual native blocked-route recovery against the actual source graph.

The generated FIELDS and the route/recovery/update methods are compiled unchanged
against small UE stand-ins. A test world moves the pawn only from the movement
input it requests (no teleport) and can place round obstacles on graph edges.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_live_home_runtime as live  # noqa: E402
from home_world import NODES  # noqa: E402

COMPILED = ('FindLiveHomePath', 'PlanLiveHome', 'BlockLiveHome', 'RecoverLiveHome', 'UpdateLiveHome')


def methods(names):
    """The named ASub01HomeCharacter definitions, verbatim from METHODS."""
    starts = [(m.start(), m.group(1)) for m in re.finditer(
        r'^(?:void|bool|const TCHAR\*) ASub01HomeCharacter::(\w+)\(', live.METHODS, re.M)]
    bounds = starts + [(len(live.METHODS), None)]
    found = {name: live.METHODS[a:b] for (a, name), (b, _) in zip(bounds, bounds[1:])}
    missing = [n for n in names if n not in found]
    assert not missing, missing
    return ''.join(found[n] for n in names)


STUBS = r'''
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>
#define TEXT(x) x
#define BIG_NUMBER 3.4e38f
using int32 = int; using int64 = long long; using TCHAR = char;
double SimNow = 0; std::vector<std::string> Logs;
#define UE_LOG(Category, Verbosity, Format, ...) do { char B[1024]; std::snprintf(B, sizeof B, Format, ##__VA_ARGS__); Logs.push_back(B); } while (0)
struct FPlatformTime { static double Seconds() { return SimNow; } };
struct FString : std::string {
  FString() {} FString(const char* s) : std::string(s) {} FString(const std::string& s) : std::string(s) {}
  const char* operator*() const { return c_str(); } bool IsEmpty() const { return empty(); } void Empty() { clear(); }
};
template <class T> T&& MoveTemp(T& x) { return std::move(x); }
template <class T> struct TArray {
  std::vector<T> V;
  int32 Num() const { return (int32)V.size(); } void Add(const T& x) { V.push_back(x); }
  void AddUnique(const T& x) { if (std::find(V.begin(), V.end(), x) == V.end()) V.push_back(x); }
  void Insert(const T& x, int32 i) { V.insert(V.begin() + i, x); } void RemoveAt(int32 i) { V.erase(V.begin() + i); }
  T& operator[](int32 i) { return V[i]; } const T& operator[](int32 i) const { return V[i]; } void Empty() { V.clear(); }
  typename std::vector<T>::const_iterator begin() const { return V.begin(); } typename std::vector<T>::const_iterator end() const { return V.end(); }
};
template <class K, class W> struct TMap {
  std::map<K, W> M;
  void Add(const K& k, const W& v) { M[k] = v; } bool Contains(const K& k) const { return M.count(k) > 0; }
  W& FindChecked(const K& k) { return M.at(k); } const W& FindChecked(const K& k) const { return M.at(k); }
  const W* Find(const K& k) const { auto i = M.find(k); return i == M.end() ? nullptr : &i->second; }
  W& FindOrAdd(const K& k) { return M[k]; } void Empty() { M.clear(); }
};
template <class T> struct TSet {
  std::set<T> S; void Add(const T& x) { S.insert(x); } bool Contains(const T& x) const { return S.count(x) > 0; }
  void Empty() { S.clear(); } int32 Num() const { return (int32)S.size(); }
};
struct FRotator { double Pitch, Yaw, Roll; FRotator(double p, double y, double r) : Pitch(p), Yaw(y), Roll(r) {} };
struct FVector {
  double X = 0, Y = 0, Z = 0; FVector() {} FVector(double x, double y, double z) : X(x), Y(y), Z(z) {}
  double Size() const { return std::sqrt(X * X + Y * Y + Z * Z); }
  static double Dist(const FVector& a, const FVector& b) { return FVector(a.X - b.X, a.Y - b.Y, a.Z - b.Z).Size(); }
  FVector operator/(double s) const { return FVector(X / s, Y / s, Z / s); }
  FRotator Rotation() const { return FRotator(0, std::atan2(Y, X) * 57.29577951308232, 0); }
  FString ToString() const { char B[96]; std::snprintf(B, sizeof B, "X=%.1f Y=%.1f Z=%.1f", X, Y, Z); return FString(B); }
};
struct FMath {
  template <class T> static T Abs(T v) { return v < 0 ? -v : v; }
  template <class T> static T Clamp(T v, T lo, T hi) { return v < lo ? lo : (v > hi ? hi : v); }
};
struct FHitResult { FVector ImpactPoint; }; struct FFindFloorResult { bool bBlockingHit = true; FHitResult HitResult; };
struct FMovement { FFindFloorResult CurrentFloor; int Stops = 0; bool IsMovingOnGround() const { return true; } void StopMovementImmediately() { ++Stops; } };
struct FCapsule { float GetScaledCapsuleHalfHeight() const { return 91; } };
struct FController { void SetControlRotation(const FRotator&) {} };
struct FPCBridge { bool Focus = false; void SetOperatorFocus(bool v) { Focus = v; } void SetLocalPrivacy(bool) {} };
class FJsonObject; template <class T> struct TSharedPtr {};
struct ASub01HomeCharacter {
@@FIELDS@@
  FVector Pos, Input; FMovement Move; FCapsule Capsule; FController Control; FController* Controller = &Control;
  FPCBridge Bridge; FPCBridge* PCBridge = &Bridge;
  FVector GetActorLocation() const { return Pos; }
  FMovement* GetCharacterMovement() { return &Move; } FCapsule* GetCapsuleComponent() { return &Capsule; }
  void AddMovementInput(const FVector& Direction, float Scale) { Input = FVector(Direction.X * Scale, Direction.Y * Scale, 0); }
};
void ASub01HomeCharacter::BeginLiveHome() {} void ASub01HomeCharacter::PollLiveHome() {}
void ASub01HomeCharacter::UpdateNativeFeedback() {} bool ASub01HomeCharacter::NativeFeedbackSeatReady() const { return false; }
@@METHODS@@
void Graph(ASub01HomeCharacter& C) {
  auto& LiveHomeNodes = C.LiveHomeNodes; auto& LiveHomeEdges = C.LiveHomeEdges;
@@GRAPH@@
}
'''

WORLD = r'''
struct Obstacle { double X, Y, R, From, To; };
int main(int argc, char** argv) {
  // argv: start target private obstacles... (each "a,b,from,to" on the midpoint of edge a-b)
  ASub01HomeCharacter C; Graph(C);
  C.LiveHome = true; C.LiveHomeFresh = true; C.LiveHomePollAt = 1e30; C.LiveHomeNode = argv[1];
  C.LiveHomePrivate = std::string(argv[3]) == "1";
  std::string StaleFrom = argv[4], StaleTo = argv[5], Retarget = argv[6];
  double StaleA = std::stod(StaleFrom), StaleB = std::stod(StaleTo);
  std::vector<Obstacle> Obstacles;
  for (int i = 7; i < argc; ++i) {
    std::string s = argv[i]; size_t p1 = s.find(','), p2 = s.find(',', p1 + 1), p3 = s.find(',', p2 + 1);
    FVector A = C.LiveHomeNodes.FindChecked(s.substr(0, p1)), B = C.LiveHomeNodes.FindChecked(s.substr(p1 + 1, p2 - p1 - 1));
    Obstacles.push_back({(A.X + B.X) / 2, (A.Y + B.Y) / 2, 18, std::stod(s.substr(p2 + 1, p3 - p2 - 1)), std::stod(s.substr(p3 + 1))});
  }
  C.Pos = C.LiveHomeNodes.FindChecked(C.LiveHomeNode);
  C.PlanLiveHome(argv[2]);
  const double Dt = 0.05, Speed = 150; double MaxStep = 0, BlockedFor = 0, MaxBlockedHold = 0;
  std::vector<std::string> Reached; std::string Last = C.LiveHomeNode; bool Retargeted = false; int BlockedTicks = 0; double FirstBlocked = -1;
  for (int Tick = 0; Tick < 2400; ++Tick) {  // 120 simulated seconds
    SimNow += Dt;
    bool Stale = SimNow >= StaleA && SimNow < StaleB; C.LiveHomeFresh = !Stale; if (!Stale) C.LiveHomeLastReceived = SimNow;
    if (!Retarget.empty() && !Retargeted && SimNow >= 90) { C.PlanLiveHome(Retarget.c_str()); Retargeted = true; }
    // Perfect floor contact under the waypoint being walked to.
    C.Move.CurrentFloor.HitResult.ImpactPoint.Z = C.LiveHomeNodes.FindChecked(C.LiveHomePath.Num() ? C.LiveHomePath[0] : C.LiveHomeNode).Z;
    C.Input = FVector(); C.UpdateLiveHome((float)Dt);
    FVector Step(C.Input.X * Speed * Dt, C.Input.Y * Speed * Dt, 0), Next(C.Pos.X + Step.X, C.Pos.Y + Step.Y, C.Pos.Z);
    bool Hit = false;
    for (auto& O : Obstacles) {
      if (SimNow < O.From || SimNow >= O.To) continue;
      double Now = std::hypot(C.Pos.X - O.X, C.Pos.Y - O.Y), After = std::hypot(Next.X - O.X, Next.Y - O.Y);
      if (After < O.R && After < Now) Hit = true;  // may always move away from an obstacle
    }
    if (!Hit) { MaxStep = std::max(MaxStep, Step.Size()); C.Pos = Next; }
    if (C.LiveHomeNode != Last) { Reached.push_back(C.LiveHomeNode); Last = C.LiveHomeNode; }
    if (C.LiveHomeBlocked) { if (FirstBlocked < 0) FirstBlocked = SimNow; ++BlockedTicks; BlockedFor += Dt; MaxBlockedHold = std::max(MaxBlockedHold, BlockedFor); } else BlockedFor = 0;
  }
  std::printf("{\"node\":\"%s\",\"target\":\"%s\",\"remaining\":%d,\"blocked\":%d,\"recoveries\":%d,\"recover_at\":%.3f,"
              "\"max_step\":%.4f,\"max_blocked_hold\":%.3f,\"blocked_ticks\":%d,\"first_blocked\":%.2f,\"focus\":%d,\"pos\":[%.2f,%.2f],\"reached\":[",
              *C.LiveHomeNode, *C.LiveHomeTarget, C.LiveHomePath.Num(), C.LiveHomeBlocked ? 1 : 0, C.LiveHomeRecoveries,
              C.LiveHomeRecoverAt, MaxStep, MaxBlockedHold, BlockedTicks, FirstBlocked, C.Bridge.Focus ? 1 : 0, C.Pos.X, C.Pos.Y);
  for (size_t i = 0; i < Reached.size(); ++i) std::printf("%s\"%s\"", i ? "," : "", Reached[i].c_str());
  std::printf("],\"logs\":[");
  for (size_t i = 0; i < Logs.size(); ++i) {
    std::string L; for (char c : Logs[i]) { if (c == '"' || c == '\\') L += '\\'; L += c; }
    std::printf("%s\"%s\"", i ? "," : "", L.c_str());
  }
  std::printf("]}\n");
}
'''


class LiveHomeRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable')
        cls.tmp = tempfile.TemporaryDirectory()
        source = (STUBS.replace('@@FIELDS@@', live.FIELDS).replace('@@METHODS@@', methods(COMPILED))
                  .replace('@@GRAPH@@', live.graph_source()) + WORLD)
        cpp = Path(cls.tmp.name) / 'recovery.cpp'
        cpp.write_text(source)
        cls.exe = Path(cls.tmp.name) / 'recovery'
        built = subprocess.run([compiler, '-std=c++17', '-O1', str(cpp), '-o', str(cls.exe)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stderr[-4000:])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def walk(self, start, target, *obstacles, private=False, stale=(-1, -1), retarget=''):
        args = [str(self.exe), start, target, '1' if private else '0', str(stale[0]), str(stale[1]), retarget]
        args += [f'{a},{b},{t0},{t1}' for a, b, t0, t1 in obstacles]
        out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
        return json.loads(out)

    def blocked_logs(self, run):
        return [log for log in run['logs'] if log.startswith('SUB01_LIVE_HOME_BLOCKED')]

    def recoveries(self, run):
        return [log for log in run['logs'] if log.startswith('SUB01_LIVE_HOME_RECOVERY')]

    def assert_physical(self, run):
        # Only requested movement input moved the pawn: never more than one walking step per tick.
        self.assertLessEqual(run['max_step'], 150 * 0.05 + 1e-6)
        self.assertFalse(run['focus'])

    def test_unobstructed_route_is_unchanged(self):
        run = self.walk('door', 'desk')
        self.assertEqual(run['reached'], ['front', 'aisle', 'desk'])
        self.assertEqual((run['node'], run['remaining'], run['blocked'], run['recoveries']), ('desk', 0, 0, 0))
        self.assertEqual(self.blocked_logs(run), [])
        self.assert_physical(run)

    def test_transient_obstruction_is_recorded_then_retried_from_reached_endpoint(self):
        run = self.walk('door', 'desk', ('front', 'aisle', 0, 9))
        self.assertEqual(run['node'], 'desk')
        self.assertEqual((run['remaining'], run['blocked'], run['recoveries']), (0, 0, 1))
        blocked = self.blocked_logs(run)
        self.assertEqual(len(blocked), 1)
        self.assertIn('node=front next=aisle target=desk attempt=0/2 final=0', blocked[0])
        # The real blocked state is held long enough for the 0.5 s feedback sender to report it.
        self.assertGreaterEqual(run['max_blocked_hold'], 1.0)
        self.assertIn('mode=retry from=front target=desk attempt=1/2', self.recoveries(run)[0])
        self.assertEqual(run['reached'], ['front', 'aisle', 'desk'])   # back to front (already its node), then on
        self.assert_physical(run)

    def test_persistent_obstruction_replans_around_the_blocked_edge(self):
        run = self.walk('door', 'desk', ('front', 'aisle', 0, 1e9))
        self.assertEqual((run['node'], run['remaining'], run['blocked']), ('desk', 0, 0))
        self.assertEqual(run['recoveries'], 2)
        modes = [re.search(r'mode=(\w+)', log).group(1) for log in self.recoveries(run)]
        self.assertEqual(modes, ['retry', 'replan'])
        reached = run['reached']
        self.assertNotIn(('front', 'aisle'), list(zip(reached, reached[1:])))
        self.assertIn('kitchen_gate', reached)          # the actual alternative through the house
        self.assertEqual(reached[-2:], ['aisle', 'desk'])
        self.assert_physical(run)

    def test_dead_end_stays_really_blocked_after_bounded_attempts(self):
        run = self.walk('door', 'desk', ('aisle', 'desk', 0, 1e9))
        self.assertEqual((run['node'], run['target'], run['blocked']), ('aisle', 'desk', 1))
        self.assertEqual(run['recoveries'], 2)
        self.assertEqual(run['recover_at'], 0)          # no further automatic attempt
        blocked = self.blocked_logs(run)
        self.assertTrue(any('final=1' in log for log in blocked))
        self.assertLessEqual(len(blocked), 3)           # bounded: no retry loop
        self.assertLessEqual(abs(run['pos'][0] - NODES['aisle'][0] * 100) + abs(run['pos'][1] - NODES['aisle'][2] * 100), 60)
        self.assert_physical(run)

    def test_privacy_only_retries_and_never_detours(self):
        # loft -> bath_aisle has an alternative through the bedroom; under privacy it is not taken.
        run = self.walk('loft', 'bathroom', ('loft', 'bath_aisle', 0, 1e9), private=True)
        self.assertEqual(run['blocked'], 1)
        self.assertNotIn('bed', run['reached'])
        modes = [re.search(r'mode=(\w+)', log).group(1) for log in self.recoveries(run)]
        self.assertTrue(modes and set(modes) == {'retry'})
        self.assert_physical(run)
        # The same obstruction without privacy is detoured through the bedroom.
        public = self.walk('loft', 'bathroom', ('loft', 'bath_aisle', 0, 1e9))
        self.assertEqual((public['node'], public['blocked']), ('bathroom', 0))
        self.assertIn('bed', public['reached'])

    def test_recovery_waits_for_a_fresh_command(self):
        # The stall is recorded at ~5.9 s; the command is stale from 6.2 s to 12 s, so the
        # retry (due at ~6.9 s) waits until the command is fresh again.
        run = self.walk('door', 'desk', ('front', 'aisle', 0, 9), stale=(6.2, 12))
        self.assertLess(run['first_blocked'], 6.2)
        self.assertEqual((run['node'], run['blocked'], run['recoveries']), ('desk', 0, 1))
        self.assertGreaterEqual(run['max_blocked_hold'], 12 - run['first_blocked'] - 0.06)
        self.assert_physical(run)

    def test_stall_on_the_way_back_is_final(self):
        # Blocked ahead; then the way back to the reached endpoint is obstructed too.
        run = self.walk('door', 'desk', ('front', 'aisle', 0, 1e9), ('door', 'front', 0, 1e9), ('aisle', 'desk', 0, 1e9))
        self.assertEqual(run['blocked'], 1)
        self.assertEqual(run['recover_at'], 0)

    def test_new_command_clears_blocked_state_and_budget(self):
        run = self.walk('door', 'desk', ('aisle', 'desk', 0, 1e9), retarget='front')
        # Planned from the endpoint actually reached (aisle), not through the blocked edge.
        self.assertEqual(run['reached'], ['front', 'aisle', 'front'])
        self.assertEqual((run['node'], run['target'], run['blocked'], run['recoveries'], run['remaining']), ('front', 'front', 0, 0, 0))
        self.assert_physical(run)

    def test_source_contract(self):
        c = live.METHODS
        self.assertNotIn('SetActorLocation', c)
        self.assertNotIn('Teleport', c)
        self.assertNotIn('NativeSeatVerified=true', c)
        self.assertIn('static constexpr int32 LiveHomeMaxRecoveries=2', live.FIELDS)
        self.assertIn('Replan=LiveHomeRecoveries>1&&!LiveHomePrivate', c)
        self.assertIn('if(Now-LiveHomeProgressAt>4){BlockLiveHome(Next,Now);return;}', c)


if __name__ == '__main__':
    unittest.main()
