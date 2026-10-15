"""A concurrent guard must never see the replacement-unlink gap of Move()."""
import shutil
import subprocess
import pytest
import unreal_native_view_settings as view


def test_compiled_actual_privacy_replacement_stays_complete_under_readers(tmp_path):
    compiler=shutil.which('c++')
    if not compiler:pytest.skip('C++ compiler unavailable')
    cpp=tmp_path/'atomic.cpp';exe=tmp_path/'atomic'
    cpp.write_text(r'''#include <cstdio>
#include <fstream>
#include <atomic>
#include <thread>
#include <cassert>
#include <string>
int main(int argc,char**argv){
 std::string dest=std::string(argv[1])+"/receipt.json",temp=dest+".tmp";
 const std::string a="{\"private\":false,\"generation\":0}\n",b="{\"private\":true,\"generation\":1}\n";
 {std::ofstream f(dest);f<<a;}
 std::atomic<bool> done{false};std::atomic<unsigned> checks{0};
 std::thread reader([&]{while(!done){std::ifstream f(dest);assert(f.is_open());std::string text((std::istreambuf_iterator<char>(f)),{});assert(text==a||text==b);++checks;}});
 for(int i=0;i<5000;i++){{std::ofstream f(temp);f<<(i%2?a:b);}assert(std::rename(temp.c_str(),dest.c_str())==0);}
 done=true;reader.join();assert(checks>0);
 // Failed replacement leaves the previous complete target intact.
 assert(std::rename((temp+"missing").c_str(),dest.c_str())!=0);
 std::ifstream f(dest);std::string text((std::istreambuf_iterator<char>(f)),{});assert(text==a||text==b);
}''')
    subprocess.run([compiler,'-std=c++17','-pthread',str(cpp),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run([str(exe),str(tmp_path)],check=True,capture_output=True)


def test_real_publisher_uses_same_directory_atomic_rename_without_guard_changes():
    body=view.METHODS.split('void ASub01HomeCharacter::PublishPrivateNativeCameraPrivacy',1)[1].split('AActor* ASub01HomeCharacter::FindAuthoredSettingsActor',1)[0]
    assert 'std::rename(TCHAR_TO_UTF8(*Temp),"/home/unreal/.sub01-private/native-view-privacy.json")' in body
    assert 'IFileManager::Get().Move' not in body
    assert 'Receipt->SetBoolField(TEXT("physical_camera_private"),Hidden)' in body
    assert 'Now-NativePrivacyPublishedAt<.2' in body
