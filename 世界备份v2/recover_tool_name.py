import platform
import sys


def get_tool_name() -> str | None:
    recover_tool_name = None
    system = platform.system().lower()
    arch = platform.machine().lower()

    format_arch = ""
    if sys.maxsize == 2**63 - 1:
        if arch in ("x86_64", "amd64"):
            format_arch = "amd64"
        elif arch in ("arm64", "aarch64"):
            format_arch = "arm64"
    else:
        if arch in ("x86", "i686"):
            format_arch = "x86"

    match system:
        case "windows":
            if format_arch == "amd64":
                recover_tool_name = "recover-tool_windows_amd64.exe"
            elif format_arch == "x86":
                recover_tool_name = "recover-tool_windows_x86.exe"
        case "darwin":
            if format_arch == "amd64":
                recover_tool_name = "recover-tool_macos_amd64"
            elif format_arch == "arm64":
                recover_tool_name = "recover-tool_macos_arm64"
        case _:
            if format_arch == "amd64":
                recover_tool_name = "recover-tool_linux_amd64"
            elif format_arch == "arm64":
                if arch == "aarch64":
                    recover_tool_name = "recover-tool_android_arm64"
                else:
                    recover_tool_name = "recover-tool_linux_arm64"

    return recover_tool_name
