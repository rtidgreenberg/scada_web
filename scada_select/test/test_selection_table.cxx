// Unit tests for SelectionTable -- no Connext runtime required. Clock values
// are injected explicitly so decimation is tested deterministically, per
// scada-select-architecture.md §8.
#include <cstdlib>
#include <iostream>

#include "SelectionTable.hpp"

namespace {

int g_failures = 0;

void check(bool condition, const char *description) {
    if (!condition) {
        std::cerr << "FAIL: " << description << "\n";
        ++g_failures;
    } else {
        std::cerr << "PASS: " << description << "\n";
    }
}

using scada_select::SelectionTable;
using Clock = SelectionTable::Clock;

Clock::time_point at_ms(std::int64_t ms) {
    return Clock::time_point(std::chrono::milliseconds(ms));
}

void test_add_contains_erase() {
    SelectionTable table(250);
    check(!table.contains(5), "uid 5 not selected before add");

    table.add(5);
    check(table.contains(5), "uid 5 selected after add");
    check(table.size() == 1, "size is 1 after one add");

    table.add(5);  // re-add is a no-op, not an error or duplicate
    check(table.size() == 1, "re-add of an already-selected uid is a no-op");

    table.erase(5);
    check(!table.contains(5), "uid 5 not selected after erase");
    check(table.size() == 0, "size is 0 after erase");

    table.erase(999);  // erasing an unselected uid is a no-op
    check(table.size() == 0, "erasing an unselected uid does not throw or grow the table");
}

void test_add_range() {
    SelectionTable table(250);
    table.add_range(100, 103);
    check(table.size() == 4, "add_range(100, 103) selects 4 uids");
    check(table.contains(100) && table.contains(103), "range endpoints are selected");
    check(!table.contains(99) && !table.contains(104), "range is exclusive of neighbors");
}

void test_should_forward_unselected() {
    SelectionTable table(250);
    check(!table.should_forward(5, at_ms(0)), "unselected uid is never forwarded");
}

void test_should_forward_first_sample_always_forwards() {
    SelectionTable table(250);
    table.add(5);
    check(table.should_forward(5, at_ms(1000)),
          "first sample for a newly-selected uid is always forwarded");
}

void test_should_forward_rate_limits() {
    SelectionTable table(250);
    table.add(5);

    check(table.should_forward(5, at_ms(0)), "sample at t=0 forwards (first ever)");
    check(!table.should_forward(5, at_ms(100)),
          "sample at t=100ms is dropped (< 250ms separation)");
    check(!table.should_forward(5, at_ms(249)),
          "sample at t=249ms is still dropped (boundary - 1)");
    check(table.should_forward(5, at_ms(250)),
          "sample at t=250ms forwards (boundary, exactly the separation)");
    check(!table.should_forward(5, at_ms(400)),
          "sample at t=400ms is dropped (only 150ms since last emit at 250ms)");
    check(table.should_forward(5, at_ms(500)),
          "sample at t=500ms forwards (250ms since last emit at 250ms)");
}

void test_period_zero_forwards_every_sample() {
    SelectionTable table(0);
    table.add(5);

    check(table.should_forward(5, at_ms(0)), "period 0: sample at t=0 forwards");
    check(table.should_forward(5, at_ms(1)), "period 0: sample at t=1ms also forwards");
    check(table.should_forward(5, at_ms(2)), "period 0: every sample forwards");
}

void test_set_period() {
    SelectionTable table(250);
    check(table.period_ms() == 250, "initial period is the YAML default");

    table.set_period(0);
    check(table.period_ms() == 250,
          "PERIOD with period_ms=0 leaves the current separation unchanged");

    table.set_period(1000);
    check(table.period_ms() == 1000, "PERIOD with nonzero period_ms overrides it");

    table.add(5);
    check(table.should_forward(5, at_ms(0)), "sample at t=0 forwards (first ever)");
    check(!table.should_forward(5, at_ms(500)),
          "sample at t=500ms is dropped under the new 1000ms separation");
    check(table.should_forward(5, at_ms(1000)),
          "sample at t=1000ms forwards under the new 1000ms separation");
}

void test_period_is_global_across_uids() {
    SelectionTable table(250);
    table.add(1);
    table.add(2);

    check(table.should_forward(1, at_ms(0)), "uid 1 first sample forwards");
    check(table.should_forward(2, at_ms(0)), "uid 2 first sample forwards independently");

    table.set_period(500);  // changes separation for all selected uids
    check(!table.should_forward(1, at_ms(300)), "uid 1 respects the new global period");
    check(!table.should_forward(2, at_ms(300)), "uid 2 respects the new global period too");
}

}  // namespace

int main() {
    test_add_contains_erase();
    test_add_range();
    test_should_forward_unselected();
    test_should_forward_first_sample_always_forwards();
    test_should_forward_rate_limits();
    test_period_zero_forwards_every_sample();
    test_set_period();
    test_period_is_global_across_uids();

    if (g_failures > 0) {
        std::cerr << g_failures << " test(s) failed\n";
        return EXIT_FAILURE;
    }
    std::cerr << "All SelectionTable tests passed\n";
    return EXIT_SUCCESS;
}
