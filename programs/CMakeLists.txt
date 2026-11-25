# The demonstration programs, over the prebuilt SDK: the Gallery, the
# demonstrator views' programs, the labs, Correspondence and the File
# Manager demoboard (Explore). Each program links GUIForms::Application (the
# engine and the host) and its model; the target names and output names are
# the ones GUI.Forms built them under, so programs/packaging/programs.json and
# the package and smoke tools (programs/tools/) find them unchanged.
#
# Every program replaces operator new with STXlib's allocator
# (gui_forms_use_library_allocator), as the in-tree programs did.

if(MINGW)
    # A program is one module: the runtimes are linked into it (GUI.Forms's
    # rule; programs/tools/package_programs.py refuses a runtime DLL).
    add_link_options(-static)
endif()

# The shared program headers: program_options.hpp, the Gallery's staging and
# headless capture, and program_support.hpp.
add_library(gui_forms_devkit_shell INTERFACE)
target_include_directories(gui_forms_devkit_shell INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}/shell")

# --- The bundled faces' notices ---------------------------------------------
# A program carries no face file (it reads the font pack compiled into
# GUI.Forms), only the faces' licences and the attribution, from the SDK's
# share/GUIForms/fonts: in a macOS bundle's Contents/Resources/fonts, beside
# a Windows or Linux program in fonts/. programs.json's fonts lists the same
# files.
set(GUI_FORMS_DEVKIT_FONT_NOTICE_NAMES
    ATTRIBUTION.md LICENSE-PortsmouthRapids.txt OFL-Arimo.txt OFL-Carlito.txt OFL-Cousine.txt OFL-Selawik.txt
    OFL-Tinos.txt)
if(GUIForms_FALLBACK_FONTS)
    list(APPEND GUI_FORMS_DEVKIT_FONT_NOTICE_NAMES OFL-Noto.txt OFL-NotoSansCJKjp.txt OFL-NotoEmoji.txt)
endif()
set(GUI_FORMS_DEVKIT_FONT_NOTICES "")
foreach(notice IN LISTS GUI_FORMS_DEVKIT_FONT_NOTICE_NAMES)
    if(NOT EXISTS "${GUIForms_FONT_DIR}/${notice}")
        message(FATAL_ERROR "The GUI.Forms SDK at ${GUIForms_FONT_DIR} lacks the font notice ${notice}")
    endif()
    list(APPEND GUI_FORMS_DEVKIT_FONT_NOTICES "${GUIForms_FONT_DIR}/${notice}")
endforeach()
if(APPLE)
    set_source_files_properties(${GUI_FORMS_DEVKIT_FONT_NOTICES} PROPERTIES MACOSX_PACKAGE_LOCATION "Resources/fonts")
endif()

# The programs that stage fonts/ beside them (Windows and Linux), filled in
# by gui_forms_devkit_program and staged once at the end.
set_property(GLOBAL PROPERTY GUI_FORMS_DEVKIT_FONT_PROGRAMS "")

# gui_forms_devkit_program(<target> OUTPUT <name> SOURCES <files...>
#                          LINKS <targets...> [BUNDLE_NAME <name> BUNDLE_ID <id>])
# BUNDLE_NAME and BUNDLE_ID make a macOS bundle.
function(gui_forms_devkit_program target)
    cmake_parse_arguments(PARSE_ARGV 1 program "" "OUTPUT;BUNDLE_NAME;BUNDLE_ID" "SOURCES;LINKS")
    if(program_BUNDLE_NAME)
        add_executable(${target} MACOSX_BUNDLE ${program_SOURCES} ${GUI_FORMS_DEVKIT_FONT_NOTICES})
        target_compile_options(${target} PRIVATE -fobjc-arc)
        set_target_properties(${target} PROPERTIES
            MACOSX_BUNDLE_BUNDLE_NAME "${program_BUNDLE_NAME}"
            MACOSX_BUNDLE_GUI_IDENTIFIER "${program_BUNDLE_ID}"
            MACOSX_BUNDLE_SHORT_VERSION_STRING "${GUIForms_VERSION_MAJOR}.${GUIForms_VERSION_MINOR}"
            MACOSX_BUNDLE_BUNDLE_VERSION "1")
    else()
        add_executable(${target} ${program_SOURCES})
        set_property(GLOBAL APPEND PROPERTY GUI_FORMS_DEVKIT_FONT_PROGRAMS ${target})
    endif()
    set_target_properties(${target} PROPERTIES OUTPUT_NAME "${program_OUTPUT}")
    target_link_libraries(${target} PRIVATE ${program_LINKS} gui_forms_devkit_shell GUIForms::Application)
    gui_forms_use_library_allocator(${target})
