#include <iostream>
#include <cassert>
#include "fan.hpp"

namespace {

bool expect(bool condition, const char *message) {
    if (condition) {
        return true;
    }
    std::cerr << "FAILED: " << message << std::endl;
    return false;
}

} // namespace

int main() {
    bool ok = true;

    // --- 1. Upward Temperature Thresholds (Ramp Up) ---
    ok &= expect(temp_level_from_temperature(40.0, 1) == 1, "40C is Level 1");
    ok &= expect(temp_level_from_temperature(46.0, 1) == 2, "46C ramps to Level 2");
    ok &= expect(temp_level_from_temperature(56.0, 1) == 3, "56C ramps to Level 3");
    ok &= expect(temp_level_from_temperature(64.0, 1) == 4, "64C ramps to Level 4");
    ok &= expect(temp_level_from_temperature(70.0, 1) == 5, "70C ramps to Level 5");
    ok &= expect(temp_level_from_temperature(75.0, 1) == 6, "75C ramps to Level 6");
    ok &= expect(temp_level_from_temperature(80.0, 1) == 7, "80C ramps to Level 7");
    ok &= expect(temp_level_from_temperature(85.0, 1) == 8, "85C ramps to Level 8");

    // Immediate jump to higher levels when hot
    ok &= expect(temp_level_from_temperature(84.0, 4) == 8, "Jump from L4 to L8 at 84C");

    // --- 2. Downward Hysteresis (Preventing Flutter / Premature Drops) ---
    // At Level 8: down threshold is 79.0C
    ok &= expect(temp_level_from_temperature(82.0, 8) == 8, "82C holds Level 8 via hysteresis");
    ok &= expect(temp_level_from_temperature(80.0, 8) == 8, "80C holds Level 8 via hysteresis");
    ok &= expect(temp_level_from_temperature(78.5, 8) == 7, "78.5C (<79.0) drops Level 8 to Level 7");

    // At Level 7: down threshold is 74.5C
    ok &= expect(temp_level_from_temperature(77.0, 7) == 7, "77C holds Level 7 via hysteresis");
    ok &= expect(temp_level_from_temperature(75.0, 7) == 7, "75C holds Level 7 via hysteresis");
    ok &= expect(temp_level_from_temperature(74.0, 7) == 6, "74C (<74.5) drops Level 7 to Level 6");

    // At Level 6: down threshold is 69.5C
    ok &= expect(temp_level_from_temperature(71.0, 6) == 6, "71C holds Level 6 via hysteresis");
    ok &= expect(temp_level_from_temperature(69.0, 6) == 5, "69C (<69.5) drops Level 6 to Level 5");

    // --- 3. compute_better_auto_level (Usage + Temperature Combined) ---
    // High CPU usage alone elevates fan level
    ok &= expect(compute_better_auto_level(50.0, 85.0, 1) == 8, ">82% load elevates to Level 8");
    ok &= expect(compute_better_auto_level(50.0, 76.0, 1) == 7, ">74% load elevates to Level 7");
    ok &= expect(compute_better_auto_level(50.0, 68.0, 1) == 6, ">66% load elevates to Level 6");

    // Low background load does not spin fans
    ok &= expect(compute_better_auto_level(40.0, 15.0, 1) == 1, "Idle/low load (<25%) stays at Level 1");

    // Max of temp and usage wins
    ok &= expect(compute_better_auto_level(84.0, 10.0, 1) == 8, "High temp wins over low usage");
    ok &= expect(compute_better_auto_level(40.0, 85.0, 1) == 8, "High usage wins over low temp");

    // Step-down damping: at most 1 level drop per call
    ok &= expect(compute_better_auto_level(40.0, 5.0, 8) == 7, "L8 drops to L7 (at most 1 step)");
    ok &= expect(compute_better_auto_level(40.0, 5.0, 7) == 6, "L7 drops to L6 (at most 1 step)");

    if (ok) {
        std::cout << "All fan curve and hysteresis tests passed!" << std::endl;
        return 0;
    }
    return 1;
}
