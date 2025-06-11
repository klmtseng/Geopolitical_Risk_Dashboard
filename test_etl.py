import pytest
from etl import calculate_risk_score # Assuming etl.py is in the same directory or PYTHONPATH

# Test cases for calculate_risk_score
# Each tuple: (tone, event_base_code, expected_score, description)
test_data = [
    # Test Case 1: Valid inputs, mid-range score.
    # Tone: 50 -> abs(50)/2 = 25. Event '14' (Protest) weight: 20. Total: 45.
    (50, '141', 45, "Valid inputs, mid-range score"),
    (50, '14', 45, "Valid inputs (2-digit code), mid-range score"),

    # Test Case 2: Negative tone, high conflict event.
    # Tone: -80 -> abs(-80)/2 = 40. Event '19' (Fight) weight: 50. Total: 90.
    (-80, '190', 90, "Negative tone, high conflict event"),
    (-80, '19', 90, "Negative tone (2-digit code), high conflict event"),

    # Test Case 3: Zero tone, low conflict event.
    # Tone: 0 -> 0/2 = 0. Event '04' (Consult) weight: 5. Total: 5.
    (0, '040', 5, "Zero tone, low conflict event (Consult)"),
    (0, '04', 5, "Zero tone (2-digit code), low conflict event (Consult)"),

    # Test Case 3b: Zero tone, specific low conflict (Appeal).
    # Tone: 0 -> 0/2 = 0. Event '13' (Appeal) weight: 10. Total: 10.
    (0, '13', 10, "Zero tone, specific low conflict (Appeal)"),

    # Test Case 4: Max tone contribution, max conflict event (should cap at 100).
    # Tone: 100 -> abs(100)/2 = 50. Event '20' (Mass violence) weight: 50. Total: 100.
    (100, '200', 100, "Max tone, max conflict event (cap at 100)"),
    (100, '20', 100, "Max tone (2-digit code), max conflict event (cap at 100)"),

    # Test Case 4b: Score exceeding 100 before cap.
    # Tone: 100 -> 50. Event '19' (Fight) weight 50. Total 100.
    # If an event had weight 60, 50 + 60 = 110, capped to 100.
    # Using existing '19' which results in 100.
    (100, '195', 100, "Score sums to 100, at cap"),

    # Test Case 5: Tone leading to >50 for tone part (already covered by abs(tone)/2, e.g. 100/2=50)
    # This is implicitly tested by cases with tone 100.

    # Test Case 6: Missing or None event_base_code.
    # Tone: 50 -> abs(50)/2 = 25. Event None weight: 0. Total: 25.
    (50, None, 25, "None event_base_code"),

    # Test Case 7: Missing or None tone.
    # Tone: None -> 0. Event '14' (Protest) weight: 20. Total: 20.
    (None, '141', 20, "None tone"),

    # Test Case 8: Event code not in defined map (should use default weight 0).
    # Tone: 20 -> abs(20)/2 = 10. Event '999' weight: 0. Total: 10.
    (20, '999', 10, "Unknown event_base_code (not in map)"),

    # Test Case 9: Non-numeric tone string
    ("invalid_tone", '141', 20, "Non-numeric tone string"), # Tone part becomes 0

    # Test Case 10: Both None
    (None, None, 0, "Both tone and event_base_code are None"),

    # Test Case 11: Event Base Code '18' (Assault)
    # Tone: 30 -> 15. Event '18' weight: 40. Total: 55.
    (30, '18', 55, "Event code for Assault"),

    # Test Case 12: Event Base Code '10' (Demand)
    # Tone: -10 -> 5. Event '10' weight: 15. Total: 20.
    (-10, '10', 20, "Event code for Demand")
]

@pytest.mark.parametrize("tone, event_base_code, expected_score, description", test_data)
def test_calculate_risk_score(tone, event_base_code, expected_score, description):
    """Tests calculate_risk_score with various inputs."""
    assert calculate_risk_score(tone, event_base_code) == expected_score, description
