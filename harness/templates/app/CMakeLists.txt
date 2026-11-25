cmake_minimum_required(VERSION 3.25)
project({{App}} LANGUAGES CXX)

# GUI.Forms comes prebuilt: build.py (the devkit's devkit_build.py) resolves
# devkit.toml's pin to one green build and unpacks its SDK at
# .sdk/gui-forms-sdk, so nothing of GUI.Forms is compiled here. Configure with
# the toolchain file the SDK was built with: the devkit's
# harness/cmake/llvm22.cmake, or GUI.Forms' Windows own-runtime toolchain
# (build.py passes the right one).
#
# The devkit's DevkitBuildGuard.cmake puts that SDK first on the package path,
# compiles through ccache with the environment the SDK was built in, and stops
# a configure or build that would compile GUI.Forms from source or miss the
# SDK, saying why; -DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON builds anyway.
set(GUI_FORMS_DEVKIT_HARNESS_ROOT "" CACHE PATH
    "The devkit's harness directory, holding harness/cmake/DevkitBuildGuard.cmake")
if(NOT GUI_FORMS_DEVKIT_HARNESS_ROOT)
    foreach(candidate IN ITEMS "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_SOURCE_DIR}/../template_harness"
                               "${CMAKE_CURRENT_SOURCE_DIR}/.devkit/harness")
        if(EXISTS "${candidate}/harness/cmake/DevkitBuildGuard.cmake")
            set(GUI_FORMS_DEVKIT_HARNESS_ROOT "${candidate}" CACHE PATH
                "The devkit's harness directory, holding harness/cmake/DevkitBuildGuard.cmake" FORCE)
            break()
        endif()
    endforeach()
endif()
if(NOT EXISTS "${GUI_FORMS_DEVKIT_HARNESS_ROOT}/harness/cmake/DevkitBuildGuard.cmake")
    message(FATAL_ERROR "No devkit harness: run build.py, which checks the devkit out at .devkit/ "
                        "(harness.lock), or set GUI_FORMS_DEVKIT_HARNESS_ROOT to a gui_forms_devkit's harness/")
endif()
set(GUI_FORMS_DEVKIT_WORKSPACE "${CMAKE_CURRENT_SOURCE_DIR}" CACHE PATH
    "The workspace root: it holds .sdk/gui-forms-sdk, .ccache and .ci")
include("${GUI_FORMS_DEVKIT_HARNESS_ROOT}/harness/cmake/DevkitBuildGuard.cmake")
gui_forms_devkit_use_sdk()
gui_forms_devkit_cache_launcher()

# Controls is the renderer-free toolkit the form's test links. Application is
# the native host, present when the SDK was built with one; it already holds
# the retained engine, so no program here links both (the SDK's one linking
# rule).
find_package(GUIForms 1.0 CONFIG REQUIRED COMPONENTS Controls OPTIONAL_COMPONENTS Application)

enable_testing()

# The form's behaviour, without a native window.
add_executable(greeter_tests src/greeter.cpp tests/greeter_tests.cpp)
target_compile_features(greeter_tests PRIVATE cxx_std_20)
target_include_directories(greeter_tests PRIVATE src)
target_link_libraries(greeter_tests PRIVATE GUIForms::Controls)
# Keep the selected SDK ahead of any other GUI.Forms installation in the
# compiler's normal include search path.
set_target_properties(greeter_tests PROPERTIES NO_SYSTEM_FROM_IMPORTED TRUE)
add_test(NAME greeter_tests COMMAND greeter_tests)
set_tests_properties(greeter_tests PROPERTIES TIMEOUT 30)

# Pointer motion, scrolling and resizing lay out no more than they must,
# over the form and over the reference control (reference/, the retained
# custom control this app's agents copy; AGENTS.md "Building on GUI.Forms").
add_executable(interaction_tests src/greeter.cpp reference/link_page.cpp reference/sample_document.cpp
    tests/interaction_tests.cpp)
target_compile_features(interaction_tests PRIVATE cxx_std_20)
target_include_directories(interaction_tests PRIVATE src reference)
target_link_libraries(interaction_tests PRIVATE GUIForms::Controls)
set_target_properties(interaction_tests PROPERTIES NO_SYSTEM_FROM_IMPORTED TRUE)
add_test(NAME interaction_tests COMMAND interaction_tests)
set_tests_properties(interaction_tests PROPERTIES TIMEOUT 60)

if(TARGET GUIForms::Application)
    add_executable({{app}} src/greeter.cpp src/main.cpp)
    target_compile_features({{app}} PRIVATE cxx_std_20)
    target_include_directories({{app}} PRIVATE src)
    target_link_libraries({{app}} PRIVATE GUIForms::Application)
    set_target_properties({{app}} PROPERTIES NO_SYSTEM_FROM_IMPORTED TRUE)

    # Controls draw only the bundled faces, so the SDK's font directory goes
    # where the host looks: Contents/Resources/fonts in a macOS bundle, and
    # fonts/ beside the executable on Windows and Linux.
    if(APPLE)
        set_target_properties({{app}} PROPERTIES MACOSX_BUNDLE TRUE)
        set({{app}}_fonts "$<TARGET_BUNDLE_CONTENT_DIR:{{app}}>/Resources/fonts")
    else()
        set({{app}}_fonts "$<TARGET_FILE_DIR:{{app}}>/fonts")
    endif()
    add_custom_command(TARGET {{app}} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory "${GUIForms_FONT_DIR}" "${{{app}}_fonts}")

    # An installed Windows SDK keeps its DLLs in bin/; stage the ones the
    # program actually uses beside it.
    if(WIN32)
        add_custom_command(TARGET {{app}} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_RUNTIME_DLLS:{{app}}> $<TARGET_FILE_DIR:{{app}}>
            COMMAND_EXPAND_LISTS)
    endif()

    # Opens the native window and closes it once ready. It needs a display:
    # CI runs it under xvfb-run on Linux.
    add_test(NAME {{app}}_starts COMMAND {{app}} --close-when-ready)
    set_tests_properties({{app}}_starts PROPERTIES TIMEOUT 60)
endif()

# Runs when configuring ends, once every target exists, and before every build.
gui_forms_devkit_build_guard()
