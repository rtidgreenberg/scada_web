// SelectionTable -- the selector's whole decision logic, deliberately DDS-free.
//
// Holds which uids are currently selected and enforces one global minimum
// separation between forwarded samples per uid (DD-027). No Connext type
// appears here -- int32_t keys, not PLC::UniqueId_t samples -- so this is
// unit-testable with no live domain (scada-select-architecture.md §2, §8).
#pragma once

#include <chrono>
#include <cstdint>
#include <unordered_map>

namespace scada_select {

class SelectionTable {
public:
    using Clock = std::chrono::steady_clock;

    // default_min_separation_ms is the selector's YAML startup default
    // (config.yaml selection.default_min_separation_ms). 0 means forward
    // every selected sample.
    explicit SelectionTable(std::uint32_t default_min_separation_ms);

    // Enable forwarding for uid. A no-op if uid is already selected -- not an
    // error, not a duplicate-enable (scada-select-architecture.md §4.2).
    void add(std::int32_t uid);

    // Disable forwarding for uid. A no-op if uid was not selected.
    void erase(std::int32_t uid);

    // Pre-enable an inclusive uid range at startup (DD-039). Equivalent to
    // calling add() for every uid in [low, high].
    void add_range(std::int32_t low, std::int32_t high);

    bool contains(std::int32_t uid) const;

    std::size_t size() const;

    // PERIOD command: period_ms == 0 means "leave the current global
    // separation unchanged" (the selector YAML default already loaded);
    // nonzero overrides it for all selected uids
    // (scada-select-architecture.md §3.1, §4.2).
    void set_period(std::uint32_t period_ms);

    std::uint32_t period_ms() const;

    // The data-plane decimation decision (scada-select-architecture.md §4.3):
    // returns true iff uid is selected AND enough time has passed since it
    // was last forwarded (or it has never been forwarded). On true, records
    // `now` as the new last-emitted time for uid. Returns false for an
    // unselected uid without recording anything.
    //
    // This does not cover lifecycle bypass (§3.4) -- a caller forwarding a
    // dispose/unregister for a selected uid does so unconditionally and
    // should not consult this method for that decision, though it may still
    // call it for ordinary value samples on the same uid.
    bool should_forward(std::int32_t uid, Clock::time_point now);

private:
    struct TagState {
        Clock::time_point last_emitted{};
        bool has_emitted{false};
    };

    std::unordered_map<std::int32_t, TagState> subscriptions_;
    std::uint32_t min_separation_ms_;
};

}  // namespace scada_select
