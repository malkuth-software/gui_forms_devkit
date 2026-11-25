# The devkit's prebuilt-SDK consumption and its build guard, for any
# CMake-driven build: the harness scripts, a terminal, or an IDE (Visual
# Studio, Xcode, CLion, VS Code) that only presses Build.
#
#   include(<devkit>/harness/harness/cmake/DevkitBuildGuard.cmake)
#   gui_forms_devkit_use_sdk()            # before find_package(GUIForms): the SDK at the fixed path
#   gui_forms_devkit_cache_launcher()     # before the first target: ccache with the recorded environment
#   find_package(GUIForms ...)
#   ... targets ...
#   gui_forms_devkit_build_guard()        # anywhere in the top-level list: runs when configuring ends
#
# The guard (harness/harness/build_guard.py) runs twice:
#   - when configuring ends (deferred, so every target exists): the SDK, the
#     GUIForms package location, the targets' sources, the compiler and the
#     compile environment. A finding stops the configure with FATAL_ERROR.
#   - before every build, as the target gui_forms_devkit_build_guard that every
#     compiled target depends on: the same checks, plus the projected cache
#     hit rate of the recorded objects not yet built. A finding fails that
#     target, so the build stops before the first compile.
# Either goes on with GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON (CMake option) or
# GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=1 (environment).

include_guard(GLOBAL)

set(GUI_FORMS_DEVKIT_HARNESS_DIR "${CMAKE_CURRENT_LIST_DIR}/.." CACHE INTERNAL "The devkit harness's tools")
set(GUI_FORMS_DEVKIT_WORKSPACE "${CMAKE_SOURCE_DIR}" CACHE PATH
    "The workspace root: it holds .sdk/gui-forms-sdk, .ccache and cache-manifest.json")
set(GUI_FORMS_DEVKIT_SDK "${GUI_FORMS_DEVKIT_WORKSPACE}/.sdk/gui-forms-sdk" CACHE PATH
    "The prebuilt GUI.Forms SDK, always at the same path (harness/harness/resolve_gui_forms.py fetch)")
option(GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD "Build even when the build guard finds the SDK or cache unused" OFF)
option(GUI_FORMS_DEVKIT_USE_CCACHE "Compile through ccache with the restored cache's environment" ON)
set(GUI_FORMS_DEVKIT_HIT_THRESHOLD "0.9" CACHE STRING "The least projected cache hit rate the guard accepts")

find_package(Python3 3.11 COMPONENTS Interpreter REQUIRED)

# The platform name the harness uses for this build's target.
function(_gui_forms_devkit_platform out)
    if(APPLE)
        set(platform "macos-arm64")
    elseif(WIN32)
        set(platform "windows-x64")
    elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$")
        set(platform "linux-arm64")
    else()
        set(platform "linux-x64")
    endif()
    set(${out} "${platform}" PARENT_SCOPE)
endfunction()

# The SDK at the fixed path first on the package search path.
macro(gui_forms_devkit_use_sdk)
    list(PREPEND CMAKE_PREFIX_PATH "${GUI_FORMS_DEVKIT_SDK}")
endmacro()

# The compile environment the restored cache was filled with, as a list of
# NAME=VALUE (an empty value: leave it unset; cmake -E env --unset does that).
function(_gui_forms_devkit_compile_environment out)
    _gui_forms_devkit_platform(platform)
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -B "${GUI_FORMS_DEVKIT_HARNESS_DIR}/build_guard.py" environment
                --workspace "${GUI_FORMS_DEVKIT_WORKSPACE}" --platform "${platform}"
        OUTPUT_VARIABLE listing RESULT_VARIABLE status OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(NOT status EQUAL 0)
        message(FATAL_ERROR "build_guard.py environment failed (${status})")
    endif()
    string(REPLACE "\n" ";" lines "${listing}")
    set(${out} "${lines}" PARENT_SCOPE)
endfunction()

# ccache as every language's launcher, through cmake -E env so the compile has
# the recorded ccache settings and locale whatever the IDE's environment.
function(gui_forms_devkit_cache_launcher)
    if(NOT GUI_FORMS_DEVKIT_USE_CCACHE)
        return()
    endif()
    find_program(GUI_FORMS_DEVKIT_CCACHE ccache)
    if(NOT GUI_FORMS_DEVKIT_CCACHE)
        return()  # the guard's launcher finding says what to do
    endif()
    _gui_forms_devkit_compile_environment(assignments)
    set(launcher "${CMAKE_COMMAND}" -E env)
    set(compile_environment "")
    foreach(assignment IN LISTS assignments)
        string(FIND "${assignment}" "=" split)
        string(SUBSTRING "${assignment}" 0 ${split} name)
        math(EXPR value_start "${split} + 1")
        string(SUBSTRING "${assignment}" ${value_start} -1 value)
        if(value STREQUAL "")
            list(APPEND launcher "--unset=${name}")
        else()
            list(APPEND launcher "${assignment}")
        endif()
        list(APPEND compile_environment "${assignment}")
    endforeach()
    list(APPEND launcher "${GUI_FORMS_DEVKIT_CCACHE}")
    foreach(language IN ITEMS C CXX OBJC OBJCXX)
        set(CMAKE_${language}_COMPILER_LAUNCHER "${launcher}" PARENT_SCOPE)
    endforeach()
    set(GUI_FORMS_DEVKIT_COMPILE_ENVIRONMENT "${compile_environment}" CACHE INTERNAL "")
    set(GUI_FORMS_DEVKIT_LAUNCHER "${GUI_FORMS_DEVKIT_CCACHE}" CACHE INTERNAL "")
