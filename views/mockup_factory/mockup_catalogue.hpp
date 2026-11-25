#pragma once

// The mockup factory's files (gui-forms-mockup): a mockup is a form
// document beside its optional fixture data and theme sheet, named by the
// form's stem:
//
//   mockups/claim_form.form        the form (docs/user/forms.md)
//   mockups/claim_form.fixture     its sample data (docs/user/mockups.md)
//   mockups/claim_form.theme.css   its theme sheet (docs/user/theme-language.md)
//
// The catalogue is every .form under one directory, at any depth, named by
// its path below the directory without the extension, with '/' between
// folders (`claim_form`, `exhibits/registry_browser`), in name order.
// Nothing here is compiled: a mockup added to the folder is listed the next
// time the catalogue is read.

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace gui_forms::mockup {

// One mockup's files. `fixture` and `sheet` are empty when the mockup has
// none.
struct MockupFiles final {
    std::string name{};
    std::filesystem::path form{};
    std::filesystem::path fixture{};
    std::filesystem::path sheet{};
};

// The fixture and sheet extensions beside a form.
inline constexpr std::string_view form_extension = ".form";
inline constexpr std::string_view fixture_extension = ".fixture";
inline constexpr std::string_view sheet_extension = ".theme.css";

// The mockup of `form`, named `name`: `fixture` and `sheet` when given,
// else the form's siblings that exist (claim_form.fixture,
// claim_form.theme.css).
[[nodiscard]] MockupFiles mockup_files(std::string name, const std::filesystem::path& form,
                                       const std::filesystem::path& fixture, const std::filesystem::path& sheet);

// Every mockup under `directory`, in name order; empty when the directory
// does not exist or cannot be read.
[[nodiscard]] std::vector<MockupFiles> find_mockups(const std::filesystem::path& directory);

// The position of the mockup named `name` in `catalogue`, or none.
[[nodiscard]] std::optional<std::size_t> find_mockup(const std::vector<MockupFiles>& catalogue,
                                                     std::string_view name);

// The bytes of the file at `path`, or none when it cannot be read whole.
// A file over maximum_mockup_file_bytes is refused (none).
inline constexpr std::size_t maximum_mockup_file_bytes = 4U * 1024U * 1024U;
[[nodiscard]] std::optional<std::string> read_mockup_file(const std::filesystem::path& path);

// When each of a mockup's files was last written, to notice a save. A file
// that is missing or cannot be read has the minimum time.
struct MockupStamps final {
    std::filesystem::file_time_type form{};
    std::filesystem::file_time_type fixture{};
    std::filesystem::file_time_type sheet{};

    friend bool operator==(const MockupStamps& left, const MockupStamps& right) noexcept {
        return left.form == right.form && left.fixture == right.fixture && left.sheet == right.sheet;
    }
};

[[nodiscard]] MockupStamps mockup_stamps(const MockupFiles& files);

// `name` as a file name for its screenshot: '/' turned into '_'.
[[nodiscard]] std::string screenshot_file_name(std::string_view name);

} // namespace gui_forms::mockup
