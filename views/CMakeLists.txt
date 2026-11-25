# The demonstrator views, one static library each, over the prebuilt SDK.
# A program (programs/) or Pocket Reference links a view and shows it; a
# view names no host. Each library's include directories are its own folder
# and programs/shell (the shared program options its *_program.hpp reads).

set(GUI_FORMS_DEVKIT_SHELL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../programs/shell" CACHE INTERNAL
    "The shared program headers (program_options.hpp, the headless capture)")

# gui_forms_devkit_view(<name> SOURCES <files...> [LINKS <targets...>])
function(gui_forms_devkit_view name)
    cmake_parse_arguments(PARSE_ARGV 1 view "" "" "SOURCES;LINKS")
    add_library(gui_forms_devkit_view_${name} STATIC ${view_SOURCES})
    add_library(gui_forms_devkit::view_${name} ALIAS gui_forms_devkit_view_${name})
    target_include_directories(gui_forms_devkit_view_${name} PUBLIC
        "${CMAKE_CURRENT_SOURCE_DIR}/${name}" "${GUI_FORMS_DEVKIT_SHELL_DIR}")
    target_link_libraries(gui_forms_devkit_view_${name} PUBLIC GUIForms::Controls ${view_LINKS})
endfunction()

# The process-control demonstrator: the owner's dialog built from the
# library's light maps, finishes and lamps.
gui_forms_devkit_view(process_control SOURCES process_control/process_control.cpp)

# The data workbench: fifty thousand orders on a virtual DataGridView with a
# find panel, a column chooser, layouts, summaries and a CRM dashboard.
gui_forms_devkit_view(data_workbench SOURCES data_workbench/data_workbench.cpp)

# The mockup factory (gui-forms-mockup): a .form, its fixture and a theme
# sheet shown at once and reloaded on save; the catalogue is ../mockups.
gui_forms_devkit_view(mockup_factory SOURCES mockup_factory/mockup_catalogue.cpp mockup_factory/mockup_factory.cpp)
target_compile_definitions(gui_forms_devkit_view_mockup_factory PUBLIC
    "GUI_FORMS_DEVKIT_MOCKUPS_DIR=\"${CMAKE_CURRENT_SOURCE_DIR}/../mockups\"")

# Touch Start: a panning surface of live tiles through the touch seams.
gui_forms_devkit_view(touch_start SOURCES touch_start/touch_input.cpp touch_start/touch_start.cpp)

# Correspondence: the fixture-backed mail client (Modern.Forms "Outlaw"); its
# CorrespondenceView is GUI.Forms' lab control (GUIForms::Lab).
gui_forms_devkit_view(correspondence
    SOURCES correspondence/correspondence_model.cpp correspondence/correspondence_controls.cpp
            correspondence/correspondence.cpp
    LINKS GUIForms::Lab)

# Code Zoom: a C++ source embedded at build time and highlighted
# (stxlib/syntax.hpp), zoomed from a minimap to a few characters with every
# frame's text rasterized at its true size. It shows one of this
# repository's files; GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE names it, relative
# to the devkit root.
set(GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE "views/code_zoom/code_sheet.cpp" CACHE STRING
    "The source the code-zoom view shows, relative to the devkit root")
set(_devkit_code_zoom_generated "${CMAKE_CURRENT_BINARY_DIR}/generated/code_zoom")
set(_devkit_code_zoom_embedded "${_devkit_code_zoom_generated}/code_zoom_embedded_source.inc")
add_custom_command(
    OUTPUT "${_devkit_code_zoom_embedded}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${_devkit_code_zoom_generated}"
    COMMAND "${CMAKE_COMMAND}"
        "-DSOURCE=${PROJECT_SOURCE_DIR}/${GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE}"
        "-DNAME=${GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE}"
        "-DOUTPUT=${_devkit_code_zoom_embedded}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/code_zoom/embed_text_file.cmake"
    DEPENDS "${PROJECT_SOURCE_DIR}/${GUI_FORMS_DEVKIT_CODE_ZOOM_SOURCE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/code_zoom/embed_text_file.cmake"
    COMMENT "Embedding the code-zoom view's source"
    VERBATIM)
gui_forms_devkit_view(code_zoom
    SOURCES code_zoom/zoom_model.cpp code_zoom/code_bench.cpp code_zoom/code_sheet.cpp code_zoom/code_zoom.cpp
            "${_devkit_code_zoom_embedded}"
    LINKS stxlib::algorithms)
target_include_directories(gui_forms_devkit_view_code_zoom PRIVATE "${_devkit_code_zoom_generated}")
