# =========================================
# BLOOD DONATION MATCHING SYSTEM
# =========================================


# =========================================
# 1. BLOOD GROUP COMPATIBILITY
# =========================================

def is_compatible(donor_blood, recipient_blood):

    compatibility = {

        "O-": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],

        "O+": ["O+", "A+", "B+", "AB+"],

        "A-": ["A-", "A+", "AB-", "AB+"],

        "A+": ["A+", "AB+"],

        "B-": ["B-", "B+", "AB-", "AB+"],

        "B+": ["B+", "AB+"],

        "AB-": ["AB-", "AB+"],

        "AB+": ["AB+"]
    }

    donor_b = str(donor_blood or "").strip().upper()
    recipient_b = str(recipient_blood or "").strip().upper()

    if donor_b not in compatibility:
        return False

    return recipient_b in compatibility[donor_b]


# =========================================
# 2. BUBBLE SORT
# Sort donors according to matching score
# Highest score comes first (Optimized with early termination)
# =========================================

def bubble_sort(donors):

    n = len(donors)

    for i in range(n):
        swapped = False

        for j in range(0, n - i - 1):

            if donors[j]["matching_score"] < donors[j + 1]["matching_score"]:

                donors[j], donors[j + 1] = \
                    donors[j + 1], donors[j]
                swapped = True

        if not swapped:
            break

    return donors


# =========================================
# 3. COMPLETE DONOR MATCHING
# =========================================

def find_best_donors(donors, recipient_blood, location):

    matched_donors = []
    norm_recipient_blood = str(recipient_blood or "").strip().upper()

    # Search through every donor
    for donor in donors:

        # -----------------------------------------
        # STEP 1: CHECK BLOOD COMPATIBILITY
        # -----------------------------------------

        donor_blood = str(donor.get("blood_group") or "").strip().upper()
        if not is_compatible(
            donor_blood,
            norm_recipient_blood
        ):
            continue

        # -----------------------------------------
        # STEP 2: CHECK AVAILABILITY
        # -----------------------------------------

        if donor.get("availability") != 1:
            continue

        # -----------------------------------------
        # STEP 3: CALCULATE MATCHING SCORE
        # -----------------------------------------

        score = 0

        # Exact blood group
        if donor_blood == norm_recipient_blood:
            score += 60

        # Compatible but not exact
        else:
            score += 40

        # Same location (safe against None values and whitespace variations)
        donor_loc = str(donor.get("location") or "").strip().lower()
        target_loc = str(location or "").strip().lower()
        if donor_loc and target_loc and donor_loc == target_loc:
            score += 20

        # -----------------------------------------
        # STEP 4: STORE SCORE
        # -----------------------------------------

        donor_copy = donor.copy()

        donor_copy["matching_score"] = score

        matched_donors.append(donor_copy) # loist of dict

    # -----------------------------------------
    # STEP 5: SORT BY SCORE
    # -----------------------------------------

    matched_donors = bubble_sort(matched_donors)

    return matched_donors