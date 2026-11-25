#pragma once

// What the programs took from GUI.Forms's private sources before they moved
// to the devkit, rebuilt on public headers: they build against the SDK,
// which installs no src/ header.
//
// start_program_thread starts an stxlib::Thread as the library's
// start_library_thread does (src/core/threading/start_thread.hpp), with the
// same failures: std::bad_alloc when STXlib's allocator is exhausted,
// std::system_error (resource_unavailable_try_again) when the host refuses
// the thread. The entry must not throw.
//
// write_program_file replaces the file at `path` with `bytes`; false when it
// cannot be opened or written whole.

#include <cstddef>
#include <filesystem>
#include <fstream>
#include <new>
#include <span>
#include <stxlib/error.hpp>
#include <stxlib/result.hpp>
#include <stxlib/threads.hpp>
#include <system_error>

namespace gui_forms::demo {

[[nodiscard]] inline stxlib::Thread start_program_thread(const stxlib::Thread::Entry entry, void* const context,
                                                         const char* const what) {
    stxlib::OperationResult<stxlib::Thread> started = stxlib::Thread::start(entry, context);
    if (started.failed()) {
        if ((*started.error()).kind() == stxlib::ErrorKind::out_of_memory) throw std::bad_alloc();
        throw std::system_error(std::make_error_code(std::errc::resource_unavailable_try_again), what);
    }
    stxlib::Thread thread = static_cast<stxlib::OperationResult<stxlib::Thread>&&>(started).take_value();
    return thread;
}

[[nodiscard]] inline bool write_program_file(const std::filesystem::path& path,
                                             const std::span<const std::byte> bytes) {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) return false;
    file.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    file.close();
    const bool written = !file.fail();
    return written;
}

} // namespace gui_forms::demo
