# The program suites that moved here from malkuth-software/gui_forms_tests
# with the programs (DEVKIT_DESIGN.md, step 7; cp14 decision 3). Include this
# file from the devkit's top-level CMakeLists.txt after the program targets
# (programs/, views/) are defined, with enable_testing() on. Each suite is
# configured only when the target it links exists: the devkit's models
# (programs/CMakeLists.txt, views/CMakeLists.txt) under their devkit names,
# gui_forms_devkit_lab_<lab>, gui_forms_devkit_view_<view> and
# gui_forms_devkit_file_manager_demoboard. The suites keep the names they
# had in gui_forms_tests.
#
# Include roots: programs/shell (program_options.hpp, gallery_staging.hpp,
# gallery_headless_capture.hpp), programs/labs (the labs), views/ (for
# "correspondence/..."), views/process_control, programs/ (for
# "file_manager_demoboard/src/..."), and tests/ (support/).
#
# A few suites read GUI.Forms' private sources (skia_raster.hpp,
# headless_host.hpp, the macOS display-link trace), which no installed SDK
# carries. They are configured only when GUI_FORMS_SOURCE_DIR names a
# gui_forms checkout at the resolved revision (.ci/gui_forms-resolved.json's
# commit); the lockstep workflow can check one out beside the SDK.
set(GUI_FORMS_SOURCE_DIR "" CACHE PATH
    "A gui_forms checkout at the resolved revision, for the suites that read its private sources")
set(_gf_devkit_tests "${CMAKE_CURRENT_LIST_DIR}")
set(_gf_devkit_root "${CMAKE_CURRENT_LIST_DIR}/..")
set(_gf_devkit_private OFF)
if(GUI_FORMS_SOURCE_DIR AND EXISTS "${GUI_FORMS_SOURCE_DIR}/src/render/skia/raster/skia_raster.hpp")
    set(_gf_devkit_private ON)
endif()

# Adds suite `name` from tests/<source>, linking `libraries`, with the shell,
# labs and tests directories as include roots.
function(gui_forms_devkit_suite name source)
    add_executable(${name} ${_gf_devkit_tests}/${source})
    target_include_directories(${name} PRIVATE
        ${_gf_devkit_tests} ${_gf_devkit_root}/programs/shell ${_gf_devkit_root}/programs/labs
        ${_gf_devkit_root}/views)
    target_link_libraries(${name} PRIVATE ${ARGN})
    add_test(NAME ${name} COMMAND ${name})
endfunction()

# The demo programs' shared command line (programs/shell/program_options.hpp).
gui_forms_devkit_suite(gui_forms_program_options_tests program_options_tests.cpp GUIForms::Controls)

foreach(_gf_lab IN ITEMS visual_inspector_lab layered_material_lab typography_scale_lab
        responsive_tracks_lab connected_controls_lab seam_proximity_lab)
    if(TARGET gui_forms_devkit_lab_${_gf_lab})
        gui_forms_devkit_suite(gui_forms_${_gf_lab}_tests ${_gf_lab}_tests.cpp gui_forms_devkit_lab_${_gf_lab})
    endif()
endforeach()

if(TARGET gui_forms_devkit_view_process_control)
    # The process-control demonstrator's window: its dialog, sheet and strip.
    gui_forms_devkit_suite(gui_forms_process_control_tests process_control_tests.cpp
        gui_forms_devkit_view_process_control)
    target_include_directories(gui_forms_process_control_tests PRIVATE ${_gf_devkit_root}/views/process_control)
endif()

# The demonstrator views: Code Zoom (its C++ language, zoom, bench report
# and sheet), the data workbench (find panel, sort, column chooser, layouts,
# summaries, dashboard) and Touch Start (its touch input and tiles).
foreach(_gf_view IN ITEMS code_zoom data_workbench)
    if(TARGET gui_forms_devkit_view_${_gf_view})
        gui_forms_devkit_suite(gui_forms_${_gf_view}_tests ${_gf_view}_tests.cpp gui_forms_devkit_view_${_gf_view})
    endif()
endforeach()

if(TARGET gui_forms_devkit_view_correspondence)
    gui_forms_devkit_suite(gui_forms_correspondence_tests correspondence_tests.cpp gui_forms_devkit_view_correspondence)
    gui_forms_devkit_suite(gui_forms_correspondence_interaction_tests correspondence_interaction_tests.cpp
        gui_forms_devkit_view_correspondence)
endif()

