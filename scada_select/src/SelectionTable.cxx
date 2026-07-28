#include "SelectionTable.hpp"

namespace scada_select {

SelectionTable::SelectionTable(std::uint32_t default_min_separation_ms)
    : min_separation_ms_(default_min_separation_ms) {}

void SelectionTable::add(std::int32_t uid) {
    // operator[] default-constructs TagState if absent; if uid is already
    // selected this touches nothing, which is the required no-op (§4.2).
    subscriptions_[uid];
}

void SelectionTable::erase(std::int32_t uid) {
    subscriptions_.erase(uid);
}

void SelectionTable::add_range(std::int32_t low, std::int32_t high) {
    for (std::int32_t uid = low; uid <= high; ++uid) {
        add(uid);
    }
}

bool SelectionTable::contains(std::int32_t uid) const {
    return subscriptions_.find(uid) != subscriptions_.end();
}

std::size_t SelectionTable::size() const {
    return subscriptions_.size();
}

void SelectionTable::set_period(std::uint32_t period_ms) {
    // 0 means "leave the current global separation unchanged" -- the
    // selector YAML default already loaded at startup (§3.1, §4.2).
    if (period_ms != 0) {
        min_separation_ms_ = period_ms;
    }
}

std::uint32_t SelectionTable::period_ms() const {
    return min_separation_ms_;
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
