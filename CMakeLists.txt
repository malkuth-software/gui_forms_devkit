# gui_forms_devkit: Pocket Reference, the demonstrator views and the
# programs, built against the prebuilt GUI.Forms SDK the pin resolves to.
#
#   python3 -B harness/harness/resolve_gui_forms.py resolve
#   python3 -B harness/harness/resolve_gui_forms.py fetch --platform <platform>
#   cmake -S . -B build -G Ninja && cmake --build build
#
# The SDK is always at .sdk/gui-forms-sdk (GUI_FORMS_DEVKIT_SDK), whatever
# the revision, so the compiler cache keeps hitting across GUI.Forms
# advances. The build guard (harness/harness/cmake/DevkitBuildGuard.cmake)
# stops a configure or build that would not use that SDK and the restored
# cache, saying why; -DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON builds anyway.
cmake_minimum_required(VERSION 3.25)
project(gui_forms_devkit VERSION 1.0.0 LANGUAGES C CXX)
if(APPLE)
    enable_language(OBJCXX)
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# The pin: the floor is what find_package's version means, and the major
# bounds it (GUIFormsConfigVersion accepts the same major only).
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/devkit.toml" _devkit_pin)
if(NOT _devkit_pin MATCHES "minimum = \"([0-9]+\\.[0-9]+\\.[0-9]+)\"")
    message(FATAL_ERROR "devkit.toml names no [gui_forms] minimum")
endif()
set(GUI_FORMS_DEVKIT_MINIMUM "${CMAKE_MATCH_1}")

include(harness/harness/cmake/DevkitBuildGuard.cmake)
gui_forms_devkit_use_sdk()
gui_forms_devkit_cache_launcher()

# Keep the SDK's headers ahead of any other GUI.Forms on the system.
set(CMAKE_NO_SYSTEM_FROM_IMPORTED ON)
find_package(GUIForms ${GUI_FORMS_DEVKIT_MINIMUM} CONFIG REQUIRED
             COMPONENTS Application Controls GalleryModel Lab DemoControls)
if(NOT TARGET stxlib::algorithms)
    find_package(stxlib CONFIG REQUIRED)
endif()
# The installed Lab and DemoControls (GUI.Forms 1.0.5) name no link
# dependency on Controls, so a static link that lists Controls first leaves
# their references (VScrollBar in CorrespondenceView) unresolved on GNU ld.
# Their dependency is declared here until GUI.Forms exports it.
foreach(gui_forms_devkit_lab_target GUIForms::Lab GUIForms::DemoControls)
    if(TARGET ${gui_forms_devkit_lab_target})
        set_property(TARGET ${gui_forms_devkit_lab_target} APPEND PROPERTY INTERFACE_LINK_LIBRARIES GUIForms::Controls)
    endif()
endforeach()

# What the resolver recorded, for every artifact's manifest.
set(GUI_FORMS_DEVKIT_RESOLVED "${GUI_FORMS_DEVKIT_WORKSPACE}/.ci/gui_forms-resolved.json")

option(GUI_FORMS_DEVKIT_BUILD_PROGRAMS "Build the demonstration programs (programs/)" ON)
option(GUI_FORMS_DEVKIT_BUILD_POCKET_REFERENCE "Build Pocket Reference (pocket_reference/)" ON)
option(GUI_FORMS_DEVKIT_BUILD_TESTS "Build the program suites (tests/programs_tests.cmake)" ON)

add_subdirectory(views)
if(GUI_FORMS_DEVKIT_BUILD_PROGRAMS AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/programs/CMakeLists.txt")
    add_subdirectory(programs)
endif()
if(GUI_FORMS_DEVKIT_BUILD_POCKET_REFERENCE)
    add_subdirectory(pocket_reference)
endif()
if(GUI_FORMS_DEVKIT_BUILD_TESTS)
    enable_testing()
    include(tests/programs_tests.cmake)
endif()

gui_forms_devkit_build_guard()