endfunction()

# --- The lab models -------------------------------------------------------------
# gui_forms_devkit_lab(<name> [DEMO]): programs/labs/<name>.cpp as a static
# library; DEMO links the demonstration controls (GUIForms::DemoControls).
function(gui_forms_devkit_lab name)
    cmake_parse_arguments(PARSE_ARGV 1 lab "DEMO" "" "")
    add_library(gui_forms_devkit_lab_${name} STATIC "${CMAKE_CURRENT_SOURCE_DIR}/labs/${name}.cpp")
    target_include_directories(gui_forms_devkit_lab_${name} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/labs")
    target_link_libraries(gui_forms_devkit_lab_${name} PUBLIC GUIForms::Controls gui_forms_devkit_shell)
    if(lab_DEMO)
        target_link_libraries(gui_forms_devkit_lab_${name} PUBLIC GUIForms::DemoControls)
    endif()
endfunction()

gui_forms_devkit_lab(vsync_lab)
gui_forms_devkit_lab(compositor_lab)
gui_forms_devkit_lab(visual_inspector_lab DEMO)
gui_forms_devkit_lab(layered_material_lab DEMO)
gui_forms_devkit_lab(custom_chrome_lab DEMO)
gui_forms_devkit_lab(typography_scale_lab DEMO)
gui_forms_devkit_lab(responsive_tracks_lab DEMO)
gui_forms_devkit_lab(connected_controls_lab DEMO)
gui_forms_devkit_lab(seam_proximity_lab DEMO)

# The File Manager demoboard's model (Explore): its windows over the lab
# controls (GUIForms::Lab).
add_library(gui_forms_devkit_file_manager_demoboard STATIC
    file_manager_demoboard/src/fixture_model.cpp
    file_manager_demoboard/src/product_window.cpp
    file_manager_demoboard/src/controller_window.cpp)
target_include_directories(gui_forms_devkit_file_manager_demoboard PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/file_manager_demoboard/include")
target_link_libraries(gui_forms_devkit_file_manager_demoboard PUBLIC GUIForms::Controls GUIForms::Lab)

# --- The programs, per host -----------------------------------------------------
# One table: <id> <model> <macOS bundle name> <bundle id suffix> <Linux name or "-">.
# A lab's model is gui_forms_devkit_lab_<id>; a view's is gui_forms_devkit_view_<id>.
set(_devkit_programs
    "gallery|GUIForms::GalleryModel|GUI.Forms Gallery|gallery|gui-forms-gallery"
    "process_control|gui_forms_devkit_view_process_control|GUI.Forms Process Control|process-control|gui-forms-process-control"
    "data_workbench|gui_forms_devkit_view_data_workbench|GUI.Forms Data Workbench|data-workbench|gui-forms-data-workbench"
    "mockup|gui_forms_devkit_view_mockup_factory|GUI.Forms Mockup|mockup|gui-forms-mockup"
    "touch_start|gui_forms_devkit_view_touch_start|GUI.Forms Touch Start|touch-start|gui-forms-touch-start"
    "code_zoom|gui_forms_devkit_view_code_zoom|GUI.Forms Code Zoom|code-zoom|gui-forms-code-zoom"
    "correspondence|gui_forms_devkit_view_correspondence|GUI.Forms Correspondence|correspondence|gui-forms-correspondence"
    "compositor_lab|gui_forms_devkit_lab_compositor_lab|GUI.Forms Compositor Lab|compositor-lab|gui-forms-compositor-lab"
    "vsync_lab|gui_forms_devkit_lab_vsync_lab|GUI.Forms VSync + Waterfall Lab|vsync-waterfall-lab|-"
    "visual_inspector_lab|gui_forms_devkit_lab_visual_inspector_lab|GUI.Forms Visual Inspector Lab|visual-inspector-lab|-"
    "layered_material_lab|gui_forms_devkit_lab_layered_material_lab|GUI.Forms Layered Material Fidelity Lab|layered-material-lab|-"
    "custom_chrome_lab|gui_forms_devkit_lab_custom_chrome_lab|GUI.Forms Custom Chrome Lab|custom-chrome-lab|-"
    "typography_scale_lab|gui_forms_devkit_lab_typography_scale_lab|GUI.Forms Typography + Scale Lab|typography-scale-lab|-"
    "responsive_tracks_lab|gui_forms_devkit_lab_responsive_tracks_lab|GUI.Forms Responsive Tracks Lab|responsive-tracks-lab|-"
    "connected_controls_lab|gui_forms_devkit_lab_connected_controls_lab|GUI.Forms Connected Controls Lab|connected-controls-lab|-"
    "seam_proximity_lab|gui_forms_devkit_lab_seam_proximity_lab|GUI.Forms Physical Seam + Proximity Lab|seam-proximity-lab|-")

foreach(_devkit_row IN LISTS _devkit_programs)
    string(REPLACE "|" ";" _devkit_fields "${_devkit_row}")
    list(GET _devkit_fields 0 id)
    list(GET _devkit_fields 1 model)
    list(GET _devkit_fields 2 display)
    list(GET _devkit_fields 3 bundle_id)
    list(GET _devkit_fields 4 linux_name)
    if(APPLE)
        gui_forms_devkit_program(gui_forms_${id} OUTPUT "${display}"
            SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/host/macos/${id}_main.mm" LINKS ${model}
            BUNDLE_NAME "${display}" BUNDLE_ID "local.guiforms.${bundle_id}")
    elseif(WIN32)
        gui_forms_devkit_program(gui_forms_${id}_windows OUTPUT "${display}"
            SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/host/windows/${id}_main.cpp" LINKS ${model})
    elseif(NOT linux_name STREQUAL "-")
        gui_forms_devkit_program(gui_forms_${id}_linux OUTPUT "${linux_name}"
            SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/host/linux/${id}_main.cpp" LINKS ${model})
    endif()
endforeach()

# Explore (the File Manager demoboard).
if(APPLE)
    gui_forms_devkit_program(gui_forms_file_manager_demoboard OUTPUT "File Manager Demoboard"
        SOURCES file_manager_demoboard/src/macos_main.mm LINKS gui_forms_devkit_file_manager_demoboard
        BUNDLE_NAME "File Manager Demoboard" BUNDLE_ID "local.guiforms.file-manager-demoboard")
elseif(WIN32)
    gui_forms_devkit_program(gui_forms_file_manager_demoboard_windows OUTPUT "File Manager Demoboard"
        SOURCES file_manager_demoboard/src/windows_main.cpp LINKS gui_forms_devkit_file_manager_demoboard)
else()
    gui_forms_devkit_program(gui_forms_file_manager_demoboard_linux OUTPUT "gui-forms-explore"
        SOURCES file_manager_demoboard/src/linux_main.cpp LINKS gui_forms_devkit_file_manager_demoboard)
endif()

# --- fonts/ beside the Windows and Linux programs ---------------------------------
# The programs share this directory, so one fonts/ serves them all; one target
# stages each notice through its own rule (one writer per file: several
# post-build copies of the same file raced on a cold parallel build).
get_property(_devkit_font_programs GLOBAL PROPERTY GUI_FORMS_DEVKIT_FONT_PROGRAMS)
if(_devkit_font_programs)
    set(_devkit_program_directory "${CMAKE_CURRENT_BINARY_DIR}")
    if(CMAKE_RUNTIME_OUTPUT_DIRECTORY)
        set(_devkit_program_directory "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
    endif()
    set(_devkit_staged_fonts "")
    foreach(notice IN LISTS GUI_FORMS_DEVKIT_FONT_NOTICES)
        get_filename_component(notice_name "${notice}" NAME)
        set(staged "${_devkit_program_directory}/fonts/${notice_name}")
        add_custom_command(OUTPUT "${staged}"
            COMMAND "${CMAKE_COMMAND}" -E make_directory "${_devkit_program_directory}/fonts"
            COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${notice}" "${staged}"
            DEPENDS "${notice}"
            VERBATIM)
        list(APPEND _devkit_staged_fonts "${staged}")
    endforeach()
    add_custom_target(gui_forms_devkit_program_fonts DEPENDS ${_devkit_staged_fonts})
    foreach(program IN LISTS _devkit_font_programs)
        add_dependencies(${program} gui_forms_devkit_program_fonts)
    endforeach()
endif()
