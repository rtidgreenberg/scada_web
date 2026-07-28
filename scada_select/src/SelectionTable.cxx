#include "SelectionTable.hpp"

namespace scada_select {

SelectionTable::SelectionTable(std::uint32_t default_min_separation_ms)
    : default_min_separation_ms_(default_min_separation_ms),
      min_separation_ms_(default_min_separation_ms) {}

void SelectionTable::add(std::int32_t uid) {
    // operator[] default-constructs TagState if absent; if uid is already
    // selected this touches nothing, which is the required no-op (§4.2).
    subscriptions_[uid];
}

void SelectionTable::erase(std::int32_t uid) {
    subscriptions_.erase(uid);
}

void SelectionTable::add_range(std::int32_t low, std::int32_t high) {
    // The counter is int64 on purpose: with an int32 counter, high == INT32_MAX
    // makes `++uid` overflow -- undefined behaviour, and in practice a loop that
    // never terminates while it grows the table. main() bounds the span; this
    // keeps the boundary itself well defined.
    for (std::int64_t uid = low; uid <= high; ++uid) {
        add(static_cast<std::int32_t>(uid));
    }
}

bool SelectionTable::contains(std::int32_t uid) const {
    return subscriptions_.find(uid) != subscriptions_.end();
}

std::size_t SelectionTable::size() const {
    return subscriptions_.size();
}

void SelectionTable::set_period(std::uint32_t period_ms) {
    // 0 restores the startup default (config.yaml / --min-separation-ms), which
    // is how the web side reverts a runtime override without having to know what
    // the operator configured (§3.1, §4.2, PlcValue.idl ValueRequest).
    //
    // 0 deliberately does NOT mean "forward every sample": the presentation
    // side is never driven at full field rate from the UI. A deployment that
    // wants no decimation configures the startup default to 0 locally.
    min_separation_ms_ = (period_ms == 0) ? default_min_separation_ms_ : period_ms;
}

std::uint32_t SelectionTable::period_ms() const {
    return min_separation_ms_;
}

std::uint32_t SelectionTable::default_period_ms() const {
    return default_min_separation_ms_;
}

bool SelectionTable::should_forward(std::int32_t uid, Clock::time_point now) {
    auto it = subscriptions_.find(uid);
    if (it == subscriptions_.end()) {
        return false;  // not selected
    }

    TagState &state = it->second;
    if (state.has_emitted && min_separation_ms_ != 0) {
        const auto period = std::chrono::milliseconds(min_separation_ms_);
        if (now - state.last_emitted < period) {
            return false;  // too soon
        }
    }

    state.last_emitted = now;
    state.has_emitted = true;
    return true;
}

}  // namespace scada_select