if(TARGET gui_forms_devkit_file_manager_demoboard)
    gui_forms_devkit_suite(gui_forms_file_manager_demoboard_tests file_manager_demoboard/demoboard_tests.cpp
        gui_forms_devkit_file_manager_demoboard)
    target_include_directories(gui_forms_file_manager_demoboard_tests PRIVATE ${_gf_devkit_root}/programs)
    add_test(NAME gui_forms_file_manager_demoboard_public_policy
        COMMAND ${CMAKE_COMMAND}
            -DDEMOBOARD_DIRECTORY=${_gf_devkit_root}/programs/file_manager_demoboard
            -P ${_gf_devkit_tests}/cmake/check_demoboard_boundaries.cmake)
endif()

# The Gallery's headless page capture (--page <id> --capture <png> --headless;
# programs/shell/gallery_headless_capture.hpp). The installed Application
# library holds OffscreenRaster::create and the embedded font pack, so an
# empty font directory looks where the hosts look.
if(TARGET GUIForms::GalleryModel)
    gui_forms_devkit_suite(gui_forms_gallery_headless_capture_tests gallery_headless_capture_tests.cpp
        GUIForms::GalleryModel GUIForms::Application)
    target_compile_definitions(gui_forms_gallery_headless_capture_tests PRIVATE GUI_FORMS_TEST_FONT_DIR="")
    gui_forms_use_library_allocator(gui_forms_gallery_headless_capture_tests)
endif()

if(_gf_devkit_private)
    if(TARGET gui_forms_devkit_lab_layered_material_lab)
        gui_forms_devkit_suite(gui_forms_layered_material_raster_tests layered_material_raster_tests.cpp
            gui_forms_devkit_lab_layered_material_lab)
        target_include_directories(gui_forms_layered_material_raster_tests PRIVATE
            ${GUI_FORMS_SOURCE_DIR}/src/render/skia/raster)
    endif()
    if(TARGET gui_forms_devkit_lab_compositor_lab)
        # The lab in each compositor state, drawn on the Skia raster every
        # host presents with: grants, fallbacks and the frame's alpha.
        gui_forms_devkit_suite(gui_forms_compositor_lab_tests compositor_lab_tests.cpp
            gui_forms_devkit_lab_compositor_lab)
        target_include_directories(gui_forms_compositor_lab_tests PRIVATE
            ${GUI_FORMS_SOURCE_DIR}/src/render/skia/raster)
    endif()
    if(TARGET gui_forms_devkit_lab_custom_chrome_lab)
        gui_forms_devkit_suite(gui_forms_custom_chrome_lab_tests custom_chrome_lab_tests.cpp
            gui_forms_devkit_lab_custom_chrome_lab)
        target_include_directories(gui_forms_custom_chrome_lab_tests PRIVATE
            ${GUI_FORMS_SOURCE_DIR}/src/host/headless)
    endif()
    if(APPLE AND TARGET GUIForms::GalleryModel)
        # Live resize on the Gallery (cp33; tests/macos_live_resize_probe.mm):
        # a scripted corner drag and a stepped resize, recording each draw's
        # timing and damage; judged on stale damage, stalls and the final
        # frame. Built only: its test ran through LaunchServices so the window
        # is active and takes the posted drag (gui_forms_tests
        # cmake/run_macos_activated_test.cmake), which is not here yet; run the
        # bundle by hand with --capture <dir> for the owner's verdict.
        add_executable(gui_forms_macos_live_resize_probe MACOSX_BUNDLE
            ${_gf_devkit_tests}/macos_live_resize_probe.mm)
        target_compile_options(gui_forms_macos_live_resize_probe PRIVATE -fobjc-arc)
        target_include_directories(gui_forms_macos_live_resize_probe PRIVATE
            ${GUI_FORMS_SOURCE_DIR} ${GUI_FORMS_SOURCE_DIR}/src/host/macos)
        target_link_libraries(gui_forms_macos_live_resize_probe PRIVATE
            GUIForms::GalleryModel GUIForms::Application)
        set_target_properties(gui_forms_macos_live_resize_probe PROPERTIES
            MACOSX_BUNDLE_GUI_IDENTIFIER "local.guiforms.live-resize-probe")
    endif()
endif()

# Each program bundle or folder carries the font licences and no face file
# (font pack stage 4).
foreach(_gf_program IN ITEMS gui_forms_gallery gui_forms_correspondence gui_forms_visual_inspector_lab
        gui_forms_layered_material_lab gui_forms_custom_chrome_lab gui_forms_typography_scale_lab
        gui_forms_responsive_tracks_lab gui_forms_connected_controls_lab gui_forms_seam_proximity_lab)
    if(APPLE AND TARGET ${_gf_program})
        add_test(NAME ${_gf_program}_font_policy
            COMMAND ${CMAKE_COMMAND}
                -DFONT_DIRECTORY=$<TARGET_BUNDLE_CONTENT_DIR:${_gf_program}>/Resources/fonts
                -P ${_gf_devkit_tests}/cmake/check_gallery_fonts.cmake)
    endif()
endforeach()