endfunction()

# Every buildsystem target under `directory`, recursively.
function(_gui_forms_devkit_targets directory out)
    get_property(targets DIRECTORY "${directory}" PROPERTY BUILDSYSTEM_TARGETS)
    get_property(children DIRECTORY "${directory}" PROPERTY SUBDIRECTORIES)
    foreach(child IN LISTS children)
        _gui_forms_devkit_targets("${child}" nested)
        list(APPEND targets ${nested})
    endforeach()
    set(${out} "${targets}" PARENT_SCOPE)
endfunction()

# The guard's arguments common to the configure check and the pre-build step.
function(_gui_forms_devkit_guard_arguments out)
    _gui_forms_devkit_platform(platform)
    set(imported "")
    if(TARGET GUIForms::Application)
        get_target_property(is_imported GUIForms::Application IMPORTED)
        if(is_imported)
            set(imported "yes")
        else()
            set(imported "no")
        endif()
    endif()
    # The launcher (empty without ccache) and imported (empty when the SDK
    # was not looked up) are joined to their options: an empty list element
    # vanishes when the list is expanded, and argparse would take the next
    # option as the value.
    set(arguments --workspace "${GUI_FORMS_DEVKIT_WORKSPACE}" --platform "${platform}"
                  --build-dir "${CMAKE_BINARY_DIR}" --cxx-compiler "${CMAKE_CXX_COMPILER}"
                  "--launcher=${GUI_FORMS_DEVKIT_LAUNCHER}" --gui-forms-dir "${GUIForms_DIR}"
                  "--imported=${imported}" --threshold "${GUI_FORMS_DEVKIT_HIT_THRESHOLD}"
                  --sources-file "${CMAKE_BINARY_DIR}/gui_forms_devkit_guard/sources.txt")
    foreach(assignment IN LISTS GUI_FORMS_DEVKIT_COMPILE_ENVIRONMENT)
        list(APPEND arguments --compile-env "${assignment}")
    endforeach()
    if(GUI_FORMS_DEVKIT_ALLOW_FULL_BUILD)
        list(APPEND arguments --allow-full-build)
    endif()
    set(${out} "${arguments}" PARENT_SCOPE)
endfunction()

# Deferred to the end of the top-level directory: list the sources, run the
# configure check, add the pre-build target and make every compiled target
# depend on it.
function(_gui_forms_devkit_build_guard_run)
    _gui_forms_devkit_targets("${CMAKE_SOURCE_DIR}" targets)
    set(sources "")
    set(compiled "")
    foreach(target IN LISTS targets)
        get_target_property(type ${target} TYPE)
        if(NOT type MATCHES "^(EXECUTABLE|STATIC_LIBRARY|SHARED_LIBRARY|MODULE_LIBRARY|OBJECT_LIBRARY)$")
            continue()
        endif()
        list(APPEND compiled ${target})
        get_target_property(target_sources ${target} SOURCES)
        get_target_property(target_directory ${target} SOURCE_DIR)
        foreach(source IN LISTS target_sources)
            if(source MATCHES "^\\$<")
                continue()  # a generator expression: resolved only at generation
            endif()
            cmake_path(ABSOLUTE_PATH source BASE_DIRECTORY "${target_directory}" NORMALIZE OUTPUT_VARIABLE absolute)
            list(APPEND sources "${absolute}")
        endforeach()
    endforeach()
    list(REMOVE_DUPLICATES sources)
    list(JOIN sources "\n" listing)
    file(WRITE "${CMAKE_BINARY_DIR}/gui_forms_devkit_guard/sources.txt" "${listing}\n")
    _gui_forms_devkit_guard_arguments(arguments)
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -B "${GUI_FORMS_DEVKIT_HARNESS_DIR}/build_guard.py" check ${arguments}
                --dry-run none
        RESULT_VARIABLE status)
    if(NOT status EQUAL 0)
        message(FATAL_ERROR "The devkit build guard stopped the configure (see above). "
                            "-DGUI_FORMS_DEVKIT_ALLOW_FULL_BUILD=ON builds anyway.")
    endif()
    add_custom_target(gui_forms_devkit_build_guard
        COMMAND "${Python3_EXECUTABLE}" -B "${GUI_FORMS_DEVKIT_HARNESS_DIR}/build_guard.py" check ${arguments}
                --dry-run objects
        COMMENT "Checking that the build uses the prebuilt GUI.Forms SDK and the restored cache"
        VERBATIM)
    foreach(target IN LISTS compiled)
        add_dependencies(${target} gui_forms_devkit_build_guard)
    endforeach()
endfunction()

function(gui_forms_devkit_build_guard)
    cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL _gui_forms_devkit_build_guard_run)
endfunction()
