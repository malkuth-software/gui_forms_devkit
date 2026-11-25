// The mockup factory's files: see mockup_catalogue.hpp.

#include "mockup_catalogue.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <ios>
#include <iterator>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

namespace gui_forms::mockup {

namespace {

// Orders mockups by name.
struct NameBefore final {
    bool operator()(const MockupFiles& left, const MockupFiles& right) const noexcept {
        return left.name < right.name;
    }
};

// `form` with its ".form" replaced by `extension`.
[[nodiscard]] std::filesystem::path sibling(const std::filesystem::path& form, std::string_view extension) {
    std::filesystem::path path = form;
    path.replace_extension();
    path += std::string(extension);
    return path;
}

[[nodiscard]] bool regular_file(const std::filesystem::path& path) {
    std::error_code error{};
    const bool regular = std::filesystem::is_regular_file(path, error);
    return regular && !error;
}

[[nodiscard]] std::filesystem::file_time_type stamp_of(const std::filesystem::path& path) {
    if (path.empty()) return std::filesystem::file_time_type::min();
    std::error_code error{};
    const std::filesystem::file_time_type written = std::filesystem::last_write_time(path, error);
    if (error) return std::filesystem::file_time_type::min();
    return written;
}

} // namespace

MockupFiles mockup_files(std::string name, const std::filesystem::path& form, const std::filesystem::path& fixture,
                         const std::filesystem::path& sheet) {
    MockupFiles files{};
    files.name = std::move(name);
    files.form = form;
    files.fixture = fixture;
    files.sheet = sheet;
    if (files.fixture.empty()) {
        const std::filesystem::path beside = sibling(form, fixture_extension);
        if (regular_file(beside)) files.fixture = beside;
    }
    if (files.sheet.empty()) {
        const std::filesystem::path beside = sibling(form, sheet_extension);
        if (regular_file(beside)) files.sheet = beside;
    }
    return files;
}

std::vector<MockupFiles> find_mockups(const std::filesystem::path& directory) {
    std::vector<MockupFiles> found{};
    std::error_code error{};
    if (!std::filesystem::is_directory(directory, error) || error) return found;
    std::filesystem::recursive_directory_iterator walk(
        directory, std::filesystem::directory_options::skip_permission_denied, error);
    const std::filesystem::recursive_directory_iterator end{};
    while (!error && walk != end) {
        const std::filesystem::directory_entry& entry = *walk;
        const std::filesystem::path& path = entry.path();
        if (entry.is_regular_file(error) && path.extension() == std::string(form_extension)) {
            std::filesystem::path relative = path.lexically_relative(directory);
            relative.replace_extension();
            found.push_back(mockup_files(relative.generic_string(), path, {}, {}));
        }
        walk.increment(error);
    }
    std::stable_sort(found.begin(), found.end(), NameBefore{});
    return found;
}

std::optional<std::size_t> find_mockup(const std::vector<MockupFiles>& catalogue, std::string_view name) {
    for (std::size_t index = 0U; index < catalogue.size(); ++index) {
        if (catalogue[index].name == name) return index;
    }
    return std::nullopt;
}

std::optional<std::string> read_mockup_file(const std::filesystem::path& path) {
    std::error_code error{};
    const std::uintmax_t size = std::filesystem::file_size(path, error);
    if (error || size > maximum_mockup_file_bytes) return std::nullopt;
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return std::nullopt;
    std::string bytes{};
    bytes.resize(static_cast<std::size_t>(size));
    stream.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    if (static_cast<std::size_t>(stream.gcount()) != bytes.size()) return std::nullopt;
    return bytes;
}

MockupStamps mockup_stamps(const MockupFiles& files) {
    MockupStamps stamps{};
    stamps.form = stamp_of(files.form);
    stamps.fixture = stamp_of(files.fixture);
    stamps.sheet = stamp_of(files.sheet);
    return stamps;
}

std::string screenshot_file_name(std::string_view name) {
    std::string file(name);
    std::replace(file.begin(), file.end(), '/', '_');
    return file;
}

} // namespace gui_forms::mockup
