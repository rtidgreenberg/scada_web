// Config -- operator-tunable startup defaults from scada_select/config.yaml
// (scada-select-architecture.md §3.7: "YAML for defaults, flags for overrides").
//
// Deliberately holds no topic names. Topic names and domain IDs come from the
// IDL constants generated out of dds/idl/PlcValue.idl, which is the single
// source of truth for them (DD-043) -- putting them in YAML as well would make
// a fourth copy that can drift.
#pragma once

#include <cstdint>
#include <string>

namespace scada_select {

// A value is present only when the YAML file actually specified it, so the CLI
// can distinguish "not configured" from "configured to the same value as the
// built-in default". Precedence is: built-in default < YAML < CLI flag.
struct FileConfig {
    bool found = false;  // the file existed and parsed

    bool has_qos_profiles = false;
    std::string qos_profiles;

    bool has_min_separation = false;
    std::uint32_t default_min_separation_ms = 0;

    bool has_uid_range_low = false;
    std::int32_t uid_range_low = 0;

    bool has_uid_range_high = false;
    std::int32_t uid_range_high = 0;
};

// Reads `path`. If the file is absent and `required` is false, returns a
// default-constructed FileConfig (found == false) -- flags and built-in
// defaults then supply everything. Throws std::runtime_error if the file is
// absent and `required` (i.e. --config was given explicitly), or if it exists
// but does not parse as the expected shape.
FileConfig load_file_config(const std::string &path, bool required);

}  // namespace scada_select
