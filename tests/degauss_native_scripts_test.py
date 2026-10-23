#!/usr/bin/env python3
"""Check the production native Scripts transitions, not a replacement launcher."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / "menu.cpp").read_text()
helpers = source[source.index("static bool degauss_native_script_request("):source.index("\nvoid process_addon(")]
cases = source[source.index("\tcase MENU_SCRIPTS_FB:"):source.index("\tcase MENU_BTPAIR2:")]
fixture = r'''
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>
static bool degauss_running = false, degauss_resume_after_script = false;
static bool degauss_starting_script_return = false;
static constexpr int DEGAUSS_NATIVE_SCRIPT_EXIT = 42;
static constexpr const char *DEGAUSS_SCRIPT_RETURN = "RETURN_PATH";
enum { MENU_SCRIPTS_FB = 1, MENU_SCRIPTS_FB2, MENU_SYSTEM1, MENU_SCRIPTS };
static constexpr int DISABLE_KEYBOARD = 1, UPSTROKE = 0x8000;
static int menustate = MENU_SCRIPTS_FB, menusub = 0, c = 0;
static char selPath[1024] = {}, Selected_F[16][1024] = {};
static pid_t ttypid = 0;
static int ttystatus = 0, next_status = 0;
static struct { int fb_terminal = 1; } cfg;
static std::string saved_command, reported_error;
static bool fail_save = false, fail_fork = false;
static std::vector<int> terminal_calls;
static bool degauss_is_frontend_script(const char *p) { return !strcmp(p, "Scripts/degauss.sh"); }
static const char *getFullPath(const char *p) { return p; }
static void video_set_degauss_native_fb(bool n) { terminal_calls.push_back(n ? 10 : 11); }
static int video_chvt(int n) { terminal_calls.push_back(20 + n); return n; }
static int video_fb_enable(int n) { terminal_calls.push_back(30 + n); return 1; }
static void video_menu_bg(int) { terminal_calls.push_back(40); }
static void vga_nag(bool n) { terminal_calls.push_back(n ? 50 : 51); }
static int user_io_status_get(const char*) { return 0; }
static void user_io_osd_key_enable(int) {}
static void OsdClear() {}
static void OsdEnable(int) {}
static void OsdSetSize(int n) { assert(n == 16); }
static void OsdSetTitle(const char*, int) {}
static void OsdWrite(int row, const char *s) { if (row == 1) reported_error = s; }
static int FileSave(const char *p, void *data, int size) {
    assert(!strcmp(p, "/tmp/script"));
    saved_command.assign(static_cast<char*>(data), size);
    return fail_save ? 0 : size;
}
static pid_t test_fork() {
    if (fail_fork) { errno = EAGAIN; return -1; }
    return 123;
}
static pid_t test_waitpid(pid_t child, int *status, int options) {
    assert(child == 123 && options == WNOHANG);
    *status = next_status;
    return child;
}
#define fork test_fork
#define waitpid test_waitpid
''' + helpers + r'''
static void step() {
    switch (menustate) {
''' + cases + r'''
    }
}
static void reset() {
    degauss_running = degauss_resume_after_script = degauss_starting_script_return = false;
    menustate = MENU_SCRIPTS_FB;
    ttypid = 0;
    c = 0;
    terminal_calls.clear();
    saved_command.clear();
    reported_error.clear();
    fail_save = fail_fork = false;
}
static void write_file(const char *path, const std::string &body, bool executable = false) {
    FILE *file = fopen(path, "wb"); assert(file);
    assert(fwrite(body.data(), 1, body.size(), file) == body.size());
    assert(!fclose(file));
    if (executable) assert(!chmod(path, 0700));
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string directory = argv[1];
    const std::string selected = directory + "/A 'quoted' script.sh";
    const std::string output = directory + "/cwd";
    write_file(selected.c_str(), "#!/bin/bash\npwd > '" + output + "'\nexit 7\n", true);
    write_file(DEGAUSS_SCRIPT_RETURN, "#!/bin/bash\nexit 0\n", true);
    const std::string record = std::string("script\0", 7) + selected;
    write_file("REQUEST_PATH", record);

    reset();
    degauss_running = true;
    menustate = MENU_SCRIPTS_FB2;
    ttypid = 123;
    next_status = DEGAUSS_NATIVE_SCRIPT_EXIT << 8;
    step();
    assert(!degauss_running && degauss_resume_after_script);
    assert(menustate == MENU_SCRIPTS_FB && ttypid == 0);
    assert(selected == selPath);
    assert((terminal_calls == std::vector<int>{11, 40, 30}));

    terminal_calls.clear();
    step();
    const auto native_calls = terminal_calls;
    assert((native_calls == std::vector<int>{11, 22, 31, 50}));
    assert(menustate == MENU_SCRIPTS_FB2 && !degauss_running && ttypid == 123);
    assert(saved_command.find("LAUNCH_ORIGIN_ID=degauss") != std::string::npos);
    assert(saved_command.find("/bin/bash -- ") == std::string::npos);
    assert(saved_command.find("Press any key to continue") != std::string::npos);
    const std::string command = directory + "/native-script.sh";
    write_file(command.c_str(), saved_command, true);
    assert(system(command.c_str()) == 0);
    FILE *cwd = fopen(output.c_str(), "rb"); assert(cwd);
    char line[2048] = {}; assert(fgets(line, sizeof(line), cwd)); fclose(cwd);
    assert(std::string(line) == directory + "\n");

    next_status = 0;
    step();
    assert(ttypid == 0 && menustate == MENU_SCRIPTS_FB2);
    step();
    assert(menustate == MENU_SCRIPTS_FB2);
    c = UPSTROKE;
    step();
    assert(!degauss_resume_after_script && degauss_starting_script_return);
    assert(menustate == MENU_SCRIPTS_FB && !strcmp(selPath, DEGAUSS_SCRIPT_RETURN));
    c = 0;
    step();
    assert(degauss_running && !degauss_starting_script_return);
    assert(selected == Selected_F[0]);
    assert(saved_command.find(DEGAUSS_SCRIPT_RETURN) != std::string::npos);
    assert(saved_command.find("Press any key") == std::string::npos);

    reset();
    snprintf(selPath, sizeof(selPath), "%s", selected.c_str());
    step();
    assert(terminal_calls == native_calls); // Same native terminal path as OSD selection.
    assert(saved_command.find("LAUNCH_ORIGIN_ID") == std::string::npos);

    reset();
    assert(!chmod(selected.c_str(), 0600));
    degauss_resume_after_script = true;
    step();
    assert(saved_command.find("/bin/bash -- ") != std::string::npos);

    reset();
    degauss_resume_after_script = true;
    fail_save = true;
    step();
    assert(ttypid == 0 && menustate == MENU_SCRIPTS_FB2);
    assert(reported_error == "Cannot write script launcher");
    assert(!degauss_running);
    assert((terminal_calls == std::vector<int>{11, 22, 31, 50, 11, 40, 30}));
    c = UPSTROKE;
    step();
    assert(menustate == MENU_SCRIPTS_FB && degauss_starting_script_return);
    fail_save = false;
    c = 0;
    step();
    assert(degauss_running);
    reset();
    degauss_starting_script_return = true;
    fail_save = true;
    step();
    assert(ttypid == 0 && menustate == MENU_SCRIPTS_FB2 && !degauss_running);
    assert(reported_error == "Cannot write script launcher");
    assert((terminal_calls == std::vector<int>{10, 22, 31, 51, 11, 40, 30}));
    c = UPSTROKE;
    step();
    assert(menustate == MENU_SYSTEM1);
    reset();
    degauss_resume_after_script = true;
    fail_fork = true;
    step();
    assert(ttypid == 0 && menustate == MENU_SCRIPTS_FB2);
    assert(reported_error == "Cannot start native script");
    c = UPSTROKE;
    step();
    assert(menustate == MENU_SCRIPTS_FB && degauss_starting_script_return);

    reset();
    write_file("REQUEST_PATH", "malformed");
    degauss_running = true;
    menustate = MENU_SCRIPTS_FB2;
    ttypid = 123;
    next_status = DEGAUSS_NATIVE_SCRIPT_EXIT << 8;
    step();
    assert(!reported_error.empty() && !degauss_resume_after_script);
    assert(menustate == MENU_SCRIPTS_FB2);
    c = UPSTROKE;
    step();
    assert(menustate == MENU_SYSTEM1);
}
'''

with tempfile.TemporaryDirectory(prefix="degauss-native-scripts-") as directory:
    request = str(Path(directory) / "request")
    return_path = str(Path(directory) / "return.sh")
    fixture = fixture.replace('"/tmp/degauss.resume"', '"REQUEST_PATH"')
    fixture = fixture.replace("REQUEST_PATH", request).replace("RETURN_PATH", return_path)
    fixture = fixture.replace("#include <sys/wait.h>", "#include <sys/wait.h>\n#include <sys/stat.h>")
    source_path = Path(directory) / "test.cpp"
    executable = Path(directory) / "test"
    source_path.write_text(fixture)
    subprocess.run([os.environ.get("CXX", "c++"), "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    str(source_path), "-o", str(executable)], check=True)
    subprocess.run([str(executable), directory], check=True)
