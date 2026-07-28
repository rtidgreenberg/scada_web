#include "Config.hpp"

#include <stdexcept>

#include <yaml-cpp/yaml.h>

namespace scada_select {
namespace {

// yaml-cpp throws on a type mismatch; restate it with the key name so an
// operator sees which line of their file is wrong rather than "bad conversion".
template <typename T>
T require_scalar(const YAML::Node &node, const char *key, const std::string &path) {
    try {
        return node.as<T>();
    } catch (const YAML::Exception &e) {
        throw std::runtime_error("config file " + path + ": key '" + key + "': " +
                                 e.what());
    }
}

// A relative path inside the config file means "relative to the config file",
// not "relative to whatever directory the selector happens to be started from".
// Absolute paths are left alone.
std::string resolve_against(const std::string &config_path, const std::string &value) {
    if (value.empty() || value.front() == '/') {
        return value;
    }
    const std::size_t slash = config_path.find_last_of('/');
    if (slash == std::string::npos) {
        return value;  // config file is in the cwd, so the value already is too
    }
    return config_path.substr(0, slash + 1) + value;
}

}  // namespace

FileConfig load_file_config(const std::string &path, bool required) {
    FileConfig cfg;

    YAML::Node root;
    try {
        root = YAML::LoadFile(path);
    } catch (const YAML::BadFile &) {
        if (required) {
            throw std::runtime_error("cannot open config file: " + path);
        }
        return cfg;  // absent and not explicitly requested
    } catch (const YAML::Exception &e) {
        throw std::runtime_error("config file " + path + ": " + e.what());
    }

    if (!root.IsMap()) {
        throw std::runtime_error("config file " + path + ": top level is not a map");
    }
    cfg.found = true;

    const YAML::Node qos = root["qos_profiles"];
    if (qos.IsDefined() && !qos.IsNull()) {
        cfg.qos_profiles = resolve_against(
            path, require_scalar<std::string>(qos, "qos_profiles", path));
        cfg.has_qos_profiles = true;
    }

    const YAML::Node selection = root["selection"];
    if (!selection.IsDefined() || selection.IsNull()) {
        return cfg;
    }
    if (!selection.IsMap()) {
        throw std::runtime_error("config file " + path + ": 'selection' is not a map");
    }

    const YAML::Node separation = selection["default_min_separation_ms"];
    if (separation.IsDefined() && !separation.IsNull()) {
        cfg.default_min_separation_ms = require_scalar<std::uint32_t>(
            separation, "selection.default_min_separation_ms", path);
        cfg.has_min_separation = true;
    }

    const YAML::Node low = selection["uid_range_low"];
    if (low.IsDefined() && !low.IsNull()) {
        cfg.uid_range_low =
            require_scalar<std::int32_t>(low, "selection.uid_range_low", path);
        cfg.has_uid_range_low = true;
    }

    const YAML::Node high = selection["uid_range_high"];
    if (high.IsDefined() && !high.IsNull()) {
        cfg.uid_range_high =
            require_scalar<std::int32_t>(high, "selection.uid_range_high", path);
        cfg.has_uid_range_high = true;
    }

    return cfg;
}

}  // namespace scada_select
