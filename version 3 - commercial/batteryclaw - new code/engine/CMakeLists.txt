cmake_minimum_required(VERSION 3.20)
project(BatteryClaw_Engine CXX)
set(CMAKE_CXX_STANDARD 17)

if(NOT WIN32)
    message(FATAL_ERROR "BatteryClaw chi chay tren Windows!")
endif()

set(WIN_LIBS wbemuuid ole32 oleaut32 powrprof psapi advapi32 pdh iphlpapi)

# ── batteryclaw.exe — executable chinh, chay voi quyen Admin ────────────────
# Tich hop: doc trang thai may + thuc thi lenh + IPC server pipe
# [Phase 1] them: power_monitor, gpu_monitor, gpu_switch, context_collector
add_executable(batteryclaw
    src/batteryclaw_main.cpp
    src/state_collector.cpp
    src/action_executor.cpp
    src/power_monitor.cpp
    src/gpu_monitor.cpp
    src/gpu_switch.cpp
    src/context_collector.cpp
)
target_include_directories(batteryclaw PRIVATE include)
target_link_libraries(batteryclaw PRIVATE ${WIN_LIBS})
target_compile_definitions(batteryclaw PRIVATE NOMINMAX NO_MAIN_SC NO_MAIN_AE)
set_target_properties(batteryclaw PROPERTIES
    LINK_FLAGS "/MANIFESTUAC:\"level='requireAdministrator'\""
)

# ── tray.exe — system tray icon, autostart khi boot ─────────────────────────
add_executable(tray WIN32 src/tray_launcher.cpp)
target_link_libraries(tray PRIVATE user32 shell32 advapi32)
target_compile_definitions(tray PRIVATE NOMINMAX)

# ── test executables (chi dung de debug) ─────────────────────────────────────
add_executable(test_state   src/state_collector.cpp
    src/power_monitor.cpp src/gpu_monitor.cpp src/context_collector.cpp)
add_executable(test_action  src/action_executor.cpp)
add_executable(test_brightness src/brightness_controller.cpp)
add_executable(test_appdetect  src/app_detector.cpp)

# [Phase 1] test rieng tung module moi
add_executable(test_power   src/power_monitor.cpp)
target_compile_definitions(test_power PRIVATE PM_TEST)
add_executable(test_gpu     src/gpu_monitor.cpp)
target_compile_definitions(test_gpu PRIVATE GPU_TEST)
add_executable(test_gpuswitch src/gpu_switch.cpp)
target_compile_definitions(test_gpuswitch PRIVATE SW_TEST)
add_executable(test_context src/context_collector.cpp)
target_compile_definitions(test_context PRIVATE CTX_TEST)

foreach(t test_state test_action test_brightness test_appdetect
          test_power test_gpu test_gpuswitch test_context)
    target_include_directories(${t} PRIVATE include)
    target_link_libraries(${t} PRIVATE ${WIN_LIBS} Dxva2 gdi32 pdh iphlpapi)
    set_target_properties(${t} PROPERTIES
        LINK_FLAGS "/MANIFESTUAC:\"level='requireAdministrator'\""
    )
endforeach()

if(MSVC)
    foreach(t batteryclaw tray test_state test_action test_brightness test_appdetect
              test_power test_gpu test_gpuswitch test_context)
        target_compile_options(${t} PRIVATE /W3 /O2)
    endforeach()
endif()
